"""Manual demo script for Phase 4: OKF Bundle, NetworkX Graph, Memory, and KnowledgeBuilder.

Creates a small project workspace inside data/demo_phase4/, scans it into SQLite,
distills linked OKF v0.3 Markdown concepts (using real Ollama by default, or pass
--fast to use local distillation without calling Ollama), inspects the NetworkX graph,
and demonstrates MemoryManager preferences, patterns, decisions, and stale expiry.

Run with:
    uv run python examples/demo_phase4_okf.py
    uv run python examples/demo_phase4_okf.py --fast
"""

import argparse
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from agno.agent import Agent

from steward.config import AppConfig
from steward.database import DatabaseManager
from steward.knowledge_builder import KnowledgeBuilder
from steward.logger import LoggerFactory
from steward.memory import MemoryManager
from steward.models import ModelFactory
from steward.okf_bundle import OKFBundle
from steward.okf_graph import OKFGraph
from steward.reader import DocumentReader
from steward.scanner import FileScanner


class Phase4ManualDemo:
    """Runs an end-to-end walkthrough of Steward's OKF v0.3 bundle, graph, and memory."""

    def __init__(self, fast_mode=False):
        """Configure paths for an isolated Phase 4 demo under data/demo_phase4/."""
        self.project_root = Path(__file__).resolve().parent.parent
        self.main_config_file = self.project_root / "config.yaml"
        self.demo_root = self.project_root / "data" / "demo_phase4"
        self.project_dir = self.demo_root / "acme_consulting"
        self.config_file = self.demo_root / "demo_config.yaml"
        self.fast_mode = fast_mode

    def prepare_workspace(self):
        """Create realistic sample project files and an isolated config."""
        if self.demo_root.exists():
            shutil.rmtree(self.demo_root)
        self.project_dir.mkdir(parents=True, exist_ok=True)

        (self.project_dir / "q3_invoice.md").write_text(
            "# Q3 Client Invoice\nAcme consulting deliverables for cloud architecture review. Total due: $4,200.\n",
            encoding="utf-8",
        )
        (self.project_dir / "migration_plan.txt").write_text(
            "Acme cloud migration checklist: verify PostgreSQL backups, test Docker failover, sign off Friday.\n",
            encoding="utf-8",
        )
        (self.project_dir / ".env").write_text("DB_PASSWORD=super_secret_do_not_copy", encoding="utf-8")

        main_cfg = AppConfig(config_path=self.main_config_file, base_dir=self.project_root)
        cfg_data = {
            "app": {"name": "StewardOKFDemo", "log_level": "INFO"},
            "models": main_cfg.get("models"),
            "scanner": {"watched_folders": [str(self.project_dir)]},
        }
        self.config_file.write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

    def _build_ollama_summarizer(self, config, logger):
        """Return a real Ollama summarizer callback (or None when --fast is used)."""
        if self.fast_mode:
            print("Using --fast local distillation (no LLM call).")
            return None
        model = ModelFactory(config, logger=logger).create_chat_model()
        agent = Agent(
            model=model,
            instructions="Summarize the document in one plain sentence under 25 words. Never include secrets.",
            markdown=False,
        )
        print(f"Using REAL Ollama summarizer: {model.id}")

        def summarize(file_name, text):
            reply = agent.run(f"File: {file_name}\nContent:\n{text[:1200]}")
            return str(getattr(reply, "content", reply)).strip()

        return summarize

    def run(self):
        """Execute all Phase 4 demo steps and print generated OKF Markdown + graph."""
        print("Running Steward Phase 4 Manual Demo (OKF v0.3 + NetworkX + Memory)...")
        self.prepare_workspace()
        config = AppConfig(config_path=self.config_file, base_dir=self.demo_root)
        config.ensure_directories()
        logger = LoggerFactory(config).get_logger("demo_phase4")

        db = DatabaseManager(config.get_path("db_path"), logger=logger)
        FileScanner(config, db, logger=logger).scan_all()
        db.upsert_software(
            {
                "name": "VSCode",
                "path": "/Applications/Visual Studio Code.app",
                "version": "1.95",
                "extensions": [".md", ".txt", ".py"],
                "status": "recent",
            }
        )

        print("\n=== STEP 1: KnowledgeBuilder -> OKF Markdown Bundle ===")
        bundle = OKFBundle(config.get_path("okf_dir"), logger=logger)
        graph = OKFGraph(bundle, logger=logger)
        summarizer = self._build_ollama_summarizer(config, logger)
        builder = KnowledgeBuilder(bundle, graph, reader=DocumentReader(config), logger=logger, summarizer=summarizer)
        stats = builder.build_from_database(db)
        print("Build stats :", stats)
        print("Graph stats :", graph.stats())

        print("\n=== STEP 2: Sample Generated OKF Concept & Graph Neighbors ===")
        hits = bundle.search_concepts("Acme invoice")
        first_rel = hits[0]["rel_path"]
        sample_path = config.get_path("okf_dir") / first_rel
        print(f"--- {first_rel} ---")
        print(sample_path.read_text(encoding="utf-8"))
        neighbors = graph.get_neighbors(first_rel)
        print("Outgoing graph neighbors:", [(n["type"], n["title"], n["rel_path"]) for n in neighbors])

        print("\n=== STEP 3: MemoryManager (Preferences, Patterns, Decisions, Expiry) ===")
        memory = MemoryManager(bundle, graph, logger=logger)
        pref = memory.record_preference("Protect Clients", "Never touch ~/Work/Clients", tags=["safety"])
        pat = memory.record_pattern("Monday Invoices", "User reviews invoices every Monday.", ttl_days=14)
        memory.record_pattern("Monday Invoices", "User reviews invoices every Monday.", ttl_days=14)
        dec = memory.record_decision("archive", str(self.project_dir / "q3_invoice.md"), "Completed Q3 billing", outcome="proposed")
        print("Saved preference :", pref)
        print("Saved pattern    :", pat, "| observations =", bundle.read_concept(pat)["frontmatter"]["x-steward-observations"])
        print("Saved decision   :", dec)

        future = datetime.now(timezone.utc) + timedelta(days=30)
        stale = memory.expire_stale_memories(now=future, delete=False)
        print("Expired stale after +30 days:", stale)
        print(f"\nExplore the full OKF folder at: {config.get_path('okf_dir')}")
        print("Phase 4 demo finished successfully!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Steward Phase 4 OKF manual demo.")
    parser.add_argument("--fast", action="store_true", help="Skip live Ollama summarization.")
    Phase4ManualDemo(fast_mode=parser.parse_args().fast).run()
