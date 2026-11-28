# Steward

Steward is a local-first, multi-agent AI assistant that runs continuously on your computer to keep files organized, track disk storage and installed software, answer questions about your documents with citations, generate Markdown/HTML reports, and execute cleanup actions safely with approval and undo.

## Safety First
- **Dry-run by default** (`safety.dry_run: true`)
- **Agno HITL confirmation & approval state machine** (`proposed -> approved/rejected -> done/failed -> undone`)
- **Recycle-first & verified ZIP archiving** — never permanently deletes directly; every action is logged in SQLite and OKF `memory/decisions/` for undo
- **Protected paths & privacy filter** — blocks protected folders even if approved, and skips `.env`/key files from reading, ChromaDB, and OKF
- **Local-first privacy** — defaults to local Ollama, SQLite, persistent ChromaDB, OKF v0.3 Markdown bundle, and `127.0.0.1`-only Docker port bindings
- **Read-only by default in Docker** — Desktop and Documents can only be changed after you set `STEWARD_DESKTOP_ACCESS=rw` / `STEWARD_DOCUMENTS_ACCESS=rw`

## The chat (0.11.0)

Type *"can you scan ~/Desktop/docs"*, then *"archive it"*: Steward shows each step live (which
helper, which tool, progress), a stats card with real numbers, a workspace panel with clickable
suggestions, and an approval card before any file changes. Answers keep running while you use
other pages. See the [User Guide](docs/user-guide/04-chat.md) and
[what's new in 0.11](review-system/12-whats-new-0.11.md).

---

## Quick Start (`uv`)

```bash
# 1. Install dependencies and create .venv with uv
uv sync

# 2. (Optional) Create local environment overrides
cp .env.example .env

# 3. Verify setup and run the complete test suite (Phases 1–9)
uv run steward --check
uv run pytest -v
```

### Run Always-On with Docker Compose (recommended, uses native host Ollama)
```bash
# 1. Start Ollama on your Mac (needs: ollama pull gemma4 && ollama pull nomic-embed-text)
ollama serve

# 2. Export host installed apps so the Docker container stays isolated
uv run python scripts/export_host_inventory.py

# 3. Build and launch steward-api, steward-worker, and steward-web
docker compose up -d --build

# 4. Open the web UI: Dashboard, Scan a folder, Chat
open http://127.0.0.1:8080

# Optional: the old Streamlit UI on http://127.0.0.1:8501
docker compose --profile legacy up -d
```

See [Phase 10: Web UI](docs/phase-10-web-ui.md) for scanning extra folders from Docker (`STEWARD_EXTRA_DIR`) and troubleshooting.

### Run Locally for Development (no Docker)
```bash
# Terminal 1: Agno AgentOS FastAPI server on http://127.0.0.1:7777
uv run python -m steward.api

# Terminal 2: Web UI dev server on http://127.0.0.1:5173 (proxies /steward to :7777)
cd frontend && npm install && npm run dev

# Terminal 3 (optional): APScheduler background worker + Downloads watcher
uv run python -m steward.worker
```

### CLI Reference
```bash
uv run steward --check              # Health check (config, DB, ChromaDB, OKF graph, models)
uv run steward --scan               # Incrementally scan configured folders into SQLite
uv run steward --software           # Discover installed software and file associations
uv run steward --watch-downloads    # Watch Downloads in real time (Ctrl+C to stop)
uv run steward --read README.md     # Extract text and metadata from a single document
uv run steward --index              # Index scanned files into local ChromaDB RAG store
uv run steward --search "budget"    # Search indexed document passages semantically
uv run steward --build-okf          # Build linked OKF v0.3 concepts from SQLite & software
uv run steward --okf-search "acme"  # Search curated OKF concepts and view linked neighbors
uv run steward --workflow scan      # Run Agno ScanWorkflow (scan -> RAG -> OKF)
uv run steward --workflow cleanup   # Run Agno CleanupWorkflow (find -> dry-run proposals -> OKF)
uv run steward --workflow report    # Run Agno ReportWorkflow (stats -> report -> OKF concept)
uv run steward --chat "Summarize my recent files"  # Chat with the Agno Orchestrator Team
uv run steward --undo 1             # Undo a completed move, ZIP archive, or recycle action
uv run steward --recommend          # Mine work patterns into OKF and print suggestions
uv run steward --report both        # Generate Markdown + styled HTML reports in reports/
```

---

## Manual Walkthrough Scripts (`examples/`)

Every phase includes a runnable, self-contained demo script:

| Phase | Script | Run Command |
| :---: | :--- | :--- |
| **1** | [demo_phase1_foundation.py](examples/demo_phase1_foundation.py) | `uv run python examples/demo_phase1_foundation.py` |
| **2** | [demo_phase2_scanning.py](examples/demo_phase2_scanning.py) | `uv run python examples/demo_phase2_scanning.py` |
| **3** | [demo_phase3_rag.py](examples/demo_phase3_rag.py) | `uv run python examples/demo_phase3_rag.py` |
| **4** | [demo_phase4_okf.py](examples/demo_phase4_okf.py) | `uv run python examples/demo_phase4_okf.py` |
| **5** | [demo_phase5_agents.py](examples/demo_phase5_agents.py) | `uv run python examples/demo_phase5_agents.py` |
| **6** | [demo_phase6_organizing.py](examples/demo_phase6_organizing.py) | `uv run python examples/demo_phase6_organizing.py` |
| **7** | [demo_phase7_reports.py](examples/demo_phase7_reports.py) | `uv run python examples/demo_phase7_reports.py` |
| **8** | [demo_phase8_api.py](examples/demo_phase8_api.py) | `uv run python examples/demo_phase8_api.py` |
| **9** | [demo_phase9_worker.py](examples/demo_phase9_worker.py) | `uv run python examples/demo_phase9_worker.py` |

---

## Documentation (`docs/`)

- **[User Guide](docs/user-guide/README.md)**: every page of the web app with screenshots, for non-technical readers
- **[Developer Guide](docs/developer-guide/README.md)**: architecture, API reference, frontend, Docker & config, testing
- **[System review](review-system/README.md)**: independent review with the status of every issue ([what's new in 0.10.0](review-system/11-whats-new-0.10.md))

Phase-by-phase build notes:

All phase guides include Mermaid flow diagrams, change tables, and run instructions:

- [Architecture Overview & Roadmap](docs/architecture.md)
- [Phase 1: Foundation and Config](docs/phase-1-foundation.md) — **Done**
- [Phase 2: File Scanning and Database](docs/phase-2-scanning.md) — **Done**
- [Phase 3: Document Reading and RAG](docs/phase-3-rag.md) — **Done**
- [Phase 4: OKF Knowledge Bundle, Graph, and Memory](docs/phase-4-okf.md) — **Done**
- [Phase 5: Agno Tools, Agents, Team, and Workflows](docs/phase-5-agents.md) — **Done**
- [Phase 6: Organizing and Cleanup Actions](docs/phase-6-organizing.md) — **Done**
- [Phase 7: Recommendations and Reports](docs/phase-7-reports.md) — **Done**
- [Phase 8: Chat UI (AgentOS + Streamlit)](docs/phase-8-ui.md) — **Done**
- [Phase 9: Docker Deployment & Scheduler](docs/phase-9-docker.md) — **Done**
- [Phase 10: Professional Web UI (Dashboard, Scan a folder, Chat)](docs/phase-10-web-ui.md) — **Done**
