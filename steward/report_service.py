"""Lists, reads and generates reports for the web UI (the UI never reads files itself)."""

from pathlib import Path


class ReportService:
    """Groups the Markdown and HTML copy of each report and serves their contents safely."""

    PERIODS = ("weekly", "daily", "monthly")
    FORMATS = {".md": "markdown", ".html": "html"}
    MEDIA_TYPES = {"markdown": "text/markdown; charset=utf-8", "html": "text/html; charset=utf-8"}

    def __init__(self, app):
        """Store the services that hold report records and render reports.

        Args:
            app: StewardApp (db, reporter, config).
        """
        self.app = app
        self.reports_dir = app.config.get_path("reports_dir")

    def library(self, limit=30):
        """Return reports newest first; the .md and .html copies of one report share an entry.

        Args:
            limit: maximum number of report files to look at.
        """
        grouped = {}
        for row in self.app.db.list_reports(limit=int(limit) * 2):
            path = Path(row["path"])
            fmt = self.FORMATS.get(path.suffix.lower())
            if fmt is None:
                continue
            entry = grouped.setdefault(path.stem, {
                "key": path.stem, "period": row["period"], "created_at": row["created_at"], "formats": {},
            })
            entry["formats"][fmt] = {"id": row["id"], "available": self._is_safe(path) and path.exists()}
        entries = sorted(grouped.values(), key=lambda e: e["created_at"], reverse=True)
        return entries[: int(limit)]

    def read(self, report_id):
        """Return {id, format, name, content} for one report file.

        Args:
            report_id: the reports-table id of one .md or .html file.
        Raises:
            KeyError: unknown id or the file is gone; ValueError: the path is outside the reports folder.
        """
        path, fmt = self._locate(report_id)
        return {"id": int(report_id), "format": fmt, "name": path.name, "content": path.read_text(encoding="utf-8")}

    def file_for_download(self, report_id):
        """Return (path, media_type, file_name) for a download response."""
        path, fmt = self._locate(report_id)
        return path, self.MEDIA_TYPES[fmt], path.name

    def generate(self, period="weekly"):
        """Create a new Markdown + HTML report now and return the new library entry.

        Args:
            period: one of PERIODS (only changes the label and file name).
        """
        period = str(period or "weekly").strip().lower()
        if period not in self.PERIODS:
            raise ValueError(f"'period' must be one of: {', '.join(self.PERIODS)}.")
        result = self.app.reporter.generate_report(period=period, output_format="both")
        key = Path(result["report_path"]).stem
        entry = next((e for e in self.library() if e["key"] == key), None)
        count = len(result.get("stats", {}).get("suggestions", []))
        message = f"New {period} report ready with {count} suggestion{'s' if count != 1 else ''}."
        return {"status": "ok", "message": message, "report": entry}

    def delete(self, key):
        """Delete one report (its Markdown and HTML copy) and return {"status", "message"}.

        Args:
            key: the report's library key, for example "steward_weekly_20261127-085222".
        Raises:
            KeyError: when no report has that key.
        """
        rows = [r for r in self.app.db.list_reports(limit=100000) if Path(r["path"]).stem == str(key)]
        if not rows:
            raise KeyError(f"Report {key} was not found. It may have been deleted already.")
        self._remove(rows)
        return {"status": "ok", "message": "Deleted the report and its files."}

    def delete_all(self):
        """Delete every report record and its files; return how many reports there were."""
        rows = self.app.db.list_reports(limit=100000)
        count = len({Path(r["path"]).stem for r in rows})
        self._remove(rows)
        return count

    def count(self):
        """Return (number of reports, bytes of their files)."""
        rows = self.app.db.list_reports(limit=100000)
        size = sum(Path(r["path"]).stat().st_size for r in rows if self._is_safe(r["path"]) and Path(r["path"]).is_file())
        return len({Path(r["path"]).stem for r in rows}), size

    def _remove(self, rows):
        """Delete report files (only inside the reports folder) and their records."""
        for row in rows:
            path = Path(row["path"])
            if self._is_safe(path) and path.is_file():
                path.unlink()
            self.app.db._execute("DELETE FROM reports WHERE id = ?", (int(row["id"]),))

    def _locate(self, report_id):
        """Find a report file by id and make sure it is a real file inside the reports folder."""
        try:
            wanted = int(report_id)
        except (TypeError, ValueError):
            raise KeyError(f"Unknown report: {report_id}") from None
        rows = self.app.db._query_all("SELECT * FROM reports WHERE id = ?", (wanted,))
        if not rows:
            raise KeyError(f"Unknown report: {report_id}")
        path = Path(rows[0]["path"])
        fmt = self.FORMATS.get(path.suffix.lower())
        if fmt is None or not self._is_safe(path):
            raise ValueError("This report file is not inside Steward's reports folder.")
        if not path.exists():
            raise KeyError(f"The file for report {report_id} no longer exists.")
        return path, fmt

    def _is_safe(self, path):
        """True only for files inside the configured reports folder (no reading other files)."""
        resolved = Path(path).resolve()
        return self.reports_dir == resolved.parent or self.reports_dir in resolved.parents
