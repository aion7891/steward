"""Manual demo script for Phase 1: Foundation, Config, Logging, and ModelFactory.

Run this script to see Phase 1 working step by step:
    uv run python examples/demo_phase1_foundation.py
"""

from pathlib import Path

from steward.config import AppConfig
from steward.logger import LoggerFactory
from steward.main import StewardApp
from steward.models import ModelConfigError, ModelFactory


class MockAgnoModel:
    """Hardcoded stand-in so the demo works even before Agno is installed."""

    def __init__(self, **kwargs):
        """Store whatever arguments ModelFactory passed to the Agno class."""
        self.kwargs = kwargs

    def __repr__(self):
        """Return a clear display string for terminal output."""
        return f"MockAgnoModel({self.kwargs})"


class Phase1ManualDemo:
    """Runs a beginner-friendly walkthrough of Steward Phase 1 components."""

    def __init__(self, config_file="config.yaml"):
        """Set up paths and load the main Steward configuration."""
        self.project_root = Path(__file__).resolve().parent.parent
        self.config_file = self.project_root / config_file

    def show_config(self):
        """Step 1: Load config.yaml, show resolved paths and safety settings."""
        print("\n=== STEP 1: AppConfig (config.yaml + .env) ===")
        config = AppConfig(config_path=self.config_file, base_dir=self.project_root)
        dirs = config.ensure_directories()
        print("App name        :", config.get("app.name"))
        print("Log level       :", config.get("app.log_level"))
        print("Database path   :", config.get_path("db_path"))
        print("OKF folder      :", config.get_path("okf_dir"))
        print("Safety dry_run  :", config.get("safety.dry_run"))
        print("Directories OK  :", len(dirs), "folders ready")
        return config

    def show_logging(self, config):
        """Step 2: Create a logger and write a sample line to console and file."""
        print("\n=== STEP 2: LoggerFactory (Console + Rotating File) ===")
        factory = LoggerFactory(config)
        logger = factory.get_logger("demo_phase1")
        logger.info("Hello from the Phase 1 manual demo!")
        log_path = config.get_path("logs_dir") / config.get("app.log_file")
        print("Log file written:", log_path)
        return logger

    def show_model_factory(self, config, logger):
        """Step 3: Show ModelFactory provider selection and API-key protection."""
        print("\n=== STEP 3: ModelFactory (Ollama Default + Cloud Safety) ===")

        def demo_loader(module_name, class_name):
            print(f"  [loader] Selected Agno class: {module_name}.{class_name}")
            return MockAgnoModel

        model_factory = ModelFactory(config, logger=logger, class_loader=demo_loader)
        print("Supported providers:", model_factory.list_supported_providers())
        print("Active config      :", model_factory.describe_active_models())

        chat_model = model_factory.create_chat_model()
        embedder = model_factory.create_embedder()
        print("Built chat model   :", chat_model)
        print("Built embedder     :", embedder)

        # Demonstrate missing API key guard for a hardcoded cloud provider call
        try:
            model_factory.create_chat_model(provider="openai", model_id="gpt-4o-mini")
        except ModelConfigError as exc:
            print("Cloud key guard OK :", exc)

    def show_bootstrap_summary(self):
        """Step 4: Run StewardApp health check summary."""
        print("\n=== STEP 4: StewardApp Health Check ===")
        app = StewardApp(config_path=self.config_file, base_dir=self.project_root)
        print(app.format_status())

    def run(self):
        """Execute all four Phase 1 demonstration steps in order."""
        print("Running Steward Phase 1 Manual Demo...")
        config = self.show_config()
        logger = self.show_logging(config)
        self.show_model_factory(config, logger)
        self.show_bootstrap_summary()
        print("\nPhase 1 demo finished successfully!")


if __name__ == "__main__":
    Phase1ManualDemo().run()
