"""Shared pytest setup: keep the developer's own .env out of the tests."""

import pytest

# Every setting Steward reads from .env (see .env.example).
STEWARD_ENV_VARS = (
    "STEWARD_CONFIG_PATH",
    "STEWARD_LOG_LEVEL",
    "STEWARD_MODEL_PROVIDER",
    "STEWARD_MODEL_ID",
    "STEWARD_DRY_RUN",
    "OLLAMA_HOST",
    "DOCKER_OLLAMA_HOST",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
)


@pytest.fixture(autouse=True)
def isolate_from_dotenv(monkeypatch):
    """Blank Steward's .env variables before every test.

    Config() loads the repo's .env into os.environ, and that would leak into
    every later test (for example STEWARD_DRY_RUN=false turning dry-run off).
    An empty value counts as "not set" in Steward, and load_dotenv never
    overwrites a variable that already exists, so the real .env is ignored.
    Tests that need a value still set it with monkeypatch.setenv.
    """
    for name in STEWARD_ENV_VARS:
        monkeypatch.setenv(name, "")
