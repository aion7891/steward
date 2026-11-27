"""Safety-first Agno Toolkit for organizing, ZIP archiving, recycling, and undo."""

from pathlib import Path

from agno.tools import Toolkit

from steward.organizer import FileOrganizer
from steward.tools.tool_paths import ToolPaths


class OrganizerTools(Toolkit):
    """Agno Toolkit delegating confirmation-gated file actions to FileOrganizer."""

    def __init__(self, config, db, memory_manager=None, logger=None, organizer=None, paths=None):
        """Register file management tools with HITL confirmation on destructive actions.

        Args:
            paths: ToolPaths that turns the user's Mac paths into paths Steward can open,
                and refuses folders Steward may not change.
        """
        self.config = config
        self.db = db
        self.paths = paths or ToolPaths()
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
        """Propose moving a file without touching disk."""
        try:
            src, dest = self._move_paths(source_path, target_folder)
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}
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
        """Propose, approve (after HITL confirm), and execute a safe file move."""
        try:
            src, dest = self._move_paths(source_path, target_folder)
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}
        proposal = self.organizer.propose_action("move", src, target_path=dest, reason=reason)
        return self._approve_and_run(proposal, dry_run)

    def archive_files(self, file_paths, archive_name="archive", reason="Archive old files", dry_run=None):
        """Propose, approve (after HITL confirm), and compress files into a ZIP archive."""
        try:
            sources = self.paths.existing_many(file_paths)
            self.paths.check_all_writable(sources)  # originals are removed after zipping
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}
        proposal = self.organizer.propose_action("archive", sources, target_path=archive_name, reason=reason)
        return self._approve_and_run(proposal, dry_run)

    def delete_files(self, file_paths, reason="User-approved cleanup", dry_run=None):
        """Propose, approve (after HITL confirm), and move files into the recycle bin."""
        try:
            sources = self.paths.existing_many(file_paths)
            self.paths.check_all_writable(sources)
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}
        results = []
        for src in sources:
            proposal = self.organizer.propose_action("delete", src, reason=reason)
            if proposal["status"] != "proposed":
                return proposal
            results.append(self._approve_and_run(proposal, dry_run))
        statuses = {r["status"] for r in results}
        overall = "dry_run" if statuses == {"dry_run"} else ("ok" if statuses == {"done"} else "mixed")
        messages = {
            "dry_run": f"Practice mode (dry-run) is on: nothing was changed. {len(results)} file(s) would go to the recycle bin.",
            "ok": f"Moved {len(results)} file(s) to Steward's recycle bin (undo is available).",
            "mixed": f"Some of the {len(results)} recycle action(s) failed; see results.",
        }
        return {"status": overall, "message": messages[overall], "results": results}

    def preflight(self, tool_name, args):
        """Return why a paused file change cannot work (missing path, read-only folder), or None.

        Runs before the approval card is shown, so the user is never asked to approve
        something that is bound to fail.

        Args:
            tool_name: move_file, archive_files or delete_files.
            args: the arguments the AI chose for that tool.
        """
        try:
            if tool_name == "move_file":
                self._move_paths(args.get("source_path"), args.get("target_folder"))
            elif tool_name in ("archive_files", "delete_files"):
                self.paths.check_all_writable(self.paths.existing_many(args.get("file_paths")))
        except ValueError as exc:
            return str(exc)
        return None

    def _move_paths(self, source_path, target_folder):
        """Return (source, destination) local paths for a move, or raise ValueError."""
        src = self.paths.existing(source_path)
        dest = str(Path(self.paths.target(target_folder)) / Path(src).name)
        self.paths.check_writable(src)
        self.paths.check_writable(dest)
        return src, dest

    def _approve_and_run(self, proposal, dry_run):
        """Approve a fresh proposal (the user already confirmed in the chat) and run it."""
        if proposal["status"] != "proposed":
            return proposal
        self.organizer.approve_action(proposal["id"])
        return self.organizer.execute_action(proposal["id"], dry_run=self._safe_dry_run(dry_run))

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
