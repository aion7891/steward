"""Recursive folder scanner, file categorizer, and anomaly detector."""

import hashlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


class FileCategorizer:
    """Classifies files by extension and recommends destination folders."""

    CATEGORY_MAP = {
        "document": {".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".odt", ".ppt", ".pptx"},
        "spreadsheet": {".xls", ".xlsx", ".csv", ".tsv", ".ods"},
        "code": {
            ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".c", ".cpp",
            ".h", ".html", ".css", ".json", ".yaml", ".yml", ".toml", ".sql", ".sh",
        },
        "image": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".heic", ".tiff", ".bmp"},
        "archive": {".zip", ".tar", ".gz", ".tgz", ".bz2", ".7z", ".rar"},
        "media": {".mp3", ".wav", ".flac", ".m4a", ".mp4", ".mov", ".mkv", ".avi"},
        "installer": {".dmg", ".pkg", ".exe", ".msi", ".deb", ".rpm", ".appimage"},
        "temporary": {".tmp", ".temp", ".bak", ".swp", ".part", ".crdownload", ".cache"},
    }

    DESTINATION_MAP = {
        "document": "~/Documents/Documents",
        "spreadsheet": "~/Documents/Spreadsheets",
        "code": "~/Documents/Code",
        "image": "~/Pictures/Sorted",
        "archive": "~/Downloads/Archives",
        "media": "~/Movies/Sorted",
        "installer": "~/Downloads/Installers",
        "temporary": "~/Downloads/Temporary",
        "other": "~/Documents/Misc",
    }

    def categorize(self, file_path):
        """Return a human-readable category for the given file path."""
        path = Path(file_path)
        ext = path.suffix.lower()
        if self.is_temp_file(path):
            return "temporary"
        for category, extensions in self.CATEGORY_MAP.items():
            if ext in extensions:
                return category
        return "other"

    def is_temp_file(self, file_path):
        """Return True if a file looks like a temporary or partial download file."""
        path = Path(file_path)
        name = path.name.lower()
        ext = path.suffix.lower()
        if ext in self.CATEGORY_MAP["temporary"]:
            return True
        if name.startswith("~$") or name.startswith(".~") or name.endswith("~"):
            return True
        return False

    def suggest_destination(self, file_path):
        """Suggest a destination directory for a newly seen or downloaded file."""
        category = self.categorize(file_path)
        raw_target = self.DESTINATION_MAP.get(category, self.DESTINATION_MAP["other"])
        return str(Path(raw_target).expanduser())


class FileScanner:
    """Scans configured directories and stores file metadata in SQLite."""

    HASH_CHUNK_SIZE = 65536

    def __init__(self, config, db, logger=None, categorizer=None):
        """Initialize scanner with AppConfig, DatabaseManager, and optional helpers."""
        self.config = config
        self.db = db
        self.logger = logger
        self.categorizer = categorizer or FileCategorizer()
        self.ignored_dirs = set(config.get("scanner.ignored_dirs", []))
        self.ignored_extensions = {
            ext.lower() for ext in config.get("scanner.ignored_extensions", [])
        }

    def scan_all(self, folders=None):
        """Scan all configured folders and return a summary of findings."""
        target_folders = (
            [Path(f).expanduser().resolve() for f in folders]
            if folders is not None
            else self.config.get_watched_folders()
        )
        started_at = datetime.now(timezone.utc).isoformat()
        files_seen = 0
        folders_scanned = 0
        errors = 0

        for folder in target_folders:
            if not folder.exists() or not folder.is_dir():
                self._log_warning(f"Skipping missing folder: {folder}")
                continue
            folders_scanned += 1
            seen, err = self._scan_folder(folder)
            files_seen += seen
            errors += err

        completed_at = datetime.now(timezone.utc).isoformat()
        findings = self.get_cleanup_findings()
        summary = {
            "started_at": started_at,
            "completed_at": completed_at,
            "folders_scanned": folders_scanned,
            "files_seen": files_seen,
            "duplicates_found": len(findings["duplicates"]),
            "large_files_found": len(findings["large_files"]),
            "stale_files_found": len(findings["stale_files"]),
            "temp_files_found": len(findings["temp_files"]),
            "errors": errors,
        }
        self.db.record_scan_run(summary)
        self._log_info(
            f"Scan complete: {files_seen} files across {folders_scanned} folders."
        )
        return summary

    def _scan_folder(self, root_folder):
        """Walk one directory tree and upsert each discovered file."""
        files_seen, errors = 0, 0
        for current_root, dir_names, file_names in os.walk(root_folder):
            dir_names[:] = [d for d in dir_names if d not in self.ignored_dirs]
            for file_name in file_names:
                file_path = Path(current_root) / file_name
                if file_path.is_symlink():
                    continue
                try:
                    self.db.upsert_file(self._build_file_record(file_path))
                    files_seen += 1
                except OSError as exc:
                    errors += 1
                    self._log_warning(f"Could not read {file_path}: {exc}")
        return files_seen, errors

    def _build_file_record(self, file_path):
        """Extract metadata and content hash for a single file."""
        stat = file_path.stat()
        now_iso = datetime.now(timezone.utc).isoformat()
        ext = file_path.suffix.lower()
        is_temp = self.categorizer.is_temp_file(file_path) or (
            ext in self.ignored_extensions
        )
        return {
            "path": str(file_path.resolve()),
            "name": file_path.name,
            "folder": str(file_path.parent.resolve()),
            "extension": ext,
            "category": self.categorizer.categorize(file_path),
            "size_bytes": stat.st_size,
            "sha256": self._compute_sha256(file_path) if stat.st_size > 0 else "",
            "created_at": self._to_iso(stat.st_ctime),
            "modified_at": self._to_iso(stat.st_mtime),
            "accessed_at": self._to_iso(stat.st_atime),
            "is_temp": 1 if is_temp else 0,
            "last_scanned_at": now_iso,
        }

    def _compute_sha256(self, file_path):
        """Compute the SHA-256 digest of a file using streaming reads."""
        digest = hashlib.sha256()
        with open(file_path, "rb") as handle:
            while True:
                chunk = handle.read(self.HASH_CHUNK_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def get_cleanup_findings(self):
        """Query SQLite for duplicates, large files, stale files, and temp files."""
        min_bytes = int(self.config.get("scanner.large_file_mb", 100)) * 1024 * 1024
        stale_days = int(self.config.get("scanner.stale_days", 90))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=stale_days)).isoformat()
        return {
            "duplicates": self.db.find_duplicates(),
            "large_files": self.db.find_large_files(min_bytes),
            "stale_files": self.db.find_stale_files(cutoff),
            "temp_files": self.db.find_temp_files(),
        }

    @staticmethod
    def _to_iso(timestamp):
        """Convert a POSIX timestamp to an ISO-8601 UTC string."""
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()

    def _log_info(self, message):
        """Log an info or warning message when a logger is attached."""
        if self.logger is not None:
            self.logger.info(message)

    def _log_warning(self, message):
        """Log a warning message when a logger is attached."""
        if self.logger is not None:
            self.logger.warning(message)
