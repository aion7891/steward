"""Background scheduler and Downloads watcher worker for continuous operation."""

import os
import signal
import time

from apscheduler.schedulers.background import BackgroundScheduler

from steward.main import StewardApp


class StewardWorker:
    """Runs periodic Scan, Cleanup, and Report workflows plus the real-time Downloads watcher."""

    DAY_MAP = {
        "monday": "mon", "tuesday": "tue", "wednesday": "wed", "thursday": "thu",
        "friday": "fri", "saturday": "sat", "sunday": "sun",
    }

    def __init__(self, app=None, config_path=None, rag_index=None, enable_watcher=True):
        """Initialize the APScheduler instance and wire Steward workflows."""
        self.app = app or StewardApp(config_path=config_path)
        self.rag_index = rag_index
        self.workflows = self.app.get_workflows(rag_index=rag_index)
        self.logger = self.app.logger_factory.get_logger("worker") if hasattr(self.app, "logger_factory") else self.app.logger
        self.enable_watcher = enable_watcher
        self.scheduler = BackgroundScheduler()
        self._running = False
        self._register_jobs()

    def _register_jobs(self):
        """Schedule ScanWorkflow, CleanupWorkflow, and ReportWorkflow from config.yaml."""
        scan_mins = max(1, int(self.app.config.get("scheduler.scan_interval_minutes", 60)))
        cleanup_hrs = max(1, int(self.app.config.get("scheduler.cleanup_interval_hours", 24)))
        report_day = self.DAY_MAP.get(
            str(self.app.config.get("scheduler.report_day", "sunday")).lower(), "sun"
        )

        self.scheduler.add_job(
            self.run_scan_job, "interval", minutes=scan_mins, id="steward_scan", replace_existing=True
        )
        self.scheduler.add_job(
            self.run_cleanup_job, "interval", hours=cleanup_hrs, id="steward_cleanup", replace_existing=True
        )
        self.scheduler.add_job(
            self.run_report_job, "cron", day_of_week=report_day, hour=9, minute=0,
            id="steward_report", replace_existing=True,
        )

    def run_scan_job(self):
        """Execute software scan + deterministic ScanWorkflow safely."""
        self._log_info("Scheduled ScanWorkflow starting.")
        try:
            # Pick up folders changed in the web UI's Settings page since the worker started
            self.app.config.load_ui_overrides()
            self.app.software_detector.detect_and_save()
            return self.workflows.run_workflow("scan")
        except Exception as exc:
            self._log_warning(f"Scheduled ScanWorkflow error: {exc}")
            return None

    def run_cleanup_job(self):
        """Execute CleanupWorkflow to generate safe dry-run proposals."""
        self._log_info("Scheduled CleanupWorkflow starting.")
        try:
            return self.workflows.run_workflow("cleanup")
        except Exception as exc:
            self._log_warning(f"Scheduled CleanupWorkflow error: {exc}")
            return None

    def run_report_job(self):
        """Execute ReportWorkflow generating both Markdown and HTML reports."""
        self._log_info("Scheduled ReportWorkflow starting.")
        try:
            return self.workflows.run_workflow(
                "report", additional_data={"period": "weekly", "output_format": "both"}
            )
        except Exception as exc:
            self._log_warning(f"Scheduled ReportWorkflow error: {exc}")
            return None

    def run_once(self):
        """Run one full cycle (scan -> cleanup -> report) immediately for tests or CLI."""
        return {
            "scan": self.run_scan_job(),
            "cleanup": self.run_cleanup_job(),
            "report": self.run_report_job(),
        }

    def list_jobs(self):
        """Return metadata for all registered APScheduler jobs."""
        return [{"id": job.id, "trigger": str(job.trigger)} for job in self.scheduler.get_jobs()]

    def start(self):
        """Start APScheduler and the optional real-time Downloads watcher."""
        if not self.scheduler.running:
            self.scheduler.start()
        if self.enable_watcher and self.app.downloads_watcher.watch_dir.exists():
            self.app.downloads_watcher.start()
        self._running = True
        self._log_info(f"StewardWorker started with {len(self.scheduler.get_jobs())} scheduled job(s).")

    def stop(self):
        """Shut down APScheduler and DownloadsWatcher cleanly."""
        self._running = False
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        self.app.downloads_watcher.stop()
        self._log_info("StewardWorker stopped cleanly.")

    def run_forever(self, poll_seconds=1.0):
        """Start background jobs and block until SIGINT or SIGTERM arrives."""
        def _handle_signal(signum, frame):
            self._running = False

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
        self.start()
        try:
            while self._running:
                time.sleep(poll_seconds)
        finally:
            self.stop()

    def _log_info(self, message):
        """Write an informational log message when a logger is attached."""
        if self.logger is not None:
            self.logger.info(message)

    def _log_warning(self, message):
        """Write a warning log message when a logger is attached."""
        if self.logger is not None:
            self.logger.warning(message)


def main():
    """Entry point for running the background worker container (`python -m steward.worker`)."""
    cfg_path = os.getenv("STEWARD_CONFIG_PATH")
    worker = StewardWorker(config_path=cfg_path)
    worker.run_forever()


if __name__ == "__main__":
    main()
