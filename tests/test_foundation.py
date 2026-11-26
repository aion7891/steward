"""Unit tests for Phase 1: Foundation and configuration."""

import pytest
import yaml

from steward.config import AppConfig, ConfigError
from steward.logger import LoggerFactory
from steward.main import StewardApp, StewardCLI
from steward.models import ModelConfigError, ModelFactory


class DummyModel:
    """Simple test double representing an Agno model or embedder."""

    def __init__(self, **kwargs):
        """Record all keyword arguments passed during instantiation."""
        self.kwargs = kwargs


class TestAppConfig:
    """Tests for YAML loading, environment overrides, paths, and validation."""

    def _write_config(self, tmp_path, content):
        """Write a temporary YAML config file and return its path."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.safe_dump(content), encoding="utf-8")
        return config_file

    def test_loads_yaml_and_merges_defaults(self, tmp_path):
        """Ensure custom YAML values override defaults while keeping other defaults."""
        cfg_file = self._write_config(tmp_path, {"app": {"log_level": "DEBUG"}})
        config = AppConfig(config_path=cfg_file, base_dir=tmp_path)

        assert config.get("app.log_level") == "DEBUG"
        assert config.get("models.provider") == "ollama"
        assert config.get("safety.dry_run") is True

    def test_env_overrides_take_precedence(self, tmp_path, monkeypatch):
        """Ensure supported environment variables override config.yaml values."""
        cfg_file = self._write_config(tmp_path, {"app": {"log_level": "INFO"}})
        monkeypatch.setenv("STEWARD_LOG_LEVEL", "WARNING")
        monkeypatch.setenv("STEWARD_MODEL_PROVIDER", "openai")
        monkeypatch.setenv("STEWARD_MODEL_ID", "gpt-4o-mini")
        monkeypatch.setenv("STEWARD_DRY_RUN", "false")

        config = AppConfig(config_path=cfg_file, base_dir=tmp_path)

        assert config.get("app.log_level") == "WARNING"
        assert config.get("models.provider") == "openai"
        assert config.get("models.model_id") == "gpt-4o-mini"
        assert config.get("safety.dry_run") is False

    def test_rejects_invalid_provider(self, tmp_path):
        """Raise ConfigError when an unsupported provider is configured."""
        cfg_file = self._write_config(tmp_path, {"models": {"provider": "unknown"}})
        with pytest.raises(ConfigError):
            AppConfig(config_path=cfg_file, base_dir=tmp_path)

    def test_ensure_directories_creates_runtime_folders(self, tmp_path):
        """Verify ensure_directories creates all configured workspace folders."""
        cfg_file = self._write_config(tmp_path, {})
        config = AppConfig(config_path=cfg_file, base_dir=tmp_path)
        created = config.ensure_directories()

        assert len(created) == 6
        assert all(path.exists() and path.is_dir() for path in created)


class TestLoggerFactory:
    """Tests for console and rotating file logger setup."""

    def test_creates_logger_with_file_and_no_duplicates(self, tmp_path):
        """Verify logger writes to disk and avoids attaching duplicate handlers."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("app:\n  log_level: INFO\n", encoding="utf-8")
        config = AppConfig(config_path=cfg_file, base_dir=tmp_path)
        factory = LoggerFactory(config)
        logger_name = "steward.test_unique_logger"

        try:
            logger_a = factory.configure_logger(name=logger_name)
            logger_b = factory.configure_logger(name=logger_name)
            logger_a.info("Phase 1 test log entry")

            assert logger_a is logger_b
            assert len(logger_a.handlers) == 2
            log_file = config.get_path("logs_dir") / "steward.log"
            assert log_file.exists()
            assert "Phase 1 test log entry" in log_file.read_text(encoding="utf-8")
        finally:
            LoggerFactory.clear_handlers(logger_name)


class TestModelFactory:
    """Tests for Agno model and embedder provider selection."""

    def _make_config(self, tmp_path, provider="ollama"):
        """Create a minimal AppConfig pointing to a temporary directory."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            f"models:\n  provider: {provider}\n  model_id: test-model\n",
            encoding="utf-8",
        )
        return AppConfig(config_path=cfg_file, base_dir=tmp_path)

    def test_builds_ollama_chat_and_embedder_models(self, tmp_path):
        """Verify Ollama models receive both model id and host."""
        config = self._make_config(tmp_path, provider="ollama")
        loaded = []

        def fake_loader(module_name, class_name):
            loaded.append((module_name, class_name))
            return DummyModel

        factory = ModelFactory(config, class_loader=fake_loader)
        chat = factory.create_chat_model()
        embedder = factory.create_embedder()

        assert chat.kwargs["id"] == "test-model"
        assert chat.kwargs["host"] == "http://localhost:11434"
        assert embedder.kwargs["id"] == "nomic-embed-text"
        assert ("agno.models.ollama", "Ollama") in loaded
        assert ("agno.knowledge.embedder.ollama", "OllamaEmbedder") in loaded

    def test_cloud_provider_requires_api_key(self, tmp_path, monkeypatch):
        """Raise ModelConfigError when a cloud provider API key is missing."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        config = self._make_config(tmp_path, provider="openai")
        factory = ModelFactory(config, class_loader=lambda m, c: DummyModel)

        with pytest.raises(ModelConfigError):
            factory.create_chat_model()

    def test_cloud_provider_passes_api_key(self, tmp_path, monkeypatch):
        """Verify cloud providers pass the API key from the environment."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-secret-key")
        config = self._make_config(tmp_path, provider="anthropic")
        factory = ModelFactory(config, class_loader=lambda m, c: DummyModel)
        model = factory.create_chat_model()

        assert model.kwargs["id"] == "test-model"
        assert model.kwargs["api_key"] == "test-secret-key"


class TestStewardApp:
    """Tests for application bootstrap and CLI execution."""

    def test_health_check_and_cli_success(self, tmp_path):
        """Verify StewardApp initializes cleanly and CLI returns exit code 0."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("app:\n  name: StewardTest\n", encoding="utf-8")

        app = StewardApp(config_path=cfg_file, base_dir=tmp_path)
        status = app.health_check()

        assert status["app_name"] == "StewardTest"
        assert status["directories_ready"] is True
        assert StewardCLI().execute(["--config", str(cfg_file), "--check"]) == 0
