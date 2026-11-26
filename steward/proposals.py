"""Safe creation of file-action proposals: never approves, never duplicates."""

from pathlib import Path


class ProposalService:
    """Creates 'proposed' actions that a human must approve later.

    It adds two guards on top of FileOrganizer.propose_action:
    - protected paths are skipped (no 'blocked' row clutter in the to-do list)
    - a file that already has an open proposal of the same kind is not proposed again
    """

    def __init__(self, config, db, organizer):
        """Store the services needed to check and create proposals.

        Args:
            config: AppConfig, used for the protected-path check.
            db: DatabaseManager holding the actions table.
            organizer: FileOrganizer that inserts the proposal rows.
        """
        self.config = config
        self.db = db
        self.organizer = organizer

    def find_open(self, action_type, source_path):
        """Return the open ('proposed') action row for this file and kind, or None.

        Args:
            action_type: 'move', 'delete' or 'archive'.
            source_path: absolute path of the file.
        """
        rows = self.db._query_all(
            "SELECT * FROM actions WHERE action_type = ? AND source_path = ? AND status = 'proposed' "
            "ORDER BY id DESC LIMIT 1",
            (action_type, str(source_path)),
        )
        return rows[0] if rows else None

    def propose_once(self, action_type, source_path, target_path=None, reason=""):
        """Create one proposal unless the path is protected or already proposed.

        Args:
            action_type: 'move', 'delete' or 'archive'.
            source_path: the file the action is about.
            target_path: destination for moves (optional).
            reason: short explanation shown on the approval card.
        """
        if not str(source_path or "").strip():
            raise ValueError("source_path is required to create a proposal.")
        resolved = str(Path(source_path).expanduser().resolve())
        if self.config.is_protected_path(resolved):
            return {"status": "skipped_protected", "source_path": resolved,
                    "message": f"Skipped protected path: {resolved}"}
        existing = self.find_open(action_type, resolved)
        if existing is not None:
            return {"status": "already_open", "id": existing["id"], "source_path": resolved,
                    "message": f"Action #{existing['id']} is already waiting for approval."}
        return self.organizer.propose_action(action_type, resolved, target_path=target_path, reason=reason)

    def propose_many(self, items):
        """Propose a batch of actions and return a summary grouped by outcome.

        Args:
            items: list of dicts with 'action_type', 'source_path' and optional 'reason'/'target_path'.
        """
        summary = {"created": [], "already_open": [], "skipped_protected": []}
        for item in items:
            result = self.propose_once(
                item["action_type"], item["source_path"],
                target_path=item.get("target_path"), reason=item.get("reason", ""),
            )
            if result["status"] == "proposed":
                summary["created"].append(result)
            elif result["status"] == "already_open":
                summary["already_open"].append(result)
            else:
                summary["skipped_protected"].append(result)
        return summary
