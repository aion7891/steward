"""A small pool of worker threads for chat jobs: different chats answer at the same time."""

import queue
import threading


class ChatWorkers:
    """Runs jobs on a few threads; jobs of the same chat still run one after another.

    One chat must stay in order (an answer, then the decision on its approval card), but a second
    chat should not wait for the first. Each chat gets its own lock; the pool has `count` threads.
    """

    def __init__(self, run, count=2):
        """Start the worker threads.

        Args:
            run: function(job) that answers one job (a dict with "session_id"); must not raise.
            count: how many answers may run at the same time.
        """
        self.run = run
        self.queue = queue.Queue()
        self.locks = {}
        self.guard = threading.Lock()
        for number in range(int(count)):
            threading.Thread(target=self._work, name=f"steward-chat-{number + 1}", daemon=True).start()

    def submit(self, job):
        """Queue a job; a free worker picks it up.

        Args:
            job: the job dict.
        """
        self.queue.put(job)

    def lock_for(self, session_id):
        """Return the lock of one chat (created on first use).

        Args:
            session_id: the conversation id.
        """
        with self.guard:
            return self.locks.setdefault(session_id, threading.Lock())

    def _work(self):
        """Worker thread: answer jobs forever, keeping each chat in order."""
        while True:
            job = self.queue.get()
            with self.lock_for(job["session_id"]):
                self.run(job)
