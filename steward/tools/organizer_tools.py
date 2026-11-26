"""Safety-first Agno Toolkit for organizing, archiving, and recycling files."""

import shutil
from datetime import datetime, timezone
from pathlib import Path

from agno.tools import Toolkit


class OrganizerTools(Toolkit):
    """Agno Toolkit with HITL confirmation, dry-run mode, protected paths, and recycle bin."""

    def __init__(self, config, db, memory_manager=None, logger=None):
        """Register file management tools with confirmation on destructive actions."""
        self.config = config
        self.db = db
        self.memory_manager = memory_manager
        self.logger = logger
        super().__init__(
            name="organizer_tools",
            tools=[
                self.propose_move,
                self.move_file,
                self.archive_files,
                self.delete_files,
                self.undo_action,
            ],
            requires_confirmation_tools=["move_file", "archive_files", "delete_files"],
        )

    def propose_move(self, source_path, target_folder, reason="Organize by category"):
        """Log a non-destructive move proposal without touching any file on disk."""
        src = Path(source_path).expanduser().resolve()
        if self.config.is_protected_path(src):
            return self._blocked(src, "propose_move")
        dest = Path(target_folder).expanduser().resolve() / src.name
        self.db.log_action("move", src, dest, status="proposed", dry_run=True, reason=reason)
        return {
            "status": "proposed",
            "message": f"Proposed moving {src.name} -> {dest}",
            "source_path": str(src),
            "target_path": str(dest),
        }

    def move_file(self, source_path, target_folder, reason="User-approved move", dry_run=None):
        """Move one file after approval, respecting dry-run and protected paths."""
        src = Path(source_path).expanduser().resolve()
        if self.config.is_protected_path(src):
            return self._blocked(src, "move")
        if not src.exists():
            return {"status": "error", "message": f"Source not found: {src}"}

        dest_dir = Path(target_folder).expanduser().resolve()
        dest = dest_dir / src.name
        is_dry = self._is_dry_run(dry_run)
        if is_dry:
            self.db.log_action("move", src, dest, status="dry_run", dry_run=True, reason=reason)
            return {"status": "dry_run", "message": f"[Dry-run] Would move {src.name} -> {dest}"}

        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        now = datetime.now(timezone.utc).isoformat()
        self.db.log_action("move", src, dest, status="done", dry_run=False, reason=reason, decided_at=now)
        self._record_okf_decision("move", str(src), reason, "done")
        return {"status": "ok", "message": f"Moved {src.name} -> {dest}", "target_path": str(dest)}

    def archive_files(self, file_paths, archive_name="archive", reason="Archive old files", dry_run=None):
        """Plan or move files into an archive folder (full zip compression expands in Phase 6)."""
        paths = [Path(p).expanduser().resolve() for p in file_paths]
        for path in paths:
            if self.config.is_protected_path(path):
                return self._blocked(path, "archive")

        archive_dir = self.config.get_path("data_dir") / "archives" / archive_name
        is_dry = self._is_dry_run(dry_run)
        if is_dry:
            for path in paths:
                self.db.log_action("archive", path, archive_dir / path.name, status="dry_run", dry_run=True, reason=reason)
            return {
                "status": "dry_run",
                "message": f"[Dry-run] Would archive {len(paths)} file(s) to {archive_dir}",
            }

        archive_dir.mkdir(parents=True, exist_ok=True)
        moved = []
        now = datetime.now(timezone.utc).isoformat()
        for path in paths:
            if not path.exists():
                continue
            target = archive_dir / path.name
            shutil.move(str(path), str(target))
            self.db.log_action("archive", path, target, status="done", dry_run=False, reason=reason, decided_at=now)
            moved.append(str(target))
        self._record_okf_decision("archive", str(archive_dir), reason, "done")
        return {"status": "ok", "message": f"Archived {len(moved)} file(s).", "archived": moved}

    def delete_files(self, file_paths, reason="User-approved cleanup", dry_run=None):
        """Safely recycle files into recycle_dir instead of permanently deleting."""
        paths = [Path(p).expanduser().resolve() for p in file_paths]
        for path in paths:
            if self.config.is_protected_path(path):
                return self._blocked(path, "delete")

        recycle_dir = self.config.get_path("recycle_dir")
        is_dry = self._is_dry_run(dry_run)
        if is_dry:
            for path in paths:
                self.db.log_action("delete", path, recycle_dir / path.name, status="dry_run", dry_run=True, reason=reason)
            return {
                "status": "dry_run",
                "message": f"[Dry-run] Would move {len(paths)} file(s) to recycle bin.",
            }

        recycle_dir.mkdir(parents=True, exist_ok=True)
        recycled = []
        now = datetime.now(timezone.utc).isoformat()
        for path in paths:
            if not path.exists():
                continue
            target = recycle_dir / f"{int(datetime.now(timezone.utc).timestamp())}_{path.name}"
            shutil.move(str(path), str(target))
            self.db.log_action("delete", path, target, status="done", dry_run=False, reason=reason, decided_at=now)
            self._record_okf_decision("delete", str(path), reason, "recycled")
            recycled.append(str(target))
        return {"status": "ok", "message": f"Moved {len(recycled)} file(s) to recycle bin.", "recycled": recycled}

    def undo_action(self, action_id):
        """Restore a completed move/archive/delete action using the SQLite actions log."""
        rows = self.db._query_all("SELECT * FROM actions WHERE id = ?", (int(action_id),))
        if not rows:
            return {"status": "not_found", "message": f"Action #{action_id} not found."}
        action = rows[0]
        if action["status"] != "done" or not action.get("target_path"):
            return {"status": "error", "message": f"Action #{action_id} is not reversible (status={action['status']})."}

        src, dest = Path(action["source_path"]), Path(action["target_path"])
        if not dest.exists():
            return {"status": "error", "message": f"Target file missing for undo: {dest}"}
        src.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dest), str(src))
        self.db._execute("UPDATE actions SET status = 'undone' WHERE id = ?", (int(action_id),))
        return {"status": "ok", "message": f"Restored {src.name} back to {src.parent}."}

    def _is_dry_run(self, override):
        """Resolve effective dry-run setting from override or AppConfig."""
        if override is not None:
            return bool(override)
        return bool(self.config.get("safety.dry_run", True))

    def _blocked(self, path, action_type):
        """Log and reject any action targeting a protected directory."""
        self.db.log_action(action_type, path, None, status="blocked", dry_run=True, reason="Protected path")
        return {"status": "blocked", "message": f"Blocked: {path} is inside a protected path."}

    def _record_okf_decision(self, action_type, target_path, reason, outcome):
        """Record the decision in OKF memory when MemoryManager is connected."""
        if self.memory_manager is not None:
            self.memory_manager.record_decision(action_type, target_path, reason, outcome=outcome)
