"""Understands short typed commands in the chat: "no" for a waiting approval, "undo that" after a change."""

import re


class ChatCommands:
    """Recognises a few plain commands so they never depend on the AI understanding them.

    - "no", "don't", "cancel", "reject"... while an approval card waits: the card is rejected.
    - "undo that", "revert back", "can you recover it"... : the last file change made from this chat is undone.

    Only short messages that are clearly one of these count; anything else goes to the AI.
    """

    MAX_WORDS = 8
    REJECT = re.compile(
        r"^(no|nope|nah|don'?t|do not|cancel|reject|stop|never ?mind|not approved?|"
        r"i (do not|don'?t) (approve|want (it|that|this))|i reject)\b"
    )
    # Words that may follow "no" ("no, don't delete it"); "no, archive the other folder" goes to the AI
    FILLER = {"thanks", "thank", "you", "please", "don't", "dont", "do", "not", "it", "that", "this", "now",
              "i", "approve", "approved", "want", "reject", "the", "change", "changes", "archive", "delete",
              "move", "zip", "them", "way", "mind", "never", "cancel"}
    UNDO = re.compile(
        r"^(please )?((can|could) you )?(please )?(undo|revert|roll ?back|reverse|recover|restore|(bring|get)( it| them| that)? back)"
        r"( (it|that|this|back|them|the|last|latest|change|changes|file|files|what you did|please))*$"
    )

    def __init__(self, store, organizer_tools):
        """Remember where to find the conversation and how to undo actions.

        Args:
            store: ChatStore with the saved conversation.
            organizer_tools: function returning the OrganizerTools used by the chat.
        """
        self.store = store
        self.organizer_tools = organizer_tools

    def classify(self, message):
        """Return "reject", "undo" or None for a user message.

        Args:
            message: the text the user typed.
        """
        words = re.sub(r"[^a-z' ]", " ", str(message).lower()).split()
        if not words or len(words) > self.MAX_WORDS:
            return None
        text = " ".join(words)
        if self.UNDO.match(text):
            return "undo"
        head = self.REJECT.match(text)
        if head and all(word in self.FILLER for word in text[head.end():].split()):
            return "reject"
        return None

    def undo(self, session_id):
        """Undo the newest file change made from this chat and return a chat reply.

        Args:
            session_id: the conversation id.
        """
        found = self.store.last_actions(session_id)
        if found is None:
            return {"status": "ok", "sources": [], "reply": (
                "There is no file change from this chat to undo. Changes made elsewhere can be "
                "undone on the Dashboard, under *Recently completed*.")}
        message_id, action_ids = found
        tools = self.organizer_tools()
        results = [tools.undo_action(action_id) for action_id in reversed(action_ids)]
        self.store.mark_undone(message_id)
        return {"status": "ok", "sources": [], "reply": self.describe(results)}

    @staticmethod
    def describe(results):
        """Turn undo results into a short Markdown reply.

        Args:
            results: the dicts returned by Organizer.undo_action, one per action.
        """
        restored = [path for r in results if r.get("status") == "undone" for path in r.get("restored", [])]
        failed = [r.get("message", "Undo failed.") for r in results if r.get("status") != "undone"]
        lines = []
        if restored:
            shown = ", ".join(f"`{path}`" for path in restored[:5])
            more = f" and {len(restored) - 5} more" if len(restored) > 5 else ""
            lines.append(f"Undone. Restored {len(restored)} item(s): {shown}{more}.")
        lines += [f"> **Steward:** {message}" for message in failed]
        return "\n\n".join(lines) or "Nothing was undone."
