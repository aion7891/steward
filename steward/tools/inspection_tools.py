"""Read-only Agno Toolkits for folder scanning, document reading, and software lookup."""

from datetime import datetime, timedelta, timezone

from agno.tools import Toolkit

from steward.tools.tool_paths import ToolPaths


class FileScannerTools(Toolkit):
    """Agno Toolkit exposing incremental folder scans and SQLite cleanup queries."""

    def __init__(self, scanner, db, config, paths=None):
        """Register file scanning and inspection functions.

        Args:
            paths: ToolPaths that turns the user's Mac paths into paths Steward can open.
        """
        self.scanner = scanner
        self.db = db
        self.config = config
        self.paths = paths or ToolPaths()
        super().__init__(
            name="file_scanner_tools",
            tools=[
                self.scan_folder,
                self.get_file_info,
                self.find_duplicates,
                self.find_large_files,
                self.find_stale_files,
            ],
        )

    def scan_folder(self, folder_path=""):
        """Scan one folder (or all configured watched folders when empty).

        Args:
            folder_path: the folder exactly as the user wrote it, e.g. ~/Desktop/docs.
        """
        try:
            folders = [self.paths.folder(folder_path)] if folder_path else None
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}
        summary = self.scanner.scan_all(folders=folders)
        where = f" in {folder_path}" if folder_path else ""
        return {
            "status": "ok",
            "message": f"Scanned {summary['files_seen']} file(s){where} ({summary['hashed_files']} hashed).",
            "summary": summary,
        }

    def get_file_info(self, file_path):
        """Return stored SQLite metadata for a single file path."""
        try:
            local = self.paths.target(file_path)
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}
        record = self.db.get_file(local)
        if record is None:
            return {"status": "not_found", "message": f"No record for {file_path}."}
        return {"status": "ok", "message": f"Found metadata for {record['name']}.", "file": record}

    def find_duplicates(self, limit=10):
        """Return groups of duplicate files sharing the same SHA-256 hash."""
        groups = self.db.find_duplicates()[: int(limit)]
        return {
            "status": "ok",
            "message": f"Found {len(groups)} duplicate group(s).",
            "duplicates": groups,
        }

    def find_large_files(self, min_mb=None, limit=15):
        """Return files larger than min_mb (defaults to scanner.large_file_mb)."""
        threshold_mb = float(min_mb if min_mb is not None else self.config.get("scanner.large_file_mb", 100))
        files = self.db.find_large_files(int(threshold_mb * 1024 * 1024))[: int(limit)]
        return {
            "status": "ok",
            "message": f"Found {len(files)} file(s) >= {threshold_mb} MB.",
            "files": files,
        }

    def find_stale_files(self, days=None, limit=15):
        """Return files not modified within the last N days."""
        stale_days = int(days if days is not None else self.config.get("scanner.stale_days", 90))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=stale_days)).isoformat()
        files = self.db.find_stale_files(cutoff)[: int(limit)]
        return {
            "status": "ok",
            "message": f"Found {len(files)} file(s) untouched for >= {stale_days} days.",
            "files": files,
        }


class DocumentReaderTools(Toolkit):
    """Agno Toolkit for extracting text and metadata from local documents safely."""

    def __init__(self, reader, paths=None):
        """Register document reading functions backed by DocumentReader.

        Args:
            paths: ToolPaths that turns the user's Mac paths into paths Steward can open.
        """
        self.reader = reader
        self.paths = paths or ToolPaths()
        super().__init__(
            name="document_reader_tools",
            tools=[self.read_document, self.extract_text],
        )

    def read_document(self, file_path):
        """Read metadata and a bounded text preview from a local document."""
        try:
            doc = self.reader.read(self.paths.existing(file_path))
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}
        if doc.skipped:
            return {"status": "skipped", "message": doc.error, "path": doc.path}
        if doc.error:
            return {"status": "error", "message": doc.error, "path": doc.path}
        return {
            "status": "ok",
            "message": f"Read {doc.file_type} document ({doc.char_count} chars).",
            "path": doc.path,
            "file_type": doc.file_type,
            "metadata": doc.metadata,
            "preview": doc.text[:2000],
        }

    def extract_text(self, file_path, max_chars=4000):
        """Extract plain text from a supported document up to max_chars."""
        try:
            doc = self.reader.read(self.paths.existing(file_path))
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}
        if doc.skipped or doc.error:
            return {"status": "error", "message": doc.error, "path": doc.path}
        return {
            "status": "ok",
            "message": f"Extracted {min(doc.char_count, int(max_chars))} chars.",
            "path": doc.path,
            "text": doc.text[: int(max_chars)],
        }


class SoftwareTools(Toolkit):
    """Agno Toolkit for querying installed software and file-type associations."""

    def __init__(self, software_detector, db):
        """Register installed software inspection tools."""
        self.detector = software_detector
        self.db = db
        super().__init__(
            name="software_tools",
            tools=[self.list_apps, self.apps_for_extension],
        )

    def list_apps(self, refresh=False):
        """List installed applications from SQLite (optionally rescanning first)."""
        apps = self.detector.detect_and_save() if refresh else self.db.list_software()
        return {
            "status": "ok",
            "message": f"Listed {len(apps)} installed application(s).",
            "apps": apps[:50],
        }

    def apps_for_extension(self, extension):
        """Return applications registered to open the given file extension."""
        matches = self.detector.find_apps_for_extension(extension)
        return {
            "status": "ok",
            "message": f"Found {len(matches)} app(s) for '{extension}'.",
            "apps": matches,
        }
