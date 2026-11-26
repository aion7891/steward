"""SQLite database layer for Steward metadata, scans, software, reports, and actions."""

import json
import sqlite3
from datetime import datetime, timezone


class DatabaseManager:
    """Manages SQLite persistence for scanned files, software, events, reports, and logs."""

    SCHEMA_STATEMENTS = (
        "CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, name TEXT NOT NULL, "
        "folder TEXT NOT NULL, extension TEXT, category TEXT, size_bytes INTEGER NOT NULL, "
        "sha256 TEXT, created_at TEXT, modified_at TEXT, accessed_at TEXT, "
        "is_temp INTEGER DEFAULT 0, status TEXT DEFAULT 'ok', last_scanned_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS scan_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "started_at TEXT NOT NULL, completed_at TEXT NOT NULL, status TEXT DEFAULT 'completed', "
        "checkpoint_path TEXT, folders_scanned INTEGER DEFAULT 0, files_seen INTEGER DEFAULT 0, "
        "hashed_files INTEGER DEFAULT 0, unchanged_files INTEGER DEFAULT 0, "
        "duplicates_found INTEGER DEFAULT 0, errors INTEGER DEFAULT 0)",
        "CREATE TABLE IF NOT EXISTS activity_events (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "timestamp TEXT NOT NULL, event_type TEXT NOT NULL, path TEXT NOT NULL, category TEXT, "
        "suggested_destination TEXT, details TEXT)",
        "CREATE TABLE IF NOT EXISTS software (name TEXT PRIMARY KEY, path TEXT, version TEXT, "
        "extensions_json TEXT, last_used_at TEXT, status TEXT, updated_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS actions (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "timestamp TEXT NOT NULL, action_type TEXT NOT NULL, source_path TEXT NOT NULL, "
        "target_path TEXT, status TEXT NOT NULL, dry_run INTEGER DEFAULT 1, reason TEXT, decided_at TEXT)",
        "CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "period TEXT NOT NULL, path TEXT NOT NULL, created_at TEXT NOT NULL)",
        "CREATE INDEX IF NOT EXISTS idx_files_sha256 ON files(sha256)",
        "CREATE INDEX IF NOT EXISTS idx_files_size ON files(size_bytes)",
        "CREATE INDEX IF NOT EXISTS idx_files_modified ON files(modified_at)",
    )
    MIGRATIONS = (
        ("files", "status", "TEXT DEFAULT 'ok'"),
        ("scan_runs", "status", "TEXT DEFAULT 'completed'"),
        ("scan_runs", "checkpoint_path", "TEXT"),
        ("scan_runs", "hashed_files", "INTEGER DEFAULT 0"),
        ("scan_runs", "unchanged_files", "INTEGER DEFAULT 0"),
        ("actions", "decided_at", "TEXT"),
    )

    def __init__(self, db_path, logger=None):
        """Initialize the database manager and ensure tables and migrations exist."""
        self.db_path = str(db_path)
        self.logger = logger
        self.initialize_schema()

    def _connect(self):
        """Open a SQLite connection with dictionary-style row access."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _execute(self, sql, params=()):
        """Run a write statement inside a transaction."""
        with self._connect() as conn:
            conn.execute(sql, params)

    def _query_all(self, sql, params=()):
        """Execute a read query and return all rows as plain dictionaries."""
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def initialize_schema(self):
        """Create core tables, indexes, and lightweight column migrations."""
        with self._connect() as conn:
            for sql in self.SCHEMA_STATEMENTS:
                conn.execute(sql)
            for table, column, col_def in self.MIGRATIONS:
                existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")

    def upsert_file(self, record):
        """Insert or update a scanned file metadata record."""
        payload = dict(record)
        payload.setdefault("status", "ok")
        sql = (
            "INSERT INTO files (path, name, folder, extension, category, size_bytes, sha256, "
            "created_at, modified_at, accessed_at, is_temp, status, last_scanned_at) "
            "VALUES (:path, :name, :folder, :extension, :category, :size_bytes, :sha256, "
            ":created_at, :modified_at, :accessed_at, :is_temp, :status, :last_scanned_at) "
            "ON CONFLICT(path) DO UPDATE SET name=excluded.name, folder=excluded.folder, "
            "extension=excluded.extension, category=excluded.category, size_bytes=excluded.size_bytes, "
            "sha256=excluded.sha256, created_at=excluded.created_at, modified_at=excluded.modified_at, "
            "accessed_at=excluded.accessed_at, is_temp=excluded.is_temp, "
            "status=excluded.status, last_scanned_at=excluded.last_scanned_at"
        )
        self._execute(sql, payload)

    def update_file_status(self, file_path, status):
        """Update the health status (e.g. 'ok', 'unreadable') of a tracked file."""
        self._execute("UPDATE files SET status = ? WHERE path = ?", (status, str(file_path)))

    def get_file(self, file_path):
        """Fetch a single file record by absolute path, or None if missing."""
        rows = self._query_all("SELECT * FROM files WHERE path = ?", (str(file_path),))
        return rows[0] if rows else None

    def list_files(self, limit=None):
        """Return stored file records ordered by path."""
        if limit is not None:
            return self._query_all("SELECT * FROM files ORDER BY path ASC LIMIT ?", (int(limit),))
        return self._query_all("SELECT * FROM files ORDER BY path ASC")

    def find_duplicates(self):
        """Return groups of files sharing the same non-empty SHA-256 hash."""
        sql = (
            "SELECT sha256, COUNT(*) AS count FROM files WHERE sha256 IS NOT NULL "
            "AND sha256 != '' AND size_bytes > 0 GROUP BY sha256 HAVING COUNT(*) > 1"
        )
        groups = []
        for item in self._query_all(sql):
            files = self._query_all(
                "SELECT * FROM files WHERE sha256 = ? ORDER BY modified_at ASC", (item["sha256"],)
            )
            groups.append({"sha256": item["sha256"], "count": item["count"], "files": files})
        return groups

    def find_large_files(self, min_bytes):
        """Return files whose size meets or exceeds min_bytes."""
        return self._query_all("SELECT * FROM files WHERE size_bytes >= ? ORDER BY size_bytes DESC", (int(min_bytes),))

    def find_stale_files(self, cutoff_iso):
        """Return files not modified since cutoff_iso (ISO-8601 string)."""
        return self._query_all("SELECT * FROM files WHERE modified_at <= ? ORDER BY modified_at ASC", (cutoff_iso,))

    def find_temp_files(self):
        """Return files flagged as temporary during scanning."""
        return self._query_all("SELECT * FROM files WHERE is_temp = 1 ORDER BY size_bytes DESC")

    def record_scan_run(self, summary):
        """Save a scan run summary with incremental hash stats and checkpoint path."""
        sql = (
            "INSERT INTO scan_runs (started_at, completed_at, status, checkpoint_path, folders_scanned, "
            "files_seen, hashed_files, unchanged_files, duplicates_found, errors) VALUES (?,?,?,?,?,?,?,?,?,?)"
        )
        self._execute(sql, (
            summary["started_at"], summary["completed_at"], summary.get("status", "completed"),
            summary.get("checkpoint_path"), summary["folders_scanned"], summary["files_seen"],
            summary.get("hashed_files", 0), summary.get("unchanged_files", 0),
            summary["duplicates_found"], summary["errors"],
        ))

    def record_activity_event(self, event_type, path, category, suggested_destination, details=""):
        """Log a Downloads or file activity event."""
        now = datetime.now(timezone.utc).isoformat()
        sql = "INSERT INTO activity_events (timestamp, event_type, path, category, suggested_destination, details) VALUES (?,?,?,?,?,?)"
        self._execute(sql, (now, event_type, str(path), category, suggested_destination, details))

    def list_activity_events(self, limit=50):
        """Return the most recent activity events."""
        return self._query_all("SELECT * FROM activity_events ORDER BY id DESC LIMIT ?", (int(limit),))

    def upsert_software(self, record):
        """Insert or update an installed software entry."""
        payload = {
            "name": record["name"], "path": record.get("path", ""), "version": record.get("version", ""),
            "extensions_json": json.dumps(record.get("extensions", [])),
            "last_used_at": record.get("last_used_at"), "status": record.get("status", "unknown"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        sql = (
            "INSERT INTO software (name, path, version, extensions_json, last_used_at, status, updated_at) "
            "VALUES (:name, :path, :version, :extensions_json, :last_used_at, :status, :updated_at) "
            "ON CONFLICT(name) DO UPDATE SET path=excluded.path, version=excluded.version, "
            "extensions_json=excluded.extensions_json, last_used_at=excluded.last_used_at, "
            "status=excluded.status, updated_at=excluded.updated_at"
        )
        self._execute(sql, payload)

    def list_software(self):
        """Return all recorded software entries with decoded extension lists."""
        results = []
        for item in self._query_all("SELECT * FROM software ORDER BY name ASC"):
            item["extensions"] = json.loads(item.pop("extensions_json") or "[]")
            results.append(item)
        return results

    def log_action(self, action_type, source_path, target_path, status, dry_run=True, reason="", decided_at=None):
        """Record a planned or executed file action for audit and undo support."""
        now = datetime.now(timezone.utc).isoformat()
        sql = "INSERT INTO actions (timestamp, action_type, source_path, target_path, status, dry_run, reason, decided_at) VALUES (?,?,?,?,?,?,?,?)"
        self._execute(sql, (
            now, action_type, str(source_path), str(target_path) if target_path else None,
            status, 1 if dry_run else 0, reason, decided_at,
        ))

    def record_report(self, period, report_path):
        """Record a generated Markdown or HTML report."""
        self._execute(
            "INSERT INTO reports (period, path, created_at) VALUES (?, ?, ?)",
            (period, str(report_path), datetime.now(timezone.utc).isoformat()),
        )

    def list_reports(self, limit=20):
        """Return generated report records ordered newest first."""
        return self._query_all("SELECT * FROM reports ORDER BY id DESC LIMIT ?", (int(limit),))
