"""Tests for the Settings page backend: override file, validation, .env locks, Ollama model checks."""

import httpx
import pytest
import yaml

from steward.config import AppConfig
from steward.ollama_models import OllamaModels
from steward.path_mapper import PathMapper
from steward.settings_service import SettingsService

CONFIG_TEXT = "# my comment stays\nscanner:\n  watched_folders: ['docs']\nsafety:\n  dry_run: true\n"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Other tests load the project .env into os.environ; start each test without those values."""
    for name in ("STEWARD_DRY_RUN", "STEWARD_MODEL_ID", "STEWARD_MODEL_PROVIDER", "OLLAMA_HOST", "STEWARD_LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)


def build(tmp_path, env=None, checker=None, on_change=None):
    """AppConfig + SettingsService over a temp folder with a commented config.yaml."""
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "config.yaml").write_text(CONFIG_TEXT, encoding="utf-8")
    config = AppConfig(config_path=tmp_path / "config.yaml", base_dir=tmp_path)
    service = SettingsService(config, PathMapper(config, env={}), checker, on_change, env=env or {})
    return config, service


def fake_ollama(models):
    """An OllamaModels whose /api/tags answers with the given models."""
    def handler(request):
        return httpx.Response(200, json={"models": models})
    return OllamaModels("http://ollama.test", transport=httpx.MockTransport(handler))


class TestOverrideFile:
    """UI changes go to data/settings.override.yaml; config.yaml is never rewritten."""

    def test_saves_to_override_file_and_keeps_config_comments(self, tmp_path):
        config, service = build(tmp_path)
        result = service.update({"dry_run": "false"})  # text "false" must mean False
        assert result["safety"]["dry_run"] is False and config.get("safety.dry_run") is False
        assert (tmp_path / "config.yaml").read_text(encoding="utf-8") == CONFIG_TEXT
        saved = yaml.safe_load(config.override_path().read_text(encoding="utf-8"))
        assert saved == {"safety": {"dry_run": False}}
        assert config.override_path().read_text(encoding="utf-8").startswith("# Settings saved from the Steward web UI")
        reloaded = AppConfig(config_path=tmp_path / "config.yaml", base_dir=tmp_path)
        assert reloaded.get("safety.dry_run") is False  # survives a restart

    def test_env_still_wins_and_locks_the_setting(self, tmp_path, monkeypatch):
        config, service = build(tmp_path)
        service.update({"dry_run": False})
        monkeypatch.setenv("STEWARD_DRY_RUN", "true")
        assert AppConfig(config_path=tmp_path / "config.yaml", base_dir=tmp_path).get("safety.dry_run") is True
        _, locked_service = build(tmp_path, env={"STEWARD_DRY_RUN": "true"})
        assert locked_service.current()["locked"] == {"dry_run": "STEWARD_DRY_RUN"}
        with pytest.raises(ValueError, match="STEWARD_DRY_RUN in .env"):
            locked_service.update({"dry_run": False})

    def test_broken_override_file_is_ignored(self, tmp_path):
        config, _ = build(tmp_path)
        config.override_path().parent.mkdir(parents=True, exist_ok=True)
        config.override_path().write_text("safety: [not: valid", encoding="utf-8")
        assert AppConfig(config_path=tmp_path / "config.yaml", base_dir=tmp_path).get("safety.dry_run") is True


class TestValidation:
    """Bad input is refused with a clear message."""

    def test_rejects_bad_values(self, tmp_path):
        _, service = build(tmp_path)
        cases = [({}, "at least one"), ({"log_level": "DEBUG"}, "cannot be changed"),
                 ({"dry_run": "maybe"}, "true or false"), ({"provider": "skynet"}, "Unknown provider"),
                 ({"watched_folders": []}, "at least one watched folder"),
                 ({"watched_folders": [str(tmp_path / "missing")]}, "not found")]
        for payload, message in cases:
            with pytest.raises(ValueError, match=message):
                service.update(payload)

    def test_watched_folders_use_scan_rules_and_dedupe(self, tmp_path):
        config, service = build(tmp_path)
        (tmp_path / "more").mkdir()
        result = service.update({"watched_folders": [str(tmp_path / "docs"), str(tmp_path / "more"), str(tmp_path / "more/")]})
        assert config.get("scanner.watched_folders") == [str((tmp_path / "docs").resolve()), str((tmp_path / "more").resolve())]
        assert [f["available"] for f in result["folders"]] == [True, True]
        (tmp_path / "docs" / "inner").mkdir()
        with pytest.raises(ValueError, match="is already inside"):
            service.update({"watched_folders": [str(tmp_path / "docs"), str(tmp_path / "docs" / "inner")]})

    def test_cloud_provider_needs_an_api_key(self, tmp_path):
        _, service = build(tmp_path)
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            service.update({"provider": "openai", "model_id": "gpt-4o-mini"})
        changed = []
        _, keyed = build(tmp_path, env={"OPENAI_API_KEY": "test-key"}, on_change=lambda: changed.append(1))
        assert keyed.update({"provider": "openai", "model_id": "gpt-4o-mini"})["models"]["provider"] == "openai"
        assert changed == [1]  # the agents get rebuilt with the new model


class TestOllamaModels:
    """Installed models and the 'can use tools' check."""

    MODELS = [{"name": "gemma4:latest", "size": 9, "capabilities": ["completion", "tools"]},
              {"name": "gemma3:4b", "size": 3, "capabilities": ["completion", "vision"]},
              {"name": "nomic-embed-text:latest", "size": 1, "capabilities": ["embedding"]},
              {"name": "gpt-oss:20b-cloud", "size": 1, "capabilities": ["completion", "tools"]}]

    def test_lists_models_with_capabilities(self):
        info = fake_ollama(self.MODELS).list_models()
        assert info["reachable"] is True
        assert [(m["name"], m["tools"], m["embedding"], m["cloud"]) for m in info["models"]] == [
            ("gemma3:4b", False, False, False), ("gemma4:latest", True, False, False),
            ("gpt-oss:20b-cloud", True, False, True), ("nomic-embed-text:latest", False, True, False)]

    def test_check_chat_model(self, tmp_path):
        ollama = fake_ollama(self.MODELS)
        assert ollama.check_chat_model("gemma4")["name"] == "gemma4:latest"  # ':latest' is implied
        with pytest.raises(ValueError, match="cannot use tools"):
            ollama.check_chat_model("gemma3:4b")
        with pytest.raises(ValueError, match="ollama pull llama9"):
            ollama.check_chat_model("llama9")
        _, service = build(tmp_path, checker=ollama)
        with pytest.raises(ValueError, match="cannot use tools"):
            service.update({"model_id": "gemma3:4b"})

    def test_unreachable_ollama(self):
        def down(request):
            raise httpx.ConnectError("refused")
        ollama = OllamaModels("http://ollama.test", transport=httpx.MockTransport(down))
        assert ollama.list_models() == {"reachable": False, "host": "http://ollama.test", "models": []}
        with pytest.raises(ValueError, match="Cannot reach Ollama"):
            ollama.check_chat_model("gemma4")
