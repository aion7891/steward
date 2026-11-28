"""Unit tests for Phase 6: Organizing strategies, approval lifecycle, ZIP archive, recycle, and undo."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from steward.main import StewardApp


class Phase6Fixture:
    """Creates an isolated StewardApp with sample files and a protected folder."""

    @staticmethod
    def build_app(tmp_path):
        """Prepare workspace files, a protected folder, and dry_run=True config."""
        inbox = tmp_path / "inbox"
        protected = tmp_path / "protected_clients"
        inbox.mkdir()
        protected.mkdir()

        (inbox / "invoice.pdf").write_text("pdf invoice", encoding="utf-8")
        (inbox / "diagram.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (inbox / "old_notes.txt").write_text("old notes from last year", encoding="utf-8")
        (inbox / "junk.tmp").write_text("temporary junk", encoding="utf-8")
        (protected / "nda.pdf").write_text("confidential client NDA", encoding="utf-8")

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            yaml.safe_dump({
                "scanner": {"watched_folders": [str(inbox)]},
                "safety": {
                    "dry_run": True,
                    "require_confirmation": True,
                    "move_to_recycle_first": True,
                    "protected_paths": [str(protected)],
                },
            }),
            encoding="utf-8",
        )
        return StewardApp(config_path=cfg_file, base_dir=tmp_path), inbox, protected


class TestFileOrganizerAndSafety:
    """Tests for organize strategies, approval state machine, protected paths, and dry-run."""

    def test_plan_organize_by_type_date_and_project_and_execute_with_undo(self, tmp_path):
        """Verify organizing plans, approval gating, execution, and full undo restore."""
        app, inbox, _ = Phase6Fixture.build_app(tmp_path)
        org = app.organizer

        type_proposals = org.plan_organize(inbox, strategy="type")
        date_proposals = org.plan_organize(inbox, strategy="date")
        proj_proposals = org.plan_organize(inbox, strategy="project")

        assert len(type_proposals) == 4
        assert any("/document/" in p["target_path"] for p in type_proposals)
        assert any("/image/" in p["target_path"] for p in type_proposals)
        assert len(date_proposals) == 4
        assert any(f"/{inbox.name}/" in p["target_path"] for p in proj_proposals)

        # Unapproved proposal MUST NOT execute
        first_id = type_proposals[0]["id"]
        assert org.execute_action(first_id, dry_run=False)["status"] == "error"

        # Approve -> dry_run=True leaves source untouched -> dry_run=False moves -> undo restores
        assert org.approve_action(first_id)["status"] == "approved"
        assert org.execute_action(first_id, dry_run=True)["status"] == "dry_run"
        src_path = Path(type_proposals[0]["source_path"])
        assert src_path.exists()

        done = org.execute_action(first_id, dry_run=False)
        assert done["status"] == "done"
        assert not src_path.exists()
        assert Path(done["target_path"]).exists()

        undone = org.undo_action(first_id)
        assert undone["status"] == "undone"
        assert src_path.exists()
        assert not Path(done["target_path"]).exists()

    def test_reject_action_and_protected_path_blocking(self, tmp_path):
        """Verify rejected actions stay untouched and protected paths are always blocked."""
        app, inbox, protected = Phase6Fixture.build_app(tmp_path)
        org = app.organizer

        prop = org.propose_action("delete", str(inbox / "junk.tmp"), reason="Cleanup")
        assert org.reject_action(prop["id"])["status"] == "rejected"
        assert org.execute_action(prop["id"], dry_run=False)["status"] == "error"
        assert (inbox / "junk.tmp").exists()

        blocked = org.propose_action("delete", str(protected / "nda.pdf"), reason="Bad request")
        assert blocked["status"] == "blocked"
        assert (protected / "nda.pdf").exists()


class TestZipArchiveAndRecycleManager:
    """Tests for manifest-backed ZIP archiving, recycle-bin delete/undo, and purge guard."""

    def test_zip_archive_and_full_undo_restore(self, tmp_path):
        """Verify archiving creates a valid ZIP, removes originals, and undo restores all files."""
        app, inbox, _ = Phase6Fixture.build_app(tmp_path)
        org = app.organizer
        files = [str(inbox / "invoice.pdf"), str(inbox / "old_notes.txt")]

        prop = org.propose_action("archive", files, target_path="q4_bundle", reason="Archive old")
        org.approve_action(prop["id"])
        done = org.execute_action(prop["id"], dry_run=False)

        assert done["status"] == "done"
        zip_path = Path(done["target_path"])
        assert zip_path.exists() and zip_path.suffix == ".zip"
        assert not (inbox / "invoice.pdf").exists()
        assert not (inbox / "old_notes.txt").exists()

        undone = org.undo_action(prop["id"])
        assert undone["status"] == "undone"
        assert (inbox / "invoice.pdf").exists()
        assert (inbox / "old_notes.txt").exists()
        assert not zip_path.exists()

    def test_recycle_delete_undo_and_confirmed_purge(self, tmp_path):
        """Verify approved delete moves to recycle, can be undone, and purge requires confirmation."""
        app, inbox, _ = Phase6Fixture.build_app(tmp_path)
        org = app.organizer
        junk = inbox / "junk.tmp"

        prop = org.propose_action("delete", str(junk), reason="Remove temp file")
        org.approve_action(prop["id"])
        done = org.execute_action(prop["id"], dry_run=False)

        assert done["status"] == "done"
        assert not junk.exists()
        assert Path(done["target_path"]).exists()
        assert len(app.recycle_manager.list_recycled()) == 1

        # Undo restores junk.tmp back to inbox
        assert org.undo_action(prop["id"])["status"] == "undone"
        assert junk.exists()

        # Recycle again and test retention-based purge guard (confirmed=False vs True)
        app.recycle_manager.move_to_recycle(junk)
        future = datetime.now(timezone.utc) + timedelta(days=45)
        blocked_purge = app.recycle_manager.purge_expired(older_than_days=30, confirmed=False, now=future)
        assert blocked_purge["status"] == "confirmation_required"
        assert len(app.recycle_manager.list_recycled()) == 1

        real_purge = app.recycle_manager.purge_expired(older_than_days=30, confirmed=True, now=future)
        assert real_purge["status"] == "ok"
        assert real_purge["purged_count"] == 1
        assert len(app.recycle_manager.list_recycled()) == 0
