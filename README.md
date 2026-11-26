# Steward

Steward is a local-first, multi-agent AI assistant that runs on your computer to keep files organized, track disk storage and installed software, answer questions about your documents, and recommend cleanup actions safely.

## Safety First
- **Dry-run by default** (`safety.dry_run: true`)
- **Confirmation required** before destructive actions
- **Recycle-first workflow** with every action logged in SQLite for audit and undo
- **Protected paths & privacy filter** — blocks actions on protected folders and skips `.env`/key files from reading, ChromaDB, and OKF
- **Local-first privacy** — defaults to local Ollama, SQLite, persistent ChromaDB vector store, and an Open Knowledge Format (OKF v0.3) Markdown bundle

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

### Run CLI Commands (Phases 1–4)
```bash
uv run steward --check              # Verify config, directories, OKF graph, and model settings
uv run steward --scan               # Incrementally scan configured folders into SQLite
uv run steward --software           # Discover installed software and file associations
uv run steward --watch-downloads    # Watch Downloads in real time (Ctrl+C to stop)
uv run steward --read README.md     # Extract text and metadata from a single document
uv run steward --index              # Index scanned files into local ChromaDB RAG store
uv run steward --search "budget"    # Search indexed document passages semantically
uv run steward --build-okf          # Build linked OKF v0.3 concepts from SQLite & software
uv run steward --okf-search "acme"  # Search curated OKF concepts and view linked neighbors
```

---

## Manual Walkthrough Scripts (`examples/`)

Run these self-contained demo scripts to see each phase working step by step:

- **Phase 1 Demo** ([examples/demo_phase1_foundation.py](examples/demo_phase1_foundation.py)): Config loading, rotating logs, real Agno `ModelFactory` (live Ollama chat + embedding check), and startup health check.
  ```bash
  uv run python examples/demo_phase1_foundation.py
  ```
- **Phase 2 Demo** ([examples/demo_phase2_scanning.py](examples/demo_phase2_scanning.py)): Isolated sandbox scan with incremental 0-hash rescans, duplicates, large/stale/temp files, sample `.app` bundle, and live Downloads events.
  ```bash
  uv run python examples/demo_phase2_scanning.py
  ```
- **Phase 3 Demo** ([examples/demo_phase3_rag.py](examples/demo_phase3_rag.py)): Real PDF, DOCX, XLSX, Markdown, Python, PNG, and `.env` (skipped) indexed into Agno `Knowledge` + persistent `ChromaDb` using real Ollama embeddings (`--offline` optional).
  ```bash
  uv run python examples/demo_phase3_rag.py
  ```
- **Phase 4 Demo** ([examples/demo_phase4_okf.py](examples/demo_phase4_okf.py)): Builds a real OKF v0.3 Markdown bundle (with real Ollama summarization by default, or `--fast`), traverses the NetworkX link graph, and runs `MemoryManager` preferences, patterns, decisions, and stale expiry.
  ```bash
  uv run python examples/demo_phase4_okf.py
  ```

---

## Documentation (`docs/`)

Documentation is organized by architecture and phase, with Mermaid flow diagrams showing what was built and how data moves through the system:

- [Architecture Overview & Roadmap](docs/architecture.md)
- [Phase 1: Foundation and Config](docs/phase-1-foundation.md) — **Done**
- [Phase 2: File Scanning and Database](docs/phase-2-scanning.md) — **Done**
- [Phase 3: Document Reading and RAG](docs/phase-3-rag.md) — **Done**
- [Phase 4: OKF Knowledge Bundle, Graph, and Memory](docs/phase-4-okf.md) — **Done**
- Phase 5: Agno tools, agents, team, and workflows — *Next*
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
│   ├── phase-2-scanning.md
│   ├── phase-3-rag.md
│   └── phase-4-okf.md
├── examples/                 # Runnable manual demo scripts
│   ├── demo_phase1_foundation.py
│   ├── demo_phase2_scanning.py
│   ├── demo_phase3_rag.py
│   └── demo_phase4_okf.py
├── steward/                  # Core Python package (100–200 lines/script, no type hints)
│   ├── config.py
│   ├── logger.py
│   ├── models.py
│   ├── database.py
│   ├── scanner.py
│   ├── software.py
│   ├── watcher.py
│   ├── reader.py
│   ├── chunker.py
│   ├── rag.py
│   ├── okf_bundle.py
│   ├── okf_graph.py
│   ├── memory.py
│   ├── knowledge_builder.py
│   └── main.py
└── tests/                    # Automated pytest suite
    ├── test_foundation.py
    ├── test_phase2.py
    ├── test_phase3.py
    └── test_phase4.py
```
