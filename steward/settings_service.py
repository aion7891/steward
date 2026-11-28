"""Reads and safely changes the settings the web UI is allowed to edit."""

import os

import yaml

from steward.config import AppConfig
from steward.models import ModelFactory
from steward.tools.tool_paths import ToolPaths

OVERRIDE_HEADER = (
    "# Settings saved from the Steward web UI. They are applied on top of config.yaml\n"
    "# (config.yaml itself is never rewritten). Values in .env still win.\n"
    "# Delete this file to go back to the values in config.yaml.\n"
)


class SettingsService:
    """Validates UI setting changes and saves them to data/settings.override.yaml."""

    EDITABLE = ("dry_run", "provider", "model_id", "watched_folders")
    # Settings that a non-empty .env variable controls; the UI cannot change these
    ENV_LOCKS = {"provider": "STEWARD_MODEL_PROVIDER", "model_id": "STEWARD_MODEL_ID", "dry_run": "STEWARD_DRY_RUN"}

    def __init__(self, config, mapper, models_checker=None, on_model_change=None, env=None):
        """Store the services needed to validate and apply settings.

        Args:
            config: the live AppConfig (changes apply to it immediately).
            mapper: PathMapper used to validate watched folders (same rules as "Scan a folder").
            models_checker: OllamaModels used to check a chosen Ollama model (None = no check).
            on_model_change: callback run after the provider or model changed (rebuilds the agents).
            env: optional dict replacing os.environ (used by tests).
        """
        self.config = config
        self.mapper = mapper
        self.models_checker = models_checker
        self.on_model_change = on_model_change
        self.env = os.environ if env is None else env

    def current(self):
        """Return the settings the UI shows, including which ones .env locks."""
        folders = []
        for raw in self.config.get("scanner.watched_folders", []):
            path = self.config._resolve_path(raw)
            folders.append({
                "path": str(path), "display_path": self.mapper.to_host(path), "available": path.is_dir(),
                # Docker shares Desktop/Documents read-only unless .env opts in (STEWARD_*_ACCESS=rw)
                "writable": path.is_dir() and ToolPaths(self.mapper).is_writable(path),
                "access_var": ToolPaths.access_var(path),
            })
        return {
            "status": "ok",
            "models": self.config.get("models"),
            "safety": self.mapper.to_host_deep(self.config.get("safety")),  # protected folders as Mac paths
            "watched_folders": self.config.get("scanner.watched_folders", []),  # kept for the legacy UI
            "folders": folders,
            "scheduler": self.config.get("scheduler"),
            "locked": self.locked(),
            "override_file": self.mapper.to_host(str(self.config.override_path())),
        }

    def locked(self):
        """Return {setting: env var} for settings fixed by a non-empty .env value."""
        return {field: var for field, var in self.ENV_LOCKS.items() if str(self.env.get(var, "")).strip()}

    def update(self, payload):
        """Validate, apply and save a change; raise ValueError with a clear message on bad input.

        Args:
            payload: dict with any of dry_run, provider, model_id, watched_folders.
        """
        if not isinstance(payload, dict) or not payload:
            raise ValueError("Send at least one setting to change.")
        unknown = sorted(set(payload) - set(self.EDITABLE))
        if unknown:
            raise ValueError(f"These settings cannot be changed here: {', '.join(unknown)}.")
        for field, var in self.locked().items():
            if field in payload:
                raise ValueError(f"'{field}' is set by {var} in .env, so it can't be changed here. "
                                 "Edit or remove that line in .env and restart Steward.")
        changes = {}
        if "dry_run" in payload:
            changes["safety"] = {"dry_run": self.parse_bool(payload["dry_run"])}
        model_changes = self._model_changes(payload)
        if model_changes:
            changes["models"] = model_changes
        if "watched_folders" in payload:
            changes["scanner"] = {"watched_folders": self._folders(payload["watched_folders"])}
        self._save(changes)
        if model_changes and self.on_model_change is not None:
            self.on_model_change()
        return self.current()

    @staticmethod
    def parse_bool(value):
        """Accept true/false (and yes/no, 1/0, on/off as text); anything else is a ValueError."""
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("true", "yes", "1", "on"):
            return True
        if text in ("false", "no", "0", "off"):
            return False
        raise ValueError("'dry_run' must be true or false.")

    def _model_changes(self, payload):
        """Validate a provider/model change (installed + can use tools, or API key present)."""
        if not {"provider", "model_id"} & set(payload):
            return {}
        provider = str(payload.get("provider", self.config.get("models.provider"))).strip().lower()
        if provider not in AppConfig.VALID_PROVIDERS:
            raise ValueError(f"Unknown provider '{provider}'. Choose one of: {', '.join(AppConfig.VALID_PROVIDERS)}.")
        model_id = str(payload.get("model_id", self.config.get("models.model_id")) or "").strip()
        if not model_id or len(model_id) > 200:
            raise ValueError("Please enter a model name.")
        if provider == "ollama" and self.models_checker is not None:
            self.models_checker.check_chat_model(model_id)
        key_var = ModelFactory.CHAT_PROVIDERS[provider]["api_key_env"]
        if key_var and not str(self.env.get(key_var, "")).strip():
            raise ValueError(f"Set {key_var} in .env (and restart Steward) before switching to {provider}.")
        return {"provider": provider, "model_id": model_id}

    def _folders(self, value):
        """Validate watched folders with the same rules as "Scan a folder"; returns container paths."""
        if not isinstance(value, list) or not value:
            raise ValueError("Keep at least one watched folder.")
        resolved = []
        for raw in value:
            path = str(self.mapper.resolve(raw))
            if path not in resolved:
                resolved.append(path)
        for path in resolved:
            # A folder inside another watched folder would be scanned twice
            parent = next((other for other in resolved if other != path and path.startswith(other.rstrip("/") + "/")), None)
            if parent:
                raise ValueError(f"'{self.mapper.to_host(path)}' is already inside '{self.mapper.to_host(parent)}', "
                                 "which is scanned with everything in it. Remove one of them.")
        return resolved

    def _save(self, changes):
        """Merge changes into the override file and into the live config."""
        path = self.config.override_path()
        try:
            saved = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, yaml.YAMLError):
            saved = {}
        saved = saved if isinstance(saved, dict) else {}
        self.config._deep_merge(saved, changes)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(OVERRIDE_HEADER + yaml.safe_dump(saved, sort_keys=True), encoding="utf-8")
        self.config._deep_merge(self.config.data, changes)
