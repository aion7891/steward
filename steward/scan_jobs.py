"""Background "scan this folder" jobs with step-by-step progress for the web UI."""

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from steward.scan_job_store import ScanJobStore


class ScanBusyError(Exception):
    """Raised when a folder scan is requested while another one is still running."""


class FolderScanJobs:
    """Runs one folder scan at a time in a background thread and tracks its progress.

    Steps: scanning -> indexing (optional) -> analyzing -> proposing (optional) -> done.
    Only one job runs at a time, so SQLite never gets two big scans writing at once.
    """

    MAX_JOBS_KEPT = 20

    def __init__(self, app, advisor, mapper, logger=None, run_inline=False, store=None):
        """Store services and the in-memory job registry.

        Args:
            app: StewardApp (scanner, db, RAG index).
            advisor: FolderAdvisor that builds findings, suggestions and proposals.
            mapper: PathMapper that validates the folder typed by the user.
            logger: optional logger.
            run_inline: run jobs in the calling thread (used by tests).
            store: optional ScanJobStore (SQLite history, built from app.db when omitted).
        """
        self.app = app
        self.advisor = advisor
        self.mapper = mapper
        self.logger = logger or app.logger
        self.run_inline = run_inline
        self.jobs = {}
        self.lock = threading.Lock()
        # Finished jobs are also saved in SQLite so results survive an API restart
        self.store = store or ScanJobStore(app.db)

    def start(self, raw_path, create_proposals=True, index_for_chat=False):
        """Validate the folder, register a job and start it. Returns the job dict.

        Args:
            raw_path: folder typed by the user.
            create_proposals: also create 'proposed' cleanup actions.
            index_for_chat: also add the folder's documents to the chat search index.
        """
        folder = self.mapper.resolve(raw_path)  # raises ValueError with a friendly message
        with self.lock:
            if any(job["status"] in ("queued", "running") for job in self.jobs.values()):
                raise ScanBusyError("A folder scan is already running. Please wait for it to finish.")
            job = self._new_job(raw_path, folder, bool(create_proposals), bool(index_for_chat))
            self.jobs[job["id"]] = job
            self._trim_history()
        self.store.save(job)
        if self.run_inline:
            self._run(job)
        else:
            threading.Thread(target=self._run, args=(job,), daemon=True, name=f"scan-{job['id']}").start()
        return self.get(job["id"])

    def get(self, job_id):
        """Return a copy of one job, or None if the id is unknown.

        Args:
            job_id: the id returned by start().
        """
        with self.lock:
            job = self.jobs.get(str(job_id))
            if job:
                return dict(job)
        return self.store.get(job_id)

    def list_recent(self, limit=10):
        """Return the most recent jobs (newest first) without their full results."""
        with self.lock:
            merged = {job["id"]: dict(job) for job in self.jobs.values()}
        for job in self.store.list_recent(limit):
            merged.setdefault(job["id"], job)  # live jobs in memory win over saved copies
        jobs = sorted(merged.values(), key=lambda j: j["created_at"], reverse=True)[: int(limit)]
        return [{k: v for k, v in job.items() if k != "result"} for job in jobs]

    def _run(self, job):
        """Execute every step of one job, recording progress and any error."""
        folder = Path(job["folder"])
        try:
            self._step(job, "scanning", 10)
            scan = self.app.scanner.scan_all(folders=[str(folder)])
            result = {"scan": {key: scan.get(key, 0) for key in
                               ("files_seen", "hashed_files", "unchanged_files", "errors")}}
            if job["options"]["index_for_chat"]:
                self._step(job, "indexing", 35)
                result["index"] = self._index_folder(folder)
            self._step(job, "analyzing", 65)
            findings = self.advisor.findings_for(folder)
            result["findings"] = self.advisor.summarize(findings)
            result.update(self.advisor.suggestions_for(folder, findings))
            if job["options"]["create_proposals"]:
                self._step(job, "proposing", 85)
                result["proposals"] = self.advisor.create_proposals(findings)
            result["protected"] = self.app.config.is_protected_path(folder)
            self._finish(job, "done", result=result)
        except Exception as exc:  # a failed job must never crash the API process
            self.logger.warning(f"Folder scan {job['id']} failed: {exc}")
            self._finish(job, "failed", error=str(exc))

    def _index_folder(self, folder):
        """Add supported documents inside folder to the RAG index (unchanged files are skipped)."""
        rag = self.app.get_rag_index()
        summary = {"indexed": 0, "skipped": 0, "errors": 0}
        for record in self.app.db.list_files():
            path = Path(record["path"])
            if record.get("is_temp") or not (path == folder or folder in path.parents):
                continue
            status = rag.index_file(path, content_hash=record.get("sha256") or None, db=self.app.db)["status"]
            key = "indexed" if status == "indexed" else ("errors" if status == "error" else "skipped")
            summary[key] += 1
        return summary

    def _new_job(self, raw_path, folder, create_proposals, index_for_chat):
        """Build the initial job record."""
        now = datetime.now(timezone.utc).isoformat()
        return {
            "id": uuid.uuid4().hex[:12], "status": "queued", "step": "queued", "progress": 0,
            "input_path": str(raw_path), "folder": str(folder),
            "display_path": self.mapper.to_host(folder),
            "options": {"create_proposals": create_proposals, "index_for_chat": index_for_chat},
            "created_at": now, "started_at": None, "finished_at": None, "error": None, "result": None,
        }

    def _step(self, job, step, progress):
        """Move a job to its next step."""
        with self.lock:
            job.update({"status": "running", "step": step, "progress": progress})
            job["started_at"] = job["started_at"] or datetime.now(timezone.utc).isoformat()

    def _finish(self, job, status, result=None, error=None):
        """Mark a job as done or failed."""
        with self.lock:
            job.update({"status": status, "step": status, "result": result, "error": error,
                        "progress": 100 if status == "done" else job["progress"],
                        "finished_at": datetime.now(timezone.utc).isoformat()})
            snapshot = dict(job)
        self.store.save(snapshot)

    def _trim_history(self):
        """Forget the oldest finished jobs so memory stays small."""
        finished = sorted((j for j in self.jobs.values() if j["status"] in ("done", "failed")),
                          key=lambda j: j["created_at"])
        for job in finished[: max(0, len(self.jobs) - self.MAX_JOBS_KEPT)]:
            self.jobs.pop(job["id"], None)
