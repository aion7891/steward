"""Unit tests for Phase 4: OKF bundle, NetworkX graph, MemoryManager, and KnowledgeBuilder."""

from datetime import datetime, timedelta, timezone

import pytest
import yaml

from steward.config import AppConfig
from steward.database import DatabaseManager
from steward.knowledge_builder import KnowledgeBuilder
from steward.memory import MemoryManager
from steward.okf_bundle import OKFBundle, OKFValidationError
from steward.okf_graph import OKFGraph
from steward.reader import DocumentReader
from steward.scanner import FileScanner


class TestOKFBundleAndGraph:
    """Tests for OKF concept validation, secret rejection, search, and NetworkX graph."""

    def test_write_read_validate_and_keep_old_version_on_failure(self, tmp_path):
        """Verify valid writes work, invalid writes fail safely, and secrets are rejected."""
        bundle = OKFBundle(tmp_path / "knowledge")
        assert (tmp_path / "knowledge" / "index.md").exists()

        rel = bundle.write_concept(
            "projects/acme.md",
            {
                "type": "project",
                "title": "Acme Project",
                "description": "Consulting deliverables for Acme.",
                "tags": ["client", "acme"],
                "x-steward-file-count": 3,
            },
            "# Acme Project\n\nConsulting workspace.",
        )
        loaded = bundle.read_concept(rel)
        assert loaded["frontmatter"]["type"] == "project"
        assert loaded["frontmatter"]["x-steward-file-count"] == 3

        # Invalid write (missing required 'type') must fail AND keep previous file intact
        with pytest.raises(OKFValidationError):
            bundle.write_concept(rel, {"title": "Broken"}, "broken body")
        assert bundle.read_concept(rel)["frontmatter"]["title"] == "Acme Project"

        # Secret-like content must be rejected
        with pytest.raises(OKFValidationError):
            bundle.write_concept(
                "files/bad.md",
                {"type": "file", "title": "Bad"},
                "OPENAI_API_KEY=sk-1234567890abcdef123456",
            )

    def test_graph_parses_markdown_links_and_finds_neighbors(self, tmp_path):
        """Verify OKFGraph builds directed edges from relative Markdown links."""
        bundle = OKFBundle(tmp_path / "knowledge")
        bundle.write_concept(
            "projects/apollo.md",
            {"type": "project", "title": "Apollo", "tags": ["launch"]},
            "# Apollo\n\nMain project.",
        )
        bundle.write_concept(
            "topics/budget.md",
            {"type": "topic", "title": "Budget", "tags": ["finance"]},
            "# Budget\n\nFinancial planning.",
        )
        bundle.write_concept(
            "files/q3-invoice.md",
            {"type": "file", "title": "Q3 Invoice", "tags": ["invoice", "finance"]},
            "Part of [Apollo](../projects/apollo.md). Topic: [Budget](../topics/budget.md).",
        )

        graph = OKFGraph(bundle)
        neighbors = graph.get_neighbors("files/q3-invoice.md")
        incoming = graph.get_incoming("projects/apollo.md")
        finance_nodes = graph.find_by_tag("finance")

        assert {n["rel_path"] for n in neighbors} == {"projects/apollo.md", "topics/budget.md"}
        assert incoming[0]["rel_path"] == "files/q3-invoice.md"
        assert len(finance_nodes) == 2
        assert graph.stats()["edges"] == 2


class TestMemoryManager:
    """Tests for preference, pattern, decision recording, and stale memory expiry."""

    def test_records_memories_reinforces_patterns_and_expires_stale(self, tmp_path):
        """Verify MemoryManager filters trivial inputs, tracks observations, and expires stale items."""
        bundle = OKFBundle(tmp_path / "knowledge")
        graph = OKFGraph(bundle)
        memory = MemoryManager(bundle, graph)

        assert memory.record_preference("trivial", "ok") is None

        pref_rel = memory.record_preference(
            "Protect Clients", "Never touch ~/Work/Clients", tags=["safety"]
        )
        pat_rel = memory.record_pattern(
            "Monday Invoices", "Opens invoices every Monday morning", confidence=0.8, ttl_days=10
        )
        memory.record_pattern(
            "Monday Invoices", "Opens invoices every Monday morning", confidence=0.9, ttl_days=10
        )
        dec_rel = memory.record_decision(
            "archive", "/tmp/old.zip", "Unused for 120 days", outcome="approved"
        )

        pat_doc = bundle.read_concept(pat_rel)
        assert bundle.read_concept(pref_rel)["frontmatter"]["type"] == "preference"
        assert pat_doc["frontmatter"]["x-steward-observations"] == 2
        assert bundle.read_concept(dec_rel)["frontmatter"]["x-steward-outcome"] == "approved"

        # Simulate 30 days in the future so the 10-day pattern becomes stale
        future = datetime.now(timezone.utc) + timedelta(days=30)
        expired = memory.expire_stale_memories(now=future, delete=False)
        assert pat_rel in expired
        assert bundle.read_concept(pat_rel)["frontmatter"]["x-steward-freshness"] == "stale"


class TestKnowledgeBuilder:
    """End-to-end tests converting SQLite scans and software into linked OKF concepts."""

    def test_builds_linked_concepts_from_scanned_files_and_software(self, tmp_path):
        """Verify KnowledgeBuilder creates file, folder, project, topic, and software concepts."""
        project_dir = tmp_path / "acme_client"
        project_dir.mkdir()
        (project_dir / "invoice_q3.md").write_text(
            "# Q3 Invoice\nConsulting invoice for Acme billing and cloud architecture.",
            encoding="utf-8",
        )
        (project_dir / ".env").write_text("SECRET_KEY=must_be_skipped_by_okf", encoding="utf-8")

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            yaml.safe_dump({"scanner": {"watched_folders": [str(project_dir)]}}),
            encoding="utf-8",
        )
        config = AppConfig(config_path=cfg_file, base_dir=tmp_path)
        config.ensure_directories()
        db = DatabaseManager(config.get_path("db_path"))
        FileScanner(config, db).scan_all()
        db.upsert_software(
            {
                "name": "MarkdownPro",
                "path": "/Applications/MarkdownPro.app",
                "version": "1.0",
                "extensions": [".md"],
                "status": "recent",
            }
        )

        bundle = OKFBundle(config.get_path("okf_dir"))
        graph = OKFGraph(bundle)
        builder = KnowledgeBuilder(bundle, graph, reader=DocumentReader(config))
        stats = builder.build_from_database(db)

        assert stats["files"] == 1
        assert stats["folders"] == 1
        assert stats["projects"] == 1
        assert stats["software"] == 1
        assert stats["topics"] >= 1
        assert stats["skipped"] == 1  # .env skipped

        hits = bundle.search_concepts("Acme invoice")
        assert len(hits) >= 1
        file_rel = hits[0]["rel_path"]
        neighbor_types = {n["type"] for n in graph.get_neighbors(file_rel)}
        assert {"folder", "project", "software", "topic"}.issubset(neighbor_types)
