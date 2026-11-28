"""Steward remembers what a chat talked about: "delete the file" after "which file is largest"."""

from types import SimpleNamespace

from agno.run.base import RunStatus

from steward.chat_found import FoundPaths
from steward.chat_memory import ChatMemory
from tests.test_chat_approvals import FakeTeam
from tests.test_chat_control import Streamed, as_output, ask, jobs_server

BIG = "/Users/you/Desktop/screenshots-recordings/Screen Recording 2026-07-08 at 16.47.31.mov"
LARGEST = f"The largest file is:\n\n- **Full Path:** `{BIG}`\n- Next: `/Users/you/Desktop/b.zip`"


def saved(role, content, **data):
    """One message as ChatStore.messages returns it."""
    return {"role": role, "content": content, "data": data}


class TestNotes:
    """Notes come from saved results: paths, folders, decisions and real changes."""

    def test_paths_in_text(self):
        text = f"See `{BIG}`. Also ~/Desktop/docs/report.pdf, and `{BIG}` again; not `npm`."
        assert ChatMemory.paths_in(text) == [BIG, "~/Desktop/docs/report.pdf"]

    def test_last_answer_paths_come_first(self):
        notes = ChatMemory(store=None).notes([
            saved("user", "scan ~/Desktop/docs"),
            saved("assistant", "Scanned it.", folder={"path": "/Users/you/Desktop/docs"}),
            saved("user", "which file is the largest one?"),
            saved("assistant", LARGEST),
        ])
        assert notes[0] == f"Paths in the last answer that named files (main one first): `{BIG}`, `/Users/you/Desktop/b.zip`"
        assert notes[1] == "Other paths mentioned in this chat (newest first): `~/Desktop/docs`"
        assert "Folder last scanned: `/Users/you/Desktop/docs`" in notes

    def test_rejected_and_done_changes(self):
        """A rejected card says nothing changed; a done change names where the files went, and an undo."""
        actions = {
            7: {"action_type": "archive", "target_path": "/app/data/archives/docs.zip", "status": "undone",
                "source_path": '["/data/Desktop/docs/a.txt", "/data/Desktop/docs/b.txt"]'},
            8: {"action_type": "delete", "target_path": "/app/data/recycle/123_big.mov", "status": "undone",
                "source_path": "/data/Desktop/big.mov"},
        }
        memory = ChatMemory(store=None, get_action=actions.get)
        card = {"summary": "Zip folder docs (33 files) into an archive", "paths": ["/Users/you/Desktop/docs"]}
        notes = memory.notes([
            saved("assistant", "needs approval", status="approval", decision="rejected", approvals=[card]),
            saved("assistant", "Done.", actions=[7]),
            saved("assistant", "Recycled it.", actions=[8]),
        ])
        assert ("2 file(s) starting with `/data/Desktop/docs/a.txt` were zipped into `/app/data/archives/docs.zip`; "
                "then unzipped again: the files are back where they were") in notes
        # A recovered file is named by its real place, never by Steward's recycle-bin path
        assert "`/data/Desktop/big.mov` was moved to Steward's recycle bin; then it was recovered and is back at " \
               "`/data/Desktop/big.mov`" in notes
        assert not any("recycle/123_big.mov" in n for n in notes)
        rejected = [n for n in notes if n.startswith("The user REJECTED")][0]
        assert "Zip folder docs (33 files)" in rejected and "no file was moved, archived, zipped" in rejected

    def test_paths_the_tools_found_come_first(self):
        """The AI only wrote the file name; the path the tool returned is still remembered, first."""
        result = str({"status": "ok", "files": [{"path": BIG, "size_bytes": 9}, {"path": "/Users/you/b.zip"}]})
        member = SimpleNamespace(tools=[SimpleNamespace(tool_name="find_large_files", result=result)], member_responses=None)
        run = SimpleNamespace(tools=[SimpleNamespace(tool_name="find_files", result='{"status": "error"}')],
                              member_responses=[member])
        found = FoundPaths().collect(run)
        assert found == [BIG, "/Users/you/b.zip"]
        notes = ChatMemory(store=None).notes([
            saved("assistant", "The largest file is Screen Recording 2026-07-08 at 16.47.31.mov.", found_paths=found)])
        assert notes[0].startswith(f"Paths in the last answer that named files (main one first): `{BIG}`")

    def test_message_alone_without_notes(self):
        store = SimpleNamespace(messages=lambda session_id, limit: [saved("user", "hello")])
        assert ChatMemory(store).with_context("s", "hello") == "hello"


class RecordingTeam(Streamed, FakeTeam):
    """Answers the first question with the largest file; records every message it is sent."""

    def __init__(self, target, tools=None):
        super().__init__(target)
        self.messages = []

    def run(self, message, session_id=None, stream=False, **kwargs):
        self.messages.append(message)
        if "largest" in message and "delete" not in message:
            done = SimpleNamespace(run_id="run-0", session_id=session_id, status=RunStatus.completed, content=LARGEST,
                                   requirements=[], tools=[], references=None, member_responses=None)
            return iter([as_output(done)]) if stream else done
        return super().run(message, session_id=session_id, stream=stream)


class TestMemoryInTheChat:
    """The team gets Steward's notes with every question, and helpers see recent answers."""

    def test_delete_the_file_carries_the_path(self, tmp_path):
        server, client, _ = jobs_server(tmp_path, team=RecordingTeam)
        ask(client, "which file is largest one ?")
        ask(client, "can you delete the file")
        sent = server.agents.team.messages
        assert sent[0] == "which file is largest one ?"  # nothing to remember yet
        assert sent[1].startswith(ChatMemory.INTRO) and f"`{BIG}`" in sent[1]
        assert sent[1].endswith("The user's message: can you delete the file")
        # The conversation itself keeps the user's own words
        saved_messages = client.get("/steward/chat/conversations/s-1").json()["messages"]
        assert saved_messages[2]["content"] == "can you delete the file"

    def test_helpers_see_the_team_history(self, tmp_path):
        server, _, _ = jobs_server(tmp_path)
        team = server.agents._build_orchestrator_team()
        assert team.add_team_history_to_members is True and team.num_team_history_runs == 3
