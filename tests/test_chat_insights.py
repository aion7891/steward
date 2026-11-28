"""Answers that scanned a folder carry a stats card with real numbers and clickable suggestions."""

from types import SimpleNamespace

from agno.run.base import RunStatus
from agno.run.team import TeamRunOutput

from steward.chat_insights import ChatInsights
from steward.path_mapper import PathMapper
from steward.tools.tool_paths import ToolPaths
from tests.test_chat_approvals import build
from tests.test_phase5 import Phase5TestHelper


def scan_run(folder, status="ok"):
    """A finished team run whose ScannerAgent member called scan_folder on folder."""
    call = SimpleNamespace(tool_name="scan_folder", tool_args={"folder_path": folder},
                           result=str({"status": status, "message": "Scanned"}))
    member = SimpleNamespace(tools=[call], member_responses=[])
    return SimpleNamespace(tools=[], member_responses=[member])


class TestFolderCard:
    """The card counts files, clean-up candidates and suggestions straight from SQLite."""

    def test_card_after_a_real_scan(self, tmp_path):
        """2 identical files -> 1 extra copy; scratch.tmp -> 1 temp file; suggestions keep their paths."""
        app, _, docs, _ = Phase5TestHelper.build_app(tmp_path)
        app.scanner.scan_all()
        card = ChatInsights(app, ToolPaths(PathMapper(None, env={}))).folder_card(scan_run(str(docs)))
        assert card["name"] == "workspace_docs" and card["files"] == 4 and card["total_bytes"] > 0
        assert card["duplicates"] == 1 and card["temp"] == 1
        kinds = {tip["kind"]: tip for tip in card["suggestions"]}
        assert kinds["deduplicate"]["paths"] and kinds["clean_temp"]["paths"][0].endswith("scratch.tmp")

    def test_no_card_without_a_successful_scan(self, tmp_path):
        """A failed scan, a missing folder, or no scan at all gives no card."""
        app, _, docs, _ = Phase5TestHelper.build_app(tmp_path)
        insights = ChatInsights(app, ToolPaths(PathMapper(None, env={})))
        assert insights.folder_card(scan_run(str(docs), status="error")) is None
        assert insights.folder_card(scan_run(str(tmp_path / "gone"))) is None
        assert insights.folder_card(SimpleNamespace(tools=[], member_responses=[])) is None


class ScanningTeam:
    """Answers at once with a run in which the ScannerAgent scanned tmp/docs."""

    def __init__(self, folder):
        self.folder = folder

    def run(self, message, session_id=None, **kwargs):
        final = TeamRunOutput(run_id="r", session_id=session_id, content="Scanned your docs.", status=RunStatus.completed)
        final.member_responses = [scan_run(self.folder)]
        return final


class TestChatReplyHasFolder:
    """The chat API returns the card next to the answer."""

    def test_reply_includes_folder_card(self, tmp_path):
        """POST /steward/chat after a scan answer includes 'folder' with the counts."""
        app, server, client = build(tmp_path)
        app.scanner.scan_all()
        server.agents.team = ScanningTeam(str(tmp_path / "docs"))
        body = client.post("/steward/chat", json={"message": "scan docs"}).json()
        assert body["status"] == "ok" and body["folder"]["name"] == "docs" and body["folder"]["files"] == 1
        assert body["folder"]["temp"] == 1  # report.tmp


class TestFreshFolderCard:
    """The workspace panel can reload a folder's numbers after files changed."""

    def test_folder_route_returns_fresh_numbers(self, tmp_path):
        """After the temp file is gone, the card no longer counts it; bad paths give 400."""
        app, _, client = build(tmp_path)
        app.scanner.scan_all()
        assert client.get("/steward/chat/folder", params={"path": str(tmp_path / "docs")}).json()["folder"]["temp"] == 1
        (tmp_path / "docs" / "report.tmp").unlink()
        fresh = client.get("/steward/chat/folder", params={"path": str(tmp_path / "docs")}).json()["folder"]
        assert fresh["temp"] == 0 and fresh["files"] == 0
        assert client.get("/steward/chat/folder", params={"path": "relative/path"}).status_code == 400
