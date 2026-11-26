# Steward Docker image shared by steward-api, steward-worker, and steward-ui
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

# Install uv for fast, reproducible lockfile installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install system build/runtime utilities and curl for container healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install dependencies first for Docker layer caching
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source and Docker config
COPY steward ./steward
COPY scripts ./scripts
COPY config.yaml config.docker.yaml ./
RUN uv sync --frozen --no-dev

EXPOSE 7777 8501

CMD ["python", "-m", "steward.api"]
