"""Steward's own notes under chat answers, and steps that cannot work are declined before asking."""

import json
import os
from types import SimpleNamespace

from agno.run.base import RunStatus

from steward.chat_notices import ChatNotices
from tests.test_chat_approvals import FakeTeam, build


def tool(name, result):
    """A finished tool call as Agno stores it on a run."""
    return SimpleNamespace(tool_name=name, result=result)


def run_with(tools, members=None, content="Done."):
    """A completed Agno run holding the given tool calls."""
    return SimpleNamespace(run_id="r", session_id="s", status=RunStatus.completed, content=content,
                           requirements=[], tools=tools, references=None, member_responses=members or [])


class TestChatNotices:
    """Notes come from the tool results, never from the AI's wording."""

    def test_practice_mode_and_problems_are_reported(self):
        """dry_run gives the practice-mode note; errors give their exact message; other tools are ignored."""
        member = run_with([
            tool("delete_files", json.dumps({"status": "dry_run", "message": "x", "results": [{"status": "dry_run"}]})),
            tool("archive_files", str({"status": "error", "message": "Steward can only read /Users/you/Desktop"})),
            tool("scan_folder", json.dumps({"status": "error", "message": "not a file tool"})),
        ])
        notes = ChatNotices().collect(run_with([], members=[member]))
        assert notes == [ChatNotices.PRACTICE, "Steward can only read /Users/you/Desktop"]
        assert ChatNotices.as_markdown(notes).startswith("> **Steward:** Practice mode")

    def test_unreadable_results_and_real_changes_add_nothing(self):
        """A done action or an unparsable result adds no note."""
        done = tool("delete_files", json.dumps({"status": "ok", "results": [{"status": "done"}]}))
        assert ChatNotices().collect(run_with([done, tool("move_file", "not json")])) == []


class CompletedTeam(FakeTeam):
    """Answers at once, claiming a delete although the tool only previewed it."""

    def run(self, message, session_id=None):
        preview = tool("delete_files", json.dumps({"status": "dry_run", "message": "Practice mode"}))
        return run_with([preview], content="The file has been successfully deleted.")


class TestChatServiceNotes:
    """The chat reply always tells the truth about file changes."""

    def test_practice_note_is_added_when_the_ai_claims_a_delete(self, tmp_path):
        """Even if the AI says 'deleted', the reply states that practice mode changed nothing."""
        _, server, client = build(tmp_path)
        server.agents.team = CompletedTeam()
        reply = client.post("/steward/chat", json={"message": "delete it"}).json()["reply"]
        assert reply.startswith("The file has been successfully deleted.")
        assert ChatNotices.PRACTICE in reply

    def test_missing_file_is_declined_without_an_approval_card(self, tmp_path):
        """A step on a path that does not exist is declined, with the reason given to the AI and the user."""
        _, server, client = build(tmp_path)
        server.agents.team = FakeTeam(str(tmp_path / "docs" / "gone.tmp"))
        body = client.post("/steward/chat", json={"message": "delete gone.tmp"}).json()
        assert body["status"] == "ok" and "run_id" not in body
        assert body["reply"].startswith("OK, I left the file alone.") and "Not found" in body["reply"]
        assert server.agents.team.rejection_note.startswith("Steward could not do this: Not found")

    def test_read_only_folder_is_declined_before_asking(self, tmp_path):
        """A folder Steward may not change is declined up front with a clear permission message."""
        _, server, client = build(tmp_path)
        os.chmod(tmp_path / "docs", 0o555)
        try:
            body = client.post("/steward/chat", json={"message": "delete report.tmp"}).json()
        finally:
            os.chmod(tmp_path / "docs", 0o755)
        assert body["status"] == "ok" and "permission to change files" in body["reply"]
        assert (tmp_path / "docs" / "report.tmp").exists()
