"""Application bootstrap and CLI entry point for Steward."""

import argparse
import sys

from steward.config import AppConfig, ConfigError
from steward.database import DatabaseManager
from steward.logger import LoggerFactory
from steward.models import ModelConfigError, ModelFactory
from steward.rag import RAGIndex
from steward.reader import DocumentReader
from steward.scanner import FileScanner
from steward.software import SoftwareDetector
from steward.watcher import DownloadsWatcher


class StewardApp:
    """Coordinates configuration, logging, database, scanning, reader, and RAG."""

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
        self._rag_index = None

    def get_rag_index(self, embedder=None):
        """Lazily initialize and return the local Agno Knowledge RAGIndex."""
        if self._rag_index is None or embedder is not None:
            self._rag_index = RAGIndex(
                self.config, logger=self.logger, embedder=embedder, reader=self.reader
            )
        return self._rag_index

    def health_check(self):
        """Return a structured summary of the current application setup."""
        models = self.model_factory.describe_active_models()
        return {
            "app_name": self.config.get("app.name"),
            "version": self.config.get("app.version"),
            "environment": self.config.get("app.environment"),
            "config_path": str(self.config.config_path),
            "db_path": str(self.config.get_path("db_path")),
            "vector_store_dir": str(self.config.get_path("vector_store_dir")),
            "log_level": self.config.get("app.log_level"),
            "directories_ready": all(path.exists() for path in self.created_dirs),
            "watched_folders": [str(p) for p in self.config.get_watched_folders()],
            "models": models,
            "safety": {
                "dry_run": self.config.get("safety.dry_run"),
                "require_confirmation": self.config.get("safety.require_confirmation"),
                "move_to_recycle_first": self.config.get("safety.move_to_recycle_first"),
            },
        }

    def format_status(self):
        """Format the health check dictionary into a readable terminal report."""
        status = self.health_check()
        models = status["models"]
        lines = [
            f"{status['app_name']} v{status['version']} ({status['environment']})",
            "-" * 52,
            f"Config file       : {status['config_path']}",
            f"Database          : {status['db_path']}",
            f"Vector store      : {status['vector_store_dir']}",
            f"Log level         : {status['log_level']}",
            f"Directories ready : {status['directories_ready']}",
            f"Chat model        : {models['chat_provider']} / {models['chat_model']}",
            f"Embedding model   : {models['embedding_provider']} / {models['embedding_model']}",
            f"Safety dry_run    : {status['safety']['dry_run']}",
            f"Watched folders   : {len(status['watched_folders'])}",
        ]
        for folder in status["watched_folders"]:
            lines.append(f"  - {folder}")
        return "\n".join(lines)

    def run_scan(self, folders=None):
        """Run an incremental folder scan and print a concise findings summary."""
        summary = self.scanner.scan_all(folders=folders)
        print(
            f"Scanned {summary['files_seen']} files ({summary['hashed_files']} hashed, "
            f"{summary['unchanged_files']} unchanged) in {summary['folders_scanned']} folder(s) | "
            f"duplicates={summary['duplicates_found']}, large={summary['large_files_found']}, "
            f"stale={summary['stale_files_found']}, temp={summary['temp_files_found']}"
        )
        return summary

    def run_software_scan(self):
        """Detect installed software, save to SQLite, and print count."""
        apps = self.software_detector.detect_and_save()
        recent = sum(1 for a in apps if a["status"] == "recent")
        rare = sum(1 for a in apps if a["status"] == "rarely_used")
        print(f"Detected {len(apps)} apps (recent={recent}, rarely_used={rare})")
        return apps

    def run_read(self, file_path):
        """Read a single document and print its extracted metadata and preview."""
        doc = self.reader.read(file_path)
        if doc.error:
            print(f"Could not read {file_path}: {doc.error}", file=sys.stderr)
            return doc
        print(f"File: {doc.path} | Type: {doc.file_type} | Chars: {doc.char_count}")
        print(f"Metadata: {doc.metadata}")
        print("--- Preview ---")
        print(doc.text[:400])
        return doc

    def run_index(self, force=False):
        """Index scanned SQLite files into the local LanceDB RAG store."""
        rag = self.get_rag_index()
        summary = rag.index_from_database(self.db, force=force)
        print(
            f"RAG index complete: indexed={summary['indexed']}, skipped={summary['skipped']}, "
            f"empty={summary['empty']}, errors={summary['errors']}, chunks={summary['total_chunks']}"
        )
        return summary

    def run_search(self, query, limit=5):
        """Search indexed passages and print ranked snippets."""
        rag = self.get_rag_index()
        hits = rag.search(query, limit=limit)
        if not hits:
            print("No matching passages found.")
            return hits
        for idx, hit in enumerate(hits, start=1):
            snippet = hit["content"].replace("\n", " ")[:180]
            print(f"{idx}. [{hit['file_type']}] {hit['file_name']} -> {snippet}")
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
        self.parser = argparse.ArgumentParser(
            prog="steward",
            description="Steward - local-first AI assistant for computer organization.",
        )
        self.parser.add_argument("--config", default=None, help="Path to config.yaml.")
        self.parser.add_argument("--check", action="store_true", help="Run health check.")
        self.parser.add_argument("--scan", action="store_true", help="Scan folders into SQLite.")
        self.parser.add_argument("--software", action="store_true", help="Detect installed apps.")
        self.parser.add_argument("--watch-downloads", action="store_true", help="Watch Downloads.")
        self.parser.add_argument("--read", default=None, help="Extract text/metadata from a file.")
        self.parser.add_argument("--index", action="store_true", help="Index scanned files into RAG.")
        self.parser.add_argument("--search", default=None, help="Search indexed document passages.")

    def execute(self, argv=None):
        """Parse CLI arguments, initialize StewardApp, and return exit code."""
        args = self.parser.parse_args(argv)
        try:
            app = StewardApp(config_path=args.config)
            if args.scan:
                app.run_scan()
                return 0
            if args.software:
                app.run_software_scan()
                return 0
            if args.watch_downloads:
                app.downloads_watcher.run_forever()
                return 0
            if args.read:
                app.run_read(args.read)
                return 0
            if args.index:
                app.run_index()
                return 0
            if args.search:
                app.run_search(args.search)
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
