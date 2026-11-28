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

## Modules added for the live chat (0.11.0)

| Module | Class | Responsibility |
|:--|:--|:--|
| `steward/tools/tool_paths.py` | `ToolPaths` | Every tool path: Mac/`~` → container path, existence, write checks (`.env` switch must be exactly `rw`) |
| `steward/tools/action_targets.py` | `ActionTargets` | What a move/archive/delete touches (files or whole folders); pre-approval check; card text |
| `steward/folder_actions.py` | `FolderActions` | Files to zip in a folder (skips hidden/private/protected), protected-inside check, remove emptied folders |
| `steward/chat_notices.py` | `ChatNotices` | Steward's own notes from real tool results (practice mode, exact errors) |
| `steward/chat_steps.py` | `ChatSteps` | Agno stream events → plain steps (hand-overs, tools, progress, helper errors) |
| `steward/chat_jobs.py` | `ChatJobs` | Chat jobs with live steps; saves answers (0.12: Stop, 5-minute limit, typed commands, memory) |
| `steward/chat_store.py` | `ChatStore` | Conversations + messages in SQLite (`chat_conversations`, `chat_messages`) |
| `steward/chat_routes.py` | `ChatRoutes` | `/steward/chat/jobs`, `/decisions`, `/conversations`, `/folder` |
| `steward/chat_insights.py` | `ChatInsights` | Folder stats card after a successful `scan_folder` (via `FolderAdvisor`) |

Changed: `ChatService` streams (`listener`), declines impossible steps before the card
(`ChatApprovals.reject_impossible`), adds notes and the folder card; `RecycleManager` recycles
folders as one item and reports archive progress; `OrganizerTools.progress` hook;
`PathMapper.to_local` and display-only `STEWARD_HOST_APP_DIR` mapping; agents get
`tool_call_limit` (team 6 hand-overs, helpers 8 tool calls). A live test once saw gemma4 hand
the same task over 98 times; the limits stop that.

## Modules added for chat control (0.12.0)

| Module | Class | Responsibility |
|:--|:--|:--|
| `steward/chat_workers.py` | `ChatWorkers` | 2 worker threads; a lock per chat keeps one chat in order while another answers |
| `steward/chat_commands.py` | `ChatCommands` | Typed "no" (rejects the waiting card) and "undo that" / "recover it" (undoes the chat's last change) |
| `steward/chat_memory.py` | `ChatMemory` | Notes on the conversation put in front of each question: last answer's paths, folder scanned, approved/REJECTED, real changes from the action log |
| `steward/chat_found.py` | `FoundPaths` | The exact paths the finding tools returned, saved on the answer (`found_paths`) so memory never depends on the AI's wording |
| `steward/tools/file_search.py` | `FileSearch` | Find by name and largest files: SQLite index first, then a capped walk of the watched folders (no scan needed) |
| `steward/tools/finder_tools.py` | `FinderTools` | Scanner tools `find_files` and `list_folder` |
| `steward/data_cleanup.py` | `DataCleanup` | Clear chats (+ Agno `web-` sessions, waiting cards), knowledge notes, topics; empty the recycle bin; restore |
| `steward/data_backups.py` | `DataBackups` | Backups in `data/backups` (chats JSON, notes ZIP); safe names; ZIP restores only `.md` inside the bundle |
| `steward/data_routes.py` | `DataRoutes` | `/steward/data`, `/data/clear`, `/data/backups/{id}/restore|delete`; permanent actions need `confirm: "DELETE"` |

Changed: `ChatService.decide` answers a rejection itself and `ChatApprovals.settle_rejected` declines
retries; `ChatJobs` raises `ChatStopped` (a `BaseException`, so no `except Exception` swallows it)
from the event listener on Stop or after 5 minutes, and records `actions` from
`OrganizerTools.done_actions`; `OrganizerTools.progress`/`done_actions` are per thread (two jobs at
once); the team passes history to helpers (`add_team_history_to_members`).

### Live chat job

```mermaid
sequenceDiagram
    participant UI as ChatProvider (browser)
    participant R as ChatRoutes
    participant J as ChatJobs (worker pool)
    participant C as ChatService
    participant T as Agno Team (streaming)
    UI->>R: POST /steward/chat/jobs {message, session_id}
    R->>J: ask() → question saved; typed no/undo handled here; job queued
    R-->>UI: 202 {job: queued}
    J->>C: answer(ChatMemory notes + message, listener → ChatSteps.handle, Stop check)
    C->>T: team.run(stream=True, stream_events=True, yield_run_output=True)
    T-->>J: events → steps ("Handing over to Scanner", "Scanning …", progress)
    loop every second
        UI->>R: GET /steward/chat/jobs/{id}
        R-->>UI: {status: running, steps, thinking}
    end
    T-->>C: final TeamRunOutput → ok / approval / error (+ notes, folder card)
    J->>J: answer saved in ChatStore, job done
    UI->>R: GET /steward/chat/jobs/{id} → {status: done, result}
```

The browser state lives in `ChatProvider` (above the routes), so leaving the Chat page does not
stop polling; on load it reads `GET /steward/chat/conversations/{id}` and resumes `active_job`.

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

Chat jobs live in memory (a restart drops a running answer; the question stays saved). At most two
chat answers run at a time (one per chat). Deleted files remain in SQLite/RAG/OKF (#4, partly mitigated), identical files share one RAG entry
(#5), OKF summaries are raw previews (#6), API and worker both write ChromaDB/SQLite (#12).
