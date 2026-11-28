"""Clears Steward's own data from Settings: chats, knowledge notes, topics and the recycle bin."""

from pathlib import Path

from steward.data_backups import DataBackups
from steward.data_records import DataRecords


class DataCleanup:
    """Removes Steward's own data, never the user's files in their folders.

    "Clear" keeps a backup in data/backups (it can be restored); "hard" deletes for good. The
    recycle bin can only be emptied for good (its backup would be the recycle bin itself).
    """

    TARGETS = ("chats", "knowledge", "topics", "recycle") + DataRecords.TARGETS
    PERMANENT = ("recycle",) + DataRecords.TARGETS  # no backup possible or needed: always "for good"
    BUSY = "Steward is still answering in the chat. Wait for the answer (or press Stop), then clear the chats."

    def __init__(self, app, chat_store, session_db, is_busy=None, forget_pending=None, records=None):
        """Remember where each kind of data lives.

        Args:
            app: StewardApp (knowledge bundle, recycle bin, data folder).
            chat_store: ChatStore with the saved conversations.
            session_db: function returning Agno's SqliteDb (the AI's own memory of each chat).
            is_busy: optional function returning True while a chat answer is running.
            forget_pending: optional function that drops approval cards still waiting.
            records: optional DataRecords (file index, actions, search index, reports).
        """
        self.records = records or DataRecords(app)
        self.bundle = app.okf_bundle
        self.okf_root = Path(app.okf_bundle.root_dir)
        self.recycle = app.organizer.recycle
        self.store = chat_store
        self.session_db = session_db
        self.is_busy = is_busy or (lambda: False)
        self.forget_pending = forget_pending or (lambda: None)
        self.backups = DataBackups(app.config.get_path("data_dir") / "backups")

    def summary(self):
        """Return how much there is of each kind of data, plus the backups."""
        chats = self.store.counts()
        notes, topics = self._note_files(None), self._note_files("topics")
        recycled = self.recycle.list_recycled()
        return {
            "chats": {"count": chats["conversations"], "messages": chats["messages"]},
            "knowledge": {"count": len(notes), "size_bytes": sum(p.stat().st_size for p in notes)},
            "topics": {"count": len(topics), "size_bytes": sum(p.stat().st_size for p in topics)},
            "recycle": {"count": len(recycled), "size_bytes": sum(i.get("size_bytes") or 0 for i in recycled)},
            "backups": self.backups.list(),
            **self.records.summary(),
        }

    def clear(self, target, hard=False):
        """Clear one kind of data and return {"status", "message", "removed", "backup"}.

        Args:
            target: "chats", "knowledge" (all notes), "topics" (topic notes only) or "recycle".
            hard: True to delete for good without a backup (the recycle bin is always for good).
        Raises:
            ValueError: for an unknown target.
            RuntimeError: when chats are cleared while an answer is running.
        """
        if target not in self.TARGETS:
            raise ValueError(f"Unknown data '{target}'. Use one of: {', '.join(self.TARGETS)}.")
        if target in DataRecords.TARGETS:
            return self.records.clear(target)
        if target == "recycle":
            return self._empty_recycle()
        if target == "chats":
            return self._clear_chats(hard)
        return self._clear_notes(target, hard)

    def restore(self, backup_id):
        """Put a backup back and return {"status", "message", "restored"}.

        Args:
            backup_id: the backup's file name (from summary()["backups"]).
        """
        path = self.backups.path_for(backup_id)
        if path.name.startswith("chats-"):
            restored = self.store.import_rows(self.backups.read_json(backup_id))
            message = f"Restored {restored} chat(s). Chats that already existed were left as they are."
        else:
            restored = self.backups.extract_markdown(backup_id, self.okf_root)
            self.bundle.refresh_index()
            message = f"Restored {restored} knowledge note(s)."
        return {"status": "ok", "message": message, "restored": restored}

    def delete_backup(self, backup_id):
        """Delete a backup for good.

        Args:
            backup_id: the backup's file name.
        """
        self.backups.delete(backup_id)
        return {"status": "ok", "message": f"Deleted backup {backup_id} for good."}

    def _clear_chats(self, hard):
        """Delete saved chats, the AI's memory of them and waiting approval cards."""
        if self.is_busy():
            raise RuntimeError(self.BUSY)
        payload = self.store.export_all()
        count = len(payload["conversations"])
        backup = self.backups.save_json("chats", payload) if count and not hard else None
        self.store.clear_all()
        self.forget_pending()
        self._forget_ai_sessions({c["id"] for c in payload["conversations"]})
        return self._result("chat(s)", count, backup)

    def _forget_ai_sessions(self, chat_ids):
        """Delete the AI's stored history of the chats (Agno sessions); background jobs keep theirs."""
        db = self.session_db()
        rows, _ = db.get_sessions(deserialize=False, include_runs=False)
        doomed = [r["session_id"] for r in rows if r["session_id"] in chat_ids or str(r["session_id"]).startswith("web-")]
        if doomed:
            db.delete_sessions(doomed)

    def _clear_notes(self, target, hard):
        """Delete knowledge notes (all, or topics only) and rebuild the knowledge index."""
        files = self._note_files("topics" if target == "topics" else None)
        backup = self.backups.save_zip(target, self.okf_root, files) if files and not hard else None
        for path in files:
            path.unlink()
        self.bundle.refresh_index()
        return self._result("topic note(s)" if target == "topics" else "knowledge note(s)", len(files), backup)

    def _empty_recycle(self):
        """Delete everything in Steward's recycle bin for good."""
        result = self.recycle.purge_expired(older_than_days=0, confirmed=True)
        count = result.get("purged_count", 0)
        return {"status": "ok", "removed": count, "backup": None,
                "message": f"Emptied the recycle bin: {count} item(s) deleted for good. Undo no longer works for them."}

    def _note_files(self, subdir):
        """Return the knowledge notes (Markdown files) in the bundle or one of its folders, without the index."""
        base = self.okf_root / subdir if subdir else self.okf_root
        index = self.okf_root / "index.md"
        return sorted(p for p in base.rglob("*.md") if p != index) if base.exists() else []

    @staticmethod
    def _result(what, count, backup):
        """The reply after a clear."""
        if backup:
            message = f"Cleared {count} {what}. A backup was kept, so you can restore them below."
        else:
            message = f"Deleted {count} {what} for good." if count else f"There were no {what} to clear."
        return {"status": "ok", "removed": count, "backup": backup, "message": message}
