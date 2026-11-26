# Steward

Steward is a local-first, multi-agent AI assistant that runs on your computer to keep files organized, track disk storage and installed software, answer questions about your documents, and recommend cleanup actions safely.

## Safety First
- **Dry-run by default** (`safety.dry_run: true`)
- **Confirmation required** before destructive actions
- **Recycle-first workflow** with every action logged in SQLite for audit and undo
- **Local-first privacy** — defaults to local Ollama, SQLite, local vector store, and an Open Knowledge Format (OKF v0.3) Markdown bundle

---

## Quick Start (`uv`)

```bash
# 1. Install dependencies and create .venv with uv
uv sync

# 2. (Optional) Create local environment overrides
cp .env.example .env

# 3. Verify setup and run all unit tests
uv run steward --check
uv run pytest -v
```

### Run CLI Commands (Phases 1–2)
```bash
uv run steward --check            # Verify config, directories, and model settings
uv run steward --scan             # Scan configured folders into SQLite
uv run steward --software         # Discover installed software and file associations
uv run steward --watch-downloads  # Watch Downloads in real time (Ctrl+C to stop)
```

---

## Manual Walkthrough Scripts (`examples/`)

Want to see each phase working without touching your personal files? Run the self-contained demo scripts:

- **Phase 1 Demo** ([examples/demo_phase1_foundation.py](examples/demo_phase1_foundation.py)): Loads config, writes a rotating log entry, exercises `ModelFactory`, and prints a health check.
  ```bash
  uv run python examples/demo_phase1_foundation.py
  ```
- **Phase 2 Demo** ([examples/demo_phase2_scanning.py](examples/demo_phase2_scanning.py)): Creates a safe sandbox inside `data/demo_phase2/` with sample duplicates, large/stale/temp files, a sample `.app` bundle, and live Downloads events.
  ```bash
  uv run python examples/demo_phase2_scanning.py
  ```

---

## Documentation (`docs/`)

Documentation is organized by architecture and phase, with Mermaid flow diagrams showing what was built and how data moves through the system:

- [Architecture Overview & Roadmap](docs/architecture.md)
- [Phase 1: Foundation and Config](docs/phase-1-foundation.md) — **Done**
- [Phase 2: File Scanning and Database](docs/phase-2-scanning.md) — **Done**
- Phase 3: Document reading and RAG — *Next*
- Phase 4: OKF knowledge bundle, graph, and memory — *Planned*
- Phase 5: Agno tools, agents, team, and workflows — *Planned*
- Phase 6: Organizing and cleanup actions — *Planned*
- Phase 7: Recommendations and reports — *Planned*
- Phase 8: Chat UI (AgentOS + Streamlit) — *Planned*
- Phase 9: Docker deployment — *Planned*

---

## Project Layout

```text
project-steward/
├── config.yaml               # Central configuration
├── .env.example              # Environment variable template
├── pyproject.toml            # uv project configuration
├── docs/                     # Distributed phase docs & Mermaid flow diagrams
│   ├── architecture.md
│   ├── phase-1-foundation.md
│   └── phase-2-scanning.md
├── examples/                 # Simple runnable manual demo scripts
│   ├── demo_phase1_foundation.py
│   └── demo_phase2_scanning.py
├── steward/                  # Core Python package (100–200 lines/script, no type hints)
│   ├── config.py
│   ├── logger.py
│   ├── models.py
│   ├── database.py
│   ├── scanner.py
│   ├── software.py
│   ├── watcher.py
│   └── main.py
└── tests/                    # Automated pytest suite
    ├── test_foundation.py
    └── test_phase2.py
```
