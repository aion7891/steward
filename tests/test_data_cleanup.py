"""Settings → Data & cleanup: clear chats, knowledge notes, topics and the recycle bin; restore backups."""

import zipfile
from types import SimpleNamespace

from steward.data_backups import DataBackups
from steward.data_cleanup import DataCleanup
from tests.test_chat_approvals import build

DELETE = {"confirm": "DELETE"}


def setup(tmp_path):
    """API server with two chats, three knowledge notes (one topic) and one recycled file."""
    app, server, client = build(tmp_path)
    store = server.chat_routes.store
    store.add_message("web-1", "user", "scan ~/Desktop/docs")
    store.add_message("web-1", "assistant", "Scanned 4 files.", {"status": "ok"})
    store.add_message("web-2", "user", "hello")
    root = app.okf_bundle.root_dir
    for rel in ("topics/invoices.md", "files/report.md", "projects/apollo.md"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(f"---\ntitle: {rel}\ntype: concept\n---\nNote {rel}\n", encoding="utf-8")
    junk = tmp_path / "junk.txt"
    junk.write_text("old", encoding="utf-8")
    app.organizer.recycle.move_to_recycle(junk)
    return app, server, client


class TestSummaryAndChats:
    """What Steward keeps, and clearing chats with or without a backup."""

    def test_summary_counts_everything(self, tmp_path):
        _, _, client = setup(tmp_path)
        data = client.get("/steward/data").json()
        assert data["chats"] == {"count": 2, "messages": 3}
        assert data["knowledge"]["count"] == 3 and data["topics"]["count"] == 1
        assert data["recycle"]["count"] == 1 and data["backups"] == []

    def test_clear_keeps_a_backup_that_restores(self, tmp_path):
        _, _, client = setup(tmp_path)
        cleared = client.post("/steward/data/clear", json={"target": "chats"}).json()
        assert cleared["removed"] == 2 and cleared["backup"].startswith("chats-") and "backup was kept" in cleared["message"]
        assert client.get("/steward/chat/conversations").json()["conversations"] == []
        restored = client.post(f"/steward/data/backups/{cleared['backup']}/restore").json()
        assert restored["restored"] == 2
        messages = client.get("/steward/chat/conversations/web-1").json()["messages"]
        assert [m["content"] for m in messages] == ["scan ~/Desktop/docs", "Scanned 4 files."]
        # Restoring twice adds nothing: existing chats are left alone
        assert client.post(f"/steward/data/backups/{cleared['backup']}/restore").json()["restored"] == 0

    def test_hard_delete_needs_the_word_delete(self, tmp_path):
        _, _, client = setup(tmp_path)
        refused = client.post("/steward/data/clear", json={"target": "chats", "hard": True, "confirm": "yes"})
        assert refused.status_code == 400 and "Type DELETE" in refused.json()["detail"]
        done = client.post("/steward/data/clear", json={"target": "chats", "hard": True, **DELETE}).json()
        assert done["backup"] is None and done["message"] == "Deleted 2 chat(s) for good."
        assert client.get("/steward/data").json()["backups"] == []

    def test_chats_wait_for_a_running_answer(self, tmp_path):
        _, server, client = setup(tmp_path)
        server.chat_routes.jobs.busy = lambda: True
        response = client.post("/steward/data/clear", json={"target": "chats"})
        assert response.status_code == 409 and "press Stop" in response.json()["detail"]

    def test_ai_memory_of_chats_is_forgotten_but_background_jobs_keep_theirs(self, tmp_path):
        app, server, _ = setup(tmp_path)
        deleted = []
        session_db = SimpleNamespace(get_sessions=lambda **kw: ([{"session_id": "web-1"}, {"session_id": "wf-77"}], 2),
                                     delete_sessions=deleted.extend)
        pending = []
        cleanup = DataCleanup(app, server.chat_routes.store, lambda: session_db, forget_pending=lambda: pending.append(1))
        cleanup.clear("chats")
        assert deleted == ["web-1"] and pending == [1]


class TestKnowledgeAndRecycle:
    """Knowledge notes (all or topics only) and the recycle bin."""

    def test_topics_only_then_restore(self, tmp_path):
        app, _, client = setup(tmp_path)
        root = app.okf_bundle.root_dir
        cleared = client.post("/steward/data/clear", json={"target": "topics"}).json()
        assert cleared["removed"] == 1 and not (root / "topics/invoices.md").exists()
        assert (root / "files/report.md").exists() and (root / "index.md").exists()
        assert "invoices" not in (root / "index.md").read_text(encoding="utf-8")
        client.post(f"/steward/data/backups/{cleared['backup']}/restore")
        assert (root / "topics/invoices.md").exists()

    def test_all_notes_for_good(self, tmp_path):
        app, _, client = setup(tmp_path)
        done = client.post("/steward/data/clear", json={"target": "knowledge", "hard": True, **DELETE}).json()
        assert done["removed"] == 3 and client.get("/steward/data").json()["knowledge"]["count"] == 0
        assert (app.okf_bundle.root_dir / "index.md").exists()

    def test_recycle_bin_is_emptied_for_good_only_with_delete(self, tmp_path):
        _, _, client = setup(tmp_path)
        assert client.post("/steward/data/clear", json={"target": "recycle"}).status_code == 400
        done = client.post("/steward/data/clear", json={"target": "recycle", **DELETE}).json()
        assert done["removed"] == 1 and "Undo no longer works" in done["message"]
        assert client.get("/steward/data").json()["recycle"]["count"] == 0


class TestBackups:
    """Backup names are checked; deleting one needs DELETE; a ZIP can't write outside the notes."""

    def test_bad_unknown_and_delete(self, tmp_path):
        _, _, client = setup(tmp_path)
        assert client.post("/steward/data/clear", json={"target": "everything"}).status_code == 400
        assert client.post("/steward/data/backups/..%2Fsteward.db/restore").status_code in (400, 404)
        assert client.post("/steward/data/backups/evil.json/restore").status_code == 400
        assert client.post("/steward/data/backups/chats-20260101-000000.json/restore").status_code == 404
        backup = client.post("/steward/data/clear", json={"target": "chats"}).json()["backup"]
        assert client.post(f"/steward/data/backups/{backup}/delete").status_code == 400
        assert client.post(f"/steward/data/backups/{backup}/delete", json=DELETE).status_code == 200
        assert client.get("/steward/data").json()["backups"] == []

    def test_zip_cannot_escape_the_knowledge_folder(self, tmp_path):
        backups = DataBackups(tmp_path / "backups")
        (tmp_path / "backups").mkdir()
        with zipfile.ZipFile(tmp_path / "backups" / "topics-20260101-000000.zip", "w") as archive:
            archive.writestr("../escaped.md", "bad")
            archive.writestr("topics/run.sh", "bad")
            archive.writestr("topics/ok.md", "good")
        root = tmp_path / "knowledge"
        assert backups.extract_markdown("topics-20260101-000000.zip", root) == 1
        assert (root / "topics/ok.md").exists() and not (tmp_path / "escaped.md").exists()
