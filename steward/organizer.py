"""Approval-gated file organization, ZIP archiving, recycling, and undo engine."""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from steward.recycle import RecycleManager
from steward.scanner import FileCategorizer


class FileOrganizer:
    """Enforces proposed -> approved -> done -> undone lifecycle with full safety guards."""

    STRATEGIES = ("type", "date", "project")

    def __init__(self, config, db, memory_manager=None, logger=None, recycle_manager=None):
        """Initialize the organizer with config, SQLite DB, OKF memory, and RecycleManager."""
        self.config = config
        self.db = db
        self.memory_manager = memory_manager
        self.logger = logger
        self.categorizer = FileCategorizer()
        self.recycle = recycle_manager or RecycleManager(
            recycle_dir=config.get_path("recycle_dir"),
            archive_dir=config.get_path("data_dir") / "archives",
            logger=logger,
        )

    def plan_organize(self, folder_path, strategy="type", destination_root=None):
        """Propose move actions organizing files in folder_path by type, date, or project."""
        if strategy not in self.STRATEGIES:
            raise ValueError(f"Unsupported strategy '{strategy}'. Choose from: {self.STRATEGIES}")
        src_dir = Path(folder_path).expanduser().resolve()
        if not src_dir.exists() or not src_dir.is_dir():
            raise FileNotFoundError(f"Folder not found: {src_dir}")

        base_dest = Path(destination_root).expanduser().resolve() if destination_root else src_dir / f"organized_by_{strategy}"
        proposals = []
        for entry in sorted(src_dir.iterdir()):
            if not entry.is_file() or entry.name.startswith("."):
                continue
            bucket = self._resolve_bucket(entry, strategy)
            proposals.append(
                self.propose_action("move", str(entry), str(base_dest / bucket / entry.name), f"Organize by {strategy} ({bucket})")
            )
        return proposals

    def propose_action(self, action_type, source_path, target_path=None, reason=""):
        """Create a 'proposed' action record in SQLite without touching any file."""
        paths = source_path if isinstance(source_path, (list, tuple)) else [source_path]
        for raw in paths:
            if self.config.is_protected_path(raw):
                action_id = self._insert_action(action_type, str(raw), target_path, "blocked", True, "Protected path")
                return {"id": action_id, "status": "blocked", "message": f"Blocked protected path: {raw}"}

        resolved_list = [str(Path(p).expanduser().resolve()) for p in paths]
        serialized_src = json.dumps(resolved_list) if isinstance(source_path, (list, tuple)) else resolved_list[0]
        action_id = self._insert_action(action_type, serialized_src, target_path, "proposed", True, reason)
        return {
            "id": action_id, "status": "proposed", "action_type": action_type,
            "source_path": serialized_src, "target_path": str(target_path) if target_path else None,
            "message": f"Proposed {action_type} action #{action_id}.",
        }

    def approve_action(self, action_id):
        """Approve a proposed action so it becomes eligible for execution."""
        action = self.get_action(action_id)
        if action is None:
            return {"status": "not_found", "message": f"Action #{action_id} not found."}
        if action["status"] != "proposed":
            return {"status": "error", "message": f"Action #{action_id} is '{action['status']}', not 'proposed'."}
        for path in self._decode_sources(action["source_path"]):
            if self.config.is_protected_path(path):
                self._set_action_status(action_id, "blocked", reason="Protected path")
                return {"status": "blocked", "message": f"Protected path blocked: {path}"}
        self._set_action_status(action_id, "approved", decided=True)
        return {"id": action_id, "status": "approved", "message": f"Approved action #{action_id}."}

    def reject_action(self, action_id, reason="Rejected by user"):
        """Reject a proposed action; nothing changes on disk."""
        if self.get_action(action_id) is None:
            return {"status": "not_found", "message": f"Action #{action_id} not found."}
        self._set_action_status(action_id, "rejected", reason=reason, decided=True)
        return {"id": action_id, "status": "rejected", "message": f"Rejected action #{action_id}."}

    def execute_action(self, action_id, dry_run=None):
        """Execute an APPROVED action (enforcing protected paths, dry-run, and undo logs)."""
        action = self.get_action(action_id)
        if action is None:
            return {"status": "not_found", "message": f"Action #{action_id} not found."}
        if action["status"] != "approved":
            return {"status": "error", "message": f"Cannot execute action #{action_id} with status '{action['status']}'; approval required."}

        sources = self._decode_sources(action["source_path"])
        for src in sources:
            if self.config.is_protected_path(src):
                self._set_action_status(action_id, "blocked", reason="Protected path")
                return {"status": "blocked", "message": f"Blocked protected path: {src}"}

        is_dry = bool(self.config.get("safety.dry_run", True) if dry_run is None else dry_run)
        if is_dry:
            return {"id": action_id, "status": "dry_run", "message": f"[Dry-run] Approved {action['action_type']} #{action_id} not applied."}

        try:
            final_target = self._apply_on_disk(action, sources)
            self._set_action_status(action_id, "done", target_path=final_target, dry_run=False)
            self._record_okf(action["action_type"], sources[0], action.get("reason", ""), "done")
            return {"id": action_id, "status": "done", "target_path": final_target, "message": f"Completed {action['action_type']} #{action_id}."}
        except Exception as exc:
            self._set_action_status(action_id, "failed", reason=str(exc), dry_run=False)
            return {"id": action_id, "status": "failed", "message": f"Action #{action_id} failed: {exc}"}

    def undo_action(self, action_id):
        """Reverse a completed move, ZIP archive, or recycle-bin delete."""
        action = self.get_action(action_id)
        if action is None:
            return {"status": "not_found", "message": f"Action #{action_id} not found."}
        if action["status"] != "done" or not action.get("target_path"):
            return {"status": "error", "message": f"Action #{action_id} cannot be undone (status={action['status']})."}

        kind, target = action["action_type"], action["target_path"]
        try:
            if kind == "move":
                dest = self.recycle.collision_safe_path(Path(action["source_path"]))
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(dest))
                restored = [str(dest)]
            elif kind == "delete":
                restored = [self.recycle.restore_from_recycle(target, original_path=action["source_path"])]
            elif kind == "archive":
                restored = self.recycle.restore_zip_archive(target)
            else:
                return {"status": "error", "message": f"Unsupported undo type: {kind}"}
            self._set_action_status(action_id, "undone")
            self._record_okf("undo", restored[0], f"Undid action #{action_id}", "undone")
            return {"id": action_id, "status": "undone", "restored": restored, "message": f"Undid {kind} action #{action_id}."}
        except Exception as exc:
            return {"id": action_id, "status": "error", "message": f"Undo failed: {exc}"}

    def get_action(self, action_id):
        """Fetch one action row from SQLite by ID."""
        rows = self.db._query_all("SELECT * FROM actions WHERE id = ?", (int(action_id),))
        return rows[0] if rows else None

    def list_actions(self, status=None, limit=50):
        """List actions from SQLite, optionally filtered by status."""
        if status:
            return self.db._query_all("SELECT * FROM actions WHERE status = ? ORDER BY id DESC LIMIT ?", (status, int(limit)))
        return self.db._query_all("SELECT * FROM actions ORDER BY id DESC LIMIT ?", (int(limit),))

    def _apply_on_disk(self, action, sources):
        """Perform the actual move, ZIP archive, or recycle operation safely."""
        kind = action["action_type"]
        if kind == "move":
            dest = self.recycle.collision_safe_path(Path(action["target_path"]))
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(Path(sources[0])), str(dest))
            return str(dest)
        if kind == "delete":
            return self.recycle.move_to_recycle(sources[0])["recycled_path"]
        if kind == "archive":
            name = Path(action["target_path"]).stem if action.get("target_path") else "archive"
            return self.recycle.create_zip_archive(sources, archive_name=name)["archive_path"]
        raise ValueError(f"Unknown action type: {kind}")

    def _resolve_bucket(self, file_path, strategy):
        """Compute the destination subfolder name for type, date, or project organization."""
        if strategy == "type":
            return self.categorizer.categorize(file_path)
        if strategy == "date":
            return datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc).strftime("%Y/%m")
        return file_path.parent.name or "general"

    def _insert_action(self, action_type, source_path, target_path, status, dry_run, reason):
        """Insert a new action row and return its auto-increment ID."""
        now = datetime.now(timezone.utc).isoformat()
        sql = "INSERT INTO actions (timestamp, action_type, source_path, target_path, status, dry_run, reason) VALUES (?,?,?,?,?,?,?)"
        with self.db._connect() as conn:
            cur = conn.execute(sql, (now, action_type, source_path, str(target_path) if target_path else None, status, 1 if dry_run else 0, reason))
            return cur.lastrowid

    def _set_action_status(self, action_id, status, target_path=None, reason=None, dry_run=None, decided=False):
        """Update status fields on an existing action row."""
        fields, params = ["status = ?"], [status]
        for col, val in (("target_path", target_path), ("reason", reason), ("dry_run", None if dry_run is None else (1 if dry_run else 0))):
            if val is not None:
                fields.append(f"{col} = ?")
                params.append(str(val) if col == "target_path" else val)
        if decided:
            fields.append("decided_at = ?")
            params.append(datetime.now(timezone.utc).isoformat())
        params.append(int(action_id))
        self.db._execute(f"UPDATE actions SET {', '.join(fields)} WHERE id = ?", tuple(params))

    @staticmethod
    def _decode_sources(raw_source):
        """Parse either a JSON list of source paths or a single path string."""
        return json.loads(raw_source) if raw_source.startswith("[") else [raw_source]

    def _record_okf(self, action_type, target_path, reason, outcome):
        """Persist the action decision into OKF memory when available."""
        if self.memory_manager is not None:
            self.memory_manager.record_decision(action_type, target_path, reason, outcome=outcome)
