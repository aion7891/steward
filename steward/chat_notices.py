"""Adds Steward's own notes to a chat answer, based on what the file tools really did."""

import ast
import json


class ChatNotices:
    """Reads the results of file-changing tools in a finished run and returns short notes.

    The AI writes the answer, and small local models sometimes misreport a tool result
    (for example "deleted" while practice mode only previewed it). These notes come from
    the tool results themselves, so the user always sees what really happened.
    """

    FILE_TOOLS = ("move_file", "archive_files", "delete_files", "organize_folder")
    PRACTICE = "Practice mode (dry-run) is on, so no files were changed. Turn it off in Settings to apply approved actions."
    PROBLEM_STATUSES = ("error", "blocked", "failed", "not_found")

    def collect(self, run):
        """Return a list of plain-language notes (no duplicates) for one run.

        Args:
            run: an Agno TeamRunOutput or RunOutput.
        """
        notes = []
        for result in self._file_tool_results(run):
            for note in self._notes_for(result):
                if note not in notes:
                    notes.append(note)
        return notes

    @staticmethod
    def as_markdown(notes):
        """Return the notes as Markdown quote lines to append to the answer.

        Args:
            notes: list of note strings.
        """
        return "\n\n".join(f"> **Steward:** {note}" for note in notes)

    def _file_tool_results(self, run):
        """Yield the parsed result dict of every file tool in the run and its member runs."""
        for tool in getattr(run, "tools", None) or []:
            if getattr(tool, "tool_name", "") in self.FILE_TOOLS:
                parsed = self._parse(getattr(tool, "result", None))
                if parsed is not None:
                    yield parsed
        for member_run in getattr(run, "member_responses", None) or []:
            yield from self._file_tool_results(member_run)

    def _notes_for(self, result):
        """Turn one tool result into notes: practice mode, or the exact problem message."""
        statuses = [result.get("status")] + [r.get("status") for r in result.get("results", []) if isinstance(r, dict)]
        notes = [self.PRACTICE] if "dry_run" in statuses else []
        if result.get("status") in self.PROBLEM_STATUSES and result.get("message"):
            notes.append(str(result["message"]))
        for item in result.get("results", []):
            if isinstance(item, dict) and item.get("status") in self.PROBLEM_STATUSES and item.get("message"):
                notes.append(str(item["message"]))
        return notes

    @staticmethod
    def _parse(raw):
        """Parse a tool result stored as JSON or as a Python dict string; None if neither."""
        if isinstance(raw, dict):
            return raw
        for loader in (json.loads, ast.literal_eval):
            try:
                value = loader(str(raw))
                return value if isinstance(value, dict) else None
            except (ValueError, SyntaxError, TypeError):
                continue
        return None
