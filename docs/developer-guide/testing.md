# Testing

## Automated tests

| Suite | Command | Count | Needs Ollama? |
|:--|:--|--:|:-:|
| Python (pytest) | `uv run pytest` | 85 | No |
| Frontend (Vitest) | `cd frontend && npm test` | 22 | No |
| Frontend build | `cd frontend && npm run build` | n/a | No |
| Code rules | `python ~/.claude/skills/feature-dev/scripts/check_rules.py <files you changed>` | n/a | No |

> Run the rule checker on the files you touch. A few older files (`main.py`, `reporter.py`,
> `recommender.py`, `software.py`, `organizer.py`) were already over 200 lines before 0.10.0.

### Python test files added for the web UI

| File | Covers |
|:--|:--|
| `tests/test_folder_scan.py` | PathMapper validation + Docker mapping, FolderAdvisor scoping, proposals (protected, dedupe), scan jobs (busy, failure) |
| `tests/test_web_api.py` | Dashboard route, folder-scan routes, run-now, cleanup never self-approves, chat status mapping |
| `tests/test_quick_fixes.py` | Mac paths in responses/chat, RAG survives Ollama outage, local days, persisted scan history |
| `tests/test_chat_sources.py` | Sources from real runs (references, file/note tools, failed reads skipped) |
| `tests/test_chat_approvals.py` | Approval card, approve/reject/404/400, **dry-run always wins** (mutation-checked) |
| `tests/test_settings.py` | Override file, `.env` locks, validation, nested folders, Ollama model checks (`httpx.MockTransport`) |
| `tests/test_reports_page.py` | Report library/generate/read/download, path-safety |

### Faking the slow or external parts

| Real thing | Test double |
|:--|:--|
| Ollama embeddings | `HashEmbedder` (`steward/chunker.py`) |
| Agno team runs | `SimpleNamespace` runs with `status`, `content`, `tools`, `references`, `member_responses`, `requirements` (see `tests/test_chat_*.py`) |
| Ollama `/api/tags` | `httpx.MockTransport` passed to `OllamaModels(transport=…)` |
| Background threads | `FolderScanJobs(..., run_inline=True)` |
| Environment | Tests that check settings clear `STEWARD_*` variables, because other tests load the project `.env` into `os.environ` |

### Mutation checks

Two safety tests were verified to **fail on the old code**:
- `test_cleanup_workflow_only_proposes_and_never_repeats`: old `workflows.py` → `assert 2 == 0`
- `test_ai_cannot_turn_a_preview_into_a_real_delete`: without `_safe_dry_run` → the file was really deleted

## Live checks (manual, how they were done)

1. Demo data: `review-system/demo/create_sample_folder.py` builds a fake home folder
   (duplicates, temp, old, large, a secret `.env`, a protected client folder).
2. Start the API on it (`STEWARD_CONFIG_PATH=config.demo.yaml uv run python -m steward.api`), the
   Vite dev server, and **Ollama with gemma4**.
3. Drive headless Chrome via the DevTools protocol (a small script using `websocket-client`):
   type into inputs with React's native value setter, click buttons by text, wait for text, take
   screenshots. Checked: every page in light/dark, errors, approvals in chat, Settings saves, reports
   under the nginx CSP in Docker.
4. For Docker checks, an **isolated** stack (`steward-test-net`, ports 8088) was used so a running
   personal stack was never touched.

Measured with gemma4 on the demo: chat answers 8–13 s; invoice question 7/8 correct with fresh sessions.
