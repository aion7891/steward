"""The user stays in control of the chat: honest rejections, typed "no" and "undo that", Stop."""

from types import SimpleNamespace

from agno.run.base import RunStatus
from agno.run.team import TeamRunOutput
from agno.team import Team

from steward.chat_commands import ChatCommands
from steward.chat_jobs import ChatJobs
from tests.test_chat_approvals import FakeRequirement, FakeTeam, build


def as_output(fake):
    """Turn a fake run into a real TeamRunOutput (chat jobs stream and expect Agno's own type)."""
    out = TeamRunOutput(run_id=fake.run_id, session_id=fake.session_id, content=fake.content, status=fake.status)
    out.requirements = fake.requirements
    return out


class Streamed:
    """Mixin: accepts Agno's streaming arguments and returns real outputs (streamed when asked)."""

    def run(self, message, session_id=None, stream=False, **kwargs):
        out = as_output(super().run(message, session_id=session_id))
        return iter([out]) if stream else out

    def continue_run(self, run_response=None, requirements=None, stream=False, **kwargs):
        out = as_output(super().continue_run(run_response=run_response, requirements=requirements))
        return iter([out]) if stream else out


class JobTeam(Streamed, FakeTeam):
    """FakeTeam usable from chat jobs: pauses for a delete, finishes after the decision."""

    def __init__(self, target, tools=None):
        super().__init__(target)


class Stubborn(FakeTeam):
    """After a rejection it claims success and tries the same change again (as gemma4 once did)."""

    def __init__(self, target, tools=None):
        super().__init__(target)
        self.continues = 0

    def continue_run(self, run_response=None, requirements=None):
        self.continues += 1
        self.notes = [getattr(req, "note", None) for req in requirements]
        retry = FakeRequirement("archive_files", {"file_paths": [self.target]})
        return SimpleNamespace(run_id="run-1", session_id=run_response.session_id, status=RunStatus.paused,
                               content="All files were successfully archived.", requirements=[retry],
                               tools=[], references=None, member_responses=None)


class StubbornTeam(Streamed, Stubborn):
    """Stubborn, usable from chat jobs."""


class Deleting(FakeTeam):
    """Really calls the organizer's delete tool once the user approves."""

    def __init__(self, target, tools=None):
        super().__init__(target)
        self.tools = tools

    def continue_run(self, run_response=None, requirements=None):
        if requirements[0].confirmation is True:
            self.tools.delete_files([self.target])
        return super().continue_run(run_response=run_response, requirements=requirements)


class ToolTeam(Streamed, Deleting):
    """Deleting, usable from chat jobs."""


def jobs_server(tmp_path, dry_run=True, team=JobTeam):
    """API server with jobs answered inline; returns (server, client, target file)."""
    _, server, client = build(tmp_path, dry_run=dry_run)
    target = tmp_path / "docs" / "report.tmp"
    server.agents.team = team(str(target), server.agents.organizer_tools)
    server.chat_routes.jobs.run_inline = True
    return server, client, target


def ask(client, message, session="s-1"):
    """Send a message as a chat job and return the finished job."""
    return client.post("/steward/chat/jobs", json={"message": message, "session_id": session}).json()["job"]


class TestTypedCommands:
    """Short, clear commands are understood by Steward itself; anything else goes to the AI."""

    def test_classify(self):
        commands = ChatCommands(store=None, organizer_tools=None)
        for text in ["no", "No!", "nope", "don't do it", "cancel", "I don't approve", "no thanks", "reject"]:
            assert commands.classify(text) == "reject", text
        for text in ["undo that", "Revert back", "please undo", "undo the last change", "roll back"]:
            assert commands.classify(text) == "undo", text
        for text in ["no, archive the other folder", "how do I undo a git commit", "revert my essay to the "
                     "version from last week please", "where is the zip", ""]:
            assert commands.classify(text) is None, text


class TestRejectionsAreHonoured:
    """A rejected change never happens, and the reply never claims it did."""

    def test_reply_is_stewards_own_and_retries_are_declined(self, tmp_path):
        """The AI claims "archived" and tries again; Steward declines the retry and states the truth."""
        server, client, target = jobs_server(tmp_path, team=StubbornTeam)
        card = ask(client, "archive report.tmp")["result"]
        decided = client.post("/steward/chat/decisions",
                              json={"run_id": card["run_id"], "approve": False, "session_id": "s-1"}).json()
        result = decided["job"]["result"]
        assert result["reply"] == "You rejected this, so Steward did not change any files."
        assert "archived" not in result["reply"] and "actions" not in result
        team = server.agents.team
        assert team.continues == 3 and team.notes[0].startswith("The user already said no")
        assert target.exists() and not list((tmp_path / "data").rglob("*.zip"))

    def test_typed_no_rejects_the_waiting_card(self, tmp_path):
        """'no' while a card waits rejects it; the card is saved as rejected and the browser is told."""
        server, client, target = jobs_server(tmp_path)
        card = ask(client, "delete report.tmp")["result"]
        result = ask(client, "no, don't")["result"]
        assert result["reply"].startswith("You rejected this") and result["decided_run_id"] == card["run_id"]
        saved = client.get("/steward/chat/conversations/s-1").json()["messages"]
        assert saved[1]["data"]["decision"] == "rejected" and target.exists()
        # With no card waiting, "no" is just a message for the AI
        assert ask(client, "no")["result"]["status"] == "approval"


class TestUndoThat:
    """'undo that' reverses the last change made from this chat."""

    def test_undo_restores_the_deleted_file_once(self, tmp_path):
        server, client, target = jobs_server(tmp_path, dry_run=False, team=ToolTeam)
        card = ask(client, "delete report.tmp")["result"]
        done = client.post("/steward/chat/decisions",
                           json={"run_id": card["run_id"], "approve": True, "session_id": "s-1"}).json()
        assert len(done["job"]["result"]["actions"]) == 1 and not target.exists()
        undone = ask(client, "undo that")
        assert undone["kind"] == "undo" and undone["result"]["reply"].startswith("Undone. Restored 1 item(s)")
        assert target.read_text(encoding="utf-8") == "scratch"
        assert ask(client, "revert back")["result"]["reply"].startswith("There is no file change")

    def test_practice_mode_changes_are_not_undone(self, tmp_path):
        """In practice mode nothing changed, so there is nothing to undo."""
        _, client, _ = jobs_server(tmp_path, dry_run=True, team=ToolTeam)
        card = ask(client, "delete report.tmp")["result"]
        client.post("/steward/chat/decisions", json={"run_id": card["run_id"], "approve": True, "session_id": "s-1"})
        assert ask(client, "undo")["result"]["reply"].startswith("There is no file change")


def stoppable_jobs(stop_after=1):
    """ChatJobs whose fake answer sends events and presses Stop after a few of them."""
    calls = []
    chat = SimpleNamespace(agents=SimpleNamespace(organizer_tools=SimpleNamespace(progress=None, done_actions=None)))
    store = SimpleNamespace(add_message=lambda *args: calls.append(args))
    jobs = ChatJobs(chat, store, run_inline=True)

    def answer(message, session_id, listener):
        for number in range(5):
            if number == stop_after:
                jobs.stop(next(iter(jobs.jobs)))
            listener(SimpleNamespace(event="TeamRunContent", run_id="team-run-7", agent_name=None, tool=None))
        return {"status": "ok", "reply": "finished", "sources": []}
    chat.answer = answer
    return jobs, calls


class TestStop:
    """Stop ends a running answer at the next event; a time limit stops answers that run too long."""

    def test_stop_ends_the_job_and_tells_agno(self, monkeypatch):
        cancelled = []
        monkeypatch.setattr(Team, "cancel_run", staticmethod(lambda run_id: cancelled.append(run_id) or True))
        jobs, calls = stoppable_jobs()
        job = jobs.ask("long question", "s")
        assert job["status"] == "done" and job["result"]["status"] == "stopped"
        assert job["result"]["reply"].startswith("Stopped.") and cancelled == ["team-run-7"]
        assert calls[-1][1] == "assistant" and calls[-1][3]["status"] == "stopped"  # saved in the conversation

    def test_time_limit(self):
        jobs, _ = stoppable_jobs(stop_after=99)
        jobs.max_seconds = 0
        result = jobs.ask("long question", "s")["result"]
        assert result["status"] == "stopped" and "5 minutes" in result["reply"]

    def test_stop_route(self, tmp_path):
        """Unknown jobs give 404; stopping a finished job changes nothing."""
        _, client, _ = jobs_server(tmp_path)
        assert client.post("/steward/chat/jobs/nope/stop").status_code == 404
        job = ask(client, "delete report.tmp")
        stopped = client.post(f"/steward/chat/jobs/{job['id']}/stop").json()["job"]
        assert stopped["result"]["status"] == "approval" and stopped["stopping"] is False
