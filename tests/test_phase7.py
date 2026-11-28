"""Unit tests for Phase 7: Pattern mining, proactive recommendations, and Markdown/HTML reports."""

import os
import time
from pathlib import Path

import yaml

from steward.main import StewardApp


class Phase7Fixture:
    """Builds a realistic workspace with duplicates, stale/temp/large files, and software."""

    @staticmethod
    def build_app(tmp_path):
        """Populate scanned files, activity events, and installed software records."""
        messy = tmp_path / "messy_folder"
        old_project = tmp_path / "legacy_2024"
        messy.mkdir()
        old_project.mkdir()

        # Mixed categories + duplicate + temp + large file
        (messy / "invoice_a.pdf").write_text("Invoice #900", encoding="utf-8")
        (messy / "invoice_b.pdf").write_text("Invoice #900", encoding="utf-8")
        (messy / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (messy / "script.py").write_text("print('hello')", encoding="utf-8")
        (messy / "scratch.tmp").write_text("temp", encoding="utf-8")
        (messy / "big_video.mp4").write_bytes(b"0" * (1024 * 1024 + 64))

        # Stale folder (untouched for 120 days)
        stale_file = old_project / "old_spec.md"
        stale_file.write_text("# Old Spec", encoding="utf-8")
        old_ts = time.time() - (120 * 24 * 3600)
        os.utime(stale_file, (old_ts, old_ts))

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            yaml.safe_dump({
                "scanner": {
                    "watched_folders": [str(messy), str(old_project)],
                    "large_file_mb": 1,
                    "stale_days": 60,
                }
            }),
            encoding="utf-8",
        )
        app = StewardApp(config_path=cfg_file, base_dir=tmp_path)
        app.scanner.scan_all()
        app.db.upsert_software({
            "name": "UnusedApp", "path": "/Applications/UnusedApp.app",
            "version": "1.0", "extensions": [".xyz"], "status": "rarely_used",
        })
        app.db.record_activity_event("download_created", str(messy / "invoice_a.pdf"), "document", "~/Documents")
        return app


class TestRecommenderAndReports:
    """Tests for PatternMiner, RecommenderEngine, and Jinja2 Markdown/HTML ReportGenerator."""

    def test_mines_work_patterns_into_okf_and_generates_prioritized_suggestions(self, tmp_path):
        """Verify PatternMiner writes OKF patterns and RecommenderEngine flags all candidate types."""
        app = Phase7Fixture.build_app(tmp_path)
        rec = app.recommender.generate_recommendations(persist_patterns=True)

        kinds = {s["kind"] for s in rec["suggestions"]}
        assert {"deduplicate", "clean_temp", "archive_stale", "review_large", "group_folder"}.issubset(kinds)
        assert rec["total_reclaimable_mb"] >= 1.0
        assert len(rec["patterns"]) >= 3

        okf_patterns = app.memory_manager.list_memories(kind="pattern")
        assert len(okf_patterns) >= 3

    def test_generates_both_markdown_and_html_reports_with_okf_concept(self, tmp_path):
        """Verify ReportGenerator renders valid Markdown and HTML, records in SQLite and OKF."""
        app = Phase7Fixture.build_app(tmp_path)
        result = app.reporter.generate_report(period="weekly", output_format="both")

        assert result["status"] == "ok"
        md_path = Path(result["files"]["markdown"])
        html_path = Path(result["files"]["html"])
        assert md_path.exists() and html_path.exists()

        md_text = md_path.read_text(encoding="utf-8")
        html_text = html_path.read_text(encoding="utf-8")
        assert "## Cleanup & Organization Suggestions" in md_text
        assert "<!DOCTYPE html>" in html_text
        assert "Steward Activity Report" in html_text
        assert len(app.db.list_reports()) == 2
        assert app.okf_bundle.read_concept(result["okf_concept"]) is not None

    def test_report_workflow_produces_suggestions_and_okf_report(self, tmp_path):
        """Verify Agno ReportWorkflow runs end-to-end with recommendations included."""
        app = Phase7Fixture.build_app(tmp_path)
        out = app.get_workflows().run_workflow("report", additional_data={"period": "weekly", "output_format": "both"})

        assert out.content["status"] == "ok"
        assert len(out.content["stats"]["suggestions"]) >= 1
        assert app.okf_bundle.read_concept(out.content["okf_concept"]) is not None
