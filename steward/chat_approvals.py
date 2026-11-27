"""Keeps chat runs that paused for approval and describes what they want to do."""

import threading
from pathlib import Path


class ChatApprovals:
    """Holds paused Agno runs until the user approves or rejects them in the chat.

    Destructive tools (move, archive, delete) need a human "yes". When the AI wants to use
    one, Agno pauses the run. We keep that run here (by run_id), show the user a plain
    description of each step, and resume the run once they decide.
    """

    MAX_PENDING = 20
    SUMMARIES = {
        "delete_files": "Move {count} file(s) to Steward's recycle bin",
        "archive_files": "Zip {count} file(s) into an archive",
        "move_file": "Move {count} file(s) to {target}",
    }

    def __init__(self, config, preflight=None):
        """Create an empty, thread-safe store.

        Args:
            config: AppConfig, used to show whether dry-run will keep the step a preview.
            preflight: optional function(tool_name, args) returning why a step cannot work
                (for example a read-only folder), or None when it can.
        """
        self.config = config
        self.preflight = preflight
        self.pending = {}
        self.lock = threading.Lock()

    def add(self, run):
        """Remember a paused run and return its id.

        Args:
            run: the paused Agno TeamRunOutput.
        """
        with self.lock:
            self.pending[str(run.run_id)] = run
            while len(self.pending) > self.MAX_PENDING:
                self.pending.pop(next(iter(self.pending)))  # forget the oldest
        return str(run.run_id)

    def pop(self, run_id):
        """Take a paused run out of the store, or raise KeyError if it is unknown or already decided.

        Args:
            run_id: the id returned to the browser with the approval card.
        """
        with self.lock:
            if str(run_id) not in self.pending:
                raise KeyError(f"No approval is waiting for run {run_id}. It may have been decided already.")
            return self.pending.pop(str(run_id))

    def open_requirements(self, run):
        """Return the steps in a run that still need a yes/no."""
        return [req for req in (getattr(run, "requirements", None) or []) if req.needs_confirmation]

    def reject_impossible(self, run):
        """Decline steps that are bound to fail, before the user is asked; return the reasons.

        Args:
            run: the paused Agno run.
        """
        reasons = []
        for req in self.open_requirements(run) if self.preflight else []:
            tool = req.tool_execution
            problem = self.preflight(tool.tool_name, dict(getattr(tool, "tool_args", None) or {}))
            if problem:
                req.reject(f"Steward could not do this: {problem}")
                if problem not in reasons:
                    reasons.append(problem)
        return reasons

    def describe(self, run):
        """Return one plain-language card entry per step waiting for approval.

        Args:
            run: the paused Agno run.
        """
        dry_run = bool(self.config.get("safety.dry_run", True))
        steps = []
        for req in self.open_requirements(run):
            tool = req.tool_execution
            args = dict(getattr(tool, "tool_args", None) or {})
            paths = args.get("file_paths") or ([args["source_path"]] if args.get("source_path") else [])
            template = self.SUMMARIES.get(tool.tool_name, "Run {tool}")
            steps.append({
                "tool": tool.tool_name,
                "agent": req.member_agent_name,
                "summary": template.format(count=len(paths), target=args.get("target_folder", "?"), tool=tool.tool_name),
                "paths": [str(p) for p in paths],
                "names": [Path(str(p)).name for p in paths],
                "reason": args.get("reason", ""),
                "dry_run": dry_run,
            })
        return steps

    def decide(self, run, approve, note=None):
        """Confirm or reject every open step of a run (it can then be resumed).

        Args:
            run: the paused Agno run.
            approve: True to allow the steps, False to refuse them.
            note: optional reason shown to the AI when rejecting.
        """
        for req in self.open_requirements(run):
            if approve:
                req.confirm()
            else:
                req.reject(note or "The user rejected this action in the chat.")
        return run
