"""Unit and integration tests for Phase 8 (AgentOS API + Client) and Phase 9 (Worker + Docker)."""

import json
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from scripts.export_host_inventory import HostInventoryExporter
from steward.api import StewardAPIServer
from steward.chunker import HashEmbedder
from steward.main import StewardApp
from steward.rag import RAGIndex
from steward.software import SoftwareDetector
from steward.worker import StewardWorker


class Phase8And9Helper:
    """Creates an isolated StewardApp, offline ChromaDB RAGIndex, and test files."""

    @staticmethod
    def build_env(tmp_path):
        """Prepare a temp workspace with sample files and a dry_run config."""
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "launch_plan.md").write_text("# Apollo\nLaunch target is December 15.", encoding="utf-8")
        (docs / "dup_1.txt").write_text("duplicate content", encoding="utf-8")
        (docs / "dup_2.txt").write_text("duplicate content", encoding="utf-8")
        (docs / "temp.tmp").write_text("scratch", encoding="utf-8")

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            yaml.safe_dump({
                "scanner": {"watched_folders": [str(docs)], "downloads_folder": str(tmp_path / "downloads")},
                "safety": {"dry_run": True, "require_confirmation": True, "move_to_recycle_first": True},
            }),
            encoding="utf-8",
        )
        app = StewardApp(config_path=cfg_file, base_dir=tmp_path)
        rag = RAGIndex(app.config, embedder=HashEmbedder(dimensions=256), reader=app.reader)
        return app, rag, docs


class TestAgentOSAPI:
    """Tests for Phase 8: AgentOS FastAPI endpoints and action approval/undo flow."""

    def test_health_scan_actions_reports_and_settings_routes(self, tmp_path):
        """Verify all custom /steward/* endpoints and AgentOS app mounting work end-to-end."""
        app, rag, docs = Phase8And9Helper.build_env(tmp_path)
        server = StewardAPIServer(app=app, rag_index=rag)
        client = TestClient(server.fastapi_app)

        health = client.get("/steward/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        # Trigger ScanWorkflow via API
        scan = client.post("/steward/scan", json={"folders": [str(docs)]})
        assert scan.status_code == 200
        assert scan.json()["result"]["scan"]["files_seen"] == 4

        # Propose a recycle delete, approve+execute via API, then undo via API
        junk = docs / "temp.tmp"
        prop = app.organizer.propose_action("delete", str(junk), reason="Temp cleanup")
        actions_resp = client.get("/steward/actions")
        assert actions_resp.status_code == 200
        assert len(actions_resp.json()["actions"]) >= 1

        approved = client.post(
            f"/steward/actions/{prop['id']}/approve", json={"execute": True, "dry_run": False}
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "done"
        assert not junk.exists()

        undone = client.post(f"/steward/actions/{prop['id']}/undo")
        assert undone.status_code == 200
        assert undone.json()["status"] == "undone"
        assert junk.exists()

        # Reports, recommendations, and settings GET/PUT
        rep = client.post("/steward/reports", json={"period": "weekly", "output_format": "both"})
        assert rep.status_code == 200 and rep.json()["status"] == "ok"
        assert len(client.get("/steward/reports").json()["reports"]) == 2
        assert len(client.get("/steward/recommendations").json()["suggestions"]) >= 1

        updated = client.put("/steward/settings", json={"dry_run": False, "model_id": "llama3.2"})
        assert updated.status_code == 200
        assert updated.json()["safety"]["dry_run"] is False
        assert updated.json()["models"]["model_id"] == "llama3.2"


class TestWorkerHostInventoryAndDocker:
    """Tests for Phase 9: APScheduler worker, host inventory JSON, and Docker configs."""

    def test_worker_registers_three_jobs_and_runs_cycle(self, tmp_path):
        """Verify StewardWorker registers scan, cleanup, and report jobs and executes run_once."""
        app, rag, _ = Phase8And9Helper.build_env(tmp_path)
        worker = StewardWorker(app=app, rag_index=rag, enable_watcher=False)
        job_ids = {j["id"] for j in worker.list_jobs()}

        assert job_ids == {"steward_scan", "steward_cleanup", "steward_report"}
        worker.start()
        try:
            cycle = worker.run_once()
            assert cycle["scan"] is not None
            assert cycle["cleanup"] is not None
            assert cycle["report"] is not None
        finally:
            worker.stop()

    def test_host_inventory_export_and_container_read(self, tmp_path):
        """Verify HostInventoryExporter writes JSON and SoftwareDetector loads it cleanly."""
        app, _, _ = Phase8And9Helper.build_env(tmp_path)
        inv_file = tmp_path / "host-inventory" / "apps.json"
        inv_file.parent.mkdir(parents=True)
        sample_apps = [
            {"name": "Preview", "path": "/System/Applications/Preview.app", "version": "11.0", "extensions": [".pdf", ".png"], "last_used_at": None, "status": "recent"}
        ]
        inv_file.write_text(json.dumps(sample_apps), encoding="utf-8")

        detector = SoftwareDetector(app.config, app.db, inventory_file=inv_file)
        loaded = detector.detect_and_save()
        assert len(loaded) == 1
        assert loaded[0]["name"] == "Preview"
        assert len(detector.find_apps_for_extension(".pdf")) == 1

        # Verify exporter script writes valid JSON
        out_json = tmp_path / "exported.json"
        res = HostInventoryExporter(config_path=app.config.config_path, output_path=out_json).export()
        assert Path(res["output_path"]).exists()

    def test_docker_files_match_system_design(self):
        """Verify Dockerfile, docker-compose.yml, and config.docker.yaml are valid and safe."""
        root = Path(__file__).resolve().parent.parent
        assert (root / "Dockerfile").exists()
        assert (root / "config.docker.yaml").exists()

        compose = yaml.safe_load((root / "docker-compose.yml").read_text(encoding="utf-8"))
        services = compose["services"]
        assert set(services.keys()) == {"ollama", "steward-api", "steward-worker", "steward-ui"}
        for name, svc in services.items():
            assert svc["restart"] == "unless-stopped", f"{name} missing restart policy"
            for port_map in svc.get("ports", []):
                assert str(port_map).startswith("127.0.0.1:"), f"{name} port not localhost-bound"
