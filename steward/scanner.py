"""Incremental recursive folder scanner, file categorizer, and anomaly detector."""

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
        "document": "~/Documents/Documents", "spreadsheet": "~/Documents/Spreadsheets",
        "code": "~/Documents/Code", "image": "~/Pictures/Sorted",
        "archive": "~/Downloads/Archives", "media": "~/Movies/Sorted",
        "installer": "~/Downloads/Installers", "temporary": "~/Downloads/Temporary",
        "other": "~/Documents/Misc",
    }

    def categorize(self, file_path):
        """Return a human-readable category for the given file path."""
        path = Path(file_path)
        if self.is_temp_file(path):
            return "temporary"
        ext = path.suffix.lower()
        for category, extensions in self.CATEGORY_MAP.items():
            if ext in extensions:
                return category
        return "other"

    def is_temp_file(self, file_path):
        """Return True if a file looks like a temporary or partial download file."""
        path = Path(file_path)
        name = path.name.lower()
        if path.suffix.lower() in self.CATEGORY_MAP["temporary"]:
            return True
        return name.startswith("~$") or name.startswith(".~") or name.endswith("~")

    def suggest_destination(self, file_path):
        """Suggest a destination directory for a newly seen or downloaded file."""
        raw_target = self.DESTINATION_MAP.get(self.categorize(file_path), self.DESTINATION_MAP["other"])
        return str(Path(raw_target).expanduser())


class FileScanner:
    """Incrementally scans configured folders, hashing only new or changed files."""

    HASH_CHUNK_SIZE = 65536

    def __init__(self, config, db, logger=None, categorizer=None):
        """Initialize scanner with AppConfig, DatabaseManager, and optional helpers."""
        self.config = config
        self.db = db
        self.logger = logger
        self.categorizer = categorizer or FileCategorizer()
        self.ignored_dirs = set(config.get("scanner.ignored_dirs", []))
        self.ignored_extensions = {ext.lower() for ext in config.get("scanner.ignored_extensions", [])}

    def scan_all(self, folders=None):
        """Incrementally scan configured folders and save a checkpointed summary."""
        target_folders = (
            [Path(f).expanduser().resolve() for f in folders]
            if folders is not None else self.config.get_watched_folders()
        )
        started_at = datetime.now(timezone.utc).isoformat()
        totals = {"folders": 0, "seen": 0, "hashed": 0, "unchanged": 0, "errors": 0}
        checkpoint = None

        for folder in target_folders:
            if not folder.exists() or not folder.is_dir():
                self._log("warning", f"Skipping missing folder: {folder}")
                continue
            totals["folders"] += 1
            stats = self._scan_folder(folder)
            for key in ("seen", "hashed", "unchanged", "errors"):
                totals[key] += stats[key]
            checkpoint = stats["checkpoint"] or checkpoint

        findings = self.get_cleanup_findings()
        summary = {
            "started_at": started_at, "completed_at": datetime.now(timezone.utc).isoformat(),
            "status": "completed", "checkpoint_path": checkpoint,
            "folders_scanned": totals["folders"], "files_seen": totals["seen"],
            "hashed_files": totals["hashed"], "unchanged_files": totals["unchanged"],
            "duplicates_found": len(findings["duplicates"]), "large_files_found": len(findings["large_files"]),
            "stale_files_found": len(findings["stale_files"]), "temp_files_found": len(findings["temp_files"]),
            "errors": totals["errors"],
        }
        self.db.record_scan_run(summary)
        self._log("info", f"Scan complete: {totals['seen']} files ({totals['hashed']} hashed, {totals['unchanged']} unchanged) across {totals['folders']} folder(s).")
        return summary

    def _scan_folder(self, root_folder):
        """Walk one directory tree, skipping hashing for unchanged files."""
        stats = {"seen": 0, "hashed": 0, "unchanged": 0, "errors": 0, "checkpoint": None}
        for current_root, dir_names, file_names in os.walk(root_folder):
            dir_names[:] = sorted(d for d in dir_names if d not in self.ignored_dirs)
            for file_name in sorted(file_names):
                file_path = Path(current_root) / file_name
                if file_path.is_symlink():
                    continue
                try:
                    record, was_hashed = self._build_file_record(file_path)
                    self.db.upsert_file(record)
                    stats["seen"] += 1
                    stats["hashed" if was_hashed else "unchanged"] += 1
                    stats["checkpoint"] = record["path"]
                except OSError as exc:
                    stats["errors"] += 1
                    self._record_unreadable(file_path)
                    self._log("warning", f"Unreadable file {file_path}: {exc}")
        return stats

    def _build_file_record(self, file_path):
        """Extract metadata, reusing cached SHA-256 when size and mtime match."""
        resolved = file_path.resolve()
        stat = resolved.stat()
        modified_iso = self._to_iso(stat.st_mtime)
        existing = self.db.get_file(resolved)
        unchanged = (
            existing is not None and existing["size_bytes"] == stat.st_size
            and existing["modified_at"] == modified_iso and existing.get("status") == "ok"
            and (stat.st_size == 0 or bool(existing.get("sha256")))
        )
        sha256 = existing["sha256"] if unchanged else (self._compute_sha256(resolved) if stat.st_size > 0 else "")
        was_hashed = (not unchanged) and (stat.st_size > 0)
        ext = resolved.suffix.lower()
        is_temp = self.categorizer.is_temp_file(resolved) or (ext in self.ignored_extensions)
        record = {
            "path": str(resolved), "name": resolved.name, "folder": str(resolved.parent),
            "extension": ext, "category": self.categorizer.categorize(resolved),
            "size_bytes": stat.st_size, "sha256": sha256,
            "created_at": self._to_iso(stat.st_ctime), "modified_at": modified_iso,
            "accessed_at": self._to_iso(stat.st_atime), "is_temp": 1 if is_temp else 0,
            "status": "ok", "last_scanned_at": datetime.now(timezone.utc).isoformat(),
        }
        return record, was_hashed

    def _record_unreadable(self, file_path):
        """Mark an unreadable file in SQLite so the scan continues safely."""
        resolved = file_path.resolve()
        if self.db.get_file(resolved) is not None:
            self.db.update_file_status(resolved, "unreadable")
            return
        now = datetime.now(timezone.utc).isoformat()
        self.db.upsert_file({
            "path": str(resolved), "name": resolved.name, "folder": str(resolved.parent),
            "extension": resolved.suffix.lower(), "category": self.categorizer.categorize(resolved),
            "size_bytes": 0, "sha256": "", "created_at": now, "modified_at": now,
            "accessed_at": now, "is_temp": 0, "status": "unreadable", "last_scanned_at": now,
        })

    def _compute_sha256(self, file_path):
        """Compute the SHA-256 digest of a file using streaming reads."""
        digest = hashlib.sha256()
        with open(file_path, "rb") as handle:
            while chunk := handle.read(self.HASH_CHUNK_SIZE):
                digest.update(chunk)
        return digest.hexdigest()

    def get_cleanup_findings(self):
        """Query SQLite for duplicates, large files, stale files, and temp files."""
        min_bytes = int(self.config.get("scanner.large_file_mb", 100)) * 1024 * 1024
        cutoff = (datetime.now(timezone.utc) - timedelta(days=int(self.config.get("scanner.stale_days", 90)))).isoformat()
        return {
            "duplicates": self.db.find_duplicates(), "large_files": self.db.find_large_files(min_bytes),
            "stale_files": self.db.find_stale_files(cutoff), "temp_files": self.db.find_temp_files(),
        }

    @staticmethod
    def _to_iso(timestamp):
        """Convert a POSIX timestamp to an ISO-8601 UTC string."""
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()

    def _log(self, level, message):
        """Emit a log message at the requested level when a logger is attached."""
        if self.logger is not None:
            getattr(self.logger, level)(message)
