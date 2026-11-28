"""Remembers what a chat talked about, so "delete the file" or "archive it" mean the right thing."""

import re


class ChatMemory:
    """Builds short, factual notes about a conversation from what Steward saved (ChatStore).

    Small local models often lose track of "it" or "the file" a few messages later. Instead of
    hoping the model remembers, Steward adds its own notes to every question: the paths the last
    answers mentioned, the folder last scanned, what the user approved or rejected, and what really
    changed on disk. The notes come from saved results, never from the AI's wording.
    """

    RECENT_MESSAGES = 16
    MAX_PATHS = 6
    MAX_NOTES = 8
    # `/Users/you/a b.mov` inside backticks (spaces allowed), or a bare path without spaces
    PATH = re.compile(r"`((?:~|/)[^`\n]+)`|(?<![\w`])((?:~|/Users|/Volumes|/data)/[^\s`'\"),;]+)")
    INTRO = ("Steward's notes on this conversation (facts, newest first). Use them for words like "
             "\"it\", \"the file\", \"that folder\" or \"the zip\", and pass these exact paths to tools. "
             "Answer as if you simply remember; never mention these notes:")
    KINDS = {"archive": "Zipped into", "delete": "Moved to Steward's recycle bin:", "move": "Moved to"}

    def __init__(self, store, get_action=None, mapper=None):
        """Remember where the conversation and the action log are.

        Args:
            store: ChatStore with the saved messages.
            get_action: optional function(action_id) returning an actions row (to say what changed).
            mapper: optional PathMapper, so Steward's own paths are shown as Mac paths.
        """
        self.store = store
        self.get_action = get_action
        self.mapper = mapper

    def with_context(self, session_id, message):
        """Return the message with Steward's notes in front, or the message alone when there are none.

        Args:
            session_id: the conversation id.
            message: the question the user just asked (already saved as the newest message).
        """
        try:
            history = self.store.messages(session_id, limit=self.RECENT_MESSAGES)
            if history and history[-1]["role"] == "user" and history[-1]["content"] == message:
                history = history[:-1]  # the question being answered now
            notes = self.notes(history)
        except Exception:  # the notes are a help; the question itself must always reach the AI
            notes = []
        if not notes:
            return message
        lines = "\n".join(f"- {note}" for note in notes)
        return f"{self.INTRO}\n{lines}\n\nThe user's message: {message}"

    def notes(self, messages):
        """Return the notes for a list of saved messages (oldest first), newest facts first.

        Args:
            messages: ChatStore messages, without the question being answered now.
        """
        notes = self._path_notes(messages)
        for message in reversed(messages):
            data = message["data"]
            if message["role"] != "assistant":
                continue
            notes += self._decision_notes(data) + self._action_notes(data)
            folder = (data.get("folder") or {}).get("path")
            if folder and not any(n.startswith("Folder last scanned") for n in notes):
                notes.append(f"Folder last scanned: `{folder}`")
        return notes[: self.MAX_NOTES]

    def _path_notes(self, messages):
        """Paths from the newest answer that named any (main one first), then earlier ones."""
        latest, earlier = [], []
        for message in reversed(messages):
            found = self.paths_in(message["content"]) + self.paths_in(" ".join(
                f"`{p}`" for step in message["data"].get("approvals", []) for p in step.get("paths", [])))
            if not latest and message["role"] == "assistant" and found:
                latest = found
            else:
                earlier += [p for p in found if p not in latest and p not in earlier]
        notes = []
        if latest:
            notes.append("Paths in the last answer that named files (main one first): " + self._quote(latest))
        if earlier:
            notes.append("Other paths mentioned in this chat (newest first): " + self._quote(earlier))
        return notes

    def _decision_notes(self, data):
        """What the user decided on an approval card."""
        if data.get("status") != "approval" or not data.get("decision"):
            return []
        summaries = "; ".join(step.get("summary", "a file change") for step in data.get("approvals", []))
        if data["decision"] == "rejected":
            return [f"The user REJECTED: {summaries}. Nothing was changed: no file was moved, "
                    "archived, zipped or deleted for it."]
        return [f"The user approved: {summaries}."]

    def _action_notes(self, data):
        """What really changed on disk for an answer (from Steward's action log)."""
        notes = []
        for action_id in data.get("actions", []) if self.get_action else []:
            action = self.get_action(action_id)
            if not action or not action.get("target_path"):
                continue
            target = self.mapper.to_host(action["target_path"]) if self.mapper else action["target_path"]
            label = self.KINDS.get(action["action_type"], action["action_type"])
            undone = " (later undone: the original files are back)" if action["status"] == "undone" else ""
            notes.append(f"Done: {label} `{target}`{undone}")
        return notes

    def _quote(self, paths):
        """Format up to MAX_PATHS paths as `a`, `b`."""
        return ", ".join(f"`{p}`" for p in paths[: self.MAX_PATHS])

    @classmethod
    def paths_in(cls, text):
        """Return the file and folder paths written in a text, in order, without repeats.

        Args:
            text: an answer or question.
        """
        found = []
        for quoted, bare in cls.PATH.findall(str(text or "")):
            path = (quoted or bare).strip().rstrip(".:")
            if path not in found and len(path) > 2:
                found.append(path)
        return found
