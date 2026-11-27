"""Tests for the quick fixes: Mac paths in responses, RAG outage, local days, saved scan history."""

from datetime import datetime, timezone

import pytest
import yaml
from agno.run.base import RunStatus

from steward.chat_service import ChatService
from steward.chunker import HashEmbedder
from steward.daily_stats import DailyStats
from steward.folder_advisor import FolderAdvisor
from steward.main import StewardApp
from steward.path_mapper import PathMapper
from steward.rag import RAGIndex
from steward.scan_job_store import ScanJobStore
from steward.scan_jobs import FolderScanJobs


def build_app(tmp_path):
    """A small StewardApp over one folder with a document and a temp file."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "notes.md").write_text("# Apollo\nLaunch is December 15.", encoding="utf-8")
    (docs / "scratch.tmp").write_text("temp", encoding="utf-8")
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.safe_dump({"scanner": {"watched_folders": [str(docs)]}}), encoding="utf-8")
    return StewardApp(config_path=cfg, base_dir=tmp_path), docs


class BrokenEmbedder(HashEmbedder):
    """Behaves like Ollama being switched off."""

    def get_embedding(self, text):
        raise ConnectionError("Failed to connect to Ollama")


class TestMacPathsInResponses:
    """Docker paths (/data/...) are shown as the user's Mac paths."""

    def test_to_host_deep_rewrites_nested_values_and_sentences(self):
        mapper = PathMapper(None, mappings=[("/Users/me/Documents", "/data/Documents")])
        data = {"path": "/data/Documents/a.pdf", "items": ["Duplicate of /data/Documents/b.pdf", 3, None],
                "other": "/data/DocumentsOld/c.pdf"}
        result = mapper.to_host_deep(data)
        assert result["path"] == "/Users/me/Documents/a.pdf"
        assert result["items"] == ["Duplicate of /Users/me/Documents/b.pdf", 3, None]
        assert result["other"] == "/data/DocumentsOld/c.pdf"  # different folder, untouched
        assert PathMapper(None, env={}).to_host_deep(data) == data  # outside Docker: no change

    def test_chat_answer_shows_mac_paths(self, tmp_path):
        app, _ = build_app(tmp_path)
        run = type("Run", (), {"content": "It is in /data/Documents/a.pdf", "status": RunStatus.completed})()
        agents = type("Agents", (), {"team": type("Team", (), {"run": lambda self, m, **kwargs: run})(), "model": None})()
        rag = type("Rag", (), {"search": lambda self, q, limit=3: []})()
        mapper = PathMapper(None, mappings=[("/Users/me/Documents", "/data/Documents")])
        reply = ChatService(app, agents, rag, mapper=mapper).answer("where?")
        assert reply["reply"] == "It is in /Users/me/Documents/a.pdf"


class TestRagSurvivesOllamaOutage:
    """Indexing reports errors instead of crashing when embeddings fail."""

    def test_index_counts_errors_and_does_not_raise(self, tmp_path):
        app, docs = build_app(tmp_path)
        app.scanner.scan_all()
        rag = RAGIndex(app.config, embedder=BrokenEmbedder(dimensions=64), reader=app.reader)
        assert rag.index_file(docs / "notes.md")["status"] == "error"
        summary = rag.index_from_database(app.db)
        assert summary["errors"] == 1 and summary["indexed"] == 0
        assert str(docs / "notes.md") not in rag.manifest  # will be retried next time


class TestLocalDays:
    """Dashboard days follow the browser's time zone."""

    def test_late_evening_utc_counts_as_next_day_in_india(self, tmp_path):
        app, _ = build_app(tmp_path)
        app.db.record_scan_run({"started_at": "2026-11-26T20:00:00+00:00", "completed_at": "2026-11-26T20:01:00+00:00",
                                "folders_scanned": 1, "files_seen": 5, "duplicates_found": 0, "errors": 0})
        now = datetime(2026, 11, 27, 6, 0, tzinfo=timezone.utc)
        stats = DailyStats(app.db)
        utc_rows = {r["date"]: r["scans"] for r in stats.series(2, tz_offset=0, now=now)}
        india_rows = {r["date"]: r["scans"] for r in stats.series(2, tz_offset=-330, now=now)}
        assert utc_rows == {"2026-11-26": 1, "2026-11-27": 0}
        assert india_rows == {"2026-11-26": 0, "2026-11-27": 1}  # 20:00 UTC = 01:30 next day in India

    def test_offset_is_validated(self):
        for bad in ("abc", 900, -900, None):
            with pytest.raises(ValueError):
                DailyStats.validate_offset(bad)
        assert DailyStats.validate_offset("-330") == -330


class TestScanHistoryIsSaved:
    """Folder-scan jobs survive an API restart."""

    def test_finished_job_is_readable_after_restart(self, tmp_path):
        app, docs = build_app(tmp_path)
        mapper = PathMapper(app.config, env={})
        first = FolderScanJobs(app, FolderAdvisor(app), mapper, run_inline=True)
        job = first.start(str(docs))
        restarted = FolderScanJobs(app, FolderAdvisor(app), mapper, run_inline=True)  # fresh memory
        saved = restarted.get(job["id"])
        assert saved["status"] == "done" and saved["result"]["scan"]["files_seen"] == 2
        assert restarted.list_recent()[0]["id"] == job["id"]

    def test_unfinished_job_is_marked_failed_on_restart(self, tmp_path):
        app, _ = build_app(tmp_path)
        store = ScanJobStore(app.db)
        store.save({"id": "abc", "status": "running", "step": "scanning", "created_at": "2026-11-27T00:00:00+00:00"})
        reloaded = ScanJobStore(app.db).get("abc")
        assert reloaded["status"] == "failed" and "restarted" in reloaded["error"]
