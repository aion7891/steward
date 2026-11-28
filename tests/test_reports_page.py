"""Tests for the Reports page backend: library, generate, read, download and path safety."""

import yaml
from fastapi.testclient import TestClient

from steward.main import StewardApp
from steward.report_service import ReportService
from steward.web_routes import WebRoutes


def build(tmp_path):
    """A StewardApp with a scanned folder and a FastAPI app holding only the web routes."""
    from fastapi import FastAPI

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "notes.md").write_text("# Apollo\nLaunch is December 15.", encoding="utf-8")
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.safe_dump({"scanner": {"watched_folders": [str(docs)]}}), encoding="utf-8")
    app = StewardApp(config_path=cfg, base_dir=tmp_path)
    app.scanner.scan_all()
    api = FastAPI()
    WebRoutes(app).register(api)
    return app, TestClient(api)


class TestReportLibrary:
    """Generate, list, read and download reports through the API."""

    def test_generate_then_list_read_and_download(self, tmp_path):
        _, client = build(tmp_path)
        created = client.post("/steward/reports/generate", json={"period": "weekly"}).json()
        entry = created["report"]
        assert created["status"] == "ok" and set(entry["formats"]) == {"markdown", "html"}
        assert created["message"].startswith("New weekly report ready with")
        assert all(f["available"] for f in entry["formats"].values())
        library = client.get("/steward/reports/library").json()["reports"]
        assert [r["key"] for r in library] == [entry["key"]]

        md = client.get(f"/steward/reports/{entry['formats']['markdown']['id']}").json()["report"]
        assert md["format"] == "markdown" and md["content"].startswith("# Steward Activity Report")
        html = client.get(f"/steward/reports/{entry['formats']['html']['id']}/download")
        assert html.status_code == 200 and html.headers["content-type"].startswith("text/html")
        assert "attachment" in html.headers["content-disposition"] and "<!DOCTYPE html>" in html.text

    def test_bad_requests(self, tmp_path):
        _, client = build(tmp_path)
        assert client.post("/steward/reports/generate", json={"period": "hourly"}).status_code == 400
        assert client.get("/steward/reports/999").status_code == 404
        assert client.get("/steward/reports/abc").status_code == 404
        assert client.get("/steward/reports/library").json()["reports"] == []

    def test_deleted_report_file_is_reported_missing(self, tmp_path):
        app, client = build(tmp_path)
        entry = client.post("/steward/reports/generate", json={}).json()["report"]
        md_id = entry["formats"]["markdown"]["id"]
        (app.config.get_path("reports_dir") / f"{entry['key']}.md").unlink()
        assert client.get(f"/steward/reports/{md_id}").status_code == 404
        library = client.get("/steward/reports/library").json()["reports"]
        assert library[0]["formats"]["markdown"]["available"] is False


class TestPathSafety:
    """A report record pointing outside the reports folder is never served."""

    def test_refuses_files_outside_reports_folder(self, tmp_path):
        app, client = build(tmp_path)
        secret = tmp_path / "secret.md"
        secret.write_text("password: hunter2", encoding="utf-8")
        app.db.record_report("weekly", str(secret))
        report_id = app.db.list_reports(limit=1)[0]["id"]
        assert client.get(f"/steward/reports/{report_id}").status_code == 400
        assert client.get(f"/steward/reports/{report_id}/download").status_code == 400
        assert ReportService(app).library()[0]["formats"]["markdown"]["available"] is False
