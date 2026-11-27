"""Safety-first Agno Toolkit for organizing, ZIP archiving, recycling, and undo."""

from pathlib import Path

from agno.tools import Toolkit

from steward.organizer import FileOrganizer


class OrganizerTools(Toolkit):
    """Agno Toolkit delegating confirmation-gated file actions to FileOrganizer."""

    def __init__(self, config, db, memory_manager=None, logger=None, organizer=None):
        """Register file management tools with HITL confirmation on destructive actions."""
        self.config = config
        self.db = db
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
        src = Path(source_path).expanduser().resolve()
        dest = Path(target_folder).expanduser().resolve() / src.name
        return self.organizer.propose_action("move", str(src), target_path=str(dest), reason=reason)

    def organize_folder(self, folder_path, strategy="type", destination_root=None):
        """Create move proposals to organize a folder by type, date, or project."""
        try:
            proposals = self.organizer.plan_organize(
                folder_path, strategy=strategy, destination_root=destination_root
            )
            return {
                "status": "proposed",
                "message": f"Created {len(proposals)} move proposal(s) using strategy '{strategy}'.",
                "proposals": proposals,
            }
        except (ValueError, FileNotFoundError) as exc:
            return {"status": "error", "message": str(exc)}

    def move_file(self, source_path, target_folder, reason="User-approved move", dry_run=None):
        """Propose, approve (after HITL confirm), and execute a safe file move."""
        src = Path(source_path).expanduser().resolve()
        dest = Path(target_folder).expanduser().resolve() / src.name
        proposal = self.organizer.propose_action("move", str(src), target_path=str(dest), reason=reason)
        if proposal["status"] != "proposed":
            return proposal
        self.organizer.approve_action(proposal["id"])
        return self.organizer.execute_action(proposal["id"], dry_run=self._safe_dry_run(dry_run))

    def archive_files(self, file_paths, archive_name="archive", reason="Archive old files", dry_run=None):
        """Propose, approve (after HITL confirm), and compress files into a ZIP archive."""
        proposal = self.organizer.propose_action(
            "archive", list(file_paths), target_path=archive_name, reason=reason
        )
        if proposal["status"] != "proposed":
            return proposal
        self.organizer.approve_action(proposal["id"])
        return self.organizer.execute_action(proposal["id"], dry_run=self._safe_dry_run(dry_run))

    def delete_files(self, file_paths, reason="User-approved cleanup", dry_run=None):
        """Propose, approve (after HITL confirm), and move files into the recycle bin."""
        results = []
        for raw_path in file_paths:
            proposal = self.organizer.propose_action("delete", str(raw_path), reason=reason)
            if proposal["status"] != "proposed":
                return proposal
            self.organizer.approve_action(proposal["id"])
            results.append(self.organizer.execute_action(proposal["id"], dry_run=self._safe_dry_run(dry_run)))
        statuses = {r["status"] for r in results}
        overall = "dry_run" if statuses == {"dry_run"} else ("ok" if statuses == {"done"} else "mixed")
        return {
            "status": overall,
            "message": f"Processed {len(results)} recycle action(s) (status={overall}).",
            "results": results,
        }

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
