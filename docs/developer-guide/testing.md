# Testing

## Automated tests

| Suite | Command | Count | Needs Ollama? |
|:--|:--|--:|:-:|
| Python (pytest) | `uv run pytest` | 156 | No |
| Frontend (Vitest) | `cd frontend && npm test` | 40 | No |
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

### Python test files added for the live chat (0.11.0)

| File | Covers |
|:--|:--|
| `tests/conftest.py` | Blanks Steward's `.env` variables for every test (the real `.env` used to leak in) |
| `tests/test_tool_paths.py` | Mac/`~`/container paths in every tool, missing and read-only folders (mutation-checked) |
| `tests/test_chat_notices.py` | Practice-mode note when the AI claims a delete; impossible steps declined before the card |
| `tests/test_folder_actions.py` | Archive/recycle/move a folder, Undo, hidden/private skipped, protected inside, progress (mutation-checked) |
| `tests/test_write_access.py` | Only exactly `rw` allows changes; Settings badge; display paths; compose defaults |
| `tests/test_chat_jobs.py` | Stream events → steps, job API, approval via jobs, conversations, Mac paths, tool limits |
| `tests/test_chat_insights.py` | Folder card from a real scan, fresh card route |

### Python test files added for chat control (0.12.0)

| File | Covers |
|:--|:--|
| `tests/test_chat_control.py` | Rejection reply + declined retries (no zip), typed "no", "undo that" once, practice mode, Stop + `cancel_run`, 5-minute limit, stop route |
| `tests/test_chat_memory.py` | Paths in text, paths the tools found first (`FoundPaths`), last-answer paths first, REJECTED notes, real places (never the recycle path), "delete the file" carries the path, team history to helpers |
| `tests/test_data_cleanup.py` | Summary, clear with backup + restore (twice), DELETE required, 409 while answering, Agno sessions, topics only, recycle bin, backup names, ZIP cannot escape |
| `tests/test_new_user.py` | Find by name / pattern and largest file before any scan, list a folder, "recover it", two chats at once, one chat in order, per-thread tool state, delete one chat |

Streaming fakes: `Streamed` in `tests/test_chat_control.py` turns the `SimpleNamespace` runs of
`FakeTeam` into real `TeamRunOutput`s, because chat jobs always stream.

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

### The 0.11.0 chat scenario (end to end)

Run 3 times from a fresh start (Desktop shared writable, dry-run off, real gemma4, real web UI):
"can you scan ~/Desktop/docs" → stats card and panel → "can you archive it" (approve; live
progress "Archiving docs (13/33)") → "delete ~/Desktop/old-report.txt" (approve) → every answer
shows its steps. Each step was checked on disk. **3/3 runs passed all 5 steps**, 2–23 s per answer.
Wait for the *Working…* bubble to appear before checking that an answer finished: right after
sending, the page has not yet started the job.

### The 0.12.0 new-user scenario (end to end)

A fresh Steward that never scanned (index empty), real gemma4, real web UI, dry-run off:
"can you search for a file named invoice" → "can you tell me the largest file name" → "can you
delete it" (approve) → "can you recover it" → "can you archive it" (approve) → a second chat with a
long question while chat 1 lists a folder → delete chat 2 from Recent chats. Checked on disk and
through the API: **7/7 steps passed** (chat 1 answered in 29 s while chat 2 took 67 s). The first run
found two bugs (archive used Steward's recycle path from the memory notes; no folder-listing tool),
both fixed before the passing run. Phase checks also covered Reject → no zip, typed "no", Stop,
Settings → Data & cleanup (clear + restore, delete for good, empty recycle bin).
