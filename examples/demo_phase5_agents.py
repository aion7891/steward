"""Manual demo script for Phase 5: Real Agno Toolkits, 6 Agents, Team, and 3 Workflows.

Creates a realistic workspace in data/demo_phase5/, runs all three deterministic Agno
Workflows (ScanWorkflow -> CleanupWorkflow -> ReportWorkflow) using real Ollama
embeddings + ChromaDB + OKF, verifies HITL confirmation flags on OrganizerTools, and
asks a live question to the real Agno ChatAgent powered by Ollama (gemma3:4b).

Run with:
    uv run python examples/demo_phase5_agents.py
    uv run python examples/demo_phase5_agents.py --offline
"""

import argparse
import shutil
from pathlib import Path

import yaml

from steward.agents import StewardAgents
from steward.chunker import HashEmbedder
from steward.config import AppConfig
from steward.main import StewardApp
from steward.rag import RAGIndex
from steward.workflows import StewardWorkflows


class Phase5ManualDemo:
    """Runs an end-to-end walkthrough of Steward's Agno Workflows, Toolkits, and Agents."""

    def __init__(self, offline=False):
        """Set up paths for an isolated Phase 5 demo under data/demo_phase5/."""
        self.project_root = Path(__file__).resolve().parent.parent
        self.main_config_file = self.project_root / "config.yaml"
        self.demo_root = self.project_root / "data" / "demo_phase5"
        self.docs_dir = self.demo_root / "my_projects"
        self.config_file = self.demo_root / "demo_config.yaml"
        self.offline = offline

    def prepare_workspace(self):
        """Populate sample project documents, duplicates, and a temp file."""
        if self.demo_root.exists():
            shutil.rmtree(self.demo_root)
        self.docs_dir.mkdir(parents=True, exist_ok=True)

        (self.docs_dir / "apollo_launch.md").write_text(
            "# Apollo Launch Plan\nTarget launch date is December 15. Owner: Engineering.\n",
            encoding="utf-8",
        )
        (self.docs_dir / "budget_q4.txt").write_text(
            "Q4 cloud infrastructure budget is $2,400 per month including backups.\n",
            encoding="utf-8",
        )
        (self.docs_dir / "budget_q4_copy.txt").write_text(
            "Q4 cloud infrastructure budget is $2,400 per month including backups.\n",
            encoding="utf-8",
        )
        (self.docs_dir / "old_draft.tmp").write_text("temporary draft", encoding="utf-8")

        main_cfg = AppConfig(config_path=self.main_config_file, base_dir=self.project_root)
        cfg_data = {
            "app": {"name": "StewardPhase5Demo", "log_level": "INFO"},
            "models": main_cfg.get("models"),
            "scanner": {"watched_folders": [str(self.docs_dir)]},
            "safety": {"dry_run": True, "require_confirmation": True, "move_to_recycle_first": True},
        }
        self.config_file.write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

    def run(self):
        """Execute all 3 Agno Workflows, inspect HITL safety, and run a live Agent query."""
        mode = "Offline HashEmbedder" if self.offline else "Real Ollama Models"
        print(f"Running Steward Phase 5 Manual Demo ({mode})...")
        self.prepare_workspace()

        app = StewardApp(config_path=self.config_file, base_dir=self.demo_root)
        embedder = HashEmbedder(dimensions=256) if self.offline else None
        rag = RAGIndex(app.config, logger=app.logger, embedder=embedder, reader=app.reader)

        print("\n=== STEP 1: ScanWorkflow (Scan -> ChromaDB RAG -> OKF Bundle) ===")
        workflows = StewardWorkflows(app, rag_index=rag, logger=app.logger)
        scan_res = workflows.run_workflow("scan", additional_data={"folders": [str(self.docs_dir)]})
        print("ScanWorkflow output   :", scan_res.content)

        print("\n=== STEP 2: CleanupWorkflow (Find -> Dry-Run Proposals -> OKF Decisions) ===")
        clean_res = workflows.run_workflow("cleanup")
        print("CleanupWorkflow output:", clean_res.content)

        print("\n=== STEP 3: ReportWorkflow (Stats -> Markdown Report -> OKF Report Concept) ===")
        rep_res = workflows.run_workflow("report", additional_data={"period": "weekly"})
        print("Report path           :", rep_res.content["report_path"])
        print("OKF report concept    :", rep_res.content["okf_concept"])

        print("\n=== STEP 4: Agno Agents, Orchestrator Team & HITL Confirmation Flags ===")
        agents = StewardAgents(app, rag_index=rag)
        print("Agents built          :", list(agents.list_agents().keys()))
        print("Team members          :", [m.name for m in agents.team.members])
        org_funcs = agents.organizer_tools.functions
        print(
            "HITL confirmation     :",
            {name: fn.requires_confirmation for name, fn in org_funcs.items()},
        )

        if self.offline:
            print("\nOffline mode active — skipping live Ollama agent chat call.")
        else:
            print("\n=== STEP 5: Live Agno ChatAgent Query (OKF First -> RAG Fallback) ===")
            question = "What is the Apollo launch target date and which file has that info?"
            print("Question:", question)
            reply = agents.chat_agent.run(question)
            answer = str(getattr(reply, "content", reply))
            if "does not support tools" in answer.lower():
                # Fallback for Ollama models without native tool-calling (e.g. gemma3:4b)
                print("Note: Current Ollama model lacks native tool-calling; retrieving OKF + RAG context directly...")
                okf_hits = agents.okf_tools.search_concepts("Apollo launch", limit=2)["results"]
                rag_hits = rag.search(question, limit=2)
                context = f"OKF hits: {okf_hits}\nRAG hits: {[{'file': h['file_name'], 'text': h['content']} for h in rag_hits]}"
                from agno.agent import Agent
                plain_agent = Agent(model=agents.model, markdown=False)
                fallback = plain_agent.run(f"Answer concisely with source file citation.\n{context}\n\nQuestion: {question}")
                answer = str(getattr(fallback, "content", fallback))
            print("Answer  :\n" + answer)

        print("\nPhase 5 demo finished successfully!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Steward Phase 5 Agno manual demo.")
    parser.add_argument("--offline", action="store_true", help="Skip live Ollama calls.")
    Phase5ManualDemo(offline=parser.parse_args().offline).run()
