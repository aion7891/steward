# Changelog

All notable changes to Steward are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.11.0] - 2026-11-28

A live, trustworthy chat: it finds the folders you name, works on whole folders, keeps going
while you use other pages, and shows every step. Fixes the problems found while testing 0.10.0.

### Added
- **Live chat jobs**: answers run on the server (`ChatJobs`, one at a time) and the page polls
  them, so switching tabs, reloading or restarting Steward never loses an answer silently.
  Routes: `POST /steward/chat/jobs`, `GET /steward/chat/jobs/{id}`, `POST /steward/chat/decisions`.
- **Live steps** (`ChatSteps`) from Agno's event stream: hand-overs between helpers, each tool
  call with its result, progress of long actions ("Archiving docs (13/33)"), failed helpers.
- **Saved conversations** in SQLite (`ChatStore`) with **Recent chats** and **New chat** in the
  sidebar. Routes: `GET/DELETE /steward/chat/conversations[/{id}]`.
- **New chat design**: centred composer with suggestions when empty, plain answers with a
  collapsible "Worked 9 s · Scanner · 2 steps" line, a **stats card** after a scan (from SQLite,
  `ChatInsights`), and a **workspace panel** (folder numbers, clickable suggestions that name the
  exact files, approvals, live activity). Light/dark, phone layout. `GET /steward/chat/folder`.
- **Whole-folder actions**: archive (hidden, private and protected files are left in place;
  emptied folders removed), recycle (one item) and move a folder; one **Undo** restores all.
  Approval cards say "Zip folder docs (33 files) into an archive".
- **Opt-in write access** in Docker: `STEWARD_DESKTOP_ACCESS`, `STEWARD_DOCUMENTS_ACCESS`,
  `STEWARD_EXTRA_ACCESS` (default `ro`); Settings shows *writable* / *read-only* per folder.
- **Steward's own notes** under answers (`ChatNotices`), based on real tool results:
  practice mode ("no files were changed") and exact error messages.
- Tests: 38 new Python tests (85 → 123) and 13 Vitest tests (22 → 35); a 5-step end-to-end chat
  scenario passed 3/3 runs with gemma4.

### Changed
- Chat tools accept Mac paths (`/Users/you/…`, `~/…`) and translate them (`ToolPaths`), also for
  reading documents and moving files.
- Steps that cannot work (missing file, read-only folder, protected folder inside) are declined
  **before** the approval card, with the reason and the fix.
- The team stops after 6 hand-overs and each helper after 8 tool calls (`tool_call_limit`); a live
  test once saw gemma4 hand the same task over 98 times.
- The Organizer no longer asks for optional details (archive name, reason) before acting.
- Steward's own folders (`/app/data/...`), protected folders and the settings file are shown as
  Mac paths (`STEWARD_HOST_APP_DIR`).

### Fixed
- Scanning a folder from the chat reported "0 files" (the scanner skipped unknown folders silently).
- Archiving or deleting a folder failed with "no existing files".
- The chat answer was lost when switching to another page.
- The AI could claim a file was deleted while practice mode only previewed it.
- `STEWARD_DESKTOP_ACCESS=yes` (or `false`) would have made the Desktop writable, because Docker
  treats any value except `ro` as read-write; Steward now requires exactly `rw`.
- The test suite no longer reads the developer's own `.env` (`tests/conftest.py`).

## [0.10.0] - 2026-11-27

A professional web app for Steward, plus fixes for the most serious issues found in the
system review (`review-system/`).

### Added
- **Web app** (`frontend/`, React + Vite, plain JavaScript) served by nginx in Docker at
  `http://127.0.0.1:8080`, with light/dark mode and five pages:
  - **Dashboard**: status cards, daily scan chart (local time), To-do with Approve / Reject,
    "Approved, waiting to run" with Run now, Recently completed with Undo, suggestions,
    file types, work habits, recent scans.
  - **Scan a folder**: type a Mac path or use a quick pick; background job with live progress;
    folder-only findings, suggestions and ready-to-approve proposals; history kept across restarts.
  - **Chat**: Markdown answers, "Looked at" sources, approval cards for file changes, Retry,
    per-conversation sessions, history in the browser.
  - **Reports**: report library, Generate now, styled report in a sandboxed frame, downloads.
  - **Settings**: dry-run switch, AI model picker (tool support and cloud models marked),
    watched folders editor, schedule; `.env`-locked settings shown as locked.
- API routes: `/steward/dashboard`, `/steward/folders/roots|scan|scan/{id}|scans`,
  `/steward/actions/{id}/execute`, `/steward/chat/{run_id}/decision`, `/steward/models`,
  `/steward/reports/library|generate|{id}|{id}/download`; `PUT/GET /steward/settings` rewritten.
- Services: `DashboardService`, `DailyStats`, `FolderAdvisor`, `ProposalService`, `FolderScanJobs`,
  `ScanJobStore`, `PathMapper`, `ChatService`, `ChatSources`, `ChatApprovals`, `SettingsService`,
  `OllamaModels`, `ReportService`, `WebRoutes`.
- Docker service `steward-web` (non-root nginx, CSP and security headers, health check) and an
  optional read-only extra folder (`STEWARD_EXTRA_DIR`); Mac paths are translated to container paths.
- Documentation: `docs/user-guide/` (illustrated), `docs/developer-guide/` (architecture, API
  reference, frontend, Docker & config, testing), `review-system/11-whats-new-0.10.md`.
- Tests: 48 new Python tests (37 → 85) and 22 Vitest tests.

### Changed
- **Default chat model is now `gemma4`** (`gemma3:4b` cannot use tools, so every agent failed).
- Settings saved from the UI go to `data/settings.override.yaml`; `config.yaml` is never rewritten.
  Order: defaults < config.yaml < override file < `.env`.
- Team routing: questions about document contents go to the ChatAgent; the AnalyzerAgent can
  search documents too (invoice demo question 3/6 → 7/8 correct).
- Chat sources are the files and notes the agents actually used, not a separate keyword search.
- Dashboard days follow the browser's time zone.
- The Streamlit UI moved behind the `legacy` Docker Compose profile.
- `.env.example` no longer sets model and dry-run overrides by default.
- Version numbers aligned to 0.10.0 (`pyproject.toml` said 0.1.0, the package 0.9.0).

### Fixed
- CleanupWorkflow approved its own proposals and re-created them every run (review #1, #3).
- Chat runs that paused for approval could never be completed (review #2).
- Actions approved during dry-run got stuck (now "Approved, waiting to run" + Run now).
- `/steward/chat` returned `status: ok` when the model failed (Agno reports errors in the run status).
- `steward --index` crashed when Ollama was not running; failures are now counted per file.
- Settings: `"false"` was read as true; saving wiped `config.yaml` comments; changes were lost in Docker.
- Folder suggestions counted the same file several times in "space you can free".
- Root `.gitignore` patterns (`reports/`, `data/`, …) ignored same-named folders anywhere in the repo.

### Security
- The AI can no longer turn dry-run off: `OrganizerTools` always applies the configured dry-run
  (previously `dry_run=False` from the model overrode it).
- Reports are only served from the reports folder; HTML reports render in `<iframe sandbox="">`.
- Chat answers render links and images as plain text; document text is never rendered as HTML.
- Ollama "cloud" models are flagged and trigger the cloud-model warning.

## [0.9.0] - 2026-11-26

First complete version: phases 1–9 (configuration, scanning, RAG, OKF knowledge bundle, Agno
agents and workflows, organizing with undo, recommendations and reports, AgentOS API with a
Streamlit UI, Docker deployment). See `docs/phase-*.md`.
