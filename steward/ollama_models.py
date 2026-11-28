"""Lists the models installed in Ollama and checks that a chat model can use tools."""

import httpx


class OllamaModels:
    """Talks to Ollama's /api/tags to see which models are installed and what they can do.

    Steward's agents need a chat model with the "tools" capability; gemma3:4b, for example,
    cannot call tools and makes every agent fail.
    """

    def __init__(self, host, timeout=5.0, transport=None):
        """Store where Ollama runs.

        Args:
            host: Ollama URL, e.g. http://localhost:11434.
            timeout: seconds to wait for Ollama.
            transport: optional httpx transport (used by tests).
        """
        self.host = str(host or "http://localhost:11434").rstrip("/")
        self.timeout = float(timeout)
        self.transport = transport

    def list_models(self):
        """Return {"reachable", "host", "models": [{name, size_bytes, tools, embedding, cloud}]}."""
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                response = client.get(f"{self.host}/api/tags")
                response.raise_for_status()
                raw = response.json().get("models", [])
        except (httpx.HTTPError, ValueError):
            return {"reachable": False, "host": self.host, "models": []}
        models = []
        for item in raw:
            capabilities = item.get("capabilities") or []
            models.append({
                "name": item.get("name", ""),
                "size_bytes": int(item.get("size") or 0),
                "tools": "tools" in capabilities,
                "embedding": "embedding" in capabilities,
                # Ollama "cloud" models run on Ollama's servers: data leaves this computer
                "cloud": str(item.get("name", "")).endswith(("-cloud", ":cloud")) or bool(item.get("remote_host")),
            })
        return {"reachable": True, "host": self.host, "models": sorted(models, key=lambda m: m["name"])}

    def check_chat_model(self, model_id):
        """Raise ValueError with a clear fix if model_id is not installed or cannot use tools.

        Args:
            model_id: the Ollama model name, e.g. "gemma4" or "qwen3:4b".
        """
        info = self.list_models()
        if not info["reachable"]:
            raise ValueError(f"Cannot reach Ollama at {self.host}. Start it with `ollama serve` and try again.")
        wanted = str(model_id).strip()
        # "gemma4" and "gemma4:latest" are the same model
        names = {wanted, wanted if ":" in wanted else f"{wanted}:latest"}
        match = next((m for m in info["models"] if m["name"] in names), None)
        if match is None:
            raise ValueError(f"Model '{wanted}' is not installed in Ollama. Install it with: ollama pull {wanted}")
        if not match["tools"]:
            raise ValueError(
                f"Model '{wanted}' cannot use tools, which Steward's agents need. "
                "Pick a model marked 'can use tools' (for example gemma4 or qwen3:4b)."
            )
        return match
