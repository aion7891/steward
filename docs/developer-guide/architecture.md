# Architecture

## Big picture

```mermaid
flowchart LR
    subgraph Browser
        UI["React app (frontend/)<br/>Dashboard · Scan · Chat · Reports · Settings"]
    end
    subgraph web["steward-web (nginx, :8080)"]
        N["static files + /steward/* proxy<br/>CSP, gzip, SPA fallback"]
    end
    subgraph api["steward-api (AgentOS + FastAPI, :7777)"]
        R1["api.py<br/>health · scan · chat · actions · reports(legacy)"]
        R2["web_routes.py<br/>dashboard · folders · execute · settings · models · reports"]
        S["Services"]
    end
    subgraph worker["steward-worker"]
        W["APScheduler: scan hourly · cleanup daily · report weekly<br/>Downloads watcher"]
    end
    UI --> N --> R1 & R2 --> S
    S --> DB[("SQLite<br/>data/steward.db")]
    S --> VS[("ChromaDB<br/>chroma/")]
    S --> OKF[("OKF notes<br/>knowledge/")]
    S --> OL["Ollama on the host"]
    W --> DB & VS & OKF
```

## Modules added for the web UI (0.10.0)

| Module | Class | Responsibility |
|:--|:--|:--|
| `steward/web_routes.py` | `WebRoutes` | Registers the web-UI routes; builds the services below |
| `steward/dashboard.py` | `DashboardService` | Status cards, to-do, approved-waiting, suggestions, categories, patterns |
| `steward/daily_stats.py` | `DailyStats` | Per-day series in the **browser's** time zone (`tz_offset`) |
| `steward/folder_advisor.py` | `FolderAdvisor` | Folder-scoped findings (skips deleted files), suggestions (union bytes), proposals |
| `steward/proposals.py` | `ProposalService` | Creates `proposed` actions only; skips protected paths; never duplicates |
| `steward/scan_jobs.py` | `FolderScanJobs` | One background folder scan at a time; steps + progress |
| `steward/scan_job_store.py` | `ScanJobStore` | Persists jobs in SQLite (`folder_scan_jobs`); interrupted jobs → failed |
| `steward/path_mapper.py` | `PathMapper` | Validates folder input; Mac path ⇄ Docker path (`/data/...`), `to_host_deep` for responses |
| `steward/chat_service.py` | `ChatService` | Runs the team per `session_id`; maps run status to `ok/error/approval` |
| `steward/chat_sources.py` | `ChatSources` | Sources from what agents actually used (references + tool calls) |
| `steward/chat_approvals.py` | `ChatApprovals` | Holds paused runs; describes steps; confirm/reject |
| `steward/settings_service.py` | `SettingsService` | Validates + saves UI settings to `data/settings.override.yaml`; `.env` locks |
| `steward/ollama_models.py` | `OllamaModels` | Installed models + capabilities (tools / embedding / cloud) |
| `steward/report_service.py` | `ReportService` | Report library, read, download (inside `reports_dir` only), generate |

Changed existing modules: `api.py` (wiring, chat routes, `_rebuild_agents`), `workflows.py`
(CleanupWorkflow proposes only), `agents.py` (routing instructions, Analyzer gets RAG),
`tools/organizer_tools.py` (`_safe_dry_run`), `rag.py` (`_safe_upsert`), `config.py`
(`load_ui_overrides`), `worker.py` (reload overrides before scans).

## Key flows

### Folder scan

```mermaid
sequenceDiagram
    participant UI as Scan page
    participant R as POST /steward/folders/scan
    participant M as PathMapper
    participant J as FolderScanJobs (thread)
    participant A as FolderAdvisor
    participant P as ProposalService
    UI->>R: {path:"/Users/you/Demo", create_proposals:true}
    R->>M: resolve() → /data/Extra (400 if missing/system/outside mounts)
    R->>J: start() (409 if one is running) → 202 {job}
    J->>J: scanner.scan_all([folder]) (+ RAG index if asked)
    J->>A: findings_for(folder) → suggestions_for(...)
    J->>P: propose_many(temp files + extra duplicate copies)
    J-->>UI: GET /folders/scan/{id} polled every 1 s → done + result
```

### Chat with approval

```mermaid
sequenceDiagram
    participant UI as Chat page
    participant C as ChatService
    participant T as Agno Team
    participant A as ChatApprovals
    UI->>C: POST /steward/chat {message, session_id}
    C->>T: team.run(message, session_id)
    T-->>C: run.status = PAUSED (delete_files needs confirmation)
    C->>A: add(run) + describe(run)
    C-->>UI: {status:"approval", run_id, approvals:[…]}
    UI->>C: POST /steward/chat/{run_id}/decision {approve:true}
    C->>A: pop(run_id) + confirm()/reject()
    C->>T: team.continue_run(run_response, requirements)
    T-->>C: COMPLETED (tool ran with dry-run enforced)
    C-->>UI: {status:"ok", reply, sources}
```

**Dry-run is enforced in the tool**, not in the prompt: `OrganizerTools._safe_dry_run()` returns
`True` whenever `safety.dry_run` is on, whatever `dry_run` the model passed.

### Action life cycle

```mermaid
stateDiagram-v2
    [*] --> proposed: ProposalService / plan_organize
    proposed --> approved: /approve (dry-run ON → stays approved = "waiting")
    proposed --> rejected: /reject
    approved --> done: /approve or /execute with dry-run OFF
    approved --> failed: error
    done --> undone: /undo
```

## Settings precedence

`defaults in config.py` < `config.yaml` (or `config.docker.yaml`) < `data/settings.override.yaml`
(written by the Settings page) < **`.env` / environment variables**. Settings fixed by a non-empty
env var are reported as `locked` and refused by `PUT /steward/settings`.

## Known limitations (see `review-system/08-issues-and-risks.md`)

Deleted files remain in SQLite/RAG/OKF (#4, partly mitigated), identical files share one RAG entry
(#5), OKF summaries are raw previews (#6), API and worker both write ChromaDB/SQLite (#12).
