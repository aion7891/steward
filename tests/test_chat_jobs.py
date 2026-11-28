"""Background chat jobs: live steps, answers that survive leaving the page, saved conversations."""

from types import SimpleNamespace

from agno.run.base import RunStatus
from agno.run.team import TeamRunOutput

from steward.chat_jobs import ChatJobs
from steward.chat_steps import ChatSteps
from steward.path_mapper import PathMapper
from tests.test_chat_approvals import FakeRequirement, build


def event(name, agent=None, tool=None):
    """One Agno stream event as the team or a member agent sends it."""
    return SimpleNamespace(event=name, agent_name=agent, tool=tool)


def tool(name, args, result=None, call_id="c1"):
    """A tool call as carried by ToolCallStarted/Completed events."""
    return SimpleNamespace(tool_name=name, tool_args=args, result=result, tool_call_id=call_id)


SCAN_EVENTS = [
    event("TeamModelRequestStarted"),
    event("TeamToolCallStarted", tool=tool("delegate_task_to_member", {"member_id": "scanneragent"}, call_id="d1")),
    event("ModelRequestStarted", agent="ScannerAgent"),
    event("ToolCallStarted", agent="ScannerAgent", tool=tool("scan_folder", {"folder_path": "/data/Desktop/docs"})),
    event("ToolCallCompleted", agent="ScannerAgent",
          tool=tool("scan_folder", {}, result="{'status': 'ok', 'message': 'Scanned 4 file(s).'}")),
    event("TeamToolCallCompleted", tool=tool("delegate_task_to_member", {}, result="done", call_id="d1")),
]


class StreamingTeam:
    """Streams SCAN_EVENTS then a real TeamRunOutput; pauses for a delete when asked to delete."""

    def __init__(self, target):
        self.target = target

    def run(self, message, session_id=None, stream=False, **kwargs):
        if "delete" in message:
            req = FakeRequirement("delete_files", {"file_paths": [self.target], "reason": "temp"})
            final = TeamRunOutput(run_id="run-9", session_id=session_id, content="paused", status=RunStatus.paused)
            final.requirements = [req]
            return iter([final])
        final = TeamRunOutput(run_id="run-1", session_id=session_id, content="Scanned 4 files.", status=RunStatus.completed)
        return iter(SCAN_EVENTS + [final])

    def continue_run(self, run_response=None, requirements=None, **kwargs):
        done = TeamRunOutput(run_id="run-9", session_id=run_response.session_id, content="Recycled it.",
                             status=RunStatus.completed)
        return iter([event("ToolCallStarted", "OrganizerAgent", tool("delete_files", {"file_paths": [self.target]})), done])


def server_with_jobs(tmp_path):
    """API server with the streaming fake team and jobs answered inline."""
    _, server, client = build(tmp_path)
    server.agents.team = StreamingTeam(str(tmp_path / "docs" / "report.tmp"))
    server.chat_routes.jobs.run_inline = True
    return server, client


class TestChatSteps:
    """Agno events become plain steps: hand-overs, tool calls with their outcome, progress."""

    def test_events_become_steps(self):
        """A hand-over and a scan become two finished steps with the tool's own message."""
        steps = ChatSteps()
        for item in SCAN_EVENTS[:4]:
            steps.handle(item)
        live = steps.snapshot()
        assert live["thinking"] == "Scanner"
        assert [s["title"] for s in live["steps"]] == ["Handing over to Scanner", "Scanning /data/Desktop/docs"]
        steps.progress("archiving", 3, 4)
        assert steps.snapshot()["steps"][1]["progress"] == {"label": "archiving", "done": 3, "total": 4}
        for item in SCAN_EVENTS[4:]:
            steps.handle(item)
        final = steps.finish()
        assert [s["status"] for s in final] == ["done", "done"] and final[1]["detail"] == "Scanned 4 file(s)."

    def test_failed_tool_and_unknown_tool(self):
        """An error result marks the step failed; an unknown tool gets a readable fallback title."""
        steps = ChatSteps()
        steps.handle(event("ToolCallStarted", "OrganizerAgent", tool("archive_files", {"file_paths": ["/a/b.txt"]})))
        steps.handle(event("ToolCallCompleted", "OrganizerAgent",
                           tool("archive_files", {}, result='{"status": "error", "message": "read-only"}')))
        steps.handle(event("ToolCallStarted", "ScannerAgent", tool("count_stars", {}, call_id="c2")))
        final = steps.finish()
        assert final[0]["title"] == "Archiving b.txt" and final[0]["status"] == "error"
        assert final[1]["title"] == "Using count stars" and final[1]["agent"] == "Scanner"


class TestChatJobsApi:
    """POST a question, poll the job, and find the conversation saved on the server."""

    def test_job_answers_and_saves_the_conversation(self, tmp_path):
        """The job holds the answer and its steps; both messages are saved under the session id."""
        _, client = server_with_jobs(tmp_path)
        started = client.post("/steward/chat/jobs", json={"message": "scan my docs", "session_id": "s-1"})
        assert started.status_code == 202
        job = client.get(f"/steward/chat/jobs/{started.json()['job']['id']}").json()["job"]
        assert job["status"] == "done" and job["result"]["reply"] == "Scanned 4 files."
        assert [s["title"] for s in job["result"]["steps"]] == ["Handing over to Scanner", "Scanning /data/Desktop/docs"]
        saved = client.get("/steward/chat/conversations/s-1").json()
        assert [m["role"] for m in saved["messages"]] == ["user", "assistant"] and saved["active_job"] is None
        assert saved["messages"][1]["data"]["steps"][1]["detail"] == "Scanned 4 file(s)."
        listed = client.get("/steward/chat/conversations").json()["conversations"]
        assert listed[0]["id"] == "s-1" and listed[0]["title"] == "scan my docs" and listed[0]["message_count"] == 2

    def test_approval_then_decision_job(self, tmp_path):
        """A paused answer becomes an approval; the decision job resumes it and the card remembers it."""
        _, client = server_with_jobs(tmp_path)
        job = client.post("/steward/chat/jobs", json={"message": "delete report.tmp", "session_id": "s-2"}).json()["job"]
        assert job["result"]["status"] == "approval" and job["result"]["run_id"] == "run-9"
        decided = client.post("/steward/chat/decisions", json={"run_id": "run-9", "approve": True, "session_id": "s-2"})
        result = decided.json()["job"]["result"]
        assert result["reply"].startswith("Recycled it.") and result["steps"][0]["title"] == "Moving report.tmp to the recycle bin"
        messages = client.get("/steward/chat/conversations/s-2").json()["messages"]
        assert messages[1]["data"]["decision"] == "approved" and len(messages) == 3

    def test_bad_requests_unknown_jobs_and_delete(self, tmp_path):
        """Missing fields give 400, an unknown job 404 with advice, delete removes the conversation."""
        _, client = server_with_jobs(tmp_path)
        assert client.post("/steward/chat/jobs", json={"message": "hi"}).status_code == 400
        assert client.post("/steward/chat/jobs", json={"message": " ", "session_id": "s"}).status_code == 400
        assert client.post("/steward/chat/decisions", json={"run_id": "x", "approve": "yes", "session_id": "s"}).status_code == 400
        gone = client.get("/steward/chat/jobs/nope")
        assert gone.status_code == 404 and "ask again" in gone.json()["detail"]
        client.post("/steward/chat/jobs", json={"message": "scan", "session_id": "s-3"})
        assert client.delete("/steward/chat/conversations/s-3").status_code == 200
        assert client.delete("/steward/chat/conversations/s-3").status_code == 404


class TestJobsShowMacPaths:
    """Steps and answers show the user's Mac paths, also while the job is still running."""

    def test_paths_in_steps_are_mapped(self, tmp_path):
        """A step that scanned /data/Desktop/docs is shown as /Users/you/Desktop/docs."""
        chat = SimpleNamespace(agents=SimpleNamespace(organizer_tools=SimpleNamespace(progress=None)))

        def answer(message, session_id, listener):
            for item in SCAN_EVENTS:
                listener(item)
            return {"status": "ok", "reply": "Found /data/Desktop/docs/a.txt", "sources": []}
        chat.answer = answer
        store = SimpleNamespace(add_message=lambda *args: None)
        mapper = PathMapper(None, env={}, mappings=[("/Users/you/Desktop", "/data/Desktop")])
        jobs = ChatJobs(chat, store, mapper=mapper, run_inline=True)
        job = jobs.ask("scan", "s")
        assert job["result"]["reply"] == "Found /Users/you/Desktop/docs/a.txt"
        assert job["result"]["steps"][1]["title"] == "Scanning /Users/you/Desktop/docs"
        assert chat.agents.organizer_tools.progress is None  # the progress hook is removed afterwards
