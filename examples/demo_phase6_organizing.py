"""Manual demo script for Phase 6: Organizing, ZIP Archiving, Recycle Bin, and Undo.

Runs inside an isolated sandbox (data/demo_phase6/) so none of your personal files
are touched. Watch every safety rule in action:
  1. Organize proposals by type and date
  2. Approval gating (refuses unapproved execution) + dry-run preview
  3. Approved move + instant undo restore
  4. Verified ZIP archive creation + full undo extraction
  5. Recycle-bin delete + undo restore + confirmed retention purge
  6. Protected-path blocking

Run with:
    uv run python examples/demo_phase6_organizing.py
"""

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from steward.main import StewardApp


class Phase6ManualDemo:
    """Runs an end-to-end walkthrough of Steward's safe file organizer and recycle bin."""

    def __init__(self):
        """Set up isolated sandbox directories under data/demo_phase6/."""
        self.project_root = Path(__file__).resolve().parent.parent
        self.demo_root = self.project_root / "data" / "demo_phase6"
        self.inbox = self.demo_root / "messy_inbox"
        self.protected = self.demo_root / "Work_Clients"
        self.config_file = self.demo_root / "demo_config.yaml"

    def prepare_sandbox(self):
        """Reset sandbox and populate sample messy files + a protected client folder."""
        if self.demo_root.exists():
            shutil.rmtree(self.demo_root)
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.protected.mkdir(parents=True, exist_ok=True)

        (self.inbox / "tax_2026.pdf").write_text("Annual tax summary", encoding="utf-8")
        (self.inbox / "diagram.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (self.inbox / "old_report_1.txt").write_text("Old Q1 report", encoding="utf-8")
        (self.inbox / "old_report_2.txt").write_text("Old Q2 report", encoding="utf-8")
        (self.inbox / "temp_scratch.tmp").write_text("Scratch pad", encoding="utf-8")
        (self.protected / "client_contract.pdf").write_text("Protected contract", encoding="utf-8")

        cfg = {
            "app": {"name": "StewardPhase6Demo", "log_level": "INFO"},
            "scanner": {"watched_folders": [str(self.inbox)]},
            "safety": {
                "dry_run": True,
                "require_confirmation": True,
                "move_to_recycle_first": True,
                "recycle_retention_days": 30,
                "protected_paths": [str(self.protected)],
            },
        }
        self.config_file.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    def run(self):
        """Execute all Phase 6 organizing, archiving, recycling, and undo steps."""
        print("Running Steward Phase 6 Manual Demo (Organizing, Archive, Recycle, Undo)...")
        self.prepare_sandbox()
        app = StewardApp(config_path=self.config_file, base_dir=self.demo_root)
        org = app.organizer

        print("\n=== STEP 1: Organize Proposals by Type & Approval Guard ===")
        proposals = org.plan_organize(self.inbox, strategy="type")
        for item in proposals:
            print(f"  Proposed #{item['id']}: {Path(item['source_path']).name} -> {item['target_path']}")

        first_id = proposals[0]["id"]
        print("Try executing WITHOUT approval:", org.execute_action(first_id, dry_run=False)["message"])
        org.approve_action(first_id)
        print("Try executing WITH dry_run    :", org.execute_action(first_id, dry_run=True)["message"])
        done_move = org.execute_action(first_id, dry_run=False)
        print("Executed approved move        :", done_move["message"])
        print("Undo move                     :", org.undo_action(first_id)["message"])

        print("\n=== STEP 2: Verified ZIP Archive + Full Undo Restore ===")
        old_files = [str(self.inbox / "old_report_1.txt"), str(self.inbox / "old_report_2.txt")]
        arch = org.propose_action("archive", old_files, target_path="old_reports", reason="Compress old reports")
        org.approve_action(arch["id"])
        done_arch = org.execute_action(arch["id"], dry_run=False)
        print("Created ZIP archive           :", done_arch["target_path"])
        print("Originals still in inbox?     :", (self.inbox / "old_report_1.txt").exists())
        print("Undo ZIP archive              :", org.undo_action(arch["id"])["message"])
        print("Originals restored in inbox?  :", (self.inbox / "old_report_1.txt").exists())

        print("\n=== STEP 3: Recycle-Bin Delete + Undo + Confirmed Purge ===")
        junk = self.inbox / "temp_scratch.tmp"
        del_prop = org.propose_action("delete", str(junk), reason="Clean temporary file")
        org.approve_action(del_prop["id"])
        done_del = org.execute_action(del_prop["id"], dry_run=False)
        print("Moved to recycle bin          :", done_del["target_path"])
        print("Undo recycle delete           :", org.undo_action(del_prop["id"])["message"])
        print("Restored to inbox?            :", junk.exists())

        # Re-recycle and demonstrate retention purge guard
        app.recycle_manager.move_to_recycle(junk)
        future = datetime.now(timezone.utc) + timedelta(days=45)
        print("Purge WITHOUT confirmation    :", app.recycle_manager.purge_expired(30, confirmed=False, now=future)["message"])
        print("Purge WITH confirmation       :", app.recycle_manager.purge_expired(30, confirmed=True, now=future))

        print("\n=== STEP 4: Protected Path Safety Check ===")
        blocked = org.propose_action("delete", str(self.protected / "client_contract.pdf"), reason="Test block")
        print("Protected path attempt        :", blocked)
        print("\nPhase 6 demo finished successfully!")


if __name__ == "__main__":
    Phase6ManualDemo().run()
