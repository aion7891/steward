# 8. Troubleshooting and FAQ

## Something looks wrong

| What you see | Why | What to do |
|:--|:--|:--|
| Red **"Steward API is not reachable"** box | Steward's background part isn't running | Run `docker compose up -d` in the Steward folder; wait 30 s (the page retries) |
| Chat: **"Failed to connect to Ollama"** + Retry | The AI app is closed | Open Ollama (or run `ollama serve`), then click **Retry** |
| Chat answer says it **can't find the file** | Small local models sometimes search badly | Rephrase, mention the file name, or try again |
| Settings: model shows **no tools** | That model can't drive Steward's helpers | Pick one marked **can use tools** (e.g. gemma4) |
| **"Folder not found … can only see these folders"** | Docker can only see shared folders | Share it with `STEWARD_EXTRA_DIR` in `.env` ([Getting started](01-getting-started.md#which-folders-can-steward-see)) |
| **Approve** did nothing to the file | Dry-run is ON (green badge, top right) | That's practice mode. Turn it off in [Settings](06-settings.md) when you're ready |
| **Run now** is greyed out | Same: dry-run is ON | Turn dry-run off in Settings |
| A setting says **Locked by … in .env** | The `.env` file fixes that value | Edit or remove that line in `.env`, then `docker compose up -d` |
| **"Steward can only read … shared read-only"** | Documents/Desktop are shared read-only by default | Add `STEWARD_DESKTOP_ACCESS=rw` (or `STEWARD_DOCUMENTS_ACCESS=rw`) to `.env` and run `docker compose up -d`, or move the file yourself |
| **"… must be 'rw' or 'ro' (found 'yes')"** | The access switch in `.env` has another value | Use exactly `rw` (allow changes) or `ro` (read-only) |
| Dashboard still mentions a file you deleted | Steward's list catches up on the next scans | Run a scan; full clean-up of old entries is on the to-do list for a future version |
| The page looks out of date | It refreshes every minute | Click **Refresh** on the Dashboard |
| Chat: **"This answer is no longer available"** | Steward restarted while it was answering | Ask again; your question is still in the chat |
| Chat: **"reconnecting…"** next to *Working…* | The page lost contact with Steward for a moment | Wait; it reconnects by itself (start Steward if the red box appears) |
| Chat: **"Starting…"** for a while | Two chats are already answering; yours is next | Wait a moment, or press **Stop** in another chat |
| Chat: **"Stopped after 5 minutes without an answer"** | The question took too long (often a very broad one) | Ask something more specific, for example with the exact path |
| Chat: the 🗑 icon in Recent chats is greyed out | That chat is still answering | Wait for the answer, or open it and press **Stop** |
| Chat: "it" or "the file" means the wrong thing | Small models sometimes mix up earlier files | Say the file name or path once; Steward remembers it from then on |
| Settings: **Delete for good** stays greyed out | It needs the word typed exactly | Type `DELETE` in capitals |
| Settings: clearing chats says **"still answering"** | A chat answer is running | Wait for it or press **Stop**, then try again |
| Chat: a red step **"… could not finish"** | A helper's AI call failed (often Ollama is busy or out of memory) | Ask again; close other apps if it keeps happening |
| Chat: the answer seems to stop early | Steward stops a helper after a few tries, so it can't loop forever | Ask a more specific question, for example with the exact path |

## Frequently asked questions

**Can Steward delete my files?**
Not on its own. "Delete" means *move to Steward's recycle bin*, only after you approve, and only
when practice mode (dry-run) is off. You can undo it.

**Do my documents go to the internet?**
No, with the default setup the AI runs on your computer through Ollama. Only if you choose a cloud
provider or an Ollama *cloud* model (marked **cloud** in Settings) are questions sent out, and a
warning appears at the top of every page while one is active.

**Does it read my passwords?**
Files that look private (`.env`, key files, names containing *password*, *secret*, *credentials*)
are skipped.

**How often does it scan?**
Every hour for the watched folders, plus whenever you use **Scan a folder**. Unchanged files are
recognized quickly, so repeat scans are light.

**Why is the AI slow?**
It runs on your computer. Expect 10–40 seconds per answer with gemma4; faster computers answer quicker.

**How do I start over?**
Use [Settings → Data & cleanup](06-settings.md#data--cleanup) to clear chats and knowledge notes, and
delete `data/settings.override.yaml` to undo Settings changes. Your files themselves are never part
of Steward's data.
