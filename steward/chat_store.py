"""Saves chat conversations in SQLite, so they survive page reloads, tab switches and restarts."""

import json
from datetime import datetime, timezone


class ChatStore:
    """One conversation per browser session id; each message keeps its full reply as JSON.

    A user message is {"role": "user", "content": text}. An assistant message keeps what the
    chat API returned (status, reply, sources, approvals, run_id, steps, duration_sec).
    """

    SCHEMA = (
        "CREATE TABLE IF NOT EXISTS chat_conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL, "
        "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS chat_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "conversation_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, run_id TEXT, "
        "data TEXT NOT NULL, created_at TEXT NOT NULL)",
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation ON chat_messages (conversation_id, id)",
    )
    TITLE_LENGTH = 60

    def __init__(self, db):
        """Create the tables if needed.

        Args:
            db: DatabaseManager (the same SQLite file as the rest of Steward).
        """
        self.db = db
        for statement in self.SCHEMA:
            self.db._execute(statement)

    def add_message(self, conversation_id, role, content, data=None):
        """Append one message, creating the conversation (titled by its first question) if new.

        Args:
            conversation_id: the browser's session id.
            role: "user" or "assistant".
            content: the text shown in the chat.
            data: optional dict with the rest of the reply (sources, steps, approvals...).
        """
        now = datetime.now(timezone.utc).isoformat()
        title = " ".join(str(content).split())[: self.TITLE_LENGTH] or "New chat"
        self.db._execute(
            "INSERT INTO chat_conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at",
            (str(conversation_id), title, now, now),
        )
        payload = dict(data or {})
        self.db._execute(
            "INSERT INTO chat_messages (conversation_id, role, content, run_id, data, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(conversation_id), role, str(content), payload.get("run_id"), json.dumps(payload), now),
        )

    def set_decision(self, run_id, decision):
        """Remember on an approval message whether the user approved or rejected it.

        Args:
            run_id: the paused run the approval card belongs to.
            decision: "approved" or "rejected".
        """
        rows = self.db._query_all("SELECT id, data FROM chat_messages WHERE run_id = ?", (str(run_id),))
        for row in rows:
            data = json.loads(row["data"])
            data["decision"] = decision
            self.db._execute("UPDATE chat_messages SET data = ? WHERE id = ?", (json.dumps(data), row["id"]))

    def list_conversations(self, limit=30):
        """Return the newest conversations first: id, title, updated_at, message_count.

        Args:
            limit: maximum number of conversations.
        """
        return self.db._query_all(
            "SELECT c.id, c.title, c.created_at, c.updated_at, COUNT(m.id) AS message_count "
            "FROM chat_conversations c LEFT JOIN chat_messages m ON m.conversation_id = c.id "
            "GROUP BY c.id ORDER BY c.updated_at DESC LIMIT ?", (int(limit),),
        )

    def messages(self, conversation_id, limit=200):
        """Return a conversation's messages, oldest first, with their data decoded.

        Args:
            conversation_id: the browser's session id.
            limit: maximum number of (newest) messages.
        """
        rows = self.db._query_all(
            "SELECT id, role, content, data, created_at FROM chat_messages WHERE conversation_id = ? "
            "ORDER BY id DESC LIMIT ?", (str(conversation_id), int(limit)),
        )
        return [{**row, "data": json.loads(row["data"])} for row in reversed(rows)]

    def delete(self, conversation_id):
        """Delete a conversation and its messages; return True when it existed.

        Args:
            conversation_id: the browser's session id.
        """
        existed = bool(self.db._query_all("SELECT id FROM chat_conversations WHERE id = ?", (str(conversation_id),)))
        self.db._execute("DELETE FROM chat_messages WHERE conversation_id = ?", (str(conversation_id),))
        self.db._execute("DELETE FROM chat_conversations WHERE id = ?", (str(conversation_id),))
        return existed
