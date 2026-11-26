"""Application bootstrap and CLI entry point for Steward."""

import argparse
import sys

from steward.config import AppConfig, ConfigError
from steward.database import DatabaseManager
from steward.knowledge_builder import KnowledgeBuilder
from steward.logger import LoggerFactory
from steward.memory import MemoryManager
from steward.models import ModelConfigError, ModelFactory
from steward.okf_bundle import OKFBundle
from steward.okf_graph import OKFGraph
from steward.rag import RAGIndex
from steward.reader import DocumentReader
from steward.scanner import FileScanner
from steward.software import SoftwareDetector
from steward.watcher import DownloadsWatcher


class StewardApp:
    """Coordinates config, logging, SQLite, scanning, RAG, and OKF memory."""

    def __init__(self, config_path=None, env_path=None, base_dir=None):
        """Load configuration and initialize core Steward services."""
        self.config = AppConfig(config_path=config_path, env_path=env_path, base_dir=base_dir)
        self.created_dirs = self.config.ensure_directories()
        self.logger_factory = LoggerFactory(self.config)
        self.logger = self.logger_factory.get_logger("app")
        self.model_factory = ModelFactory(self.config, logger=self.logger)
        self.db = DatabaseManager(self.config.get_path("db_path"), logger=self.logger)
        self.scanner = FileScanner(self.config, self.db, logger=self.logger)
        self.software_detector = SoftwareDetector(self.config, self.db, logger=self.logger)
        self.downloads_watcher = DownloadsWatcher(self.config, self.db, logger=self.logger)
        self.reader = DocumentReader(self.config, logger=self.logger)
        self.okf_bundle = OKFBundle(self.config.get_path("okf_dir"), logger=self.logger)
        self.okf_graph = OKFGraph(self.okf_bundle, logger=self.logger)
        self.memory_manager = MemoryManager(self.okf_bundle, self.okf_graph, logger=self.logger)
        self.knowledge_builder = KnowledgeBuilder(
            self.okf_bundle, self.okf_graph, reader=self.reader, logger=self.logger
        )
        self._rag_index = None

    def get_rag_index(self, embedder=None):
        """Lazily initialize and return the local Agno Knowledge ChromaDB RAGIndex."""
        if self._rag_index is None or embedder is not None:
            self._rag_index = RAGIndex(
                self.config, logger=self.logger, embedder=embedder, reader=self.reader
            )
        return self._rag_index

    def health_check(self):
        """Return a structured summary of the current application setup."""
        return {
            "app_name": self.config.get("app.name"), "version": self.config.get("app.version"),
            "environment": self.config.get("app.environment"), "config_path": str(self.config.config_path),
            "db_path": str(self.config.get_path("db_path")),
            "vector_store_dir": str(self.config.get_path("vector_store_dir")),
            "okf_dir": str(self.config.get_path("okf_dir")), "okf_stats": self.okf_graph.stats(),
            "log_level": self.config.get("app.log_level"),
            "directories_ready": all(path.exists() for path in self.created_dirs),
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
            f"Safety dry_run    : {s['safety']['dry_run']}",
            f"Watched folders   : {len(s['watched_folders'])}",
        ] + [f"  - {folder}" for folder in s["watched_folders"]]
        return "\n".join(lines)

    def run_scan(self, folders=None):
        """Run an incremental folder scan and print a concise findings summary."""
        s = self.scanner.scan_all(folders=folders)
        print(
            f"Scanned {s['files_seen']} files ({s['hashed_files']} hashed, {s['unchanged_files']} unchanged) | "
            f"duplicates={s['duplicates_found']}, large={s['large_files_found']}, stale={s['stale_files_found']}, temp={s['temp_files_found']}"
        )
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
        print(f"File: {doc.path} | Type: {doc.file_type} | Chars: {doc.char_count}\nMetadata: {doc.metadata}")
        print("--- Preview ---\n" + doc.text[:400])
        return doc

    def run_index(self, force=False):
        """Index scanned SQLite files into the local ChromaDB RAG store."""
        s = self.get_rag_index().index_from_database(self.db, force=force)
        print(f"RAG index complete: indexed={s['indexed']}, skipped={s['skipped']}, empty={s['empty']}, errors={s['errors']}, chunks={s['total_chunks']}")
        return s

    def run_search(self, query, limit=5):
        """Search indexed passages in ChromaDB and print ranked snippets."""
        hits = self.get_rag_index().search(query, limit=limit)
        if not hits:
            print("No matching passages found.")
            return hits
        for idx, hit in enumerate(hits, start=1):
            print(f"{idx}. [{hit['file_type']}] {hit['file_name']} -> {hit['content'].replace(chr(10), ' ')[:180]}")
        return hits

    def run_build_okf(self):
        """Build linked OKF concepts from SQLite files and software inventory."""
        stats = self.knowledge_builder.build_from_database(self.db)
        g = self.okf_graph.stats()
        print(f"OKF build complete: {stats} | Graph: {g['nodes']} nodes, {g['edges']} edges")
        return stats

    def run_okf_search(self, query, limit=5):
        """Search curated OKF concepts and display their linked neighbors."""
        hits = self.okf_bundle.search_concepts(query, limit=limit)
        if not hits:
            print("No matching OKF concepts found.")
            return hits
        for idx, item in enumerate(hits, start=1):
            fm = item["frontmatter"]
            neighbors = [n["title"] for n in self.okf_graph.get_neighbors(item["rel_path"])[:3]]
            print(f"{idx}. [{fm.get('type')}] {fm.get('title')} ({item['rel_path']}) | links={neighbors}")
        return hits

    def run(self):
        """Start the application bootstrap and print its status summary."""
        self.logger.info("Starting Steward status check.")
        print(self.format_status())
        return 0


class StewardCLI:
    """Parses command-line arguments and runs StewardApp safely."""

    def __init__(self):
        """Build the argument parser for the Steward command line."""
        self.parser = argparse.ArgumentParser(prog="steward", description="Steward local AI assistant.")
        for flag, kwargs in (
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
        ):
            self.parser.add_argument(flag, **kwargs)

    def execute(self, argv=None):
        """Parse CLI arguments, initialize StewardApp, and return exit code."""
        args = self.parser.parse_args(argv)
        try:
            app = StewardApp(config_path=args.config)
            actions = (
                (args.scan, app.run_scan), (args.software, app.run_software_scan),
                (args.watch_downloads, app.downloads_watcher.run_forever),
                (args.read, lambda: app.run_read(args.read)), (args.index, app.run_index),
                (args.search, lambda: app.run_search(args.search)),
                (args.build_okf, app.run_build_okf),
                (args.okf_search, lambda: app.run_okf_search(args.okf_search)),
            )
            for enabled, func in actions:
                if enabled:
                    func()
                    return 0
            return app.run()
        except (ConfigError, ModelConfigError, FileNotFoundError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1


def main(argv=None):
    """Entry point for running Steward via 'uv run steward'."""
    return StewardCLI().execute(argv)


if __name__ == "__main__":
    raise SystemExit(main())
