# Steward — System Review

> **Reviewed:** 26 Nov 2026 · **Branch:** `v0-ant-g` · **Commit:** `2bff203`
> **Compared against:** `Steward-System-Design.pdf` (the PRD, 21 pages) and `project-skill.md`
> **Method:** every source file was read line by line, the 37 automated tests were run, and the whole system was tested live on a fake sample folder with real local AI models (Ollama).

> 🆕 **Update, 28 Nov 2026 (Steward 0.13.0):** Settings can delete everything Steward keeps (a
> complete reset; archives are never deleted), single reports can be deleted, the sidebar folds into
> icons and the Dashboard puts the to-do list last. See **[14-whats-new-0.13.md](14-whats-new-0.13.md)**.
>
> **Update, 28 Nov 2026 (Steward 0.12.0):** a "no" is honoured and reported truthfully, the chat
> remembers what "it" is, finds files by name, can be stopped, undoes and recovers, runs two chats
> at once, and Settings can clear Steward's own data. New colours. See
> **[13-whats-new-0.12.md](13-whats-new-0.12.md)**.
>
> **Update, 28 Nov 2026 (Steward 0.11.0):** the chat now finds folders you name, archives and
> deletes whole folders, keeps working while you switch tabs, and shows every step live. See
> **[12-whats-new-0.11.md](12-whats-new-0.11.md)**.
>
> **Update, 27 Nov 2026 (Steward 0.10.0):** a new web app, chat approvals, real chat sources and
> safe settings were added, and the most serious issues below are now fixed. Start with
> **[11-whats-new-0.10.md](11-whats-new-0.10.md)** for what changed and the updated scorecard. The rest of
> this folder is the original review (still accurate for the parts not mentioned there).

---

## Start here

This folder explains **what Steward is, how it works inside, how to use it, and what still needs fixing**. It is written so a non-technical person can follow it. Technical details are kept in clearly marked sections.

| # | Read this | When you want to… |
|:-:|:--|:--|
| 1 | [01-what-is-steward.md](01-what-is-steward.md) | Understand the idea in plain words (no code) |
| 2 | [02-architecture.md](02-architecture.md) | See the big picture: the parts and how they connect |
| 3 | [03-how-it-works-step-by-step.md](03-how-it-works-step-by-step.md) | Follow each job (scan, chat, cleanup, reports) step by step with flow diagrams |
| 4 | [04-data-and-memory.md](04-data-and-memory.md) | Know where Steward keeps what it learns, and how to look inside |
| 5 | [05-how-to-use.md](05-how-to-use.md) | Install, run, and use Steward day to day (CLI, web UI, Docker) |
| 6 | [06-live-test-results.md](06-live-test-results.md) | See what actually happened when I tested it on a sample folder |
| 7 | [07-prd-compliance.md](07-prd-compliance.md) | Check every PRD requirement: done, partial, or missing |
| 8 | [08-issues-and-risks.md](08-issues-and-risks.md) | See every bug and risk found, ranked by severity, with the fix |
| 9 | [09-improvement-roadmap.md](09-improvement-roadmap.md) | Get a step-by-step fix plan plus AI/ML upgrades |
| 10 | [10-explain-to-non-tech.md](10-explain-to-non-tech.md) | Get a ready-made script and FAQ for explaining Steward to anyone |
| 11 | [11-whats-new-0.10.md](11-whats-new-0.10.md) | **What changed in 0.10.0**: fixed issues, new web app, updated scorecard |
| 12 | [12-whats-new-0.11.md](12-whats-new-0.11.md) | **What changed in 0.11.0**: live chat, folder actions, opt-in write access, scenario test |
| 13 | [13-whats-new-0.12.md](13-whats-new-0.12.md) | **What changed in 0.12.0**: honest rejections, Stop, memory, find files, two chats, data cleanup, new colours |
| 14 | [14-whats-new-0.13.md](14-whats-new-0.13.md) | **What changed in 0.13.0**: delete everything, report delete, collapsible sidebar, new Dashboard order |
| — | [demo/](demo/) | Rerun my test yourself (sample folder generator + demo config + script) |

---

## The verdict in one minute

**Steward is a solid, well-organised first version.** All 9 build phases exist, the code is cleanly split into small classes, all 37 tests pass, and the core safety ideas work in practice. Protected folders are blocked, secret files are never read, deleted files go to a recycle bin, and undo works.

It is **not yet safe or reliable to leave running on its own**. The pieces work one at a time, but some of the connections between them are broken:

1. **The scheduled cleanup approves its own suggestions.** You never get asked, and the suggestions get stuck in a state the UI can't handle.
2. **Chat requests that change files never finish.** The AI correctly pauses to ask permission, but there is no button anywhere to give it.
3. **The default model in `config.yaml` (`gemma3:4b`) can't use tools**, so every agent fails. Switch to **`gemma4`**: tested, it works and answers in about 34 seconds.
4. **Steward never forgets deleted files.** It keeps reporting duplicates that are already in the recycle bin.
5. **Identical files hide each other in search.** Indexing one copy deletes the other copy's search entries.
6. **"Summaries" are just the first 180 characters of each file, copied as-is**, not AI summaries. That goes against the PRD's privacy rule.

### Scorecard

| Area | Score | One-line reason |
|:--|:-:|:--|
| Code structure & readability | 🟢 8/10 | Small single-purpose classes and clear names. 5 files go over the 200-line rule and some lines are very long |
| Safety (files can't be lost) | 🟡 7/10 | Recycle, undo, and protected paths all work. The approval flow itself is broken |
| Scanning & database | 🟢 7/10 | Incremental hashing works. It never removes deleted files and has no crash-resume |
| Search (RAG) | 🟡 6/10 | Real semantic search works. Duplicate files wipe each other's entries |
| Knowledge graph (OKF) | 🟡 5/10 | Valid and linked, but summaries, topics, and projects are simple guesses, and it is rebuilt from zero every hour |
| AI agents & chat | 🟡 5/10 | Q&A works with `gemma4`. Actions that need approval can't be completed |
| Background automation | 🔴 4/10 | Runs on schedule, but creates fake approvals and repeats the same proposals |
| Reports & recommendations | 🟢 7/10 | Clear Markdown/HTML output. "Reclaimable space" counts the same files twice |
| Docker deployment | 🟢 7/10 | Valid compose file, local-only ports, read-only mounts. Two processes share one vector DB |
| Tests | 🟡 6/10 | 37 passing, but none cover the bugs above (multi-step flows) |

**Overall: about 6/10, a working prototype.** Roughly 2–3 focused days of fixes (see [09-improvement-roadmap.md](09-improvement-roadmap.md)) would make it safe to run unattended.
