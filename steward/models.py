"""Factory for creating configured Agno chat and embedding models."""

import importlib
import os


class ModelConfigError(Exception):
    """Raised when a model provider is unsupported, missing keys, or unavailable."""


class ModelFactory:
    """Selects and builds Agno LLM and embedding model instances from AppConfig."""

    CHAT_PROVIDERS = {
        "ollama": {
            "module": "agno.models.ollama",
            "class_name": "Ollama",
            "api_key_env": None,
        },
        "openai": {
            "module": "agno.models.openai",
            "class_name": "OpenAIChat",
            "api_key_env": "OPENAI_API_KEY",
        },
        "anthropic": {
            "module": "agno.models.anthropic",
            "class_name": "Claude",
            "api_key_env": "ANTHROPIC_API_KEY",
        },
        "gemini": {
            "module": "agno.models.google",
            "class_name": "Gemini",
            "api_key_env": "GEMINI_API_KEY",
        },
    }

    EMBEDDING_PROVIDERS = {
        "ollama": {
            "module": "agno.knowledge.embedder.ollama",
            "class_name": "OllamaEmbedder",
            "api_key_env": None,
        },
        "openai": {
            "module": "agno.knowledge.embedder.openai",
            "class_name": "OpenAIEmbedder",
            "api_key_env": "OPENAI_API_KEY",
        },
        "gemini": {
            "module": "agno.knowledge.embedder.google",
            "class_name": "GeminiEmbedder",
            "api_key_env": "GEMINI_API_KEY",
        },
    }

    def __init__(self, config, logger=None, class_loader=None):
        """Store configuration, optional logger, and optional custom class loader."""
        self.config = config
        self.logger = logger
        self._class_loader = class_loader or self._default_class_loader

    def list_supported_providers(self):
        """Return sorted lists of supported chat and embedding providers."""
        return {
            "chat": sorted(self.CHAT_PROVIDERS.keys()),
            "embedding": sorted(self.EMBEDDING_PROVIDERS.keys()),
        }

    def describe_active_models(self):
        """Return a summary of the currently configured chat and embedding models."""
        return {
            "chat_provider": self.config.get("models.provider", "ollama"),
            "chat_model": self.config.get("models.model_id", "llama3.2"),
            "host": self.config.get("models.host", "http://localhost:11434"),
            "embedding_provider": self.config.get("models.embedding_provider", "ollama"),
            "embedding_model": self.config.get(
                "models.embedding_model", "nomic-embed-text"
            ),
        }

    def create_chat_model(self, provider=None, model_id=None):
        """Instantiate an Agno chat model for the configured or requested provider."""
        selected_provider = (
            provider or self.config.get("models.provider", "ollama")
        ).lower()
        selected_model = model_id or self.config.get("models.model_id", "llama3.2")

        spec = self._get_provider_spec(self.CHAT_PROVIDERS, selected_provider, "chat")
        api_key = self._require_api_key(spec, selected_provider)
        model_cls = self._load_class(spec["module"], spec["class_name"])

        kwargs = {"id": selected_model}
        if selected_provider == "ollama":
            kwargs["host"] = self.config.get("models.host", "http://localhost:11434")
        elif api_key:
            kwargs["api_key"] = api_key

        self._log_info(
            f"Creating chat model provider='{selected_provider}' model='{selected_model}'"
        )
        return model_cls(**kwargs)

    def create_embedder(self, provider=None, model_id=None):
        """Instantiate an Agno embedder for the configured or requested provider."""
        selected_provider = (
            provider or self.config.get("models.embedding_provider", "ollama")
        ).lower()
        selected_model = model_id or self.config.get(
            "models.embedding_model", "nomic-embed-text"
        )

        spec = self._get_provider_spec(
            self.EMBEDDING_PROVIDERS, selected_provider, "embedding"
        )
        api_key = self._require_api_key(spec, selected_provider)
        embedder_cls = self._load_class(spec["module"], spec["class_name"])

        kwargs = {"id": selected_model}
        if selected_provider == "ollama":
            kwargs["host"] = self.config.get("models.host", "http://localhost:11434")
            kwargs["dimensions"] = int(
                self.config.get("models.embedding_dimensions", 768)
            )
        elif api_key:
            kwargs["api_key"] = api_key

        self._log_info(
            f"Creating embedder provider='{selected_provider}' model='{selected_model}'"
        )
        return embedder_cls(**kwargs)

    def _get_provider_spec(self, registry, provider_name, kind):
        """Look up a provider specification or raise a helpful error."""
        if provider_name not in registry:
            supported = ", ".join(sorted(registry.keys()))
            raise ModelConfigError(
                f"Unsupported {kind} provider '{provider_name}'. "
                f"Supported providers: {supported}"
            )
        return registry[provider_name]

    def _require_api_key(self, spec, provider_name):
        """Verify that a required cloud provider API key exists in the environment."""
        env_var = spec["api_key_env"]
        if not env_var:
            return None
        api_key = os.getenv(env_var, "").strip()
        if not api_key:
            raise ModelConfigError(
                f"Missing required environment variable '{env_var}' "
                f"for provider '{provider_name}'."
            )
        return api_key

    def _load_class(self, module_name, class_name):
        """Load the target Agno class and wrap import issues cleanly."""
        try:
            return self._class_loader(module_name, class_name)
        except (ImportError, AttributeError) as exc:
            raise ModelConfigError(
                f"Could not import '{class_name}' from '{module_name}'. "
                f"Install Agno and provider dependencies before calling this model: {exc}"
            ) from exc

    @staticmethod
    def _default_class_loader(module_name, class_name):
        """Import a module dynamically and retrieve the requested class."""
        module = importlib.import_module(module_name)
        return getattr(module, class_name)

    def _log_info(self, message):
        """Write an informational log message when a logger is attached."""
        if self.logger is not None:
            self.logger.info(message)
