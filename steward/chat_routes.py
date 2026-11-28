"""HTTP routes for background chat jobs and saved conversations."""

from fastapi import Body, HTTPException
from fastapi.responses import JSONResponse

from steward.chat_jobs import ChatJobs
from steward.chat_store import ChatStore


class ChatRoutes:
    """Registers /steward/chat/jobs (ask, poll), /steward/chat/decisions and /steward/chat/conversations."""

    MAX_MESSAGE = 4000
    GONE = "This answer is no longer available (Steward may have restarted). Please ask again."

    def __init__(self, app, chat, mapper=None, run_inline=False):
        """Create the conversation store and the job queue.

        Args:
            app: StewardApp (for the SQLite database).
            chat: ChatService that answers questions.
            mapper: optional PathMapper for Mac paths.
            run_inline: answer jobs synchronously (used by tests).
        """
        self.chat = chat
        self.mapper = mapper
        self.store = ChatStore(app.db)
        self.jobs = ChatJobs(chat, self.store, mapper=mapper, run_inline=run_inline)

    def register(self, api):
        """Attach the routes to a FastAPI app.

        Args:
            api: the FastAPI application.
        """
        self._register_jobs(api)
        self._register_conversations(api)

    def _register_jobs(self, api):
        """Ask, decide and poll routes."""

        @api.post("/steward/chat/jobs")
        def ask(payload=Body(...)):
            data = payload if isinstance(payload, dict) else {}
            message = str(data.get("message", "")).strip()
            session_id = self._session(data)
            if not message:
                raise HTTPException(status_code=400, detail="'message' is required.")
            if len(message) > self.MAX_MESSAGE:
                raise HTTPException(status_code=400, detail=f"Please keep messages under {self.MAX_MESSAGE} characters.")
            return JSONResponse(status_code=202, content={"status": "ok", "job": self.jobs.ask(message, session_id)})

        @api.post("/steward/chat/decisions")
        def decide(payload=Body(...)):
            data = payload if isinstance(payload, dict) else {}
            if not isinstance(data.get("approve"), bool) or not str(data.get("run_id", "")).strip():
                raise HTTPException(status_code=400, detail="Send 'run_id' and 'approve' (true or false).")
            job = self.jobs.decide(data["run_id"], data["approve"], self._session(data))
            return JSONResponse(status_code=202, content={"status": "ok", "job": job})

        @api.get("/steward/chat/jobs/{job_id}")
        def poll(job_id):
            job = self.jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail=self.GONE)
            return {"status": "ok", "job": job}

    def _register_conversations(self, api):
        """List, open and delete saved conversations."""

        @api.get("/steward/chat/conversations")
        def conversations(limit=30):
            try:
                count = max(1, min(int(limit), 100))
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail="'limit' must be a number.") from exc
            return {"status": "ok", "conversations": self.store.list_conversations(count)}

        @api.get("/steward/chat/conversations/{conversation_id}")
        def conversation(conversation_id):
            return {"status": "ok", "id": conversation_id, "messages": self.store.messages(conversation_id),
                    "active_job": self.jobs.active_for(conversation_id)}

        @api.get("/steward/chat/folder")
        def folder_card(path=""):
            # Fresh numbers for the workspace panel after files were changed
            try:
                card = self.chat.insights.card_for_path(path)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return {"status": "ok", "folder": self.mapper.to_host_deep(card) if self.mapper else card}

        @api.delete("/steward/chat/conversations/{conversation_id}")
        def delete(conversation_id):
            if self.jobs.active_for(conversation_id):
                raise HTTPException(status_code=409, detail="Wait for the current answer before deleting this chat.")
            if not self.store.delete(conversation_id):
                raise HTTPException(status_code=404, detail="Conversation not found.")
            return {"status": "ok"}

    @staticmethod
    def _session(data):
        """Return the conversation id from a request body, or raise a 400."""
        session_id = str(data.get("session_id", "")).strip()
        if not session_id or len(session_id) > 100:
            raise HTTPException(status_code=400, detail="'session_id' is required (up to 100 characters).")
        return session_id
