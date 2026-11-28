"""Works out which files and knowledge notes the AI actually looked at while answering."""

import json
import re
from pathlib import Path


class ChatSources:
    """Collects sources from an Agno run: the team run, plus every member agent's run.

    Sources come from three places:
    - knowledge-search references (documents the RAG search returned)
    - tools that read one file (read_document, extract_text)
    - tools that read or search knowledge notes (read_concept, neighbors, search_concepts)
    """

    FILE_TOOLS = {"read_document": "file_path", "extract_text": "file_path"}
    NOTE_TOOLS = {"read_concept": "rel_path", "neighbors": "rel_path"}
    REL_PATH_PATTERN = re.compile(r"""["']rel_path["']\s*:\s*["']([^"']+)["']""")
    NOTE_ID_PATTERN = re.compile(r"-[0-9a-f]{8}$")
    FAILED_PATTERN = re.compile(r"""^\s*\{\s*["']status["']\s*:\s*["'](error|not_found|skipped)["']""")

    def __init__(self, limit=8):
        """Set the maximum number of sources to return.

        Args:
            limit: how many sources to keep (the first ones found win).
        """
        self.limit = int(limit)

    def collect(self, run):
        """Return a list of {"kind": "file"|"note", "label", "path"} without duplicates.

        Args:
            run: an Agno TeamRunOutput or RunOutput (anything with tools/references).
        """
        found = []
        self._walk(run, found)
        unique, seen = [], set()
        for source in found:
            key = (source["kind"], source["path"])
            if key not in seen:
                seen.add(key)
                unique.append(source)
        return unique[: self.limit]

    def _walk(self, run, found):
        """Visit one run, then the runs of every team member it delegated to."""
        for group in getattr(run, "references", None) or []:
            for document in getattr(group, "references", None) or []:
                self._add_document(document, found)
        for tool in getattr(run, "tools", None) or []:
            self._add_tool(tool, found)
        for member_run in getattr(run, "member_responses", None) or []:
            self._walk(member_run, found)

    def _add_document(self, document, found):
        """Add one knowledge-search result (a dict with meta_data.path)."""
        meta = (document or {}).get("meta_data") or {}
        path = meta.get("path") or meta.get("source_path")
        if path:
            found.append(self.file_source(path))

    def _add_tool(self, tool, found):
        """Add the file or notes one tool call touched."""
        name = getattr(tool, "tool_name", "")
        args = getattr(tool, "tool_args", None) or {}
        if self.FAILED_PATTERN.search(str(getattr(tool, "result", "") or "")):
            return  # a read that failed (e.g. "File not found") was not really looked at
        if name in self.FILE_TOOLS and args.get(self.FILE_TOOLS[name]):
            found.append(self.file_source(args[self.FILE_TOOLS[name]]))
        elif name in self.NOTE_TOOLS and args.get(self.NOTE_TOOLS[name]):
            found.append(self.note_source(args[self.NOTE_TOOLS[name]]))
        elif name == "search_concepts":
            for rel_path in self.REL_PATH_PATTERN.findall(str(getattr(tool, "result", "") or "")):
                found.append(self.note_source(rel_path))
        elif name == "search_knowledge_base":
            # Fallback when references were not recorded: the tool result is a JSON list of documents
            for document in self._json_list(getattr(tool, "result", "")):
                self._add_document(document, found)

    @staticmethod
    def file_source(path):
        """A source pointing at a real file on disk."""
        return {"kind": "file", "label": Path(str(path)).name, "path": str(path)}

    @classmethod
    def note_source(cls, rel_path):
        """A source pointing at a knowledge note; the label drops the folder, .md and note id."""
        label = cls.NOTE_ID_PATTERN.sub("", Path(str(rel_path)).stem)
        return {"kind": "note", "label": label, "path": str(rel_path)}

    @staticmethod
    def _json_list(text):
        """Parse a JSON list of dicts, or return [] for anything else."""
        try:
            value = json.loads(str(text or ""))
        except ValueError:
            return []
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
