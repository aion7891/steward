"""Saves folder-scan jobs in SQLite so their results survive an API restart."""

import json


class ScanJobStore:
    """Keeps one row per folder-scan job: id, status, created_at and the full job as JSON."""

    SCHEMA = (
        "CREATE TABLE IF NOT EXISTS folder_scan_jobs (id TEXT PRIMARY KEY, status TEXT NOT NULL, "
        "created_at TEXT NOT NULL, data TEXT NOT NULL)"
    )
    INTERRUPTED = "Steward restarted before this scan finished. Please run it again."

    def __init__(self, db):
        """Create the table if needed and close out jobs a previous run left unfinished.

        Args:
            db: DatabaseManager (the same SQLite file as the rest of Steward).
        """
        self.db = db
        self.db._execute(self.SCHEMA)
        self._mark_interrupted()

    def save(self, job):
        """Insert or update one job.

        Args:
            job: the job dict built by FolderScanJobs.
        """
        self.db._execute(
            "INSERT INTO folder_scan_jobs (id, status, created_at, data) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET status = excluded.status, data = excluded.data",
            (job["id"], job["status"], job["created_at"], json.dumps(job)),
        )

    def get(self, job_id):
        """Return one saved job, or None if it does not exist.

        Args:
            job_id: the id returned when the scan started.
        """
        rows = self.db._query_all("SELECT data FROM folder_scan_jobs WHERE id = ?", (str(job_id),))
        return json.loads(rows[0]["data"]) if rows else None

    def list_recent(self, limit=10):
        """Return the newest saved jobs first.

        Args:
            limit: maximum number of jobs.
        """
        rows = self.db._query_all(
            "SELECT data FROM folder_scan_jobs ORDER BY created_at DESC LIMIT ?", (int(limit),)
        )
        return [json.loads(row["data"]) for row in rows]

    def _mark_interrupted(self):
        """Jobs still 'queued' or 'running' from an earlier process can never finish: mark them failed."""
        rows = self.db._query_all("SELECT data FROM folder_scan_jobs WHERE status IN ('queued', 'running')")
        for row in rows:
            job = json.loads(row["data"])
            job.update({"status": "failed", "step": "failed", "error": self.INTERRUPTED})
            self.save(job)
