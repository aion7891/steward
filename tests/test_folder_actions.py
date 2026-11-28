"""Archive, recycle and move whole folders from the chat tools, with one Undo for everything."""

from pathlib import Path

import yaml

from steward.main import StewardApp
from steward.tools import OrganizerTools
from tests.test_chat_approvals import FakeTeam, build


class FolderHelper:
    """A real (dry-run OFF) workspace: docs/ with a sub-folder, hidden and private files."""

    @staticmethod
    def build(tmp_path, protected_inside=False):
        """Return (organizer tools, docs folder, workspace folder)."""
        work = tmp_path / "work"
        docs = work / "docs"
        (docs / "sub").mkdir(parents=True)
        (docs / "empty-before").mkdir()
        for rel, text in (("a.txt", "alpha"), ("b.md", "beta"), ("sub/c.txt", "gamma"),
                          (".DS_Store", "mac"), (".env", "TOKEN=x")):
            (docs / rel).write_text(text, encoding="utf-8")
        protected = docs / "clients" if protected_inside else tmp_path / "clients"
        protected.mkdir()
        (protected / "contract.txt").write_text("keep", encoding="utf-8")
        cfg = tmp_path / "config.yaml"
        cfg.write_text(yaml.safe_dump({"scanner": {"watched_folders": [str(work)]},
                                       "safety": {"dry_run": False, "protected_paths": [str(protected)]}}),
                       encoding="utf-8")
        app = StewardApp(config_path=cfg, base_dir=tmp_path)
        return OrganizerTools(app.config, app.db, organizer=app.organizer), docs, work


class TestArchiveFolder:
    """Archiving a folder zips its normal files and leaves hidden/private files in place."""

    def test_archive_folder_then_undo(self, tmp_path):
        """3 files zipped (2 left in place), emptied sub-folder removed, Undo restores all paths."""
        org, docs, _ = FolderHelper.build(tmp_path)
        steps = []
        org.progress = lambda label, done, total: steps.append((label, done, total))
        result = org.archive_files([str(docs)])
        assert result["status"] == "done" and result["file_count"] == 3 and len(result["skipped"]) == 2
        assert Path(result["target_path"]).name.startswith("docs_")
        assert steps == [("archiving", 1, 3), ("archiving", 2, 3), ("archiving", 3, 3)]
        assert not (docs / "sub").exists() and not (docs / "a.txt").exists()
        assert (docs / ".env").exists() and (docs / "empty-before").is_dir()  # never touched
        org.undo_action(result["id"])
        assert (docs / "sub" / "c.txt").read_text(encoding="utf-8") == "gamma"
        assert (docs / "a.txt").exists() and (docs / "b.md").exists()

    def test_folder_with_only_private_files_is_refused(self, tmp_path):
        """A folder holding nothing but hidden/private files gives a clear 'Nothing to archive'."""
        org, docs, _ = FolderHelper.build(tmp_path)
        only_private = docs / "keys"
        only_private.mkdir()
        (only_private / "id_rsa").write_text("secret", encoding="utf-8")
        result = org.archive_files([str(only_private)])
        assert result["status"] == "error" and "Nothing to archive" in result["message"]


class TestRecycleAndMoveFolder:
    """A folder goes to the recycle bin (or moves) as one item, so one Undo brings it all back."""

    def test_recycle_folder_then_undo(self, tmp_path):
        """The whole folder, hidden files included, is recycled and restored as one item."""
        org, docs, _ = FolderHelper.build(tmp_path)
        result = org.delete_files([str(docs)])
        assert result["status"] == "ok" and not docs.exists()
        recycled = Path(result["results"][0]["target_path"])
        assert (recycled / "sub" / "c.txt").exists()
        org.undo_action(result["results"][0]["id"])
        assert (docs / "sub" / "c.txt").exists() and (docs / ".env").exists()

    def test_move_folder_and_refuse_moving_into_itself(self, tmp_path):
        """A folder moves with its contents; moving it inside itself is refused."""
        org, docs, work = FolderHelper.build(tmp_path)
        assert org.move_file(str(docs), str(docs / "sub"))["status"] == "error"
        result = org.move_file(str(docs), str(work / "old-stuff"))
        assert result["status"] == "done" and (work / "old-stuff" / "docs" / "sub" / "c.txt").exists()

    def test_protected_folder_inside_blocks_recycle_and_stays_out_of_archive(self, tmp_path):
        """Recycling a folder that holds a protected folder is blocked; archiving leaves it alone."""
        org, docs, _ = FolderHelper.build(tmp_path, protected_inside=True)
        blocked = org.delete_files([str(docs)])
        assert blocked["status"] == "blocked" and "protected folder" in blocked["message"]
        archived = org.archive_files([str(docs)])
        assert archived["status"] == "done" and (docs / "clients" / "contract.txt").exists()


class TestFolderApprovalCard:
    """The approval card names the folder and counts its files."""

    def test_archive_card_counts_only_files_that_will_be_zipped(self, tmp_path):
        """Hidden and private files stay, so they are not counted on an archive card."""
        org, docs, _ = FolderHelper.build(tmp_path)
        assert org.describe_targets([str(docs)], "archive_files") == {"folders": ["docs"], "file_count": 3}
        assert org.describe_targets([str(docs)], "delete_files") == {"folders": ["docs"], "file_count": 5}

    def test_card_says_folder_and_file_count(self, tmp_path):
        """Deleting a folder from the chat shows 'Move folder docs (1 file) ...'."""
        _, server, client = build(tmp_path)
        server.agents.team = FakeTeam(str(tmp_path / "docs"))
        body = client.post("/steward/chat", json={"message": "delete the docs folder"}).json()
        assert body["status"] == "approval"
        assert body["approvals"][0]["summary"] == "Move folder docs (1 file) to Steward's recycle bin"
