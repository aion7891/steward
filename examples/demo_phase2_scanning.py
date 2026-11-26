"""Manual demo script for Phase 2: Scanner, SQLite DB, Software, and Downloads Watcher.

Creates a safe sandbox inside data/demo_phase2/ with hardcoded sample files so you can
see duplicate detection, large/stale/temp detection, software discovery, and Downloads
categorization without touching your personal files.

Run with:
    uv run python examples/demo_phase2_scanning.py
"""

import os
import plistlib
import shutil
import time
from pathlib import Path

import yaml

from steward.config import AppConfig
from steward.database import DatabaseManager
from steward.logger import LoggerFactory
from steward.scanner import FileScanner
from steward.software import SoftwareDetector
from steward.watcher import DownloadsWatcher


class Phase2ManualDemo:
    """Runs an interactive, hardcoded walkthrough of all Phase 2 components."""

    def __init__(self):
        """Configure an isolated demo workspace under data/demo_phase2/."""
        self.project_root = Path(__file__).resolve().parent.parent
        self.demo_root = self.project_root / "data" / "demo_phase2"
        self.docs_dir = self.demo_root / "sample_docs"
        self.downloads_dir = self.demo_root / "sample_downloads"
        self.apps_dir = self.demo_root / "sample_apps"
        self.config_file = self.demo_root / "demo_config.yaml"

    def prepare_sandbox(self):
        """Reset the demo folder and populate hardcoded sample files and apps."""
        if self.demo_root.exists():
            shutil.rmtree(self.demo_root)
        for folder in (self.docs_dir, self.downloads_dir, self.apps_dir):
            folder.mkdir(parents=True, exist_ok=True)

        # 1. Duplicate files (exact same content -> same SHA-256)
        (self.docs_dir / "invoice_jan.txt").write_text("Invoice #1042 - $500", encoding="utf-8")
        (self.docs_dir / "invoice_jan_copy.txt").write_text("Invoice #1042 - $500", encoding="utf-8")

        # 2. Temporary file
        (self.docs_dir / "unsaved_draft.tmp").write_text("temp buffer", encoding="utf-8")

        # 3. Large file (2 MB; demo threshold is 1 MB)
        (self.docs_dir / "backup_archive.zip").write_bytes(b"X" * (2 * 1024 * 1024))

        # 4. Stale file (timestamped 120 days ago; demo threshold is 30 days)
        stale_note = self.docs_dir / "old_meeting_notes.md"
        stale_note.write_text("# 2025 Planning Notes\nOld notes.", encoding="utf-8")
        old_time = time.time() - (120 * 24 * 3600)
        os.utime(stale_note, (old_time, old_time))

        # 5. Simulated macOS .app bundle so SoftwareDetector demo is deterministic
        plist_dir = self.apps_dir / "StewardEditor.app" / "Contents"
        plist_dir.mkdir(parents=True)
        plist_payload = {
            "CFBundleDisplayName": "StewardEditor",
            "CFBundleShortVersionString": "1.2.0",
            "CFBundleDocumentTypes": [{"CFBundleTypeExtensions": ["md", "txt", "py"]}],
        }
        with open(plist_dir / "Info.plist", "wb") as handle:
            plistlib.dump(plist_payload, handle)

        # 6. Hardcoded demo config pointing only to the sandbox
        demo_cfg = {
            "app": {"name": "StewardDemo", "log_level": "INFO"},
            "scanner": {
                "watched_folders": [str(self.docs_dir)],
                "downloads_folder": str(self.downloads_dir),
                "ignored_dirs": [".git", "node_modules"],
                "ignored_extensions": [".tmp", ".crdownload", ".part"],
                "large_file_mb": 1,
                "stale_days": 30,
            },
        }
        self.config_file.write_text(yaml.safe_dump(demo_cfg), encoding="utf-8")
        print(f"Prepared isolated sandbox at: {self.demo_root}")

    def run_scanner_demo(self, config, db, logger):
        """Step 1: Scan sample_docs and print every SQLite cleanup finding."""
        print("\n=== STEP 1: FileScanner + SQLite Findings ===")
        scanner = FileScanner(config, db, logger=logger)
        summary = scanner.scan_all()
        findings = scanner.get_cleanup_findings()

        print("Scan summary :", summary)
        print("Duplicates   :", [[f["name"] for f in g["files"]] for g in findings["duplicates"]])
        print("Large files  :", [f["name"] for f in findings["large_files"]])
        print("Stale files  :", [f["name"] for f in findings["stale_files"]])
        print("Temp files   :", [f["name"] for f in findings["temp_files"]])

    def run_software_demo(self, config, db, logger):
        """Step 2: Discover sample installed software and query by extension."""
        print("\n=== STEP 2: SoftwareDetector (App -> Extension Mapping) ===")
        detector = SoftwareDetector(config, db, logger=logger, app_dirs=[self.apps_dir])
        apps = detector.detect_and_save()
        for app in apps:
            print(
                f"  App: {app['name']} v{app['version']} | status={app['status']} "
                f"| extensions={app['extensions']}"
            )
        py_apps = detector.find_apps_for_extension(".py")
        print("Apps that open .py files:", [a["name"] for a in py_apps])

    def run_downloads_demo(self, config, db, logger):
        """Step 3: Watch sample_downloads in real time and drop new files into it."""
        print("\n=== STEP 3: DownloadsWatcher (Real-Time Categorization) ===")
        watcher = DownloadsWatcher(config, db, logger=logger, watch_dir=self.downloads_dir)
        watcher.start()
        try:
            # Drop a partial download (ignored) and two real files (categorized)
            (self.downloads_dir / "video.mp4.crdownload").write_text("partial", encoding="utf-8")
            (self.downloads_dir / "quarterly_report.pdf").write_text("PDF data", encoding="utf-8")
            (self.downloads_dir / "vacation_photo.jpg").write_bytes(b"\xff\xd8\xff\xe0")
            time.sleep(0.6)
        finally:
            watcher.stop()

        events = db.list_activity_events()
        print(f"Recorded {len(events)} activity event(s) in SQLite:")
        for ev in events:
            print(
                f"  - {Path(ev['path']).name} [{ev['category']}] -> {ev['suggested_destination']}"
            )

    def run(self):
        """Execute the full Phase 2 manual demo."""
        print("Running Steward Phase 2 Manual Demo...")
        self.prepare_sandbox()
        config = AppConfig(config_path=self.config_file, base_dir=self.demo_root)
        config.ensure_directories()
        logger = LoggerFactory(config).get_logger("demo_phase2")
        db = DatabaseManager(config.get_path("db_path"), logger=logger)

        self.run_scanner_demo(config, db, logger)
        self.run_software_demo(config, db, logger)
        self.run_downloads_demo(config, db, logger)
        print(f"\nSQLite database saved at: {config.get_path('db_path')}")
        print("Phase 2 demo finished successfully!")


if __name__ == "__main__":
    Phase2ManualDemo().run()
