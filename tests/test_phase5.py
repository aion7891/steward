"""Unit tests for Phase 5: Agno Toolkits, 6 Agents, Orchestrator Team, and 3 Workflows."""

import yaml

from steward.agents import StewardAgents
from steward.chunker import HashEmbedder
from steward.main import StewardApp
from steward.rag import RAGIndex
from steward.tools import (
    DocumentReaderTools,
    FileScannerTools,
    OKFTools,
    OrganizerTools,
    ReportTools,
    SoftwareTools,
)
from steward.workflows import StewardWorkflows


class Phase5TestHelper:
    """Builds an isolated StewardApp workspace with sample files for Phase 5 tests."""

    @staticmethod
    def build_app(tmp_path):
        """Create sample project files, a duplicate, a temp file, and protected folder."""
        docs = tmp_path / "workspace_docs"
        protected = tmp_path / "clients_protected"
        docs.mkdir()
        protected.mkdir()

        (docs / "plan.md").write_text("# Apollo Plan\nLaunch checklist and architecture notes.", encoding="utf-8")
        (docs / "copy_a.txt").write_text("identical invoice text", encoding="utf-8")
        (docs / "copy_b.txt").write_text("identical invoice text", encoding="utf-8")
        (docs / "scratch.tmp").write_text("temp scratch", encoding="utf-8")
        (protected / "contract.txt").write_text("Do not touch client contract.", encoding="utf-8")

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            yaml.safe_dump({
                "scanner": {"watched_folders": [str(docs)]},
                "safety": {"dry_run": True, "protected_paths": [str(protected)]},
            }),
            encoding="utf-8",
        )
        app = StewardApp(config_path=cfg_file, base_dir=tmp_path)
        rag = RAGIndex(app.config, embedder=HashEmbedder(dimensions=256), reader=app.reader)
        return app, rag, docs, protected


class TestAgnoToolkits:
    """Tests for all 6 Agno Toolkits including HITL confirmation and safety guards."""

    def test_inspection_okf_and_report_toolkits(self, tmp_path):
        """Verify scanner, reader, software, OKF, and report toolkits return clean dicts."""
        app, _, docs, _ = Phase5TestHelper.build_app(tmp_path)
        scan_tools = FileScannerTools(app.scanner, app.db, app.config)
        read_tools = DocumentReaderTools(app.reader)
        sw_tools = SoftwareTools(app.software_detector, app.db)
        okf_tools = OKFTools(app.okf_bundle, app.okf_graph)
        rep_tools = ReportTools(app.config, app.db, app.scanner, app.okf_graph)

        assert scan_tools.scan_folder(str(docs))["status"] == "ok"
        assert len(scan_tools.find_duplicates()["duplicates"]) == 1
        assert read_tools.read_document(str(docs / "plan.md"))["status"] == "ok"
        assert sw_tools.list_apps()["status"] == "ok"

        w1 = okf_tools.write_concept("projects/apollo.md", "project", "Apollo", "Launch project", "# Apollo")
        w2 = okf_tools.write_concept("topics/launch.md", "topic", "Launch", "Release topic", "# Launch")
        assert w1["status"] == "ok" and w2["status"] == "ok"
        assert okf_tools.link_concepts("projects/apollo.md", "topics/launch.md")["status"] == "ok"
        assert len(okf_tools.neighbors("projects/apollo.md")["neighbors"]) == 1
        assert rep_tools.render_report(period="weekly")["status"] == "ok"

    def test_organizer_tools_hitl_confirmation_protected_and_dry_run(self, tmp_path):
        """Verify destructive tools require confirmation, respect dry-run, and block protected paths."""
        app, _, docs, protected = Phase5TestHelper.build_app(tmp_path)
        org = OrganizerTools(app.config, app.db, memory_manager=app.memory_manager)

        assert org.functions["move_file"].requires_confirmation is True
        assert org.functions["archive_files"].requires_confirmation is True
        assert org.functions["delete_files"].requires_confirmation is True
        assert org.functions["propose_move"].requires_confirmation is False

        # Protected path is blocked even when dry_run=False
        blocked = org.delete_files([str(protected / "contract.txt")], dry_run=False)
        assert blocked["status"] == "blocked"
        assert (protected / "contract.txt").exists()

        # Default dry-run does not delete file on disk
        dry = org.delete_files([str(docs / "scratch.tmp")])
        assert dry["status"] == "dry_run"
        assert (docs / "scratch.tmp").exists()


class TestAgnoAgentsTeamAndWorkflows:
    """Tests for the 6 Agno Agents, Orchestrator Team, and 3 deterministic Workflows."""

    def test_builds_six_agents_and_orchestrator_team(self, tmp_path):
        """Verify all 6 specialist agents, Orchestrator Team, and OKF-only long-term memory."""
        app, rag, _, _ = Phase5TestHelper.build_app(tmp_path)
        agents = StewardAgents(app, rag_index=rag)

        all_agents = agents.list_agents()
        assert set(all_agents.keys()) == {
            "scanner", "analyzer", "organizer", "recommender", "reporter", "chat"
        }
        assert len(agents.team.members) == 6
        assert agents.chat_agent.knowledge is rag.get_knowledge()
        assert agents.chat_agent.update_memory_on_run is False

    def test_runs_scan_cleanup_and_report_workflows_end_to_end(self, tmp_path):
        """Execute ScanWorkflow, CleanupWorkflow, and ReportWorkflow via Agno Workflow.run."""
        app, rag, docs, _ = Phase5TestHelper.build_app(tmp_path)
        workflows = StewardWorkflows(app, rag_index=rag)

        scan_out = workflows.run_workflow("scan", additional_data={"folders": [str(docs)]})
        assert scan_out.content["scan"]["files_seen"] == 4
        assert scan_out.content["rag"]["indexed"] == 3  # scratch.tmp skipped
        assert scan_out.content["okf"]["files"] == 3

        cleanup_out = workflows.run_workflow("cleanup")
        assert cleanup_out.content["awaiting_confirmation"] is True
        assert cleanup_out.content["proposals_count"] >= 2  # 1 temp + 1 duplicate
        assert len(cleanup_out.content["okf_decisions"]) == cleanup_out.content["proposals_count"]
        # Nothing deleted on disk during CleanupWorkflow proposals
        assert (docs / "scratch.tmp").exists()

        report_out = workflows.run_workflow("report", additional_data={"period": "weekly"})
        assert report_out.content["status"] == "ok"
        assert app.okf_bundle.read_concept(report_out.content["okf_concept"]) is not None
        assert len(app.db.list_reports()) == 1
