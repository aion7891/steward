"""HTTP routes used by the web frontend: dashboard stats and "scan a folder" jobs."""

from fastapi import Body, HTTPException

from steward.dashboard import DashboardService
from steward.folder_advisor import FolderAdvisor
from steward.path_mapper import PathMapper
from steward.scan_jobs import FolderScanJobs, ScanBusyError


class WebRoutes:
    """Builds the dashboard and folder-scan services and registers their routes."""

    def __init__(self, app, mapper=None, run_inline=False):
        """Create the services shared by the web routes.

        Args:
            app: StewardApp with all core services.
            mapper: optional PathMapper (built from the environment when omitted).
            run_inline: run folder scans synchronously (used by tests).
        """
        self.app = app
        self.mapper = mapper or PathMapper(app.config)
        self.advisor = FolderAdvisor(app)
        self.dashboard = DashboardService(app, self.advisor)
        self.jobs = FolderScanJobs(app, self.advisor, self.mapper, run_inline=run_inline)

    def register(self, api):
        """Attach all web routes to a FastAPI app.

        Args:
            api: the FastAPI application (the AgentOS base app).
        """
        self._register_dashboard(api)
        self._register_folder_scan(api)

    def _register_dashboard(self, api):
        """GET /steward/dashboard: stats, daily series, to-do and suggestions."""

        @api.get("/steward/dashboard")
        def dashboard(days=14):
            try:
                return {"status": "ok", **self.dashboard.summary(days=days)}
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    def _register_folder_scan(self, api):
        """Folder roots, start a scan job, poll a job and list recent jobs."""

        @api.get("/steward/folders/roots")
        def folder_roots():
            return {"status": "ok", "in_docker": self.mapper.in_docker, "roots": self.mapper.list_roots()}

        @api.post("/steward/folders/scan", status_code=202)
        def start_folder_scan(payload=Body(default=None)):
            data = payload or {}
            try:
                job = self.jobs.start(
                    data.get("path", ""),
                    create_proposals=self._as_bool(data.get("create_proposals", True)),
                    index_for_chat=self._as_bool(data.get("index_for_chat", False)),
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except ScanBusyError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return {"status": "ok", "job": job}

        @api.get("/steward/folders/scan/{job_id}")
        def folder_scan_status(job_id):
            job = self.jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail=f"Unknown scan job: {job_id}")
            return {"status": "ok", "job": job}

        @api.get("/steward/folders/scans")
        def recent_folder_scans(limit=10):
            return {"status": "ok", "jobs": self.jobs.list_recent(limit=int(limit))}

    @staticmethod
    def _as_bool(value):
        """Read true/false from JSON booleans or strings like "false" safely."""
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)
