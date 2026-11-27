# API reference

Base URL: `http://127.0.0.1:7777` (direct) or `http://127.0.0.1:8080` (through nginx in Docker).
Interactive docs: `/docs`. Errors are FastAPI style: `{"detail": "readable message"}`.
Examples below are **real responses** captured from a running stack (trimmed with `…`); paths are
shown as Mac paths because responses pass through `PathMapper.to_host_deep`.

## Status and dashboard

### `GET /steward/health`

```json
{"status": "ok", "pending_actions": 3,
 "models": {"chat_provider": "ollama", "chat_model": "gemma4", "host": "http://host.docker.internal:11434", …},
 "safety": {"dry_run": true, "require_confirmation": true, "move_to_recycle_first": true}, …}
```

### `GET /steward/dashboard?days=14&tz_offset=-330`

`days` 1–90; `tz_offset` = JavaScript `Date.getTimezoneOffset()` (minutes behind UTC, −840…840). Both validated → 400.

```json
{"status": {"last_scan_at": "2026-11-27T08:52:52+00:00", "files_tracked": 14, "total_size_bytes": 3191145,
            "files_indexed": 10, "scans_today": 3, "files_checked_today": 39, "files_changed_today": 14,
            "pending_actions": 3, "approved_waiting": 1, "errors_24h": 0, "reclaimable_bytes": 884, …},
 "daily": [{"date": "2026-11-27", "scans": 3, "files_checked": 39, "files_changed": 14, "errors": 0,
            "downloads": 0, "proposals": 5, "actions_done": 1}, …],
 "todo": [{"id": 5, "action_type": "delete", "source_path": "/Users/you/Demo/Downloads/invoice-q3 (1).pdf",
           "reason": "Duplicate of …", "status": "proposed", "size_bytes": 765, …}],
 "approved_waiting": […], "suggestions": […], "findings": {…}, "categories": […],
 "recent_scans": […], "patterns": [{"title": "…", "description": "…"}],
 "system": {"provider": "ollama", "model": "gemma4", "cloud_model": false, "dry_run": true}}
```

## Folder scans

### `GET /steward/folders/roots`

```json
{"status": "ok", "in_docker": true,
 "roots": [{"label": "Demo", "host_path": "/Users/you/Demo", "path": "/data/Extra", "available": true}]}
```

### `POST /steward/folders/scan` → 202

Body: `{"path": "/Users/you/Demo/Downloads", "create_proposals": true, "index_for_chat": false}`

```json
{"job": {"id": "ace14958b81d", "status": "running", "step": "scanning", "progress": 10,
         "display_path": "/Users/you/Demo/Downloads",
         "options": {"create_proposals": true, "index_for_chat": false}, …}}
```

| Error | When |
|:--|:--|
| 400 `Please enter a folder path.` / `… is a file, not a folder.` / `'/' is too broad to scan…` / `… is a system folder…` | Bad input |
| 400 `Folder not found: /Users/you/Pictures. Steward runs in Docker and can only see these folders: /Users/you/Demo. To scan another folder, set STEWARD_EXTRA_DIR in .env and restart.` | Outside the mounts |
| 409 `A folder scan is already running…` | One job at a time |

### `GET /steward/folders/scan/{job_id}` (404 if unknown)

```json
{"job": {"status": "done", "progress": 100, …,
  "result": {"scan": {"files_seen": 4, "hashed_files": 0, "unchanged_files": 4, "errors": 0},
             "findings": {"duplicates": {"count": 1, "extra_copies": 1, "total_bytes": 765, "items": […]},
                          "temp_files": {"count": 1, "total_bytes": 23, "items": […]}, …},
             "suggestions": [{"priority": "high", "kind": "deduplicate", "title": "Remove 1 duplicate copy(ies)",
                              "reason": "Identical copies exist; the oldest copy is kept.", "paths": […]}],
             "reclaimable_bytes": 788,
             "proposals": {"created": […], "already_open": […], "skipped_protected": […]},
             "protected": false}}}
```

### `GET /steward/folders/scans?limit=10`

Recent jobs, newest first, without `result` (memory + SQLite `folder_scan_jobs`).

## Actions

| Route | Body | Result |
|:--|:--|:--|
| `GET /steward/actions?status=proposed&limit=50` | | `{"actions": [...]}` |
| `POST /steward/actions/{id}/approve` | `{"execute": true, "dry_run": null}` | `dry_run` (preview, stays `approved`) / `done` / `blocked` / `failed` |
| `POST /steward/actions/{id}/execute` | `{"dry_run": null}` | Runs an already-approved action; 404 unknown, 400 bad id |
| `POST /steward/actions/{id}/reject` | `{"reason": "…"}` | `rejected` |
| `POST /steward/actions/{id}/undo` | | `undone` + `restored` paths |

## Chat

### `POST /steward/chat`

Body: `{"message": "How much is due on the Acme invoice?", "session_id": "web-…"}` (400 if empty)

```json
{"status": "ok", "session_id": "web-…", "reply": "The amount due … is 4,800 USD …",
 "sources": [{"kind": "file", "label": "invoice-q3 (1).pdf", "path": "/Users/you/Demo/Downloads/invoice-q3 (1).pdf"},
             {"kind": "note", "label": "acme", "path": "projects/acme.md"}]}
```

`status: "error"`: model failure (for example Ollama down), `sources: []`.
`status: "approval"`: the AI wants to change files:

```json
{"status": "approval", "run_id": "…", "session_id": "web-…",
 "reply": "Steward wants to change files and needs your approval.",
 "approvals": [{"tool": "delete_files", "agent": "OrganizerAgent",
                "summary": "Move 1 file(s) to Steward's recycle bin", "names": ["report.tmp"],
                "paths": ["/Users/you/Demo/Downloads/report.tmp"], "reason": "…", "dry_run": true}]}
```

### `POST /steward/chat/{run_id}/decision`

Body: `{"approve": true}` (must be a JSON boolean → else 400). Returns the same shape as `/chat`.
404: `No approval is waiting for run … It may have been decided already.`

## Settings

### `GET /steward/settings`

```json
{"models": {"provider": "ollama", "model_id": "gemma4", …},
 "safety": {"dry_run": true, "protected_paths": ["/data/Extra/Documents/Work/Clients"], …},
 "watched_folders": ["/data/Extra/Documents", …],
 "folders": [{"path": "/data/Extra/Documents", "display_path": "/Users/you/Demo/Documents", "available": true}, …],
 "scheduler": {"scan_interval_minutes": 60, …}, "locked": {}, "override_file": "/app/data/settings.override.yaml"}
```

### `PUT /steward/settings`

Body: any of `dry_run`, `provider`, `model_id`, `watched_folders`. Returns the new settings or 400:
`'dry_run' must be true or false.` · `'dry_run' is set by STEWARD_DRY_RUN in .env…` ·
`Model 'gemma3:4b' cannot use tools…` · `Model 'x' is not installed in Ollama. Install it with: ollama pull x` ·
`Set OPENAI_API_KEY in .env…` · `… is already inside …` · `These settings cannot be changed here: …`.
A provider/model change rebuilds the agents.

### `GET /steward/models`

```json
{"providers": ["ollama", "openai", "anthropic", "gemini"],
 "ollama": {"reachable": true, "host": "…",
            "models": [{"name": "gemma4:latest", "size_bytes": 9461576343, "tools": true, "embedding": false, "cloud": false}, …]}}
```

## Reports

| Route | Result |
|:--|:--|
| `GET /steward/reports/library?limit=30` | `{"reports": [{"key": "steward_weekly_20261127-085222", "period": "weekly", "created_at": "…", "formats": {"html": {"id": 2, "available": true}, "markdown": {"id": 1, "available": true}}}]}` |
| `POST /steward/reports/generate` `{"period": "weekly"}` | `{"message": "New weekly report ready with 5 suggestions.", "report": {…}}`; 400 for other periods than weekly/daily/monthly |
| `GET /steward/reports/{id}` | `{"report": {"id": 1, "format": "markdown", "name": "….md", "content": "# Steward Activity Report …"}}` |
| `GET /steward/reports/{id}/download` | File (attachment). 404 unknown/missing, 400 if the stored path is outside `reports_dir` |

## Older routes (kept for the CLI and the legacy Streamlit UI)

`POST /steward/scan` (ScanWorkflow) · `GET/POST /steward/reports` (raw rows / generate) ·
`GET /steward/recommendations` · plus the routes AgentOS adds for agents, the team and workflows
(listed on the `/docs` page of the running API).
