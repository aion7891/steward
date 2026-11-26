# Steward

Steward is a local-first, multi-agent AI assistant that runs continuously on your computer to keep files organized, track disk storage and installed software, answer questions about your documents with citations, generate Markdown/HTML reports, and execute cleanup actions safely with approval and undo.

## Safety First
- **Dry-run by default** (`safety.dry_run: true`)
- **Agno HITL confirmation & approval state machine** (`proposed -> approved/rejected -> done/failed -> undone`)
- **Recycle-first & verified ZIP archiving** — never permanently deletes directly; every action is logged in SQLite and OKF `memory/decisions/` for undo
- **Protected paths & privacy filter** — blocks protected folders even if approved, and skips `.env`/key files from reading, ChromaDB, and OKF
- **Local-first privacy** — defaults to local Ollama, SQLite, persistent ChromaDB, OKF v0.3 Markdown bundle, and `127.0.0.1`-only Docker port bindings

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

### Run Local Chat UI & AgentOS API
```bash
# Terminal 1: Start Agno AgentOS FastAPI server on http://127.0.0.1:7777
uv run python -m steward.api

# Terminal 2: Start Local Streamlit UI on http://127.0.0.1:8501
uv run streamlit run steward/ui.py

# Terminal 3 (optional): Start APScheduler background worker + Downloads watcher
uv run python -m steward.worker
```

### Run Always-On with Docker Compose (4 Services)
```bash
# 1. Export host installed apps so the Docker container stays isolated
uv run python scripts/export_host_inventory.py

# 2. Build and launch ollama, steward-api, steward-worker, and steward-ui
docker compose up -d --build

# 3. Pull your local Ollama models once
docker compose exec ollama ollama pull gemma3:4b
docker compose exec ollama ollama pull nomic-embed-text

# 4. Open http://127.0.0.1:8501 (Streamlit UI) or http://127.0.0.1:7777/steward/health
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
