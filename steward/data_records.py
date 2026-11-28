"""Clears Steward's records behind the Dashboard: file index and scans, actions, search index, reports."""

from steward.report_service import ReportService


class DataRecords:
    """The records Steward rebuilds by itself (scanning, indexing, generating); deleted for good only.

    - "index": the file index and scan history (Dashboard numbers, chart, suggestions, recent scans)
    - "actions": the to-do list and the history of past changes (Undo stops working for those)
    - "search": the document search index the chat uses for questions about file contents
    - "reports": generated reports and their files
    Files in the user's folders, the recycle bin and archives are never touched here.
    """

    TARGETS = ("index", "actions", "search", "reports")
    INDEX_TABLES = ("activity_events", "scan_runs", "files", "software", "folder_scan_jobs")

    def __init__(self, app, rag_index=None, scan_jobs=None):
        """Remember where the records live.

        Args:
            app: StewardApp (SQLite database, reports folder).
            rag_index: optional RAGIndex (the document search index).
            scan_jobs: optional FolderScanJobs (folder scans of the Scan page, kept in memory too).
        """
        self.db = app.db
        self.rag_index = rag_index
        self.scan_jobs = scan_jobs
        self.reports = ReportService(app)

    def summary(self):
        """Return how much there is of each kind of record."""
        files = self._one("SELECT COUNT(*) AS n, COALESCE(SUM(size_bytes), 0) AS size FROM files")
        todo = self._one("SELECT COUNT(*) AS n FROM actions WHERE status IN ('proposed', 'approved')")["n"]
        reports, report_bytes = self.reports.count()
        searchable = len(self.rag_index._load_manifest()) if self.rag_index is not None else 0
        return {
            "index": {"count": files["n"], "size_bytes": files["size"],
                      "scans": self._one("SELECT COUNT(*) AS n FROM scan_runs")["n"]},
            "actions": {"count": self._one("SELECT COUNT(*) AS n FROM actions")["n"], "todo": todo},
            "search": {"count": searchable},
            "reports": {"count": reports, "size_bytes": report_bytes},
        }

    def clear(self, target):
        """Delete one kind of record for good and return {"status", "message", "removed", "backup"}.

        Args:
            target: one of TARGETS.
        Raises:
            ValueError: for an unknown target.
            RuntimeError: when the scan history is cleared while a folder scan runs.
        """
        if target not in self.TARGETS:
            raise ValueError(f"Unknown data '{target}'. Use one of: {', '.join(self.TARGETS)}.")
        removed, message = getattr(self, f"_clear_{target}")()
        return {"status": "ok", "removed": removed, "backup": None, "message": message}

    def _clear_index(self):
        """File index and scan history; the next scan rebuilds them."""
        if self.scan_jobs is not None:
            try:
                self.scan_jobs.forget_all()
            except Exception as exc:  # ScanBusyError: a folder scan is running
                raise RuntimeError(str(exc)) from exc
        files = self._one("SELECT COUNT(*) AS n FROM files")["n"]
        for table in self.INDEX_TABLES:
            self.db._execute(f"DELETE FROM {table}")  # table names are fixed above, never user input
        return files, f"Deleted the file index ({files:,} files) and the scan history. The next scan starts fresh."

    def _clear_actions(self):
        """To-do list and past changes; files already recycled or archived stay where they are."""
        count = self._one("SELECT COUNT(*) AS n FROM actions")["n"]
        self.db._execute("DELETE FROM actions")
        return count, (f"Deleted {count:,} to-do item(s) and past action(s). Files already in the recycle bin "
                       "or archives stay there.")

    def _clear_search(self):
        """Document search index; documents are indexed again when a scan asks for it."""
        count = self.rag_index.clear() if self.rag_index is not None else 0
        return count, (f"Deleted the search index for {count:,} document(s). To search document contents again, "
                       "scan a folder with “Also make documents searchable in Chat”.")

    def _clear_reports(self):
        """Generated reports; new ones are still made on schedule or with Generate now."""
        count = self.reports.delete_all()
        return count, f"Deleted {count:,} report(s) and their files."

    def _one(self, sql):
        """Run a query that returns one row."""
        return self.db._query_all(sql)[0]
