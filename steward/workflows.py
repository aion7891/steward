"""Deterministic, step-based Agno Workflows for Steward background jobs."""

from pathlib import Path

from agno.db.sqlite import SqliteDb
from agno.workflow import Step, StepOutput, Workflow

from steward.proposals import ProposalService
from steward.tools import ReportTools


class StewardWorkflows:
    """Builds and runs ScanWorkflow, CleanupWorkflow, and ReportWorkflow via Agno."""

    def __init__(self, app, rag_index=None, logger=None):
        """Initialize Agno Workflows wired to StewardApp services."""
        self.app = app
        self.rag_index = rag_index
        self.logger = logger or app.logger
        self.workflow_db = SqliteDb(
            db_file=str(app.config.get_path("data_dir") / "agno_sessions.db")
        )
        # Cleanup only PROPOSES; a human approves each action later (never auto-approved)
        self.proposals = ProposalService(app.config, app.db, app.organizer)
        self.report_tools = ReportTools(
            app.config, app.db, app.scanner, app.okf_graph,
            recommender=app.recommender, reporter=app.reporter,
        )

        self.scan_workflow = self._build_scan_workflow()
        self.cleanup_workflow = self._build_cleanup_workflow()
        self.report_workflow = self._build_report_workflow()

    def _build_scan_workflow(self):
        """ScanWorkflow: incremental scan -> update ChromaDB RAG -> update OKF bundle."""
        return Workflow(
            id="steward-scan-workflow",
            name="ScanWorkflow",
            description="Scan configured folders, update RAG embeddings, and refresh OKF.",
            db=self.workflow_db,
            steps=[
                Step(name="scan_folders", executor=self._step_scan_folders),
                Step(name="update_rag", executor=self._step_update_rag),
                Step(name="update_okf", executor=self._step_update_okf),
            ],
        )

    def _build_cleanup_workflow(self):
        """CleanupWorkflow: find candidates -> propose safe actions -> log decisions to OKF."""
        return Workflow(
            id="steward-cleanup-workflow",
            name="CleanupWorkflow",
            description="Find cleanup candidates, propose dry-run actions, and record in OKF.",
            db=self.workflow_db,
            steps=[
                Step(name="find_candidates", executor=self._step_find_candidates),
                Step(name="propose_actions", executor=self._step_propose_cleanup),
                Step(name="log_to_okf", executor=self._step_log_cleanup_okf),
            ],
        )

    def _build_report_workflow(self):
        """ReportWorkflow: collect stats -> render Markdown report -> save OKF report concept."""
        return Workflow(
            id="steward-report-workflow",
            name="ReportWorkflow",
            description="Collect system stats, render report, and store it as an OKF concept.",
            db=self.workflow_db,
            steps=[
                Step(name="collect_stats", executor=self._step_collect_stats),
                Step(name="render_report", executor=self._step_render_report),
                Step(name="save_report_concept", executor=self._step_save_report_okf),
            ],
        )

    def _step_scan_folders(self, step_input):
        """Step 1 of ScanWorkflow: run incremental folder scan into SQLite."""
        extra = step_input.additional_data or {}
        folders = extra.get("folders")
        summary = self.app.scanner.scan_all(folders=folders)
        return StepOutput(content={"scan": summary}, success=True)

    def _step_update_rag(self, step_input):
        """Step 2 of ScanWorkflow: index new or changed files into ChromaDB."""
        rag = self.rag_index or self.app.get_rag_index()
        rag_stats = rag.index_from_database(self.app.db)
        prev = step_input.previous_step_content if isinstance(step_input.previous_step_content, dict) else {}
        return StepOutput(content={**prev, "rag": rag_stats}, success=True)

    def _step_update_okf(self, step_input):
        """Step 3 of ScanWorkflow: rebuild curated OKF concepts and NetworkX graph."""
        okf_stats = self.app.knowledge_builder.build_from_database(self.app.db)
        prev = step_input.previous_step_content if isinstance(step_input.previous_step_content, dict) else {}
        return StepOutput(
            content={**prev, "okf": okf_stats, "graph": self.app.okf_graph.stats()},
            success=True,
        )

    def _step_find_candidates(self, step_input):
        """Step 1 of CleanupWorkflow: query duplicates, large, stale, and temp files."""
        findings = self.app.scanner.get_cleanup_findings()
        return StepOutput(content={"findings": findings}, success=True)

    def _step_propose_cleanup(self, step_input):
        """Step 2 of CleanupWorkflow: create 'proposed' actions that wait for the user's approval."""
        prev = step_input.previous_step_content if isinstance(step_input.previous_step_content, dict) else {}
        findings = prev.get("findings", {})
        items = [{"action_type": "delete", "source_path": f["path"], "reason": "Temporary file candidate"}
                 for f in findings.get("temp_files", [])[:10]]
        for group in findings.get("duplicates", [])[:10]:
            # Keep the earliest copy and propose recycling extra duplicates
            items.extend({"action_type": "delete", "source_path": f["path"], "reason": "Duplicate file candidate"}
                         for f in group["files"][1:])
        # Files already deleted or moved must not be proposed again
        items = [item for item in items if Path(item["source_path"]).exists()]
        outcome = self.proposals.propose_many(items)
        proposals = [{"action": "delete", "path": r["source_path"], "result": r} for r in outcome["created"]]
        return StepOutput(
            content={"findings": findings, "proposals": proposals, "awaiting_confirmation": True,
                     "already_open": len(outcome["already_open"]),
                     "skipped_protected": len(outcome["skipped_protected"])},
            success=True,
        )

    def _step_log_cleanup_okf(self, step_input):
        """Step 3 of CleanupWorkflow: record proposed cleanup decisions in OKF memory."""
        prev = step_input.previous_step_content if isinstance(step_input.previous_step_content, dict) else {}
        proposals = prev.get("proposals", [])
        logged = []
        for item in proposals:
            rel = self.app.memory_manager.record_decision(
                action_type=item["action"],
                target_path=item["path"],
                reason=item["result"].get("message", "Cleanup candidate"),
                outcome="proposed",
            )
            logged.append(rel)
        self.app.okf_bundle.refresh_index()
        return StepOutput(
            content={"proposals_count": len(proposals), "okf_decisions": logged, "awaiting_confirmation": True,
                     "already_open": prev.get("already_open", 0), "skipped_protected": prev.get("skipped_protected", 0)},
            success=True,
        )

    def _step_collect_stats(self, step_input):
        """Step 1 of ReportWorkflow: collect fresh storage and activity stats."""
        stats = self.report_tools.collect_stats()["stats"]
        return StepOutput(content={"stats": stats}, success=True)

    def _step_render_report(self, step_input):
        """Step 2 of ReportWorkflow: render Markdown/HTML report files to reports/."""
        extra = step_input.additional_data or {}
        period = extra.get("period", "weekly")
        output_format = extra.get("output_format", "markdown")
        rendered = self.report_tools.render_report(period=period, output_format=output_format)
        return StepOutput(content=rendered, success=True)

    def _step_save_report_okf(self, step_input):
        """Step 3 of ReportWorkflow: store the generated report as an OKF concept."""
        rendered = step_input.previous_step_content if isinstance(step_input.previous_step_content, dict) else {}
        report_path = rendered.get("report_path", "")
        name = Path(report_path).stem if report_path else "report"
        rel_path = f"reports/{self.app.okf_bundle.slugify(name)}.md"
        stats = rendered.get("stats", {})
        saved = self.app.okf_bundle.write_concept(
            rel_path,
            {
                "type": "report",
                "title": f"Steward Report ({name})",
                "description": f"Tracked {stats.get('total_files', 0)} files ({stats.get('total_size_mb', 0)} MB).",
                "tags": ["report", "summary"],
                "sources": [report_path] if report_path else [],
                "x-steward-report-path": report_path,
            },
            f"# Steward Report ({name})\n\nReport file: `{report_path}`\n\n- Files: {stats.get('total_files', 0)}\n- Duplicate groups: {stats.get('duplicate_groups', 0)}",
        )
        self.app.okf_bundle.refresh_index()
        self.app.okf_graph.update_node(saved)
        return StepOutput(content={**rendered, "okf_concept": saved}, success=True)

    def run_workflow(self, name, additional_data=None):
        """Run one of 'scan', 'cleanup', or 'report' workflows by name."""
        mapping = {
            "scan": self.scan_workflow,
            "cleanup": self.cleanup_workflow,
            "report": self.report_workflow,
        }
        key = str(name).strip().lower()
        if key not in mapping:
            raise ValueError(f"Unknown workflow '{name}'. Choose from: {list(mapping.keys())}")
        return mapping[key].run(input=f"Run {key} workflow", additional_data=additional_data or {})
