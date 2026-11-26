"""Daily statistics and the "what needs to be done" list for the web dashboard."""

import json
from datetime import datetime, timedelta, timezone

MB = 1024 * 1024


class DashboardService:
    """Collects everything the Dashboard page shows in one call.

    All numbers come from SQLite, the RAG manifest and OKF memory, so the
    dashboard never needs the AI model and stays fast. Days are UTC days.
    """

    MIN_DAYS, MAX_DAYS = 1, 90

    def __init__(self, app, advisor):
        """Store the services the dashboard reads from.

        Args:
            app: StewardApp (config, db, organizer, memory manager).
            advisor: FolderAdvisor used for machine-wide suggestions.
        """
        self.app = app
        self.db = app.db
        self.advisor = advisor

    def summary(self, days=14):
        """Return status cards, a daily series, the to-do list and suggestions.

        Args:
            days: how many days of history to include (1-90).
        """
        days = self._validate_days(days)
        findings = self.advisor.findings_for(None)
        advice = self.advisor.suggestions_for(None, findings)
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "days": days,
            "status": dict(self._status_cards(advice["reclaimable_mb"]), reclaimable_bytes=advice["reclaimable_bytes"]),
            "daily": self._daily_series(days),
            "todo": self._actions_with_size("proposed"),
            "approved_waiting": self._actions_with_size("approved"),
            "suggestions": advice["suggestions"],
            "findings": self.advisor.summarize(findings),
            "categories": self._categories(),
            "recent_scans": self.db._query_all("SELECT * FROM scan_runs ORDER BY id DESC LIMIT 8"),
            "patterns": self._patterns(),
            "system": self._system(),
        }

    def _validate_days(self, days):
        """Turn days into an int inside the allowed range or raise ValueError."""
        try:
            value = int(days)
        except (TypeError, ValueError):
            raise ValueError("'days' must be a whole number.") from None
        if not self.MIN_DAYS <= value <= self.MAX_DAYS:
            raise ValueError(f"'days' must be between {self.MIN_DAYS} and {self.MAX_DAYS}.")
        return value

    def _status_cards(self, reclaimable_mb):
        """Headline numbers: last scan, files, today's activity, pending work, errors."""
        now = datetime.now(timezone.utc)
        today, day_ago = now.date().isoformat(), (now - timedelta(hours=24)).isoformat()
        files = self._one("SELECT COUNT(*) AS n, COALESCE(SUM(size_bytes), 0) AS b FROM files")
        last = self._one("SELECT MAX(completed_at) AS at FROM scan_runs")
        runs_today = self._one(
            "SELECT COUNT(*) AS n, COALESCE(SUM(files_seen), 0) AS seen, COALESCE(SUM(hashed_files), 0) AS changed "
            "FROM scan_runs WHERE substr(started_at, 1, 10) = ?", (today,))
        scan_errors = self._one("SELECT COALESCE(SUM(errors), 0) AS n FROM scan_runs WHERE started_at >= ?", (day_ago,))
        failed = self._one("SELECT COUNT(*) AS n FROM actions WHERE status = 'failed' AND timestamp >= ?", (day_ago,))
        return {
            "last_scan_at": last["at"],
            "files_tracked": files["n"],
            "total_size_mb": round(files["b"] / MB, 2),
            "total_size_bytes": files["b"],
            "files_indexed": self._indexed_count(),
            "scans_today": runs_today["n"],
            "files_checked_today": runs_today["seen"],
            "files_changed_today": runs_today["changed"],
            "pending_actions": self._count_actions("proposed"),
            "approved_waiting": self._count_actions("approved"),
            "errors_24h": scan_errors["n"] + failed["n"],
            "reclaimable_mb": reclaimable_mb,
        }

    def _daily_series(self, days):
        """One row per day (oldest first) with scans, files, events and actions; gaps are zero."""
        start = (datetime.now(timezone.utc) - timedelta(days=days - 1)).date()
        rows = {(start + timedelta(days=i)).isoformat(): self._empty_day(start + timedelta(days=i))
                for i in range(days)}
        queries = (
            ("SELECT substr(started_at, 1, 10) AS d, COUNT(*) AS scans, SUM(files_seen) AS files_checked, "
             "SUM(hashed_files) AS files_changed, SUM(errors) AS errors FROM scan_runs GROUP BY d"),
            "SELECT substr(timestamp, 1, 10) AS d, COUNT(*) AS downloads FROM activity_events GROUP BY d",
            "SELECT substr(timestamp, 1, 10) AS d, COUNT(*) AS proposals FROM actions GROUP BY d",
            ("SELECT substr(decided_at, 1, 10) AS d, COUNT(*) AS actions_done FROM actions "
             "WHERE status IN ('done', 'undone') AND decided_at IS NOT NULL GROUP BY d"),
        )
        for sql in queries:
            for row in self.db._query_all(sql):
                if row["d"] in rows:
                    rows[row["d"]].update({k: (v or 0) for k, v in row.items() if k != "d"})
        return list(rows.values())

    @staticmethod
    def _empty_day(day):
        """A zero-filled row for a day with no activity."""
        return {"date": day.isoformat(), "scans": 0, "files_checked": 0, "files_changed": 0,
                "errors": 0, "downloads": 0, "proposals": 0, "actions_done": 0}

    def _actions_with_size(self, status, limit=50):
        """Actions with one status (newest first), each with the file size if known.

        Args:
            status: 'proposed' (needs a decision) or 'approved' (approved, not yet run).
            limit: maximum number of rows.
        """
        items = []
        for action in self.app.organizer.list_actions(status=status, limit=limit):
            record = self.db.get_file(action["source_path"])
            size = int(record["size_bytes"]) if record else 0
            items.append(dict(action, size_bytes=size, size_mb=round(size / MB, 2)))
        return items

    def _categories(self):
        """File count and size per category, biggest first."""
        rows = self.db._query_all(
            "SELECT COALESCE(category, 'other') AS category, COUNT(*) AS count, "
            "COALESCE(SUM(size_bytes), 0) AS bytes FROM files GROUP BY category ORDER BY bytes DESC")
        return [{"category": r["category"], "count": r["count"], "size_bytes": r["bytes"],
                 "size_mb": round(r["bytes"] / MB, 2)} for r in rows]

    def _patterns(self, limit=6):
        """Learned work patterns from OKF memory (title + description)."""
        items = self.app.memory_manager.list_memories(kind="pattern")[:limit]
        return [{"title": i["frontmatter"].get("title"), "description": i["frontmatter"].get("description")}
                for i in items]

    def _system(self):
        """Model, provider and safety settings shown in the app header."""
        provider = str(self.app.config.get("models.provider", "ollama"))
        return {"provider": provider, "model": self.app.config.get("models.model_id"),
                "cloud_model": provider != "ollama", "dry_run": bool(self.app.config.get("safety.dry_run", True))}

    def _indexed_count(self):
        """Number of files in the RAG manifest (read from disk, no vector DB needed)."""
        name = self.app.config.get("rag.collection_name", "documents")
        manifest = self.app.config.get_path("vector_store_dir") / f"{name}_manifest.json"
        try:
            return len(json.loads(manifest.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return 0

    def _count_actions(self, status):
        """Count actions with one status."""
        return self._one("SELECT COUNT(*) AS n FROM actions WHERE status = ?", (status,))["n"]

    def _one(self, sql, params=()):
        """Run a query that returns exactly one row."""
        return self.db._query_all(sql, params)[0]
