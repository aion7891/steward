"""Application bootstrap and CLI entry point for Steward."""

import argparse
import sys

from steward.config import AppConfig, ConfigError
from steward.logger import LoggerFactory
from steward.models import ModelFactory


class StewardApp:
    """Coordinates configuration, logging, directories, and model setup."""

    def __init__(self, config_path=None, env_path=None, base_dir=None):
        """Load configuration and initialize core Phase 1 services."""
        self.config = AppConfig(
            config_path=config_path,
            env_path=env_path,
            base_dir=base_dir,
        )
        self.created_dirs = self.config.ensure_directories()
        self.logger_factory = LoggerFactory(self.config)
        self.logger = self.logger_factory.get_logger("app")
        self.model_factory = ModelFactory(self.config, logger=self.logger)

    def health_check(self):
        """Return a structured summary of the current application setup."""
        models = self.model_factory.describe_active_models()
        return {
            "app_name": self.config.get("app.name"),
            "version": self.config.get("app.version"),
            "environment": self.config.get("app.environment"),
            "config_path": str(self.config.config_path),
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
        safety = status["safety"]
        lines = [
            f"{status['app_name']} v{status['version']} ({status['environment']})",
            "-" * 52,
            f"Config file       : {status['config_path']}",
            f"Log level         : {status['log_level']}",
            f"Directories ready : {status['directories_ready']}",
            f"Chat model        : {models['chat_provider']} / {models['chat_model']}",
            f"Embedding model   : {models['embedding_provider']} / {models['embedding_model']}",
            f"Safety dry_run    : {safety['dry_run']}",
            f"Watched folders   : {len(status['watched_folders'])}",
        ]
        for folder in status["watched_folders"]:
            lines.append(f"  - {folder}")
        return "\n".join(lines)

    def run(self):
        """Start the application bootstrap and print its status summary."""
        self.logger.info("Starting Steward foundation check.")
        summary = self.format_status()
        print(summary)
        self.logger.info("Steward foundation check completed successfully.")
        return 0


class StewardCLI:
    """Parses command-line arguments and runs StewardApp safely."""

    def __init__(self):
        """Build the argument parser for the Steward command line."""
        self.parser = argparse.ArgumentParser(
            prog="steward",
            description="Steward - local-first AI assistant for computer organization.",
        )
        self.parser.add_argument(
            "--config",
            default=None,
            help="Path to a YAML configuration file (defaults to config.yaml).",
        )
        self.parser.add_argument(
            "--check",
            action="store_true",
            help="Run a startup configuration and directory health check.",
        )

    def execute(self, argv=None):
        """Parse CLI arguments, initialize StewardApp, and return exit code."""
        args = self.parser.parse_args(argv)
        try:
            app = StewardApp(config_path=args.config)
            return app.run()
        except ConfigError as exc:
            print(f"Configuration error: {exc}", file=sys.stderr)
            return 1


def main(argv=None):
    """Entry point for running Steward via 'uv run steward' or 'python -m steward.main'."""
    cli = StewardCLI()
    return cli.execute(argv)


if __name__ == "__main__":
    raise SystemExit(main())
