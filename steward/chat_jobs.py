"""Runs chat questions in the background so the browser can leave, come back and still get the answer."""

import queue
import threading
import time
import uuid
from datetime import datetime, timezone

from agno.team import Team

from steward.chat_commands import ChatCommands
from steward.chat_memory import ChatMemory
from steward.chat_steps import ChatSteps


class ChatStopped(BaseException):
    """Raised between AI events to end a job early (BaseException, so no "except Exception" hides it)."""


class ChatJobs:
    """A queue of chat jobs answered one at a time by a single worker thread.

    A local model can only answer one question at a time anyway. Each job records its live
    steps (ChatSteps), and its question and answer are saved in the ChatStore, so the
    conversation survives tab switches, reloads and restarts. A job is
    {"id", "kind", "session_id", "status" ("queued"|"running"|"done"), "stopping", "steps",
    "thinking", "result", "created_at"}. A job can be stopped, and stops itself after MAX_SECONDS.
    """

    MAX_JOBS = 50
    MAX_SECONDS = 300
    STOPPED = {
        "user": "Stopped. Steward did not finish this answer.",
        "timeout": "Stopped after 5 minutes without an answer. Try a shorter or more specific question.",
    }

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
        self.max_seconds = self.MAX_SECONDS
        self.commands = ChatCommands(store, lambda: chat.agents.organizer_tools)
        self.memory = ChatMemory(store, lambda action_id: chat.agents.organizer_tools.organizer.get_action(action_id), mapper)
        self.jobs = {}
        self.lock = threading.Lock()
        self.queue = queue.Queue()
        if not run_inline:
            threading.Thread(target=self._work, name="steward-chat-jobs", daemon=True).start()

    def ask(self, message, session_id):
        """Queue a question; the question is saved at once, the answer when it is ready.

        A typed "no" while an approval card waits rejects that card, and "undo that" undoes the
        last change from this chat, without depending on the AI to understand them.

        Args:
            message: the user's question (already checked to be non-empty).
            session_id: the browser's conversation id.
        """
        self.store.add_message(session_id, "user", message)
        command = self.commands.classify(message)
        run_id = self.store.pending_approval(session_id) if command == "reject" else None
        if run_id:
            self.store.set_decision(run_id, "rejected")
            return self._start({"kind": "decision", "run_id": run_id, "approve": False,
                                "session_id": session_id, "typed": True})
        if command == "undo":
            return self._start({"kind": "undo", "session_id": session_id})
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
        """Return a job as the browser sees it, or None when unknown (for example after a restart)."""
        with self.lock:
            job = self.jobs.get(str(job_id))
            return self._view(job) if job else None

    def stop(self, job_id):
        """Ask a queued or running job to stop; return its view, or None when unknown.

        File changes already made stay made (they can be undone); the job ends at the next AI event.

        Args:
            job_id: id returned by ask() or decide().
        """
        with self.lock:
            job = self.jobs.get(str(job_id))
        if job is None:
            return None
        if job["status"] != "done":
            job["stop"] = "user"
            if job.get("run_id"):
                Team.cancel_run(job["run_id"])  # also tells Agno, which stops at its next check
        return self.get(job_id)

    def busy(self):
        """Return True while any chat answer is queued or running."""
        with self.lock:
            return any(job["status"] in ("queued", "running") for job in self.jobs.values())

    def active_for(self, session_id):
        """Return the queued or running job of a conversation (session_id), or None."""
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
            self._run(self.queue.get())

    def _run(self, job):
        """Answer one job, record its steps and save the answer (never raises)."""
        job["status"] = "running"
        recorder, started = job["recorder"], time.time()
        tools = self.chat.agents.organizer_tools
        tools.progress, tools.done_actions = recorder.progress, []  # live "3/14"; changes for "undo that"
        try:
            result = self._answer(job, self._listener(job, started))
        except ChatStopped as stop:
            result = {"status": "stopped", "reply": self.STOPPED[stop.args[0]], "sources": []}
        except KeyError as exc:
            result = {"status": "error", "reply": str(exc.args[0]), "sources": []}
        except Exception as exc:  # a failed answer must never stop the worker thread
            result = {"status": "error", "reply": f"Steward could not answer: {exc}", "sources": []}
        finally:
            tools.progress, actions, tools.done_actions = None, tools.done_actions, None
        result = {**result, "steps": recorder.finish(), "duration_sec": round(time.time() - started, 1)}
        if actions:
            result["actions"] = actions
        if job.get("typed"):
            result["decided_run_id"] = job["run_id"]  # the browser marks that card "rejected"
        result = self.mapper.to_host_deep(result) if self.mapper is not None else result
        self.store.add_message(job["session_id"], "assistant", result.get("reply", ""), result)
        job.update(status="done", result=result)

    def _answer(self, job, listener):
        """Run the job's question, decision or undo and return the chat reply."""
        if job.get("stop"):
            raise ChatStopped(job["stop"])  # stopped while still waiting in the queue
        if job["kind"] == "message":  # with Steward's notes on this chat, so "it" means the right thing
            message = self.memory.with_context(job["session_id"], job["message"])
            return self.chat.answer(message, job["session_id"], listener=listener)
        if job["kind"] == "undo":
            return self.commands.undo(job["session_id"])
        return self.chat.decide(job["run_id"], job["approve"], listener=listener)

    def _listener(self, job, started):
        """Return the function that receives the AI's events: records steps, honours Stop and the time limit."""
        def listen(event):
            if job.get("run_id") is None:
                job["run_id"] = getattr(event, "run_id", None)
            if not job.get("stop") and time.time() - started > self.max_seconds:
                job["stop"] = "timeout"
            if job.get("stop"):
                raise ChatStopped(job["stop"])
            job["recorder"].handle(event)
        return listen

    def _view(self, job):
        """Return the browser's view of a job: no internals, live steps, Mac paths."""
        live = job["recorder"].snapshot()
        view = {key: job.get(key) for key in ("id", "kind", "session_id", "status", "result", "created_at")}
        view.update(steps=live["steps"], thinking=live["thinking"], stopping=bool(job.get("stop")))
        return self.mapper.to_host_deep(view) if self.mapper is not None else view
