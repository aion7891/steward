"""Builds the folder stats card for chat answers that scanned a folder."""

from datetime import datetime, timezone
from pathlib import Path

from steward.chat_notices import ChatNotices
from steward.folder_advisor import FolderAdvisor


class ChatInsights:
    """After the AI scanned a folder, collect real numbers and suggestions for it from SQLite.

    The card comes from the database, not from the AI's wording, so the chat and the side
    panel always show exact counts. Suggestions keep their file paths, so clicking one can
    ask Steward to act on exactly those files.
    """

    MAX_SUGGESTIONS = 6

    def __init__(self, app, paths):
        """Store the app and the path helper.

        Args:
            app: StewardApp (database and scanner).
            paths: ToolPaths, to turn the folder the user wrote into the local folder.
        """
        self.app = app
        self.paths = paths
        self.advisor = FolderAdvisor(app)

    def folder_card(self, run):
        """Return the card for the last folder this run scanned successfully, or None.

        Args:
            run: an Agno TeamRunOutput (member runs are searched too).
        """
        raw_folder = self._scanned_folder(run)
        if not raw_folder:
            return None
        try:
            folder = Path(self.paths.folder(raw_folder))
        except ValueError:
            return None
        return self.card_for(folder)

    def card_for_path(self, raw_path):
        """Return fresh stats for a folder the user named (Mac path), or raise ValueError.

        Args:
            raw_path: the folder as the browser shows it, e.g. /Users/you/Downloads/docs.
        """
        return self.card_for(Path(self.paths.folder(raw_path)))

    def card_for(self, folder):
        """Return the stats and suggestions for one local folder.

        Args:
            folder: a folder path Steward can open.
        """
        findings = self.advisor.findings_for(folder)
        summary = self.advisor.summarize(findings)
        tips = self.advisor.suggestions_for(folder, findings)
        # Only files that still exist: recycled or moved files can linger in the database
        records = [r for r in self.app.db.list_files()
                   if FolderAdvisor._is_inside(r["path"], folder) and Path(r["path"]).exists()]
        suggestions = [
            {key: tip[key] for key in ("priority", "kind", "title", "reason", "reclaimable_mb", "paths")}
            for tip in tips["suggestions"][: self.MAX_SUGGESTIONS]
        ]
        return {
            "path": str(folder), "name": folder.name or str(folder),
            "files": len(records), "total_bytes": sum(int(r.get("size_bytes") or 0) for r in records),
            "duplicates": summary["duplicates"]["extra_copies"], "temp": summary["temp_files"]["count"],
            "stale": summary["stale_files"]["count"], "large": summary["large_files"]["count"],
            "reclaimable_bytes": tips["reclaimable_bytes"], "suggestions": suggestions,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        }

    def _scanned_folder(self, run):
        """Return the folder_path of the last successful scan_folder call in the run, or None."""
        found = None
        for tool in getattr(run, "tools", None) or []:
            if getattr(tool, "tool_name", "") == "scan_folder":
                args = dict(getattr(tool, "tool_args", None) or {})
                result = ChatNotices._parse(getattr(tool, "result", None)) or {}
                if args.get("folder_path") and result.get("status") == "ok":
                    found = args["folder_path"]
        for member_run in getattr(run, "member_responses", None) or []:
            found = self._scanned_folder(member_run) or found
        return found
