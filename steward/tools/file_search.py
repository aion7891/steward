"""Finds files by name and the biggest files, also for a new user whose folders were never scanned."""

import fnmatch
import os
from datetime import datetime, timezone
from pathlib import Path


class FileSearch:
    """Looks in Steward's index (SQLite) first, then walks the watched folders on disk.

    The index is only filled by scans, so a new user would otherwise hear "nothing found".
    Walking only reads names and sizes (no hashing) and stops after MAX_FILES files.
    """

    MAX_FILES = 20000

    def __init__(self, config, db):
        """Remember the settings (watched folders, ignored folders) and the index.

        Args:
            config: AppConfig.
            db: DatabaseManager with the files table.
        """
        self.config = config
        self.db = db

    def find(self, name, limit=20):
        """Return files whose name contains `name` (or matches a pattern like *.pdf), newest first.

        Args:
            name: part of a file name, for example "invoice", or a pattern such as "*.pdf".
            limit: maximum number of files.
        """
        query = str(name or "").strip().lower()
        if not query:
            raise ValueError("Tell me (part of) the file name to look for.")
        pattern = query if any(ch in query for ch in "*?[") else f"*{query}*"
        rows = self.db._query_all("SELECT path, name, size_bytes, modified_at FROM files WHERE lower(name) LIKE ?",
                                  (pattern.replace("*", "%").replace("?", "_"),))
        found = {r["path"]: r for r in rows if self._visible(r["path"])}
        for entry in self.walk():
            if fnmatch.fnmatch(entry["name"].lower(), pattern):
                found.setdefault(entry["path"], entry)
        return sorted(found.values(), key=lambda r: str(r["modified_at"]), reverse=True)[: int(limit)]

    def largest(self, min_bytes=0, limit=15):
        """Return the biggest files (at least min_bytes), biggest first.

        Args:
            min_bytes: smallest size to include.
            limit: maximum number of files.
        """
        rows = self.db.find_large_files(int(min_bytes))
        existing = [r for r in rows if self._visible(r["path"])]
        if not existing and not self._indexed():
            existing = [e for e in self.walk() if e["size_bytes"] >= int(min_bytes)]
        return sorted(existing, key=lambda r: r["size_bytes"], reverse=True)[: int(limit)]

    def walk(self):
        """Yield {"path", "name", "size_bytes", "modified_at"} for files in the watched folders."""
        ignored = set(self.config.get("scanner.ignored_dirs", []))
        seen = 0
        for root in self.config.get_watched_folders():
            if not Path(root).is_dir():
                continue
            for folder, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ignored]
                for file_name in files:
                    if file_name.startswith("."):
                        continue
                    seen += 1
                    if seen > self.MAX_FILES:
                        return
                    entry = self._entry(Path(folder) / file_name)
                    if entry:
                        yield entry

    @staticmethod
    def _visible(path):
        """True for a file that still exists and is not hidden (.DS_Store, .env...)."""
        return not Path(path).name.startswith(".") and Path(path).is_file()

    def _indexed(self):
        """True when any scan has filled the index."""
        return bool(self.db._query_all("SELECT 1 FROM files LIMIT 1"))

    @staticmethod
    def _entry(path):
        """Describe one file, or None when it vanished or can't be read."""
        try:
            info = path.stat()
        except OSError:
            return None
        modified = datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat()
        return {"path": str(path), "name": path.name, "size_bytes": info.st_size, "modified_at": modified}
