"""Safety-first Agno Toolkit for organizing, ZIP archiving, recycling, and undo."""

import threading
from pathlib import Path

from agno.tools import Toolkit

from steward.folder_actions import FolderActions
from steward.organizer import FileOrganizer
from steward.tools.action_targets import ActionTargets, ProtectedPathError
from steward.tools.tool_paths import ToolPaths


class OrganizerTools(Toolkit):
    """Agno Toolkit delegating confirmation-gated file actions to FileOrganizer.

    Move, archive and delete accept files and whole folders. Set `progress` to a
    function(label, done, total) to hear about long actions ("archiving", 6, 14).
    """

    def __init__(self, config, db, memory_manager=None, logger=None, organizer=None, paths=None):
        """Register file management tools with HITL confirmation on destructive actions.

        Args:
            paths: ToolPaths that turns the user's Mac paths into paths Steward can open,
                and refuses folders Steward may not change.
        """
        self.config = config
        self.db = db
        self.paths = paths or ToolPaths()
        self.folders = FolderActions(config)
        self.targets = ActionTargets(self.paths, self.folders)
        # Per chat job (each runs in its own thread, two can run at once): live progress and the
        # ids of changes really made ("undo that")
        self._job = threading.local()
        self.organizer = organizer or FileOrganizer(
            config, db, memory_manager=memory_manager, logger=logger
        )
        super().__init__(
            name="organizer_tools",
            tools=[
                self.propose_move,
                self.organize_folder,
                self.move_file,
                self.archive_files,
                self.delete_files,
                self.undo_action,
            ],
            requires_confirmation_tools=["move_file", "archive_files", "delete_files"],
        )

    def propose_move(self, source_path, target_folder, reason="Organize by category"):
        """Propose moving a file or folder without touching disk."""
        try:
            src, dest = self.targets.move(source_path, target_folder)
        except ValueError as exc:
            return self._refusal(exc)
        return self.organizer.propose_action("move", src, target_path=dest, reason=reason)

    def organize_folder(self, folder_path, strategy="type", destination_root=None):
        """Create move proposals to organize a folder by type, date, or project."""
        try:
            folder = self.paths.folder(folder_path)
            destination = self.paths.target(destination_root) if destination_root else None
            self.paths.check_writable(folder)
            proposals = self.organizer.plan_organize(folder, strategy=strategy, destination_root=destination)
            return {
                "status": "proposed",
                "message": f"Created {len(proposals)} move proposal(s) using strategy '{strategy}'.",
                "proposals": proposals,
            }
        except (ValueError, FileNotFoundError) as exc:
            return {"status": "error", "message": str(exc)}

    def move_file(self, source_path, target_folder, reason="User-approved move", dry_run=None):
        """Move a file or a whole folder into target_folder (after the user approves)."""
        try:
            src, dest = self.targets.move(source_path, target_folder)
        except ValueError as exc:
            return self._refusal(exc)
        proposal = self.organizer.propose_action("move", src, target_path=dest, reason=reason)
        return self._approve_and_run(proposal, dry_run)

    def archive_files(self, file_paths, archive_name="archive", reason="Archive old files", dry_run=None):
        """Zip files or whole folders into one archive (after the user approves); one Undo restores all."""
        try:
            files, folders, skipped = self.targets.archive(file_paths)
        except ValueError as exc:
            return self._refusal(exc)
        name = Path(folders[0]).name if folders and archive_name == "archive" else archive_name  # zip named after the folder
        proposal = self.organizer.propose_action("archive", files, target_path=name, reason=reason)
        self.organizer.recycle.on_progress = self._report  # reads the progress of the job's own thread
        result = self._approve_and_run(proposal, dry_run)
        if result.get("status") == "done":
            for folder in folders:
                self.folders.remove_emptied_folders(files, folder)
        result["file_count"], result["skipped"] = len(files), skipped
        if skipped:
            result["message"] = f"{result.get('message', '')} {len(skipped)} hidden, private or protected file(s) were left in place.".strip()
        return result

    def delete_files(self, file_paths, reason="User-approved cleanup", dry_run=None):
        """Move files or whole folders to the recycle bin (after the user approves); undo is available."""
        try:
            items = self.targets.delete(file_paths)
        except ValueError as exc:
            return self._refusal(exc)
        results = []
        for done, item in enumerate(items, start=1):
            proposal = self.organizer.propose_action("delete", item, reason=reason)
            if proposal["status"] != "proposed":
                return proposal
            results.append(self._approve_and_run(proposal, dry_run))
            if self.progress is not None:
                self.progress("recycling", done, len(items))
        statuses = {r["status"] for r in results}
        overall = "dry_run" if statuses == {"dry_run"} else ("ok" if statuses == {"done"} else "mixed")
        messages = {
            "dry_run": f"Practice mode (dry-run) is on: nothing was changed. {len(results)} item(s) would go to the recycle bin.",
            "ok": f"Moved {len(results)} item(s) to Steward's recycle bin (undo is available).",
            "mixed": f"Some of the {len(results)} recycle action(s) failed; see results.",
        }
        return {"status": overall, "message": messages[overall], "results": results}

    @property
    def progress(self):
        """Function(label, done, total) showing live progress for this thread's chat job, or None."""
        return getattr(self._job, "progress", None)

    @progress.setter
    def progress(self, value):
        self._job.progress = value

    @property
    def done_actions(self):
        """List collecting ids of changes made by this thread's chat job, or None."""
        return getattr(self._job, "done_actions", None)

    @done_actions.setter
    def done_actions(self, value):
        self._job.done_actions = value

    def _report(self, label, done, total):
        """Pass zip progress to this thread's chat job, if any."""
        if self.progress is not None:
            self.progress(label, done, total)

    def preflight(self, tool_name, args):
        """Return why a paused file change cannot work, or None (runs before the approval card)."""
        return self.targets.check(tool_name, args)

    def describe_targets(self, raw_paths, tool_name=None):
        """Return {"folders", "file_count"} for an approval card, or None for bad paths."""
        return self.targets.describe(raw_paths, tool_name)

    def _refusal(self, exc):
        """Turn a ValueError into a tool result; protected paths are 'blocked', others 'error'."""
        return {"status": "blocked" if isinstance(exc, ProtectedPathError) else "error", "message": str(exc)}

    def _approve_and_run(self, proposal, dry_run):
        """Approve a fresh proposal (the user already confirmed in the chat) and run it."""
        if proposal["status"] != "proposed":
            return proposal
        self.organizer.approve_action(proposal["id"])
        result = self.organizer.execute_action(proposal["id"], dry_run=self._safe_dry_run(dry_run))
        if result.get("status") == "done" and self.done_actions is not None:
            self.done_actions.append(result["id"])
        return result

    def _safe_dry_run(self, requested):
        """Return the dry-run flag to use: the config's dry-run always wins.

        The AI chooses tool arguments, so it may ask for dry_run=False. While dry-run is ON in
        config, every action stays a preview; the AI can only make an action safer, never riskier.
        """
        if self.config.get("safety.dry_run", True):
            return True
        return None if requested is None else bool(requested)

    def undo_action(self, action_id):
        """Restore a completed move, ZIP archive, or recycle-bin delete by action ID."""
        return self.organizer.undo_action(action_id)
