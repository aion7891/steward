# Changelog

All notable changes to Steward are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
