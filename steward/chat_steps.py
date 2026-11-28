"""Turns the AI's live events into plain steps: which helper works on what, and the outcome."""

import ast
import json
import threading
import time
from pathlib import Path


class ChatSteps:
    """Records the steps of one chat answer while it runs (thread-safe).

    Each step is {"id", "kind" ("handoff"|"tool"), "agent", "title", "detail", "status"
    ("running"|"done"|"error"), "progress", "started", "ended"}. `thinking` names the helper
    that is currently waiting for the model, or None.
    """

    DELEGATE_TOOLS = ("delegate_task_to_member", "delegate_task_to_members")
    TOOL_TITLES = {
        "scan_folder": "Scanning {folder_path}", "get_file_info": "Looking up {file_path}",
        "find_duplicates": "Looking for duplicate files", "find_large_files": "Looking for large files",
        "find_stale_files": "Looking for old files", "read_document": "Reading {file_path}",
        "extract_text": "Reading {file_path}", "archive_files": "Archiving {file_paths}",
        "delete_files": "Moving {file_paths} to the recycle bin", "move_file": "Moving {source_path} to {target_folder}",
        "propose_move": "Suggesting to move {source_path}", "organize_folder": "Planning how to organise {folder_path}",
        "undo_action": "Undoing action #{action_id}", "search_concepts": "Searching knowledge notes for “{query}”",
        "read_concept": "Reading note {rel_path}", "search_knowledge_base": "Searching your documents for “{query}”",
        "get_recommendations": "Working out suggestions", "collect_stats": "Collecting statistics",
        "render_report": "Writing a report", "list_apps": "Listing installed apps",
    }
    PROBLEMS = ("error", "blocked", "failed", "not_found")

    def __init__(self):
        """Start with no steps."""
        self.steps = []
        self.thinking = None
        self.lock = threading.Lock()

    def handle(self, event):
        """Update the steps from one Agno stream event (unknown events are ignored).

        Args:
            event: an Agno RunOutputEvent or TeamRunOutputEvent.
        """
        name = str(getattr(event, "event", "") or "")
        team = name.startswith("Team")
        who = "Steward" if team else self.agent_label(getattr(event, "agent_name", None))
        with self.lock:
            if name.endswith("ModelRequestStarted"):
                self.thinking = who
            elif name.endswith("ModelRequestCompleted"):
                self.thinking = None
            elif name.endswith("ToolCallStarted"):
                self._start_tool(getattr(event, "tool", None), who)
            elif name.endswith("ToolCallCompleted") or name.endswith("ToolCallError"):
                self._finish_tool(getattr(event, "tool", None), failed=name.endswith("Error"))
            elif name.endswith("RunError"):
                self._add_error(who, getattr(event, "content", None))

    def progress(self, label, done, total):
        """Show progress of a long action on the step that is running ("archiving 3/14").

        Args:
            label: what is happening, for example "archiving".
            done: items finished so far.
            total: all items.
        """
        with self.lock:
            running = [s for s in self.steps if s["status"] == "running" and s["kind"] == "tool"]
            if running:
                running[-1]["progress"] = {"label": label, "done": int(done), "total": int(total)}

    def snapshot(self):
        """Return a copy of the steps and who is thinking, safe to send to the browser."""
        with self.lock:
            return {"steps": [dict(step) for step in self.steps], "thinking": self.thinking}

    def finish(self):
        """Close steps left running (the answer is complete) and return the final list."""
        with self.lock:
            for step in self.steps:
                if step["status"] == "running":
                    step.update(status="done", ended=time.time())
            self.thinking = None
            return [dict(step) for step in self.steps]

    @staticmethod
    def agent_label(name):
        """Return a friendly helper name: 'ScannerAgent' or 'scanneragent' -> 'Scanner'."""
        text = str(name or "").strip()
        if text.lower().endswith("agent"):
            text = text[:-5]
        return text[:1].upper() + text[1:] if text else "Steward"

    def _start_tool(self, tool, who):
        """Add a running step for a tool call or a hand-over to a helper."""
        if tool is None:
            return
        args = dict(getattr(tool, "tool_args", None) or {})
        step = {"id": len(self.steps) + 1, "call_id": getattr(tool, "tool_call_id", None), "agent": who,
                "detail": None, "status": "running", "progress": None, "started": time.time(), "ended": None}
        if tool.tool_name in self.DELEGATE_TOOLS:
            helper = self.agent_label(args.get("member_id") or "helper")
            step.update(kind="handoff", agent=helper, title=f"Handing over to {helper}")
        else:
            step.update(kind="tool", title=self._title(tool.tool_name, args))
        self.steps.append(step)

    def _add_error(self, who, message):
        """Record that a helper (or the team) failed, so the user sees it instead of silence."""
        now = time.time()
        self.steps.append({"id": len(self.steps) + 1, "call_id": None, "kind": "tool", "agent": who,
                           "title": f"{who} could not finish", "detail": self._short(message), "status": "error",
                           "progress": None, "started": now, "ended": now})

    def _finish_tool(self, tool, failed):
        """Mark the matching running step done (or failed) and add the tool's own message."""
        call_id = getattr(tool, "tool_call_id", None)
        name = getattr(tool, "tool_name", "")
        for step in reversed(self.steps):
            if step["status"] == "running" and (step["call_id"] == call_id or call_id is None):
                outcome = self._parse(getattr(tool, "result", None))
                bad = failed or outcome.get("status") in self.PROBLEMS
                detail = outcome.get("message") if name not in self.DELEGATE_TOOLS else None
                step.update(status="error" if bad else "done", ended=time.time(), detail=self._short(detail))
                return

    def _title(self, tool_name, args):
        """Return the plain-language title of a tool call."""
        template = self.TOOL_TITLES.get(tool_name, f"Using {tool_name.replace('_', ' ')}")
        values = {key: self._name_of(value) for key, value in args.items()}
        try:
            return template.format(**values)
        except (KeyError, IndexError):
            return template.split(" {")[0]

    @staticmethod
    def _name_of(value):
        """Show a path as its full text, and a list of paths as one name or 'N items'."""
        if isinstance(value, (list, tuple)):
            return Path(str(value[0])).name if len(value) == 1 else f"{len(value)} items"
        return str(value)

    @staticmethod
    def _short(text, limit=200):
        """Trim long tool messages for the step list."""
        text = str(text or "").strip()
        return (text[: limit - 1] + "…") if len(text) > limit else (text or None)

    @staticmethod
    def _parse(raw):
        """Parse a tool result (JSON or Python dict text); {} when it is plain text."""
        if isinstance(raw, dict):
            return raw
        for loader in (json.loads, ast.literal_eval):
            try:
                value = loader(str(raw))
                return value if isinstance(value, dict) else {}
            except (ValueError, SyntaxError, TypeError):
                continue
        return {}
