"""Runs chat questions in the background so the browser can leave, come back and still get the answer."""

import queue
import threading
import time
import uuid
from datetime import datetime, timezone

from steward.chat_steps import ChatSteps


class ChatJobs:
    """A queue of chat jobs answered one at a time by a single worker thread.

    A local model can only answer one question at a time anyway. Each job records its live
    steps (ChatSteps), and its question and answer are saved in the ChatStore, so the
    conversation survives tab switches, reloads and restarts. A job is
    {"id", "kind", "session_id", "status" ("queued"|"running"|"done"), "steps", "thinking",
    "result", "created_at"}.
    """

    MAX_JOBS = 50

    def __init__(self, chat, store, mapper=None, run_inline=False):
        """Create the queue (and the worker thread unless run_inline).

        Args:
            chat: ChatService that answers questions and decisions.
            store: ChatStore that saves the conversation.
            mapper: optional PathMapper; paths in steps and answers are shown as Mac paths.
            run_inline: answer inside start() instead of a thread (used by tests).
        """
        self.chat = chat
        self.store = store
        self.mapper = mapper
        self.run_inline = run_inline
        self.jobs = {}
        self.lock = threading.Lock()
        self.queue = queue.Queue()
        if not run_inline:
            threading.Thread(target=self._work, name="steward-chat-jobs", daemon=True).start()

    def ask(self, message, session_id):
        """Queue a question; the question is saved at once, the answer when it is ready.

        Args:
            message: the user's question (already checked to be non-empty).
            session_id: the browser's conversation id.
        """
        self.store.add_message(session_id, "user", message)
        return self._start({"kind": "message", "message": message, "session_id": session_id})

    def decide(self, run_id, approve, session_id):
        """Queue an approve/reject decision for an approval card.

        Args:
            run_id: id from the approval card.
            approve: True to allow the file changes, False to refuse them.
            session_id: the browser's conversation id.
        """
        self.store.set_decision(run_id, "approved" if approve else "rejected")
        return self._start({"kind": "decision", "run_id": str(run_id), "approve": bool(approve), "session_id": session_id})

    def get(self, job_id):
        """Return a job as the browser sees it, or None when unknown (for example after a restart).

        Args:
            job_id: id returned by ask() or decide().
        """
        with self.lock:
            job = self.jobs.get(str(job_id))
            return self._view(job) if job else None

    def active_for(self, session_id):
        """Return the queued or running job of a conversation, or None.

        Args:
            session_id: the browser's conversation id.
        """
        with self.lock:
            for job in reversed(list(self.jobs.values())):
                if job["session_id"] == session_id and job["status"] in ("queued", "running"):
                    return self._view(job)
        return None

    def _start(self, fields):
        """Create a job, queue it (or run it now in inline mode) and return its view."""
        job = {**fields, "id": uuid.uuid4().hex, "status": "queued", "result": None,
               "created_at": datetime.now(timezone.utc).isoformat(), "recorder": ChatSteps()}
        with self.lock:
            self.jobs[job["id"]] = job
            while len(self.jobs) > self.MAX_JOBS:
                self.jobs.pop(next(iter(self.jobs)))  # forget the oldest
        if self.run_inline:
            self._run(job)
        else:
            self.queue.put(job)
        return self.get(job["id"])

    def _work(self):
        """Worker thread: answer queued jobs one after another, forever."""
        while True:
            job = self.queue.get()
            self._run(job)

    def _run(self, job):
        """Answer one job, record its steps and save the answer (never raises)."""
        job["status"] = "running"
        recorder, started = job["recorder"], time.time()
        tools = self.chat.agents.organizer_tools
        tools.progress = recorder.progress  # "archiving 3/14" appears on the running step
        try:
            if job["kind"] == "message":
                result = self.chat.answer(job["message"], job["session_id"], listener=recorder.handle)
            else:
                result = self.chat.decide(job["run_id"], job["approve"], listener=recorder.handle)
        except KeyError as exc:
            result = {"status": "error", "reply": str(exc.args[0]), "sources": []}
        except Exception as exc:  # a failed answer must never stop the worker thread
            result = {"status": "error", "reply": f"Steward could not answer: {exc}", "sources": []}
        finally:
            tools.progress = None
        result = {**result, "steps": recorder.finish(), "duration_sec": round(time.time() - started, 1)}
        result = self.mapper.to_host_deep(result) if self.mapper is not None else result
        self.store.add_message(job["session_id"], "assistant", result.get("reply", ""), result)
        job.update(status="done", result=result)

    def _view(self, job):
        """Return the browser's view of a job: no internals, live steps, Mac paths."""
        live = job["recorder"].snapshot()
        view = {key: job.get(key) for key in ("id", "kind", "session_id", "status", "result", "created_at")}
        view.update(steps=live["steps"], thinking=live["thinking"])
        return self.mapper.to_host_deep(view) if self.mapper is not None else view
