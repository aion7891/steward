"""Groups scan, download and action history into days in the user's local time."""

from datetime import datetime, time, timedelta, timezone


class DailyStats:
    """Builds one row per local day from the scan_runs, activity_events and actions tables.

    Timestamps are stored in UTC. The browser sends its offset from UTC (JavaScript's
    Date.getTimezoneOffset(), e.g. India = -330), so "today" matches the user's clock.
    """

    MAX_OFFSET_MINUTES = 14 * 60

    def __init__(self, db):
        """Store the DatabaseManager to read history from.

        Args:
            db: DatabaseManager.
        """
        self.db = db

    @classmethod
    def validate_offset(cls, tz_offset):
        """Return tz_offset as an int, or raise ValueError if it is not a sensible offset.

        Args:
            tz_offset: minutes BEHIND UTC, as given by JavaScript's getTimezoneOffset().
        """
        try:
            value = int(tz_offset)
        except (TypeError, ValueError):
            raise ValueError("'tz_offset' must be a whole number of minutes.") from None
        if abs(value) > cls.MAX_OFFSET_MINUTES:
            raise ValueError("'tz_offset' must be between -840 and 840 minutes.")
        return value

    def series(self, days, tz_offset=0, now=None):
        """Return `days` rows (oldest first) with scans, files, downloads and actions per day.

        Args:
            days: number of days, ending today (local time).
            tz_offset: minutes behind UTC (see validate_offset).
            now: optional aware datetime used as "now" (for tests).
        """
        zone = timezone(timedelta(minutes=-self.validate_offset(tz_offset)))
        start = (now or datetime.now(timezone.utc)).astimezone(zone).date() - timedelta(days=int(days) - 1)
        rows = {(start + timedelta(days=i)).isoformat(): self.empty_day(start + timedelta(days=i)) for i in range(int(days))}
        since = datetime.combine(start, time.min, zone).astimezone(timezone.utc).isoformat()

        for run in self.db._query_all(
                "SELECT started_at, files_seen, hashed_files, errors FROM scan_runs WHERE started_at >= ?", (since,)):
            self._add(rows, run["started_at"], zone, scans=1, files_checked=run["files_seen"],
                      files_changed=run["hashed_files"], errors=run["errors"])
        for event in self.db._query_all("SELECT timestamp FROM activity_events WHERE timestamp >= ?", (since,)):
            self._add(rows, event["timestamp"], zone, downloads=1)
        for action in self.db._query_all("SELECT timestamp FROM actions WHERE timestamp >= ?", (since,)):
            self._add(rows, action["timestamp"], zone, proposals=1)
        for action in self.db._query_all(
                "SELECT decided_at FROM actions WHERE status IN ('done', 'undone') AND decided_at >= ?", (since,)):
            self._add(rows, action["decided_at"], zone, actions_done=1)
        return list(rows.values())

    @staticmethod
    def empty_day(day):
        """A zero-filled row for a day with no activity."""
        return {"date": day.isoformat(), "scans": 0, "files_checked": 0, "files_changed": 0,
                "errors": 0, "downloads": 0, "proposals": 0, "actions_done": 0}

    @staticmethod
    def _add(rows, stamp, zone, **amounts):
        """Add amounts to the local day of one UTC timestamp (ignored if outside the range)."""
        try:
            moment = datetime.fromisoformat(str(stamp))
        except ValueError:
            return
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        row = rows.get(moment.astimezone(zone).date().isoformat())
        if row is not None:
            for key, amount in amounts.items():
                row[key] += int(amount or 0)
