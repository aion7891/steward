"""Application bootstrap and CLI entry point for Steward."""

import argparse
import sys

from steward.agents import StewardAgents
from steward.config import AppConfig, ConfigError
from steward.database import DatabaseManager
from steward.knowledge_builder import KnowledgeBuilder
from steward.logger import LoggerFactory
from steward.memory import MemoryManager
from steward.models import ModelConfigError, ModelFactory
from steward.okf_bundle import OKFBundle
from steward.okf_graph import OKFGraph
from steward.organizer import FileOrganizer
from steward.rag import RAGIndex
from steward.reader import DocumentReader
from steward.recommender import RecommenderEngine
from steward.reporter import ReportGenerator
from steward.scanner import FileScanner
from steward.software import SoftwareDetector
from steward.watcher import DownloadsWatcher
from steward.workflows import StewardWorkflows


class StewardApp:
    """Coordinates config, SQLite, scanning, RAG, OKF, organizer, reports, and agents."""

    def __init__(self, config_path=None, env_path=None, base_dir=None):
        """Load configuration and initialize core Steward services."""
        self.config = AppConfig(config_path=config_path, env_path=env_path, base_dir=base_dir)
        self.created_dirs = self.config.ensure_directories()
        self.logger = LoggerFactory(self.config).get_logger("app")
        self.model_factory = ModelFactory(self.config, logger=self.logger)
        self.db = DatabaseManager(self.config.get_path("db_path"), logger=self.logger)
        self.scanner = FileScanner(self.config, self.db, logger=self.logger)
        self.software_detector = SoftwareDetector(self.config, self.db, logger=self.logger)
        self.downloads_watcher = DownloadsWatcher(self.config, self.db, logger=self.logger)
        self.reader = DocumentReader(self.config, logger=self.logger)
        self.okf_bundle = OKFBundle(self.config.get_path("okf_dir"), logger=self.logger)
        self.okf_graph = OKFGraph(self.okf_bundle, logger=self.logger)
        self.memory_manager = MemoryManager(self.okf_bundle, self.okf_graph, logger=self.logger)
        self.knowledge_builder = KnowledgeBuilder(self.okf_bundle, self.okf_graph, reader=self.reader, logger=self.logger)
        self.organizer = FileOrganizer(self.config, self.db, memory_manager=self.memory_manager, logger=self.logger)
        self.recycle_manager = self.organizer.recycle
        self.recommender = RecommenderEngine(self.config, self.db, self.scanner, memory_manager=self.memory_manager, logger=self.logger)
        self.reporter = ReportGenerator(
            self.config, self.db, self.scanner, self.okf_graph, self.recommender,
            okf_bundle=self.okf_bundle, logger=self.logger,
        )
        self._rag_index, self._agents, self._workflows = None, None, None

    def get_rag_index(self, embedder=None):
        """Lazily initialize and return the local Agno Knowledge ChromaDB RAGIndex."""
        if self._rag_index is None or embedder is not None:
            self._rag_index = RAGIndex(self.config, logger=self.logger, embedder=embedder, reader=self.reader)
        return self._rag_index

    def get_agents(self, model=None, rag_index=None):
        """Lazily build and return the 6 Agno Agents and Orchestrator Team."""
        if self._agents is None or model is not None:
            self._agents = StewardAgents(self, model=model, rag_index=rag_index or self.get_rag_index())
        return self._agents

    def get_workflows(self, rag_index=None):
        """Lazily build and return the 3 deterministic Agno Workflows."""
        if self._workflows is None or rag_index is not None:
            self._workflows = StewardWorkflows(self, rag_index=rag_index, logger=self.logger)
        return self._workflows

    def health_check(self):
        """Return a structured summary of the current application setup."""
        return {
            "app_name": self.config.get("app.name"), "version": self.config.get("app.version"),
            "environment": self.config.get("app.environment"), "config_path": str(self.config.config_path),
            "db_path": str(self.config.get_path("db_path")), "vector_store_dir": str(self.config.get_path("vector_store_dir")),
            "okf_dir": str(self.config.get_path("okf_dir")), "okf_stats": self.okf_graph.stats(),
            "log_level": self.config.get("app.log_level"), "directories_ready": all(p.exists() for p in self.created_dirs),
            "watched_folders": [str(p) for p in self.config.get_watched_folders()],
            "models": self.model_factory.describe_active_models(),
            "safety": {
                "dry_run": self.config.get("safety.dry_run"),
                "require_confirmation": self.config.get("safety.require_confirmation"),
                "move_to_recycle_first": self.config.get("safety.move_to_recycle_first"),
            },
        }

    def format_status(self):
        """Format the health check dictionary into a readable terminal report."""
        s = self.health_check()
        m, okf = s["models"], s["okf_stats"]
        lines = [
            f"{s['app_name']} v{s['version']} ({s['environment']})", "-" * 52,
            f"Config file       : {s['config_path']}", f"Database          : {s['db_path']}",
            f"Vector store      : {s['vector_store_dir']}",
            f"OKF bundle        : {s['okf_dir']} ({okf['nodes']} nodes, {okf['edges']} edges)",
            f"Chat model        : {m['chat_provider']} / {m['chat_model']}",
            f"Embedding model   : {m['embedding_provider']} / {m['embedding_model']}",
            f"Safety dry_run    : {s['safety']['dry_run']}", f"Watched folders   : {len(s['watched_folders'])}",
        ] + [f"  - {folder}" for folder in s["watched_folders"]]
        return "\n".join(lines)

    def run_scan(self, folders=None):
        """Run an incremental folder scan and print a concise findings summary."""
        s = self.scanner.scan_all(folders=folders)
        print(f"Scanned {s['files_seen']} files ({s['hashed_files']} hashed, {s['unchanged_files']} unchanged) | dup={s['duplicates_found']}, large={s['large_files_found']}, stale={s['stale_files_found']}, temp={s['temp_files_found']}")
        return s

    def run_software_scan(self):
        """Detect installed software, save to SQLite, and print count."""
        apps = self.software_detector.detect_and_save()
        recent = sum(1 for a in apps if a["status"] == "recent")
        print(f"Detected {len(apps)} apps (recent={recent}, rarely_used={len(apps) - recent})")
        return apps

    def run_read(self, file_path):
        """Read a single document and print its extracted metadata and preview."""
        doc = self.reader.read(file_path)
        if doc.error:
            print(f"Could not read {file_path}: {doc.error}", file=sys.stderr)
            return doc
        print(f"File: {doc.path} | Type: {doc.file_type} | Chars: {doc.char_count}\nMetadata: {doc.metadata}\n--- Preview ---\n{doc.text[:400]}")
        return doc

    def run_index(self, force=False):
        """Index scanned SQLite files into the local ChromaDB RAG store."""
        s = self.get_rag_index().index_from_database(self.db, force=force)
        print(f"RAG index: indexed={s['indexed']}, skipped={s['skipped']}, empty={s['empty']}, errors={s['errors']}, chunks={s['total_chunks']}")
        return s

    def run_search(self, query, limit=5):
        """Search indexed passages in ChromaDB and print ranked snippets."""
        hits = self.get_rag_index().search(query, limit=limit)
        for idx, hit in enumerate(hits, start=1):
            print(f"{idx}. [{hit['file_type']}] {hit['file_name']} -> {hit['content'].replace(chr(10), ' ')[:180]}")
        if not hits:
            print("No matching passages found.")
        return hits

    def run_build_okf(self):
        """Build linked OKF concepts from SQLite files and software inventory."""
        stats = self.knowledge_builder.build_from_database(self.db)
        g = self.okf_graph.stats()
        print(f"OKF build: {stats} | Graph: {g['nodes']} nodes, {g['edges']} edges")
        return stats

    def run_okf_search(self, query, limit=5):
        """Search curated OKF concepts and display their linked neighbors."""
        hits = self.okf_bundle.search_concepts(query, limit=limit)
        for idx, item in enumerate(hits, start=1):
            fm = item["frontmatter"]
            links = [n["title"] for n in self.okf_graph.get_neighbors(item["rel_path"])[:3]]
            print(f"{idx}. [{fm.get('type')}] {fm.get('title')} ({item['rel_path']}) | links={links}")
        if not hits:
            print("No matching OKF concepts found.")
        return hits

    def run_recommendations(self):
        """Mine work patterns and print proactive cleanup/organization suggestions."""
        rec = self.recommender.generate_recommendations(persist_patterns=True)
        print(f"Patterns found: {len(rec['patterns'])} | Suggestions: {len(rec['suggestions'])} ({rec['total_reclaimable_mb']} MB reclaimable)")
        for s in rec["suggestions"]:
            print(f"  - [{s['priority'].upper()}] {s['title']} ({s['reclaimable_mb']} MB): {s['reason']}")
        return rec

    def run_report(self, output_format="markdown", period="weekly"):
        """Generate a Markdown, HTML, or dual report and print output path(s)."""
        res = self.reporter.generate_report(period=period, output_format=output_format)
        print(f"Report generated: {res['files']} | OKF: {res['okf_concept']}")
        return res

    def run_workflow(self, name):
        """Run one of Steward's deterministic Agno Workflows (scan, cleanup, report)."""
        res = self.get_workflows().run_workflow(name)
        print(f"Workflow '{name}' finished: {getattr(res, 'content', res)}")
        return res

    def run_chat(self, message):
        """Send a question to the Agno Orchestrator Team and print its response."""
        reply = self.get_agents().team.run(message)
        print(getattr(reply, "content", reply))
        return reply

    def run(self):
        """Print Steward's startup status summary."""
        print(self.format_status())
        return 0


class StewardCLI:
    """Parses command-line arguments and runs StewardApp safely."""

    FLAGS = (
        ("--config", {"default": None, "help": "Path to config.yaml."}),
        ("--check", {"action": "store_true", "help": "Run health check."}),
        ("--scan", {"action": "store_true", "help": "Scan folders into SQLite."}),
        ("--software", {"action": "store_true", "help": "Detect installed apps."}),
        ("--watch-downloads", {"action": "store_true", "help": "Watch Downloads."}),
        ("--read", {"default": None, "help": "Extract text/metadata from a file."}),
        ("--index", {"action": "store_true", "help": "Index scanned files into RAG."}),
        ("--search", {"default": None, "help": "Search indexed document passages."}),
        ("--build-okf", {"action": "store_true", "help": "Build OKF knowledge bundle."}),
        ("--okf-search", {"default": None, "help": "Search curated OKF concepts."}),
        ("--recommend", {"action": "store_true", "help": "Mine work patterns and print suggestions."}),
        ("--report", {"choices": ["markdown", "html", "both"], "help": "Generate periodic report."}),
        ("--workflow", {"choices": ["scan", "cleanup", "report"], "help": "Run an Agno workflow."}),
        ("--chat", {"default": None, "help": "Ask the Agno Orchestrator Team a question."}),
        ("--undo", {"type": int, "default": None, "help": "Undo a completed file action by ID."}),
    )

    def __init__(self):
        """Build the argument parser for the Steward command line."""
        self.parser = argparse.ArgumentParser(prog="steward", description="Steward local AI assistant.")
        for flag, kwargs in self.FLAGS:
            self.parser.add_argument(flag, **kwargs)

    def execute(self, argv=None):
        """Parse CLI arguments, initialize StewardApp, and return exit code."""
        args = self.parser.parse_args(argv)
        try:
            app = StewardApp(config_path=args.config)
            dispatch = (
                (args.scan, app.run_scan), (args.software, app.run_software_scan),
                (args.watch_downloads, app.downloads_watcher.run_forever),
                (args.read, lambda: app.run_read(args.read)), (args.index, app.run_index),
                (args.search, lambda: app.run_search(args.search)),
                (args.build_okf, app.run_build_okf),
                (args.okf_search, lambda: app.run_okf_search(args.okf_search)),
                (args.recommend, app.run_recommendations),
                (args.report, lambda: app.run_report(output_format=args.report)),
                (args.workflow, lambda: app.run_workflow(args.workflow)),
                (args.chat, lambda: app.run_chat(args.chat)),
                (args.undo is not None, lambda: print(app.organizer.undo_action(args.undo))),
            )
            for enabled, func in dispatch:
                if enabled:
                    func()
                    return 0
            return app.run()
        except (ConfigError, ModelConfigError, FileNotFoundError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1


def main(argv=None):
    """Entry point for running Steward via 'uv run steward'."""
    return StewardCLI().execute(argv)


if __name__ == "__main__":
    raise SystemExit(main())
