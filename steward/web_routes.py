"""HTTP routes used by the web frontend: dashboard stats and "scan a folder" jobs."""

from fastapi import Body, HTTPException
from fastapi.responses import FileResponse

from steward.config import AppConfig
from steward.dashboard import DashboardService
from steward.folder_advisor import FolderAdvisor
from steward.ollama_models import OllamaModels
from steward.path_mapper import PathMapper
from steward.report_service import ReportService
from steward.scan_jobs import FolderScanJobs, ScanBusyError
from steward.settings_service import SettingsService


class WebRoutes:
    """Builds the dashboard and folder-scan services and registers their routes."""

    def __init__(self, app, mapper=None, run_inline=False, on_model_change=None):
        """Create the services shared by the web routes.

        Args:
            app: StewardApp with all core services.
            mapper: optional PathMapper (built from the environment when omitted).
            run_inline: run folder scans synchronously (used by tests).
            on_model_change: called after Settings changed the chat model (rebuilds agents).
        """
        self.app = app
        self.mapper = mapper or PathMapper(app.config)
        self.advisor = FolderAdvisor(app)
        self.dashboard = DashboardService(app, self.advisor)
        self.jobs = FolderScanJobs(app, self.advisor, self.mapper, run_inline=run_inline)
        self.ollama = OllamaModels(app.config.get("models.host"))
        self.settings = SettingsService(app.config, self.mapper, self.ollama, on_model_change)
        self.reports = ReportService(app)

    def register(self, api):
        """Attach all web routes to a FastAPI app.

        Args:
            api: the FastAPI application (the AgentOS base app).
        """
        self._register_dashboard(api)
        self._register_folder_scan(api)
        self._register_execute(api)
        self._register_settings(api)
        self._register_reports(api)

    def _register_execute(self, api):
        """POST /steward/actions/{id}/execute: run an action that is already approved.

        Approving while dry-run is on only previews the action and leaves it 'approved'.
        This route lets the user run it for real later, without approving it twice.
        """

        @api.post("/steward/actions/{action_id}/execute")
        def execute_action(action_id, payload=Body(default=None)):
            data = payload or {}
            dry_run = None if data.get("dry_run") is None else self._as_bool(data["dry_run"])
            try:
                result = self.app.organizer.execute_action(int(action_id), dry_run=dry_run)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="action_id must be a number.") from exc
            if result["status"] == "not_found":
                raise HTTPException(status_code=404, detail=result["message"])
            return result

    def _register_dashboard(self, api):
        """GET /steward/dashboard: stats, daily series, to-do and suggestions."""

        @api.get("/steward/dashboard")
        def dashboard(days=14, tz_offset=0):
            try:
                return {"status": "ok", **self.mapper.to_host_deep(self.dashboard.summary(days=days, tz_offset=tz_offset))}
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
            return {"status": "ok", "job": self.mapper.to_host_deep(job)}

        @api.get("/steward/folders/scan/{job_id}")
        def folder_scan_status(job_id):
            job = self.jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail=f"Unknown scan job: {job_id}")
            return {"status": "ok", "job": self.mapper.to_host_deep(job)}

        @api.get("/steward/folders/scans")
        def recent_folder_scans(limit=10):
            return {"status": "ok", "jobs": self.mapper.to_host_deep(self.jobs.list_recent(limit=int(limit)))}

    def _register_settings(self, api):
        """GET/PUT /steward/settings and GET /steward/models (installed Ollama models)."""

        @api.get("/steward/settings")
        def get_settings():
            return self.settings.current()

        @api.put("/steward/settings")
        def update_settings(payload=Body(...)):
            try:
                return self.settings.update(payload)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        @api.get("/steward/models")
        def list_models():
            return {"status": "ok", "providers": list(AppConfig.VALID_PROVIDERS), "ollama": self.ollama.list_models()}

    def _register_reports(self, api):
        """Report library, generate now, delete one report, read one report, download one report file."""

        @api.get("/steward/reports/library")  # registered before /{report_id} on purpose
        def report_library(limit=30):
            return {"status": "ok", "reports": self.reports.library(limit=int(limit))}

        @api.post("/steward/reports/generate")
        def generate_report(payload=Body(default=None)):
            try:
                return self.reports.generate((payload or {}).get("period", "weekly"))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        @api.delete("/steward/reports/library/{key}")
        def delete_report(key):
            return self._report_call(self.reports.delete, key)

        @api.get("/steward/reports/{report_id}")
        def read_report(report_id):
            return {"status": "ok", "report": self._report_call(self.reports.read, report_id)}

        @api.get("/steward/reports/{report_id}/download")
        def download_report(report_id):
            path, media_type, name = self._report_call(self.reports.file_for_download, report_id)
            return FileResponse(path, media_type=media_type, filename=name)

    @staticmethod
    def _report_call(method, report_id):
        """Run a ReportService lookup and turn its errors into 404 / 400 responses."""
        try:
            return method(report_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @staticmethod
    def _as_bool(value):
        """Read true/false from JSON booleans or strings like "false" safely."""
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)
