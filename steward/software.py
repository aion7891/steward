"""Installed software discovery and file-type association detector."""

import plistlib
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


class SoftwareDetector:
    """Detects installed applications, supported file types, and usage freshness."""

    CLI_FALLBACK_TOOLS = {
        "python3": [".py"],
        "git": [".git", ".md"],
        "docker": [".dockerfile", ".yml", ".yaml"],
        "code": [".py", ".js", ".ts", ".md", ".json", ".yaml"],
        "ollama": [".gguf", ".modelfile"],
        "sqlite3": [".db", ".sqlite", ".sqlite3"],
    }

    def __init__(self, config, db, logger=None, app_dirs=None):
        """Initialize the software detector with config, DB, and optional scan dirs."""
        self.config = config
        self.db = db
        self.logger = logger
        self.app_dirs = app_dirs

    def detect_and_save(self):
        """Discover installed software, persist to SQLite, and return the list."""
        records = self.discover_software()
        for record in records:
            self.db.upsert_software(record)
        self._log_info(f"Recorded {len(records)} installed software entries.")
        return records

    def discover_software(self):
        """Scan OS application directories and fall back to common CLI tools."""
        records = []
        if self.app_dirs is not None:
            for directory in self.app_dirs:
                records.extend(self._scan_macos_dir(Path(directory)))
        elif sys.platform == "darwin":
            for directory in (Path("/Applications"), Path.home() / "Applications"):
                records.extend(self._scan_macos_dir(directory))
        elif sys.platform.startswith("linux"):
            for directory in (
                Path("/usr/share/applications"),
                Path.home() / ".local/share/applications",
            ):
                records.extend(self._scan_linux_dir(directory))

        if not records:
            records.extend(self._discover_cli_tools())
        return sorted(records, key=lambda item: item["name"].lower())

    def _scan_macos_dir(self, directory):
        """Inspect .app bundles in a macOS Applications directory."""
        if not directory.exists() or not directory.is_dir():
            return []
        found = []
        for entry in sorted(directory.iterdir()):
            if entry.suffix.lower() != ".app" or not entry.is_dir():
                continue
            record = self._parse_macos_bundle(entry)
            if record is not None:
                found.append(record)
        return found

    def _parse_macos_bundle(self, app_path):
        """Extract name, version, extensions, and last-used time from Info.plist."""
        plist_path = app_path / "Contents" / "Info.plist"
        name = app_path.stem
        version = ""
        extensions = set()

        if plist_path.exists():
            try:
                with open(plist_path, "rb") as handle:
                    info = plistlib.load(handle)
                name = info.get("CFBundleDisplayName") or info.get("CFBundleName") or name
                version = str(
                    info.get("CFBundleShortVersionString")
                    or info.get("CFBundleVersion")
                    or ""
                )
                for doc_type in info.get("CFBundleDocumentTypes", []):
                    for ext in doc_type.get("CFBundleTypeExtensions", []):
                        cleaned = str(ext).strip().lower().lstrip(".")
                        if cleaned and cleaned != "*":
                            extensions.add(f".{cleaned}")
            except Exception as exc:
                self._log_warning(f"Failed reading plist for {app_path.name}: {exc}")

        last_used_iso = self._read_last_used(app_path)
        return {
            "name": str(name),
            "path": str(app_path.resolve()),
            "version": version,
            "extensions": sorted(extensions),
            "last_used_at": last_used_iso,
            "status": self._classify_usage(last_used_iso),
        }

    def _scan_linux_dir(self, directory):
        """Parse basic metadata from Linux .desktop launcher files."""
        if not directory.exists() or not directory.is_dir():
            return []
        found = []
        for entry in sorted(directory.glob("*.desktop")):
            try:
                text = entry.read_text(encoding="utf-8", errors="ignore")
                name = self._extract_desktop_field(text, "Name") or entry.stem
                exec_cmd = self._extract_desktop_field(text, "Exec") or str(entry)
                last_used_iso = self._read_last_used(entry)
                found.append(
                    {
                        "name": name,
                        "path": exec_cmd,
                        "version": "",
                        "extensions": [],
                        "last_used_at": last_used_iso,
                        "status": self._classify_usage(last_used_iso),
                    }
                )
            except OSError:
                continue
        return found

    def _discover_cli_tools(self):
        """Detect common developer tools on PATH as a portable fallback."""
        found = []
        for tool_name, extensions in self.CLI_FALLBACK_TOOLS.items():
            resolved = shutil.which(tool_name)
            if not resolved:
                continue
            tool_path = Path(resolved)
            last_used_iso = self._read_last_used(tool_path)
            found.append(
                {
                    "name": tool_name,
                    "path": resolved,
                    "version": "",
                    "extensions": list(extensions),
                    "last_used_at": last_used_iso,
                    "status": self._classify_usage(last_used_iso),
                }
            )
        return found

    def find_apps_for_extension(self, extension):
        """Return installed software entries registered to open the given extension."""
        target = extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        return [
            app
            for app in self.db.list_software()
            if target in app.get("extensions", [])
        ]

    def _read_last_used(self, path):
        """Read the latest access/modification timestamp as an ISO-8601 UTC string."""
        try:
            stat = path.stat()
            stamp = max(stat.st_atime, stat.st_mtime)
            return datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat()
        except OSError:
            return None

    def _classify_usage(self, last_used_iso):
        """Classify an app as 'recent' or 'rarely_used' using scanner.stale_days."""
        if not last_used_iso:
            return "unknown"
        stale_days = int(self.config.get("scanner.stale_days", 90))
        cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
        last_used = datetime.fromisoformat(last_used_iso)
        return "recent" if last_used >= cutoff else "rarely_used"

    @staticmethod
    def _extract_desktop_field(text, key):
        """Read the first matching Key=Value entry from a Linux .desktop file."""
        prefix = f"{key}="
        for line in text.splitlines():
            if line.startswith(prefix):
                return line[len(prefix) :].strip()
        return ""

    def _log_info(self, message):
        """Log an informational message when a logger is attached."""
        if self.logger is not None:
            self.logger.info(message)

    def _log_warning(self, message):
        """Log a warning message when a logger is attached."""
        if self.logger is not None:
            self.logger.warning(message)
