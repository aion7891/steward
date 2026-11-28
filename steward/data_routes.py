"""HTTP routes for Settings → Data & cleanup: what Steward keeps, clear it, and restore backups."""

from fastapi import Body, HTTPException

from steward.data_cleanup import DataCleanup
from steward.data_records import DataRecords


class DataRoutes:
    """Registers /steward/data (summary), /steward/data/clear and /steward/data/backups/{id}/...

    Anything that deletes for good (hard clear, emptying the recycle bin, deleting a backup) needs
    {"confirm": "DELETE"} in the request, so it can never happen by one stray click or request.
    """

    CONFIRM_WORD = "DELETE"

    def __init__(self, app, chat_routes, session_db, forget_pending=None, rag_index=None, scan_jobs=None):
        """Create the cleanup service.

        Args:
            app: StewardApp.
            chat_routes: ChatRoutes (its store holds the chats; its jobs say if an answer is running).
            session_db: function returning Agno's SqliteDb.
            forget_pending: optional function that drops waiting approval cards.
            rag_index: optional RAGIndex (the document search index).
            scan_jobs: optional FolderScanJobs (refuses to clear the scan history while a scan runs).
        """
        records = DataRecords(app, rag_index=rag_index, scan_jobs=scan_jobs)
        self.cleanup = DataCleanup(app, chat_routes.store, session_db, is_busy=lambda: chat_routes.jobs.busy(),
                                   forget_pending=forget_pending, records=records)

    def register(self, api):
        """Attach the routes to a FastAPI app.

        Args:
            api: the FastAPI application.
        """

        @api.get("/steward/data")
        def summary():
            return {"status": "ok", **self.cleanup.summary()}

        @api.post("/steward/data/clear")
        def clear(payload=Body(...)):
            data = payload if isinstance(payload, dict) else {}
            target, hard = str(data.get("target", "")), data.get("hard", False) is True
            if target not in DataCleanup.TARGETS:
                raise HTTPException(status_code=400, detail=f"'target' must be one of: {', '.join(DataCleanup.TARGETS)}.")
            if hard or target in DataCleanup.PERMANENT:
                self._check_confirm(data)
            try:
                return self.cleanup.clear(target, hard=hard)
            except RuntimeError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

        @api.post("/steward/data/backups/{backup_id}/restore")
        def restore(backup_id):
            return self._on_backup(lambda: self.cleanup.restore(backup_id))

        @api.post("/steward/data/backups/{backup_id}/delete")
        def delete_backup(backup_id, payload=Body(default=None)):
            self._check_confirm(payload if isinstance(payload, dict) else {})
            return self._on_backup(lambda: self.cleanup.delete_backup(backup_id))

    def _check_confirm(self, data):
        """Refuse a permanent delete unless the request says {"confirm": "DELETE"}."""
        if data.get("confirm") != self.CONFIRM_WORD:
            raise HTTPException(status_code=400, detail="This deletes for good. Type DELETE to confirm.")

    @staticmethod
    def _on_backup(action):
        """Run a backup action, turning bad or unknown backup names into 400 / 404."""
        try:
            return action()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
