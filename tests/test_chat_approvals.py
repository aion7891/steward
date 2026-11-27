"""Tests for approving file changes from the chat (review issue #2) and the dry-run safety rule."""

from types import SimpleNamespace

import yaml
from agno.run.base import RunStatus
from fastapi.testclient import TestClient

from steward.api import StewardAPIServer
from steward.chunker import HashEmbedder
from steward.main import StewardApp
from steward.rag import RAGIndex
from steward.tools import OrganizerTools


class FakeRequirement:
    """Behaves like agno.run.requirement.RunRequirement for one confirmation step."""

    def __init__(self, tool_name, tool_args):
        self.tool_execution = SimpleNamespace(tool_name=tool_name, tool_args=tool_args)
        self.member_agent_name = "OrganizerAgent"
        self.confirmation = None

    @property
    def needs_confirmation(self):
        return self.confirmation is None

    def confirm(self):
        self.confirmation = True

    def reject(self, note=None):
        self.confirmation = False


class FakeTeam:
    """run() pauses for one delete; continue_run() finishes based on the user's decision."""

    def __init__(self):
        self.sessions = []

    def run(self, message, session_id=None):
        self.sessions.append(session_id)
        req = FakeRequirement("delete_files", {"file_paths": ["/docs/report.tmp"], "reason": "temp file"})
        return SimpleNamespace(run_id="run-1", session_id=session_id, status=RunStatus.paused, content="paused",
                               requirements=[req], tools=[], references=None, member_responses=None)

    def continue_run(self, run_response=None, requirements=None):
        approved = requirements[0].confirmation is True
        text = "Moved report.tmp to the recycle bin." if approved else "OK, I left the file alone."
        return SimpleNamespace(run_id="run-1", session_id=run_response.session_id, status=RunStatus.completed,
                               content=text, requirements=[], tools=[], references=None, member_responses=None)


def build(tmp_path, dry_run=True):
    """API server whose team is replaced by FakeTeam."""
    (tmp_path / "docs").mkdir()
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.safe_dump({"scanner": {"watched_folders": [str(tmp_path / "docs")]},
                                   "safety": {"dry_run": dry_run}}), encoding="utf-8")
    app = StewardApp(config_path=cfg, base_dir=tmp_path)
    server = StewardAPIServer(app=app, rag_index=RAGIndex(app.config, embedder=HashEmbedder(dimensions=64), reader=app.reader))
    server.agents.team = FakeTeam()
    server.chat.agents = server.agents
    return app, server, TestClient(server.fastapi_app)


class TestApproveFromChat:
    """A paused run becomes an approval card; the decision resumes it."""

    def test_pause_shows_a_plain_language_card(self, tmp_path):
        _, server, client = build(tmp_path)
        body = client.post("/steward/chat", json={"message": "delete report.tmp", "session_id": "s-1"}).json()
        assert body["status"] == "approval" and body["run_id"] == "run-1" and body["session_id"] == "s-1"
        step = body["approvals"][0]
        assert step["summary"] == "Move 1 file(s) to Steward's recycle bin"
        assert step["names"] == ["report.tmp"] and step["reason"] == "temp file" and step["dry_run"] is True
        assert server.agents.team.sessions == ["s-1"]  # the conversation id reaches the AI

    def test_approve_and_reject_resume_the_run(self, tmp_path):
        _, _, client = build(tmp_path)
        client.post("/steward/chat", json={"message": "delete report.tmp"})
        approved = client.post("/steward/chat/run-1/decision", json={"approve": True}).json()
        assert approved["status"] == "ok" and approved["reply"] == "Moved report.tmp to the recycle bin."
        # Deciding twice is refused: the run is no longer waiting
        assert client.post("/steward/chat/run-1/decision", json={"approve": True}).status_code == 404
        client.post("/steward/chat", json={"message": "delete report.tmp"})
        rejected = client.post("/steward/chat/run-1/decision", json={"approve": False}).json()
        assert rejected["reply"] == "OK, I left the file alone."

    def test_bad_decisions_are_refused(self, tmp_path):
        _, _, client = build(tmp_path)
        client.post("/steward/chat", json={"message": "delete report.tmp"})
        assert client.post("/steward/chat/run-1/decision", json={"approve": "yes"}).status_code == 400
        assert client.post("/steward/chat/unknown/decision", json={"approve": True}).status_code == 404


class TestDryRunAlwaysWins:
    """The AI chooses tool arguments; it must never be able to switch dry-run off."""

    def test_ai_cannot_turn_a_preview_into_a_real_delete(self, tmp_path):
        app, _, _ = build(tmp_path, dry_run=True)
        target = tmp_path / "docs" / "report.tmp"
        target.write_text("temp", encoding="utf-8")
        result = OrganizerTools(app.config, app.db, organizer=app.organizer).delete_files([str(target)], dry_run=False)
        assert result["status"] == "dry_run" and target.exists()

    def test_ai_can_ask_for_a_preview_when_dry_run_is_off(self, tmp_path):
        app, _, _ = build(tmp_path, dry_run=False)
        target = tmp_path / "docs" / "report.tmp"
        target.write_text("temp", encoding="utf-8")
        tools = OrganizerTools(app.config, app.db, organizer=app.organizer)
        assert tools.delete_files([str(target)], dry_run=True)["status"] == "dry_run" and target.exists()
        assert tools.delete_files([str(target)])["status"] == "ok" and not target.exists()
