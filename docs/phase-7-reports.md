# Phase 7: Recommendations and Reports

## Goal
Teach Steward to learn recurring work patterns from file, download, and software history (`PatternMiner`), persist those patterns into OKF `knowledge/memory/patterns/`, proactively suggest prioritized cleanup and organization actions with reclaimable space estimates (`RecommenderEngine`), and render periodic **Markdown and styled HTML** reports via **Jinja2** (`ReportGenerator`).

## Flow Diagram

```mermaid
flowchart TB
    SQLite[(SQLite DB\nfiles | activity_events | software)] --> Miner[PatternMiner]
    Miner -->|Persist Patterns| OKFPat[(OKF knowledge/memory/patterns/)]

    SQLite --> Rec[RecommenderEngine]
    Scanner[FileScanner Cleanup Findings] --> Rec
    Miner --> Rec
    Rec --> Suggestions["Prioritized Suggestions\ndeduplicate | clean_temp | archive_stale\nreview_large | group_folder"]

    SQLite --> RepGen[ReportGenerator - Jinja2]
    OKFGraph[OKFGraph Stats] --> RepGen
    Suggestions --> RepGen

    RepGen --> MD["Markdown Report\nreports/steward_weekly_*.md"]
    RepGen --> HTML["Styled HTML Report\nreports/steward_weekly_*.html"]
    RepGen --> RepDB[(SQLite reports table)]
    RepGen --> OKFRep[(OKF knowledge/reports/)]
```

## What Gets Mined & Reported

| Area | Details |
| :--- | :--- |
| **Learned Work Patterns** | Peak active weekday, dominant file category, untouched/inactive project folders (`> stale_days`), and clusters of rarely-used software — saved to `knowledge/memory/patterns/`. |
| **Proactive Suggestions** | Prioritized (`high` / `medium` / `low`) suggestions with `reclaimable_mb`: duplicate removal, temporary file cleanup, stale file archiving, large file review, and organizing mixed-category folders. |
| **Markdown & HTML Reports** | Jinja2-rendered reports (`autoescape=True` for HTML) showing disk usage, category breakdown, top folders, activity over time, software usage, learned patterns, and cleanup suggestions. |

## What Happened & What Changed

| File | Change | Responsibility |
| :--- | :--- | :--- |
| `pyproject.toml` & `uv.lock` | Updated | Added `jinja2` via `uv add jinja2`. |
| `steward/recommender.py` | Added | `PatternMiner` & `RecommenderEngine`: mines work habits into OKF and generates prioritized suggestions with reclaimable MB. |
| `steward/reporter.py` | Added | `ReportGenerator`: aggregates stats + recommendations and renders Markdown, HTML, or both via Jinja2, logging to SQLite and `knowledge/reports/`. |
| `steward/tools/knowledge_tools.py` | Updated | Upgraded `ReportTools` to delegate to `ReportGenerator` and added `get_recommendations()` for `RecommenderAgent`. |
| `steward/agents.py`, `workflows.py`, `main.py`, `config.yaml` | Updated | Wired `RecommenderEngine` & `ReportGenerator` into `StewardApp`, `RecommenderAgent`, and `ReportWorkflow`; added `--recommend` and `--report <markdown|html|both>` CLI flags (`v0.7.0`). |
| `tests/test_phase7.py` | Added | Tests pattern mining into OKF, prioritized suggestions, dual Markdown + HTML Jinja2 rendering, and `ReportWorkflow`. |
| `examples/demo_phase7_reports.py` | Added | Self-contained sandbox demo generating learned OKF patterns, prioritized suggestions, and both `.md` and `.html` reports you can open in a browser. |

## How to Run & Try Manually

```bash
# Sync dependencies with uv
uv sync

# Run all unit tests (Phases 1–7)
uv run pytest -v

# Run the Phase 7 manual demo (generates real Markdown + HTML reports in data/demo_phase7/reports/)
uv run python examples/demo_phase7_reports.py

# Run against your real scanned database via CLI
uv run steward --recommend
uv run steward --report both
```
