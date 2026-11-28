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
    REJECTED_REPLY = "You rejected this, so Steward did not change any files."
    ALREADY_REJECTED = "The user already said no to this change. Do not try it again; answer briefly."
    SUMMARIES = {
        "delete_files": "Move {count} file(s) to Steward's recycle bin",
        "archive_files": "Zip {count} file(s) into an archive",
        "move_file": "Move {count} file(s) to {target}",
    }
    FOLDER_SUMMARIES = {
        "delete_files": "Move folder {folders} ({files}) to Steward's recycle bin",
        "archive_files": "Zip folder {folders} ({files}) into an archive",
        "move_file": "Move folder {folders} ({files}) to {target}",
    }

    def __init__(self, config, preflight=None, summarize=None):
        """Create an empty, thread-safe store.

        Args:
            config: AppConfig, used to show whether dry-run will keep the step a preview.
            preflight: optional function(tool_name, args) returning why a step cannot work
                (for example a read-only folder), or None when it can.
            summarize: optional function(paths, tool_name) returning {"folders", "file_count"}, so the
                card can say "Zip folder docs (14 files)".
        """
        self.config = config
        self.preflight = preflight
        self.summarize = summarize
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

    def clear(self):
        """Forget every waiting approval (used when all chats are cleared)."""
        with self.lock:
            self.pending.clear()

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
            paths = [paths] if isinstance(paths, str) else list(paths)
            steps.append({
                "tool": tool.tool_name,
                "agent": req.member_agent_name,
                "summary": self._summary(tool.tool_name, paths, args.get("target_folder", "?")),
                "paths": [str(p) for p in paths],
                "names": [Path(str(p)).name for p in paths],
                "reason": args.get("reason", ""),
                "dry_run": dry_run,
            })
        return steps

    def _summary(self, tool_name, paths, target):
        """Return the card title, naming folders and counting their files when possible."""
        info = self.summarize(paths, tool_name) if self.summarize else None
        if info and info["folders"]:
            template = self.FOLDER_SUMMARIES.get(tool_name, "Run {tool}")
            count = info["file_count"]
            files = f"{count} file" + ("" if count == 1 else "s")
            return template.format(folders=", ".join(info["folders"]), files=files, target=target, tool=tool_name)
        template = self.SUMMARIES.get(tool_name, "Run {tool}")
        return template.format(count=len(paths), target=target, tool=tool_name)

    def settle_rejected(self, run, resume, attempts=2):
        """After a rejection, let the AI finish its turn; any new file change it tries is declined too.

        The AI's own words are not shown afterwards (a small model once claimed "archived" here);
        resuming only keeps the conversation history right ("the user said no").

        Args:
            run: the paused run whose steps were just rejected.
            resume: function(run) that continues a run and returns the next run.
            attempts: how many new tries are declined before giving up.
        """
        for _ in range(attempts + 1):
            try:
                run = resume(run)
            except Exception:  # the reply is already decided; a failed follow-up changes nothing
                return
            open_steps = self.open_requirements(run)
            if not open_steps:
                return
            for req in open_steps:
                req.reject(self.ALREADY_REJECTED)

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
