"""A new user's first chat: find a file, the largest file, recover it; two chats at once; delete a chat."""

import threading
import time
from types import SimpleNamespace

from steward.chat_commands import ChatCommands
from steward.chat_workers import ChatWorkers
from steward.tools import FinderTools
from tests.test_chat_approvals import build


def home(tmp_path):
    """API server whose watched folder (docs) was never scanned, with a few files of known size."""
    app, server, client = build(tmp_path)
    docs = tmp_path / "docs"
    (docs / "taxes").mkdir()
    (docs / "taxes" / "Invoice-2024.pdf").write_bytes(b"x" * 3000)
    (docs / "holiday.mov").write_bytes(b"x" * 9000)
    (docs / ".hidden-invoice.pdf").write_bytes(b"x" * 99999)
    return app, server.agents.scanner_tools, FinderTools(app.config, app.db)


class TestFindingFilesBeforeTheFirstScan:
    """Searching by name and the largest file work even though nothing was scanned yet."""

    def test_find_by_name_and_pattern(self, tmp_path):
        _, _, tools = home(tmp_path)
        found = tools.find_files("invoice")
        assert found["status"] == "ok" and [f["name"] for f in found["files"]] == ["Invoice-2024.pdf"]
        assert [f["name"] for f in tools.find_files("*.pdf")["files"]] == ["Invoice-2024.pdf"]  # hidden files skipped
        assert tools.find_files("nothing-like-this")["message"].startswith("No file matching")
        assert tools.find_files("  ")["status"] == "error"

    def test_largest_file_without_a_scan_then_from_the_index(self, tmp_path):
        app, tools, _ = home(tmp_path)
        assert tools.find_large_files(min_mb=0, limit=1)["files"][0]["name"] == "holiday.mov"
        app.scanner.scan_all()
        (tmp_path / "docs" / "holiday.mov").unlink()  # the index still lists it; deleted files are skipped
        assert tools.find_large_files(min_mb=0, limit=1)["files"][0]["name"] == "Invoice-2024.pdf"

    def test_list_a_folder(self, tmp_path):
        """'What is in docs?' lists files and sub-folders (not hidden ones) with sizes."""
        _, _, tools = home(tmp_path)
        listed = tools.list_folder(str(tmp_path / "docs"))
        names = {item["name"]: item["kind"] for item in listed["items"]}
        assert names == {"holiday.mov": "file", "report.tmp": "file", "taxes": "folder"}
        assert listed["message"].endswith("holds 3 item(s).")
        assert tools.list_folder(str(tmp_path / "missing"))["status"] == "error"

    def test_recover_it_means_undo(self):
        commands = ChatCommands(store=None, organizer_tools=None)
        for text in ["can you recover it", "Can you recover it?", "bring it back", "restore the file"]:
            assert commands.classify(text) == "undo", text
        for text in ["can you restore my thesis from last year", "bring me a coffee", "can you archive it"]:
            assert commands.classify(text) is None, text


class TestTwoChatsAtOnce:
    """A second chat answers while the first is still working; one chat stays in order."""

    def test_other_chat_does_not_wait(self):
        first_started, release, finished = threading.Event(), threading.Event(), []

        def run(job):
            if job["name"] == "slow":
                first_started.set()
                release.wait(5)
            finished.append(job["name"])
        workers = ChatWorkers(run, count=2)
        workers.submit({"session_id": "chat-a", "name": "slow"})
        assert first_started.wait(2)
        workers.submit({"session_id": "chat-b", "name": "quick"})
        deadline = time.time() + 2
        while "quick" not in finished and time.time() < deadline:
            time.sleep(0.01)
        assert finished == ["quick"]  # chat B answered while chat A was still busy
        release.set()

    def test_same_chat_stays_in_order(self):
        order = []

        def run(job):
            order.append(f"start {job['name']}")
            time.sleep(0.05)
            order.append(f"end {job['name']}")
        workers = ChatWorkers(run, count=2)
        workers.submit({"session_id": "chat-a", "name": "1"})
        workers.submit({"session_id": "chat-a", "name": "2"})
        deadline = time.time() + 2
        while len(order) < 4 and time.time() < deadline:
            time.sleep(0.01)
        assert order == ["start 1", "end 1", "start 2", "end 2"]

    def test_progress_and_changes_belong_to_each_job(self, tmp_path):
        """Two jobs at once never see each other's progress or recorded changes."""
        _, server, _ = build(tmp_path)
        tools, seen = server.agents.organizer_tools, {}
        tools.done_actions = [1]

        def other_job():
            seen["actions"], seen["progress"] = tools.done_actions, tools.progress
        thread = threading.Thread(target=other_job)
        thread.start()
        thread.join()
        assert seen == {"actions": None, "progress": None} and tools.done_actions == [1]


class TestDeletingOneChat:
    """Recent chats can delete one chat; its AI memory goes too; running chats are marked."""

    def test_delete_one_chat(self, tmp_path):
        _, server, client = build(tmp_path)
        forgotten = []
        server.agents.session_db = SimpleNamespace(delete_session=forgotten.append)
        server.chat_routes.store.add_message("web-1", "user", "hello")
        server.chat_routes.store.add_message("web-2", "user", "other chat")
        listed = client.get("/steward/chat/conversations").json()["conversations"]
        assert {c["id"]: c["running"] for c in listed} == {"web-1": False, "web-2": False}
        assert client.delete("/steward/chat/conversations/web-1").status_code == 200
        assert forgotten == ["web-1"]
        assert [c["id"] for c in client.get("/steward/chat/conversations").json()["conversations"]] == ["web-2"]
