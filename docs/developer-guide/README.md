# Steward Developer Guide

For people who change Steward's code. For using Steward, see the [User Guide](../user-guide/README.md).

| Page | Contents |
|:--|:--|
| [Architecture](architecture.md) | How the web UI, API, services and stores fit together; request flows with diagrams |
| [API reference](api-reference.md) | Every `/steward/*` route with real example requests and responses |
| [Frontend](frontend.md) | Code map, design system, data-loading patterns, **how to add a page** |
| [Docker & configuration](docker-and-config.md) | Services, volumes, every environment variable, the settings override order |
| [Testing](testing.md) | pytest, Vitest, and how the live browser checks were done |

## Quick start for development

```bash
uv sync                                   # Python deps
uv run python -m steward.api              # API on http://127.0.0.1:7777  (http://127.0.0.1:7777/docs for Swagger)
cd frontend && npm install && npm run dev # UI on http://127.0.0.1:5173 (proxies /steward → :7777)
uv run pytest                             # 85 Python tests (no Ollama needed)
cd frontend && npm test                   # 22 Vitest tests
```

## House rules (from `project-skill.md` and the feature workflow)

- Python, class-based, **no type hints**, functions ≤ 50 lines, files ≤ 200 lines. Check with
  `python ~/.claude/skills/feature-dev/scripts/check_rules.py <files>`.
- Frontend: plain JavaScript (no TypeScript), one component per file, files ≤ 200 lines.
- The UI talks **only** to `/steward/*`. It never reads files or calls models (PRD p.14).
- Anything that changes files must go through a `proposed` action and a human decision.
- Tests never need Ollama: use `HashEmbedder`, fake teams/runs, `httpx.MockTransport`.
