# 6. Live test results (sample folder)

**When:** 26–27 Nov 2026 · **Machine:** macOS (Apple Silicon), Python 3.14 venv, Agno 3.2.1, ChromaDB 1.5.9
**Models (local Ollama):** `gemma4` (chat), `qwen3:4b` and `gemma3:4b` (compared), `nomic-embed-text` (embeddings)
**Rerun it yourself:** `bash review-system/demo/run_demo.sh`

## 6.1 The sample "home folder"

[demo/create_sample_folder.py](demo/create_sample_folder.py) builds 13 files. **Each one is planted to test one feature:**

```text
sample_home/
├── Documents/
│   ├── .env                          🔒 fake API key → must never be read, embedded, or copied
│   ├── Acme/
│   │   ├── invoice-q3.pdf            📄 PDF: "Total amount due: 4,800 USD"
│   │   ├── phoenix-kickoff.docx      📄 Word document
│   │   └── budget-2026.xlsx          📊 Excel sheet
│   ├── Recipes/
│   │   ├── pasta.md                  📝 Markdown
│   │   ├── pasta-copy.md             👯 exact duplicate of pasta.md
│   │   └── old-shopping-list.txt     🕰️ dated 200 days ago → "stale"
│   └── Work/Clients/contract.txt     🛡️ in a PROTECTED path → must never be moved
├── Downloads/
│   ├── invoice-q3 (1).pdf            👯 exact duplicate of the Acme invoice
│   ├── report.tmp                    🗑️ temporary file
│   ├── holiday-photo.png             🖼️ image (metadata only)
│   └── big-installer.dmg             🐘 3 MB (large_file_mb = 2 in demo config)
└── Desktop/hello.py                  💻 code
```

The demo uses its own [config.demo.yaml](demo/config.demo.yaml), so **all data stays in `review-system/demo/`**. Your real `~/Documents`, `data/`, and `knowledge/` were not touched.

## 6.2 Results, feature by feature

| # | Test | Command / method | Expected | Actual | Result |
|:-:|:--|:--|:--|:--|:-:|
| 0 | Automated tests | `pytest -q` | pass | **37 passed** in 8 s | ✅ |
| 1 | Health check | `--check` | config, paths, model | all shown, dry_run = True | ✅ |
| 2 | First scan | `--scan` | 13 files hashed | `13 hashed, 0 unchanged · dup=2 large=1 stale=1 temp=1` | ✅ |
| 3 | Incremental scan | `--scan` again | 0 hashed | `0 hashed, 13 unchanged` | ✅ |
| 4 | Software detection | `--software` | apps listed | 30 apps (14 recent, 16 rarely used) | ✅ |
| 5 | Read PDF | `--read invoice-q3.pdf` | text + metadata | 181 chars, `[Page 1] … 4,800 USD` | ✅ |
| 6 | Secret file guard | `--read .env` | refused | `Skipped sensitive file` | ✅ |
| 7 | RAG indexing | `--index` | 10 indexed, 3 skipped | `indexed=10 skipped=3 chunks=10` | ✅ |
| 8 | Re-index unchanged | `--index` again | all skipped | `indexed=0 skipped=13` | ✅ |
| 9 | **Duplicates in RAG** | inspect ChromaDB vs manifest | 10 files stored | **8 stored**: `invoice-q3.pdf` and `pasta-copy.md` were erased by their twins | 🐞 |
| 10 | Semantic search | `--search "how much money is due on the invoice"` | invoice first | invoice first, then the kickoff doc and budget | ✅ |
| 11 | OKF build | `--build-okf` | linked notes | 11 files, 5 folders, 5 projects, 30 apps, 24 topics · **75 nodes / 111 edges** · `.env` + `.tmp` skipped | ✅ |
| 12 | OKF quality | read `files/invoice-q3-*.md` | distilled summary | first 180 chars **copied raw** (amount + email); "Downloads" is a *project*; "Opened with" = ChatGPT Atlas, Claude, DuckDuckGo | ⚠️ |
| 13 | Protected content | read `files/contract-*.md` | — | the confidential contract is indexed and previewed in OKF (protected = "don't move", not "don't read") | ⚠️ |
| 14 | Recommendations | `--recommend` | suggestions | 5 suggestions, 3 patterns | ✅ |
| 15 | Pattern counter | `--recommend` twice | observations stay 1 | **observations = 2** (it counts runs, not evidence) | ⚠️ |
| 16 | Reports | `--report both` | md + html + OKF | all three written | ✅ |
| 17 | **Cleanup workflow** | `--workflow cleanup` | 3 rows `proposed` | 3 rows **`approved`** (no human), dry_run = 1 | 🐞 |
| 18 | Cleanup repeat | run it again | no duplicates | **6 rows** (same 3 proposed again) | 🐞 |
| 19 | UI pending count | `GET /steward/health` | 3 pending | `pending_actions = 0` | 🐞 |
| 20 | Can those rows be approved? | `POST /actions/1/approve` | — | `error: Action #1 is 'approved', not 'proposed'` (stuck forever) | 🐞 |
| 21 | Proper proposal + dry-run approve | API | stays safe | `dry_run`, but row left at `approved` | ⚠️ |
| 22 | Real delete → recycle | API `dry_run:false` | file in recycle | `done` → `data/recycle/20261126…_report.tmp` | ✅ |
| 23 | Undo | `POST /actions/{id}/undo` | file back | `undone`, file restored | ✅ |
| 24 | Protected path | propose delete of `Work/Clients/contract.txt` | blocked | `blocked` | ✅ |
| 25 | Organize plan | `plan_organize(Downloads, "type")` | proposals | 4 `proposed` rows → `organized_by_type/<category>/…` | ✅ |
| 26 | Settings type-safety | `PUT /settings {"dry_run":"false"}` | dry_run false | **dry_run = True** (`bool("false")`) | ⚠️ |
| 27 | Settings file | after PUT | comments kept | `config.demo.yaml` rewritten, **all comments gone** | ⚠️ |
| 28 | **Ghost files** | recycle `pasta-copy.md`, rescan | row removed | row **still in DB**, still in RAG manifest and OKF; still reported as a duplicate | 🐞 |
| 29 | Downloads watcher | drop a new PDF | event + proposal | event logged in 3 s ✅; suggested **`/Users/kumarnishant/Documents/Documents`** (real home, hard-coded); **no proposal**, not added to `files` | ⚠️ |
| 30 | Chat, `gemma3:4b` (default in `config.yaml`) | `--chat` | answer | `does not support tools (status code: 400)` | 🐞 |
| 31 | Chat, `qwen3:4b` | `--chat` | answer | correct, cited path + quote, **~100 s** | ✅ |
| 32 | Chat, **`gemma4`** | `--chat` × 6 | correct every time | **3/6 correct** (18–34 s). Failures: Team routed to **AnalyzerAgent**, which has no RAG and looked for a file literally named "Acme invoice" | ⚠️ |
| 33 | Chat action → approval | Team: "delete report.tmp" | pause, then confirm | **paused ✅** (`RunStatus.paused`, file untouched), but `/steward/chat` returns only text: **no way to confirm**, no action row created | 🐞 |
| 34 | Docker compose | `docker compose config` | valid | valid; Docker running. *Not started* (it would scan your real `~/Documents`) | ✅ |
| 35 | Demo script | `bash run_demo.sh` | runs clean | completes in ~43 s | ✅ |

**Totals (36 checks):** ✅ 20 pass · ⚠️ 8 work with caveats · 🐞 8 bugs (several counted under one issue in [08](08-issues-and-risks.md)).

## 6.3 Key evidence (raw output)

**Incremental scan:**

```text
Scanned 13 files (13 hashed, 0 unchanged) | dup=2, large=1, stale=1, temp=1
Scanned 13 files (0 hashed, 13 unchanged) | dup=2, large=1, stale=1, temp=1
```

**Duplicates erasing each other in ChromaDB:**

```text
INFO    Deleted 1 documents with content_hash '636927a0cca5…' from 'documents'
chunks actually stored in ChromaDB: 8
manifest claims: 10 files, 10 chunks
```

**Cleanup workflow approving itself:**

```text
id | action_type | status   | dry_run | reason
1  | delete      | approved | 1       | Temporary file candidate
2  | delete      | approved | 1       | Duplicate file candidate
3  | delete      | approved | 1       | Duplicate file candidate
HEALTH: pending_actions = 0
APPROVE workflow row #1: error - Action #1 is 'approved', not 'proposed'.
```

**Safety features that work:**

```text
APPROVE (real): done -> 20261126182428389239_report.tmp   | file still in Downloads? False
UNDO: undone                                              | file back? True
PROTECTED: blocked - contract.txt
Could not read sample_home/Documents/.env: Skipped sensitive file
```

**Ghost files after recycling:**

```text
Recycled pasta-copy.md: done | exists on disk: False
After rescan -> DB still has row for deleted file? True
Duplicate groups still reported: 2 (should be 1 now)
Search index still has the recycled file? True
OKF concept still exists? True
```

**Chat: model comparison:**

```text
gemma3:4b → ERROR Error in Team run: registry.ollama.ai/library/gemma3:4b does not support tools (status code: 400)
qwen3:4b  → "The amount due on the Acme invoice is $4,800 USD. Source: …/Downloads/invoice-q3 (1).pdf" (99.8 s)
gemma4    → run 1 (18 s): "4,800 USD, as stated in the file invoice-q3 (1).pdf"            ✅
            run 2 (22 s): "The AnalyzerAgent reported … 'Acme invoice' was not available"  ❌ wrong agent
            run 3 (29 s): "4,800 USD … …/Downloads/invoice-q3 (1).pdf"                     ✅
            run 4 (19 s): "I was unable to locate the 'Acme invoice document' …"           ❌
```

Note that every correct answer cites the **Downloads copy**. That's because the RAG bug (#5) erased the original in `Documents/Acme/`.

**Approval pause in chat (gemma4):**

```text
RUN STATUS: RunStatus.paused | is_paused: True
REQUIREMENTS: tool_name='delete_files', requires_confirmation=True, member_agent_name='OrganizerAgent'
REPLY TEXT: Team run paused. The following require input:
- OrganizerAgent: delete_files requires confirmation
new action rows: 0 | file exists: True
```

## 6.4 What I did **not** test

- `docker compose up` (it would mount and scan your real home folders). The compose file was validated instead.
- Cloud providers (OpenAI, Anthropic, Gemini). No keys were used, and only the "missing key" error path is covered by unit tests.
- Very large collections. Performance concerns in [08](08-issues-and-risks.md) are based on reading the code (for example, the hourly full OKF rebuild over your ~8,000 real files).
- The Streamlit page in a browser. Its API calls were tested directly through FastAPI's `TestClient`.

➡️ Next: [07-prd-compliance.md](07-prd-compliance.md)
