"""Unit tests for Phase 2: File scanning, SQLite database, software, and watcher."""

import os
import plistlib
import time

import yaml

from steward.config import AppConfig
from steward.database import DatabaseManager
from steward.scanner import FileCategorizer, FileScanner
from steward.software import SoftwareDetector
from steward.watcher import DownloadsWatcher


class Phase2TestHelper:
    """Creates isolated temporary configs and SQLite databases for Phase 2 tests."""

    @staticmethod
    def build_env(tmp_path, watched_folders=None, downloads_dir=None):
        """Create an AppConfig and DatabaseManager rooted inside tmp_path."""
        watch_list = [str(p) for p in (watched_folders or [tmp_path / "docs"])]
        dl_dir = str(downloads_dir or (tmp_path / "downloads"))
        cfg_data = {
            "scanner": {
                "watched_folders": watch_list,
                "downloads_folder": dl_dir,
                "ignored_dirs": [".git", "node_modules"],
                "ignored_extensions": [".tmp", ".crdownload", ".part"],
                "large_file_mb": 1,
                "stale_days": 30,
            }
        }
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.safe_dump(cfg_data), encoding="utf-8")
        config = AppConfig(config_path=cfg_file, base_dir=tmp_path)
        config.ensure_directories()
        db = DatabaseManager(config.get_path("db_path"))
        return config, db


class TestScannerAndDatabase:
    """Tests for FileScanner metadata extraction and SQLite cleanup queries."""

    def test_scan_detects_duplicates_large_stale_and_temp_files(self, tmp_path):
        """Verify scanner finds duplicates, large files, stale files, and temp files."""
        docs_dir = tmp_path / "docs"
        ignored_dir = docs_dir / ".git"
        docs_dir.mkdir()
        ignored_dir.mkdir()

        # Duplicate pair with identical content
        (docs_dir / "report_a.txt").write_text("quarterly budget", encoding="utf-8")
        (docs_dir / "report_b.txt").write_text("quarterly budget", encoding="utf-8")

        # Ignored directory file must not be scanned
        (ignored_dir / "HEAD").write_text("ref: refs/heads/main", encoding="utf-8")

        # Temporary file
        (docs_dir / "draft.tmp").write_text("scratch", encoding="utf-8")

        # Large file (>= 1 MB threshold in test config)
        large_file = docs_dir / "big_archive.zip"
        large_file.write_bytes(b"0" * (1024 * 1024 + 16))

        # Stale file (modified 60 days ago > 30 day threshold)
        stale_file = docs_dir / "old_notes.md"
        stale_file.write_text("old notes", encoding="utf-8")
        old_ts = time.time() - (60 * 24 * 3600)
        os.utime(stale_file, (old_ts, old_ts))

        config, db = Phase2TestHelper.build_env(tmp_path, watched_folders=[docs_dir])
        scanner = FileScanner(config, db)
        summary = scanner.scan_all()
        findings = scanner.get_cleanup_findings()

        assert summary["folders_scanned"] == 1
        assert summary["files_seen"] == 5
        assert summary["duplicates_found"] == 1
        assert len(findings["duplicates"][0]["files"]) == 2
        assert len(findings["large_files"]) == 1
        assert findings["large_files"][0]["name"] == "big_archive.zip"
        assert len(findings["stale_files"]) == 1
        assert findings["stale_files"][0]["name"] == "old_notes.md"
        assert len(findings["temp_files"]) == 1
        assert findings["temp_files"][0]["name"] == "draft.tmp"
        assert db.get_file(ignored_dir / "HEAD") is None

    def test_categorizer_maps_extensions_and_destinations(self):
        """Verify FileCategorizer assigns expected categories and destinations."""
        cat = FileCategorizer()
        assert cat.categorize("invoice.pdf") == "document"
        assert cat.categorize("budget.xlsx") == "spreadsheet"
        assert cat.categorize("script.py") == "code"
        assert cat.categorize("photo.jpg") == "image"
        assert cat.categorize("~$temp_doc.docx") == "temporary"
        assert cat.suggest_destination("installer.dmg").endswith("Installers")


class TestSoftwareDetector:
    """Tests for installed app discovery and file-type association lookup."""

    def test_parses_macos_app_bundle_and_tracks_usage(self, tmp_path):
        """Verify Info.plist parsing, extension mapping, and recent vs stale status."""
        apps_dir = tmp_path / "Applications"
        plist_dir = apps_dir / "NotePadPro.app" / "Contents"
        plist_dir.mkdir(parents=True)
        plist_data = {
            "CFBundleDisplayName": "NotePadPro",
            "CFBundleShortVersionString": "2.4.1",
            "CFBundleDocumentTypes": [
                {"CFBundleTypeExtensions": ["md", "txt"]},
            ],
        }
        with open(plist_dir / "Info.plist", "wb") as handle:
            plistlib.dump(plist_data, handle)

        config, db = Phase2TestHelper.build_env(tmp_path)
        detector = SoftwareDetector(config, db, app_dirs=[apps_dir])
        apps = detector.detect_and_save()
        md_apps = detector.find_apps_for_extension(".md")

        assert len(apps) == 1
        assert apps[0]["name"] == "NotePadPro"
        assert apps[0]["version"] == "2.4.1"
        assert apps[0]["extensions"] == [".md", ".txt"]
        assert apps[0]["status"] == "recent"
        assert len(md_apps) == 1
        assert md_apps[0]["name"] == "NotePadPro"


class TestDownloadsWatcher:
    """Tests for Downloads monitoring, filtering, and destination suggestions."""

    def test_inspect_file_and_ignores_partial_downloads(self, tmp_path):
        """Verify DownloadsWatcher records suggestions and skips .crdownload files."""
        dl_dir = tmp_path / "downloads"
        dl_dir.mkdir()
        partial = dl_dir / "movie.mp4.crdownload"
        partial.write_text("in progress", encoding="utf-8")
        pdf = dl_dir / "tax_return.pdf"
        pdf.write_text("tax data", encoding="utf-8")

        seen = []
        config, db = Phase2TestHelper.build_env(tmp_path, downloads_dir=dl_dir)
        watcher = DownloadsWatcher(
            config, db, watch_dir=dl_dir, on_suggestion=seen.append
        )

        assert watcher.inspect_file(partial) is None
        suggestion = watcher.inspect_file(pdf)
        events = db.list_activity_events()

        assert suggestion is not None
        assert suggestion["category"] == "document"
        assert suggestion["suggested_destination"].endswith("Documents")
        assert len(seen) == 1
        assert len(events) == 1
        assert events[0]["category"] == "document"

    def test_live_observer_detects_new_download(self, tmp_path):
        """Verify watchdog observer catches a newly created file in real time."""
        dl_dir = tmp_path / "downloads"
        dl_dir.mkdir()
        captured = []
        config, db = Phase2TestHelper.build_env(tmp_path, downloads_dir=dl_dir)
        watcher = DownloadsWatcher(
            config, db, watch_dir=dl_dir, on_suggestion=captured.append
        )

        watcher.start()
        try:
            new_file = dl_dir / "diagram.png"
            new_file.write_bytes(b"\x89PNG\r\n\x1a\n")
            deadline = time.time() + 3.0
            while not captured and time.time() < deadline:
                time.sleep(0.05)
        finally:
            watcher.stop()

        assert len(captured) >= 1
        assert captured[0]["name"] == "diagram.png"
        assert captured[0]["category"] == "image"
