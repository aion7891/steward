"""API tests for the web frontend routes: dashboard, folder scans, run-now, and safe cleanup."""

import time
from datetime import datetime, timezone

import yaml
from fastapi.testclient import TestClient

from steward.api import StewardAPIServer
from steward.chunker import HashEmbedder
from steward.main import StewardApp
from steward.rag import RAGIndex


class WebApiHelper:
    """Builds a StewardAPIServer (with AgentOS) over a small sample folder."""

    @staticmethod
    def build_client(tmp_path, dry_run=True):
        """Create sample files, a config, the API server and a TestClient."""
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "notes.md").write_text("# Apollo\nLaunch is December 15.", encoding="utf-8")
        (docs / "dup_1.txt").write_text("duplicate content", encoding="utf-8")
        (docs / "dup_2.txt").write_text("duplicate content", encoding="utf-8")
        (docs / "temp.tmp").write_text("scratch", encoding="utf-8")
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.safe_dump({
            "scanner": {"watched_folders": [str(docs)]},
            "safety": {"dry_run": dry_run},
        }), encoding="utf-8")
        app = StewardApp(config_path=cfg_file, base_dir=tmp_path)
        rag = RAGIndex(app.config, embedder=HashEmbedder(dimensions=256), reader=app.reader)
        server = StewardAPIServer(app=app, rag_index=rag)
        return app, server, TestClient(server.fastapi_app), docs

    @staticmethod
    def wait_for_job(client, job_id, timeout=20):
        """Poll a folder-scan job until it finishes (or fail the test on timeout)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = client.get(f"/steward/folders/scan/{job_id}").json()["job"]
            if job["status"] in ("done", "failed"):
                return job
            time.sleep(0.1)
        raise AssertionError(f"Job {job_id} did not finish in {timeout}s")


class TestDashboardRoute:
    """GET /steward/dashboard on empty and populated databases."""

    def test_empty_database_returns_zeros(self, tmp_path):
        """A fresh install shows zero cards, a zero-filled series, and no to-do items."""
        _, _, client, _ = WebApiHelper.build_client(tmp_path)
        body = client.get("/steward/dashboard").json()
        assert body["status"]["files_tracked"] == 0
        assert body["status"]["last_scan_at"] is None
        assert len(body["daily"]) == 14 and all(day["scans"] == 0 for day in body["daily"])
        assert body["todo"] == [] and body["approved_waiting"] == []
        assert body["system"]["dry_run"] is True

    def test_days_must_be_between_1_and_90(self, tmp_path):
        """Out-of-range or non-numeric days give a 400 with a clear message."""
        _, _, client, _ = WebApiHelper.build_client(tmp_path)
        for bad in ("0", "91", "abc"):
            response = client.get(f"/steward/dashboard?days={bad}")
            assert response.status_code == 400 and "days" in response.json()["detail"]
        assert len(client.get("/steward/dashboard?days=7").json()["daily"]) == 7
        # The browser's time-zone offset is validated too
        assert client.get("/steward/dashboard?tz_offset=abc").status_code == 400
        assert client.get("/steward/dashboard?tz_offset=-330").status_code == 200

    def test_stats_and_todo_after_a_scan(self, tmp_path):
        """After a scan, today's row, the status cards and the to-do list are filled."""
        app, _, client, docs = WebApiHelper.build_client(tmp_path)
        app.scanner.scan_all()
        app.organizer.propose_action("delete", str(docs / "temp.tmp"), reason="Temp cleanup")
        body = client.get("/steward/dashboard").json()
        today = datetime.now(timezone.utc).date().isoformat()
        assert body["daily"][-1]["date"] == today and body["daily"][-1]["scans"] == 1
        assert body["status"]["files_tracked"] == 4 and body["status"]["scans_today"] == 1
        # Exact byte counts let the UI show small files as "7 B" instead of "0 B"
        assert body["status"]["total_size_bytes"] == sum(c["size_bytes"] for c in body["categories"]) > 0
        assert body["status"]["pending_actions"] == 1
        assert body["todo"][0]["size_bytes"] == len("scratch")
        assert {s["kind"] for s in body["suggestions"]} >= {"deduplicate", "clean_temp"}


class TestFolderScanRoutes:
    """Folder roots, starting and polling scans, and input errors."""

    def test_scan_folder_end_to_end(self, tmp_path):
        """POST starts a job (202); polling returns findings, suggestions and proposals."""
        app, _, client, docs = WebApiHelper.build_client(tmp_path)
        roots = client.get("/steward/folders/roots").json()
        assert roots["in_docker"] is False and roots["roots"][0]["available"] is True
        started = client.post("/steward/folders/scan", json={"path": str(docs), "create_proposals": "true"})
        assert started.status_code == 202
        job = WebApiHelper.wait_for_job(client, started.json()["job"]["id"])
        assert job["status"] == "done", job["error"]
        assert job["result"]["findings"]["duplicates"]["count"] == 1
        assert len(job["result"]["proposals"]["created"]) == 2  # temp + extra duplicate
        assert {a["status"] for a in app.organizer.list_actions()} == {"proposed"}
        assert client.get("/steward/folders/scans").json()["jobs"][0]["status"] == "done"

    def test_bad_paths_and_unknown_jobs(self, tmp_path):
        """Invalid folders give 400 with a message; unknown job ids give 404."""
        _, _, client, docs = WebApiHelper.build_client(tmp_path)
        for payload in ({}, {"path": ""}, {"path": "not/absolute"}, {"path": str(docs / "nope")}, {"path": "/"}):
            response = client.post("/steward/folders/scan", json=payload)
            assert response.status_code == 400 and response.json()["detail"]
        assert client.get("/steward/folders/scan/doesnotexist").status_code == 404


class TestRunNowAndCleanup:
    """POST /steward/actions/{id}/execute and the fixed CleanupWorkflow."""

    def test_approve_in_dry_run_then_run_now(self, tmp_path):
        """A dry-run approval waits on the dashboard; run-now executes it; errors are clear."""
        app, _, client, docs = WebApiHelper.build_client(tmp_path)
        prop = app.organizer.propose_action("delete", str(docs / "temp.tmp"), reason="Temp cleanup")
        preview = client.post(f"/steward/actions/{prop['id']}/approve", json={"execute": True, "dry_run": True})
        assert preview.json()["status"] == "dry_run" and (docs / "temp.tmp").exists()
        waiting = client.get("/steward/dashboard").json()
        assert waiting["status"]["approved_waiting"] == 1 and waiting["approved_waiting"][0]["id"] == prop["id"]
        done = client.post(f"/steward/actions/{prop['id']}/execute", json={"dry_run": "false"})
        assert done.json()["status"] == "done" and not (docs / "temp.tmp").exists()
        assert client.post(f"/steward/actions/{prop['id']}/execute", json={}).json()["status"] == "error"
        assert client.post("/steward/actions/9999/execute", json={}).status_code == 404
        assert client.post("/steward/actions/abc/execute", json={}).status_code == 400

    def test_cleanup_workflow_only_proposes_and_never_repeats(self, tmp_path):
        """Two cleanup runs create proposals once; none of them is approved by the system."""
        app, server, _, _ = WebApiHelper.build_client(tmp_path)
        app.scanner.scan_all()
        first = server.workflows.run_workflow("cleanup").content
        second = server.workflows.run_workflow("cleanup").content
        assert first["proposals_count"] == 2
        assert second["proposals_count"] == 0 and second["already_open"] == 2
        statuses = [a["status"] for a in app.organizer.list_actions()]
        assert statuses == ["proposed", "proposed"]


class FakeRun:
    """Stands in for an Agno run result: content plus a run status."""

    def __init__(self, content, status):
        self.content = content
        self.status = status


class TestChatStatus:
    """POST /steward/chat reports model errors and approval pauses honestly."""

    def test_chat_maps_run_status_to_api_status(self, tmp_path, monkeypatch):
        """ERROR runs become 'error', COMPLETED runs 'ok'; a pause with no approval step is an error.

        (Pauses WITH approval steps are covered in tests/test_chat_approvals.py.)
        """
        from agno.run.base import RunStatus

        _, server, client, _ = WebApiHelper.build_client(tmp_path)
        cases = [
            (FakeRun("Failed to connect to Ollama.", RunStatus.error), "error", "Failed to connect to Ollama."),
            (FakeRun("Team run paused.", RunStatus.paused), "error", "The AI paused for input Steward cannot collect in chat yet."),
            (FakeRun("Launch is December 15.", RunStatus.completed), "ok", "Launch is December 15."),
        ]
        for run, expected, reply in cases:
            monkeypatch.setattr(server.agents.team, "run", lambda message, run=run, **kwargs: run)
            body = client.post("/steward/chat", json={"message": "When is the Apollo launch?"}).json()
            assert body["status"] == expected and body["reply"] == reply
            if expected != "ok":
                assert body["sources"] == []
        assert client.post("/steward/chat", json={"message": "  "}).status_code == 400
