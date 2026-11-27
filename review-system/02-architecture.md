# 2. Architecture: the big picture

## 2.1 The layer cake

Steward is built in **layers**. Requests flow *down*: you talk to the interface, the interface talks to the AI team, the AI team uses tools, and **only tools touch your files and databases**. This rule matters most for safety, because an AI agent can never "reach around" a tool to delete something.

```mermaid
flowchart TB
    subgraph L1["① Interfaces: how YOU talk to Steward"]
        UI["🖥️ Streamlit web page<br/>steward/ui.py · port 8501"]
        CLI["⌨️ Command line<br/>steward/main.py · uv run steward ..."]
        API["🌐 AgentOS API (FastAPI)<br/>steward/api.py · port 7777"]
    end
    subgraph L2["② Triggers: things that start work on their own"]
        SCH["⏰ Scheduler (APScheduler)<br/>steward/worker.py"]
        WAT["👁️ Downloads watcher (watchdog)<br/>steward/watcher.py"]
    end
    subgraph L3["③ Orchestration: who decides what to do"]
        TEAM["🧭 StewardTeam (Agno Team)<br/>routes chat to the right agent<br/>steward/agents.py"]
        WF["📋 3 fixed Workflows<br/>Scan · Cleanup · Report<br/>steward/workflows.py"]
    end
    subgraph L4["④ Agents: AI workers with one job each"]
        AG["Scanner · Analyzer · Organizer<br/>Recommender · Reporter · Chat"]
    end
    subgraph L5["⑤ Toolkits: the ONLY code that touches files/data"]
        TK["FileScannerTools · DocumentReaderTools · SoftwareTools<br/>OrganizerTools · OKFTools · ReportTools<br/>steward/tools/"]
    end
    subgraph L6["⑥ Engines: plain Python classes doing the real work"]
        EN["FileScanner · DocumentReader · RAGIndex · KnowledgeBuilder<br/>FileOrganizer · RecycleManager · RecommenderEngine · ReportGenerator"]
    end
    subgraph L7["⑦ Data: where things are stored"]
        DB[("🗃️ SQLite<br/>data/steward.db")]
        VS[("🔎 ChromaDB<br/>chroma/")]
        OKF[("📓 OKF bundle<br/>knowledge/")]
        ARC[("♻️ Recycle + ZIP archives<br/>data/recycle, data/archives")]
    end
    MODEL["🧠 ModelFactory → Ollama (gemma4, nomic-embed-text)<br/>or OpenAI / Claude / Gemini · steward/models.py"]

    UI -->|HTTP only| API
    CLI --> TEAM
    CLI --> WF
    API --> TEAM
    API --> WF
    SCH --> WF
    WAT --> DB
    TEAM --> AG
    AG --> TK
    WF --> TK
    WF --> EN
    TK --> EN
    EN --> DB & VS & OKF & ARC
    AG -. asks .-> MODEL
    TEAM -. asks .-> MODEL
    EN -. embeddings .-> MODEL
```

> **Plain words:** the web page is just a remote control. The API is the front desk. The Team is the receptionist. The Agents are specialists. The Toolkits are their hand tools, and the Data layer is the filing cabinets.

> **Reviewer's note:** the PRD says workflows go through toolkits. In the code, the **Scan workflow calls the engines directly** ([workflows.py:76-97](../steward/workflows.py#L76-L97)). That's fine in practice, but it means the Analyzer *agent* is never used in the scan, so no AI summaries are written. See [08-issues-and-risks.md](08-issues-and-risks.md) #9.

## 2.2 The six agents and their tools

```mermaid
flowchart LR
    T{{"🧭 StewardTeam<br/>(receptionist)"}}
    T --> SA["🔍 ScannerAgent"]
    T --> AA["📖 AnalyzerAgent"]
    T --> OA["🗂️ OrganizerAgent"]
    T --> RA["💡 RecommenderAgent"]
    T --> RP["📊 ReporterAgent"]
    T --> CA["💬 ChatAgent"]

    SA --- FST["FileScannerTools<br/>scan_folder · get_file_info<br/>find_duplicates · find_large_files · find_stale_files"]
    SA --- SWT["SoftwareTools<br/>list_apps · apps_for_extension"]
    AA --- DRT["DocumentReaderTools<br/>read_document · extract_text"]
    AA --- OKT["OKFTools<br/>read/write/link/search concepts · neighbors"]
    OA --- FST
    OA --- ORT["OrganizerTools ⚠️<br/>propose_move · organize_folder<br/>move_file🔒 · archive_files🔒 · delete_files🔒 · undo_action"]
    OA --- OKT
    RA --- FST
    RA --- RPT["ReportTools<br/>collect_stats · get_recommendations · render_report"]
    RA --- OKT
    RP --- RPT
    RP --- OKT
    CA --- OKT
    CA --- DRT
    CA --- KN[("RAG Knowledge<br/>(ChromaDB search)")]
```

🔒 = needs human confirmation (Agno HITL) before it runs. The confirmation is configured in [organizer_tools.py:30](../steward/tools/organizer_tools.py#L30).

| Agent | Its one job | Defined at |
|:--|:--|:--|
| ScannerAgent | Scan folders, list duplicates, big/old files, installed apps | [agents.py:59](../steward/agents.py#L59) |
| AnalyzerAgent | Read documents, write summaries into the OKF notebook | [agents.py:72](../steward/agents.py#L72) |
| OrganizerAgent | Propose and (after approval) do moves, archives, deletes | [agents.py:86](../steward/agents.py#L86) |
| RecommenderAgent | Look at habits and suggest what to do next | [agents.py:99](../steward/agents.py#L99) |
| ReporterAgent | Build usage reports | [agents.py:112](../steward/agents.py#L112) |
| ChatAgent | Answer questions, OKF first, then RAG, with citations | [agents.py:125](../steward/agents.py#L125) |
| StewardTeam | Route each message to the single best agent | [agents.py:143](../steward/agents.py#L143) |

All agents share **one model** (built once by `ModelFactory`) and **one session database** (`data/agno_sessions.db`). Agno's own long-term "user memory" is **switched off** (`update_memory_on_run: False`), as the PRD requires, so OKF is the only long-term memory.

## 2.3 The three workflows (fixed checklists)

```mermaid
flowchart LR
    subgraph Scan["ScanWorkflow (every 60 min)"]
        s1[scan_folders] --> s2[update_rag] --> s3[update_okf]
    end
    subgraph Clean["CleanupWorkflow (every 24 h)"]
        c1[find_candidates] --> c2[propose_actions ⚠️] --> c3[log_to_okf]
    end
    subgraph Rep["ReportWorkflow (Sundays 09:00)"]
        r1[collect_stats] --> r2[render_report] --> r3[save_report_concept]
    end
```

⚠️ The PRD's cleanup is *find → recommend → **wait for my confirmation** → act → log*. The code has **no "wait" or "act" step**, and step 2 marks proposals as *approved* by itself. See [08](08-issues-and-risks.md) #1.

## 2.4 Three stores, three kinds of memory

```mermaid
flowchart LR
    F["📄 A file on disk<br/>invoice-q3.pdf"]
    F -->|"metadata + SHA-256"| DB[("🗃️ SQLite<br/>FACTS that change often<br/>name, size, dates, hash,<br/>category, actions, events")]
    F -->|"raw text cut into chunks<br/>+ embeddings"| VS[("🔎 ChromaDB<br/>RAW TEXT for search<br/>'Total amount due: 4,800 USD'")]
    F -->|"curated note + links"| OKF[("📓 OKF bundle<br/>CHECKED KNOWLEDGE<br/>file → folder → project → topic → app")]
    DB -. "same sha256 links all three" .- VS
    VS -. .- OKF
```

| Store | Holds | Written by | Read by |
|:--|:--|:--|:--|
| **SQLite** `data/steward.db` | file list, scan runs, activity events, apps, actions, reports | Scanner, Watcher, Organizer, Reporter | almost everything |
| **ChromaDB** `chroma/` | text chunks + embeddings | `RAGIndex` | ChatAgent (via Agno Knowledge) |
| **OKF** `knowledge/` | one Markdown note per file / folder / project / topic / app / pattern / decision / report | `KnowledgeBuilder`, `MemoryManager`, `ReportGenerator` | ChatAgent and others via `OKFTools` |
| **Agno sessions** `data/agno_sessions.db` | chat history, workflow runs | Agno | Agno |
| **Recycle / archives** `data/recycle`, `data/archives` | files you "deleted" or zipped, with sidecar metadata for undo | `RecycleManager` | undo |

More detail and real examples are in [04-data-and-memory.md](04-data-and-memory.md).

## 2.5 How Docker runs it (always-on mode)

```mermaid
flowchart TB
    subgraph Mac["Your Mac"]
        OL["🧠 Ollama app (native)<br/>localhost:11434"]
        HI["scripts/export_host_inventory.py<br/>→ host-inventory/apps.json"]
        subgraph DC["docker compose (all ports bound to 127.0.0.1)"]
            API["steward-api<br/>AgentOS :7777<br/>health-checked"]
            WK["steward-worker<br/>scheduler + Downloads watcher"]
            UI["steward-ui<br/>Streamlit :8501"]
        end
        V1["~/Documents, ~/Desktop<br/>(read-only)"]
        V2["~/Downloads<br/>(read-write)"]
        V3["./knowledge ./data ./chroma ./reports<br/>(read-write, survive restarts)"]
    end
    UI -->|"http://steward-api:7777"| API
    API -->|host.docker.internal| OL
    WK -->|host.docker.internal| OL
    V1 --> API & WK
    V2 --> API & WK
    V3 --- API & WK
    HI -->|read-only mount| API & WK
    WK -. "waits until healthy" .-> API
```

- One `Dockerfile`, three services with different start commands, all `restart: unless-stopped`.
- Ollama runs **natively on your Mac**, not in a container (a deliberate change from the PRD, commit `2bff203`), so the GPU is used and models aren't downloaded twice.
- ⚠️ `steward-api` and `steward-worker` are **two processes writing the same ChromaDB folder and the same SQLite file** at the same time. See [08](08-issues-and-risks.md) #12.

## 2.6 Code map: which file does what

| File | Lines | Class(es) | Responsibility |
|:--|--:|:--|:--|
| [config.py](../steward/config.py) | 180 | `AppConfig` | Loads `config.yaml` + `.env`, defaults, validation, path helpers, protected-path check |
| [logger.py](../steward/logger.py) | 102 | `LoggerFactory` | Console + rotating file logs (`data/logs/steward.log`) |
| [models.py](../steward/models.py) | 173 | `ModelFactory` | Builds the chat model / embedder for ollama, openai, anthropic, gemini |
| [database.py](../steward/database.py) | 200 | `DatabaseManager` | SQLite schema, migrations, queries |
| [scanner.py](../steward/scanner.py) | 191 | `FileCategorizer`, `FileScanner` | Walk folders, hash changed files, categorise, find dup/large/stale/temp |
| [software.py](../steward/software.py) | 206 | `SoftwareDetector` | Read `/Applications` `Info.plist` or the host inventory JSON |
| [watcher.py](../steward/watcher.py) | 171 | `DownloadsWatcher` | Real-time Downloads events, wait until a file stops growing, suggest destination |
| [reader.py](../steward/reader.py) | 178 | `DocumentReader` | Extract text from PDF/DOCX/XLSX/text/code + image EXIF, size and secret guards |
| [chunker.py](../steward/chunker.py) | 153 | `TextChunker`, `HashEmbedder` | Split text into 800-char chunks with 120 overlap. Offline test embedder |
| [rag.py](../steward/rag.py) | 180 | `RAGIndex` | ChromaDB via Agno Knowledge: index, re-index on change, search |
| [okf_bundle.py](../steward/okf_bundle.py) | 191 | `OKFBundle` | Read, write, validate (incl. secret regex), search OKF notes, `index.md` |
| [okf_graph.py](../steward/okf_graph.py) | 183 | `OKFGraph` | Parse Markdown links into a NetworkX graph: neighbours, related, by tag |
| [memory.py](../steward/memory.py) | 176 | `MemoryManager` | Preferences, patterns, decisions with expiry dates |
| [knowledge_builder.py](../steward/knowledge_builder.py) | 199 | `KnowledgeBuilder` | Turn SQLite rows into linked OKF notes |
| [tools/*.py](../steward/tools/) | 376 | 6 Toolkits | What agents are allowed to call |
| [agents.py](../steward/agents.py) | 176 | `StewardAgents` | 6 agents + the team |
| [workflows.py](../steward/workflows.py) | 194 | `StewardWorkflows` | Scan / Cleanup / Report workflows |
| [organizer.py](../steward/organizer.py) | 204 | `FileOrganizer` | Action life-cycle proposed → approved → done → undone, protected paths, dry-run |
| [recycle.py](../steward/recycle.py) | 185 | `RecycleManager` | Recycle bin, verified ZIP archives, restore, confirmed purge |
| [recommender.py](../steward/recommender.py) | 213 | `PatternMiner`, `RecommenderEngine` | Rule-based habit mining + prioritised suggestions |
| [reporter.py](../steward/reporter.py) | 224 | `ReportGenerator` | Stats → Jinja2 Markdown/HTML report → OKF note |
| [main.py](../steward/main.py) | 251 | `StewardApp`, `StewardCLI` | Wires every service together, CLI commands |
| [api.py](../steward/api.py) | 177 | `StewardAPIServer` | AgentOS + `/steward/*` routes |
| [client.py](../steward/client.py) | 95 | `StewardClient` | HTTP client used by the UI |
| [ui.py](../steward/ui.py) | 182 | `StewardUI` | Chat, approval cards, reports, settings tabs |
| [worker.py](../steward/worker.py) | 142 | `StewardWorker` | APScheduler jobs + watcher, clean shutdown |

**How the pieces get wired:** `StewardApp.__init__` ([main.py:29-51](../steward/main.py#L29-L51)) creates every engine once and shares them. The RAG index, agents, and workflows are created lazily, only when first needed. This is a clean design (simple manual dependency injection) and it's easy to follow.

➡️ Next: [03-how-it-works-step-by-step.md](03-how-it-works-step-by-step.md)
