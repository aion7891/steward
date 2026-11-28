"""Settings → Data & cleanup, part 2: the records behind the Dashboard, the search index and reports."""

from steward.chunker import HashEmbedder
from steward.rag import RAGIndex
from steward.report_service import ReportService
from tests.test_chat_approvals import build

DELETE = {"confirm": "DELETE"}


def filled(tmp_path):
    """API server with a scan, a to-do item, one indexed document and one report."""
    app, server, client = build(tmp_path)
    doc = tmp_path / "docs" / "notes.txt"
    doc.write_text("Apollo launch moved to May.", encoding="utf-8")
    app.scanner.scan_all()
    app.organizer.propose_action("delete", str(tmp_path / "docs" / "report.tmp"), reason="temp file")
    server.rag_index.index_file(str(doc))
    report = ReportService(app).generate("weekly")["report"]
    return app, server, client, report


def clear(client, target, **body):
    """POST a clear request and return the response."""
    return client.post("/steward/data/clear", json={"target": target, **body})


class TestRecordsSummary:
    """Settings shows how much there is of each record."""

    def test_counts(self, tmp_path):
        _, _, client, _ = filled(tmp_path)
        data = client.get("/steward/data").json()
        assert data["index"]["count"] == 2 and data["index"]["scans"] == 1 and data["index"]["size_bytes"] > 0
        assert data["actions"] == {"count": 1, "todo": 1}
        assert data["search"]["count"] == 1 and data["reports"]["count"] == 1

    def test_always_needs_delete(self, tmp_path):
        """These records have no backup, so every target needs DELETE, even without hard=true."""
        _, _, client, _ = filled(tmp_path)
        for target in ("index", "actions", "search", "reports"):
            response = clear(client, target)
            assert response.status_code == 400 and "Type DELETE" in response.json()["detail"], target


class TestClearingEmptiesTheDashboard:
    """After clearing, the Dashboard really shows nothing (and the next scan starts fresh)."""

    def test_index_and_actions(self, tmp_path):
        app, _, client, _ = filled(tmp_path)
        assert clear(client, "index", **DELETE).json()["message"].startswith("Deleted the file index (2 files)")
        assert clear(client, "actions", **DELETE).json()["removed"] == 1
        dash = client.get("/steward/dashboard?days=7&tz_offset=0").json()
        status = dash["status"]
        assert status["files_tracked"] == 0 and status["last_scan_at"] is None and status["pending_actions"] == 0
        assert dash["todo"] == [] and dash["recent_scans"] == [] and dash["suggestions"] == []
        assert dash["categories"] == [] and sum(day["scans"] for day in dash["daily"]) == 0
        app.scanner.scan_all()  # start fresh: the next scan fills it again
        assert client.get("/steward/dashboard?days=7&tz_offset=0").json()["status"]["files_tracked"] == 2

    def test_index_waits_for_a_running_folder_scan(self, tmp_path):
        _, server, client, _ = filled(tmp_path)
        server.web_routes.jobs.jobs["busy"] = {"id": "busy", "status": "running", "created_at": "now"}
        response = clear(client, "index", **DELETE)
        assert response.status_code == 409 and "folder scan is running" in response.json()["detail"]


class TestSearchIndex:
    """Clearing the search index empties it here and in the worker's copy."""

    def test_clear_and_reindex_from_another_process(self, tmp_path):
        app, server, client, _ = filled(tmp_path)
        worker_rag = RAGIndex(app.config, embedder=HashEmbedder(dimensions=64), reader=app.reader)
        assert len(worker_rag.manifest) == 1  # the worker remembers the document as indexed
        done = clear(client, "search", **DELETE).json()
        assert done["removed"] == 1 and client.get("/steward/data").json()["search"]["count"] == 0
        assert server.rag_index.search("Apollo") == []
        # The worker's next run reads the (now empty) list again, so the document is indexed anew
        assert worker_rag.index_from_database(app.db)["indexed"] >= 1


class TestReports:
    """All reports from Settings, or one at a time from the Reports page; only inside the reports folder."""

    def test_delete_one_report(self, tmp_path):
        app, _, client, report = filled(tmp_path)
        files = list(app.config.get_path("reports_dir").glob(f"{report['key']}.*"))
        assert len(files) == 2
        assert client.delete(f"/steward/reports/library/{report['key']}").status_code == 200
        assert not any(f.exists() for f in files)
        assert client.get("/steward/reports/library").json()["reports"] == []
        assert client.delete(f"/steward/reports/library/{report['key']}").status_code == 404

    def test_delete_all_never_touches_files_outside_the_reports_folder(self, tmp_path):
        app, _, client, _ = filled(tmp_path)
        outside = tmp_path / "docs" / "my-own-notes.md"
        outside.write_text("mine", encoding="utf-8")
        app.db._execute("INSERT INTO reports (period, path, created_at) VALUES (?, ?, ?)",
                        ("weekly", str(outside), "2026-11-28T00:00:00+00:00"))
        done = clear(client, "reports", **DELETE).json()
        assert done["removed"] == 2 and outside.exists()
        assert client.get("/steward/data").json()["reports"]["count"] == 0
