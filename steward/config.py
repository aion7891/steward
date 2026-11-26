"""Configuration loader and validator for Steward."""

import copy
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv


class ConfigError(Exception):
    """Raised when configuration cannot be loaded or fails validation."""


class AppConfig:
    """Loads config.yaml and .env, resolves paths, and validates settings."""

    VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
    VALID_PROVIDERS = ("ollama", "openai", "anthropic", "gemini")

    DEFAULT_DATA = {
        "app": {
            "name": "Steward",
            "version": "0.1.0",
            "environment": "development",
            "log_level": "INFO",
            "log_file": "steward.log",
            "log_max_bytes": 5242880,
            "log_backup_count": 3,
        },
        "paths": {
            "data_dir": "data",
            "db_path": "data/steward.db",
            "vector_store_dir": "vector_store",
            "okf_dir": "knowledge",
            "recycle_dir": "data/recycle",
            "reports_dir": "reports",
            "logs_dir": "data/logs",
        },
        "scanner": {
            "watched_folders": ["~/Documents", "~/Downloads", "~/Desktop"],
            "downloads_folder": "~/Downloads",
            "ignored_dirs": [".git", ".venv", "node_modules", "__pycache__"],
            "ignored_extensions": [".tmp", ".part", ".crdownload"],
            "large_file_mb": 100,
            "stale_days": 90,
        },
        "models": {
            "provider": "ollama",
            "model_id": "llama3.2",
            "host": "http://localhost:11434",
            "temperature": 0.2,
            "embedding_provider": "ollama",
            "embedding_model": "nomic-embed-text",
            "embedding_dimensions": 768,
        },
        "rag": {"table_name": "steward_documents", "chunk_size": 800, "chunk_overlap": 120, "max_file_chars": 100000, "default_top_k": 5},
        "safety": {
            "dry_run": True,
            "require_confirmation": True,
            "move_to_recycle_first": True,
        },
        "scheduler": {
            "scan_interval_minutes": 60,
            "cleanup_interval_hours": 24,
            "report_day": "sunday",
        },
        "server": {
            "host": "127.0.0.1",
            "port": 8000,
            "ui_port": 8501,
        },
    }

    def __init__(self, config_path=None, env_path=None, base_dir=None):
        """Initialize configuration from YAML file and environment variables."""
        self.base_dir = Path(base_dir).resolve() if base_dir else Path.cwd().resolve()
        self._load_env(env_path)
        chosen_path = config_path or os.getenv("STEWARD_CONFIG_PATH", "config.yaml")
        self.config_path = self._resolve_path(chosen_path)
        self.data = copy.deepcopy(self.DEFAULT_DATA)
        self._load_yaml()
        self._apply_env_overrides()
        self.validate()

    def _load_env(self, env_path):
        """Load environment variables from a .env file when present."""
        target = self._resolve_path(env_path) if env_path else self.base_dir / ".env"
        if target.exists():
            load_dotenv(dotenv_path=target, override=False)

    def _load_yaml(self):
        """Read config.yaml and merge it onto the default settings."""
        if not self.config_path.exists():
            raise ConfigError(f"Configuration file not found: {self.config_path}")
        try:
            with open(self.config_path, "r", encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"Invalid YAML in {self.config_path}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ConfigError("Top-level configuration must be a YAML mapping.")
        self._deep_merge(self.data, loaded)

    def _deep_merge(self, target, updates):
        """Recursively merge nested dictionaries in place."""
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                self._deep_merge(target[key], value)
            else:
                target[key] = value

    def _apply_env_overrides(self):
        """Apply supported environment variable overrides."""
        log_level = os.getenv("STEWARD_LOG_LEVEL")
        if log_level:
            self.data["app"]["log_level"] = log_level.strip().upper()
        provider = os.getenv("STEWARD_MODEL_PROVIDER")
        if provider:
            self.data["models"]["provider"] = provider.strip().lower()
        model_id = os.getenv("STEWARD_MODEL_ID")
        if model_id:
            self.data["models"]["model_id"] = model_id.strip()
        ollama_host = os.getenv("OLLAMA_HOST")
        if ollama_host:
            self.data["models"]["host"] = ollama_host.strip()
        dry_run = os.getenv("STEWARD_DRY_RUN")
        if dry_run is not None and dry_run.strip() != "":
            self.data["safety"]["dry_run"] = dry_run.strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )

    def validate(self):
        """Validate key configuration fields and raise ConfigError if invalid."""
        level = str(self.get("app.log_level", "")).upper()
        if level not in self.VALID_LOG_LEVELS:
            raise ConfigError(
                f"Unsupported log_level '{level}'. Use one of: {self.VALID_LOG_LEVELS}"
            )
        provider = str(self.get("models.provider", "")).lower()
        if provider not in self.VALID_PROVIDERS:
            raise ConfigError(
                f"Unsupported model provider '{provider}'. "
                f"Use one of: {self.VALID_PROVIDERS}"
            )
        if self.get("scanner.large_file_mb", 0) <= 0:
            raise ConfigError("scanner.large_file_mb must be greater than zero.")
        if self.get("scanner.stale_days", 0) <= 0:
            raise ConfigError("scanner.stale_days must be greater than zero.")

    def get(self, dotted_key, default=None):
        """Look up a nested setting using dot notation (e.g. 'models.provider')."""
        current = self.data
        for part in dotted_key.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    def get_path(self, key_name):
        """Resolve a configured path under the 'paths' section to an absolute Path."""
        raw_value = self.get(f"paths.{key_name}")
        if not raw_value:
            raise ConfigError(f"Missing path setting: paths.{key_name}")
        return self._resolve_path(raw_value)

    def get_watched_folders(self):
        """Return expanded Path objects for all configured watched folders."""
        folders = self.get("scanner.watched_folders", [])
        return [self._resolve_path(folder) for folder in folders]

    def ensure_directories(self):
        """Create required runtime directories on disk if they do not exist."""
        dir_keys = (
            "data_dir",
            "vector_store_dir",
            "okf_dir",
            "recycle_dir",
            "reports_dir",
            "logs_dir",
        )
        created = []
        for key in dir_keys:
            folder = self.get_path(key)
            folder.mkdir(parents=True, exist_ok=True)
            created.append(folder)
        return created

    def _resolve_path(self, raw_path):
        """Expand user home shortcuts and resolve relative paths against base_dir."""
        expanded = Path(str(raw_path)).expanduser()
        if expanded.is_absolute():
            return expanded.resolve()
        return (self.base_dir / expanded).resolve()
