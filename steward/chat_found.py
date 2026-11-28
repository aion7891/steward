"""Remembers the exact files a chat answer's tools found, whatever the AI wrote about them."""

from steward.chat_notices import ChatNotices


class FoundPaths:
    """Collects file paths from the results of Steward's finding tools in an Agno run.

    A small model may answer "the largest file is Screen Recording.mov" without its folder. The
    tool result still has the full path, so Steward keeps it with the answer ("found_paths") and
    ChatMemory can tell the AI exactly which file "it" is in the next question.
    """

    LIMIT = 5
    # Tool name -> the list in its result that holds {"path": ...} entries
    TOOLS = {"find_files": "files", "find_large_files": "files", "find_stale_files": "files",
             "list_folder": "items"}

    def collect(self, run):
        """Return up to LIMIT paths in the order the tools returned them (biggest first for sizes).

        Args:
            run: an Agno TeamRunOutput or RunOutput.
        """
        found = []
        self._walk(run, found)
        unique = []
        for path in found:
            if path not in unique:
                unique.append(path)
        return unique[: self.LIMIT]

    def _walk(self, run, found):
        """Visit one run, then the runs of the team members it delegated to."""
        for tool in getattr(run, "tools", None) or []:
            key = self.TOOLS.get(getattr(tool, "tool_name", ""))
            result = ChatNotices._parse(getattr(tool, "result", None)) if key else None
            if isinstance(result, dict) and result.get("status") == "ok":
                found += [str(item["path"]) for item in result.get(key) or [] if isinstance(item, dict) and item.get("path")]
        for member_run in getattr(run, "member_responses", None) or []:
            self._walk(member_run, found)
