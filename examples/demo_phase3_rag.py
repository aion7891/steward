"""Manual demo script for Phase 3: Document Reading, Privacy Filter, and ChromaDB RAG.

Creates hardcoded sample documents (DOCX, XLSX, Markdown, Python, PNG, plus a sensitive
.env file that MUST be skipped) inside data/demo_phase3/, extracts content with
DocumentReader, indexes them into real Agno Knowledge + persistent ChromaDB using the
offline HashEmbedder, and runs semantic search queries without needing Ollama running.

Run with:
    uv run python examples/demo_phase3_rag.py
"""

import shutil
from pathlib import Path

import yaml
from docx import Document as DocxDocument
from openpyxl import Workbook
from PIL import Image

from steward.chunker import HashEmbedder
from steward.config import AppConfig
from steward.database import DatabaseManager
from steward.logger import LoggerFactory
from steward.rag import RAGIndex
from steward.reader import DocumentReader
from steward.scanner import FileScanner


class Phase3ManualDemo:
    """Runs a hardcoded end-to-end walkthrough of Phase 3 document reading and ChromaDB RAG."""

    def __init__(self):
        """Set up paths for an isolated Phase 3 demo workspace under data/demo_phase3/."""
        self.project_root = Path(__file__).resolve().parent.parent
        self.demo_root = self.project_root / "data" / "demo_phase3"
        self.docs_dir = self.demo_root / "sample_documents"
        self.config_file = self.demo_root / "demo_config.yaml"

    def prepare_sample_documents(self):
        """Create hardcoded multi-format documents plus a sensitive .env file."""
        if self.demo_root.exists():
            shutil.rmtree(self.demo_root)
        self.docs_dir.mkdir(parents=True, exist_ok=True)

        docx_file = self.docs_dir / "q4_roadmap.docx"
        doc = DocxDocument()
        doc.add_paragraph("Steward Q4 Roadmap: ship local ChromaDB RAG and OKF memory graph.")
        doc.add_paragraph("Key deadline: finish Docker Compose packaging by December 15.")
        doc.save(str(docx_file))

        xlsx_file = self.docs_dir / "cloud_costs.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "MonthlySpend"
        ws.append(["Service", "Owner", "MonthlyUSD"])
        ws.append(["VectorStorage", "Platform", 45])
        ws.append(["BackupBucket", "Infra", 18])
        wb.save(str(xlsx_file))
        wb.close()

        (self.docs_dir / "home_server.md").write_text(
            "# Home Server Guide\nRun Ollama locally on port 11434 with gemma3:4b and nomic-embed-text.\n",
            encoding="utf-8",
        )
        (self.docs_dir / "cleanup_rules.py").write_text(
            '"""Rules for archiving old downloads into compressed zip bundles."""\n'
            "ARCHIVE_AFTER_DAYS = 90\n",
            encoding="utf-8",
        )
        Image.new("RGB", (640, 480), color="teal").save(str(self.docs_dir / "architecture_sketch.png"))

        # Sensitive file that Steward must NEVER read or embed into ChromaDB
        (self.docs_dir / ".env").write_text("SECRET_API_KEY=do_not_index_this", encoding="utf-8")

        cfg_data = {
            "app": {"name": "StewardRAGDemo", "log_level": "INFO"},
            "scanner": {"watched_folders": [str(self.docs_dir)]},
            "rag": {"collection_name": "documents", "chunk_size": 300, "chunk_overlap": 40},
        }
        self.config_file.write_text(yaml.safe_dump(cfg_data), encoding="utf-8")
        print(f"Prepared 5 documents + 1 sensitive .env file in: {self.docs_dir}")

    def step_read_documents(self, config, logger):
        """Step 1: Read each file and show sensitive-file protection in action."""
        print("\n=== STEP 1: DocumentReader (Multi-Format + Sensitive Filter) ===")
        reader = DocumentReader(config=config, logger=logger)
        for path in sorted(self.docs_dir.iterdir()):
            doc = reader.read(path)
            if doc.skipped:
                print(f"  - {path.name:<24} [SKIPPED ] {doc.error}")
            else:
                preview = doc.text.replace("\n", " ")[:90]
                print(f"  - {path.name:<24} [{doc.file_type:<8}] {doc.char_count:>3} chars | {preview}")

    def step_index_and_search(self, config, logger):
        """Step 2 & 3: Scan into SQLite, index into ChromaDB, and run semantic queries."""
        print("\n=== STEP 2: Scan -> Agno Knowledge + ChromaDB Indexing ===")
        db = DatabaseManager(config.get_path("db_path"), logger=logger)
        FileScanner(config, db, logger=logger).scan_all()

        rag = RAGIndex(config, logger=logger, embedder=HashEmbedder(dimensions=256))
        first_stats = rag.index_from_database(db)
        second_stats = rag.index_from_database(db)
        print("First index run :", first_stats)
        print("Second run (unchanged skipped):", second_stats)
        print("RAG index stats :", rag.get_stats())

        print("\n=== STEP 3: Passage-Level Semantic Search (ChromaDB) ===")
        sample_queries = [
            "Docker Compose packaging deadline",
            "Ollama port 11434 gemma3",
            "MonthlyUSD BackupBucket Infra",
            "640x480 PNG image",
        ]
        for query in sample_queries:
            hits = rag.search(query, limit=2)
            print(f"\nQuery: '{query}'")
            for rank, hit in enumerate(hits, start=1):
                snippet = hit["content"].replace("\n", " ")[:110]
                print(f"  {rank}. {hit['file_name']} ({hit['file_type']}) -> {snippet}")

    def run(self):
        """Execute all Phase 3 manual demo steps."""
        print("Running Steward Phase 3 Manual Demo (ChromaDB)...")
        self.prepare_sample_documents()
        config = AppConfig(config_path=self.config_file, base_dir=self.demo_root)
        config.ensure_directories()
        logger = LoggerFactory(config).get_logger("demo_phase3")
        self.step_read_documents(config, logger)
        self.step_index_and_search(config, logger)
        print("\nPhase 3 demo finished successfully!")


if __name__ == "__main__":
    Phase3ManualDemo().run()
