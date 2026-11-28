"""Tests for chat sources taken from what the agents actually used (review issue #14)."""

from types import SimpleNamespace

import yaml
from agno.run.base import RunStatus

from steward.chat_service import ChatService
from steward.chat_sources import ChatSources
from steward.main import StewardApp


def tool(name, args=None, result=""):
    """A fake Agno ToolExecution."""
    return SimpleNamespace(tool_name=name, tool_args=args or {}, result=result)


def reference(*paths):
    """A fake MessageReferences group as recorded by search_knowledge_base."""
    docs = [{"name": f"{p}#chunk-1", "content": "...", "meta_data": {"path": p, "file_name": p.split("/")[-1]}} for p in paths]
    return SimpleNamespace(query="q", references=docs)


def team_run(member_runs, status=RunStatus.completed, content="answer"):
    """A fake team run that delegated to members (shape matches Agno 3.2 TeamRunOutput)."""
    return SimpleNamespace(content=content, status=status, references=None,
                           tools=[tool("delegate_task_to_member", {"member_id": "chatagent"}, "answer")],
                           member_responses=member_runs)


class TestChatSources:
    """ChatSources.collect walks the team run and every member run."""

    def test_collects_references_file_reads_and_notes_without_duplicates(self):
        member = SimpleNamespace(
            references=[reference("/docs/invoice.pdf", "/docs/budget.xlsx")],
            tools=[
                tool("read_document", {"file_path": "/docs/invoice.pdf"}),  # duplicate of a reference
                tool("search_concepts", {"query": "acme"},
                     "{'status': 'ok', 'results': [{'rel_path': 'projects/acme.md'}, {'rel_path': 'files/invoice-9ea16736.md'}]}"),
                tool("read_concept", {"rel_path": "projects/acme.md"}),  # duplicate note
                tool("list_apps", {}),  # irrelevant tool
            ],
            member_responses=None,
        )
        sources = ChatSources().collect(team_run([member]))
        assert sources == [
            {"kind": "file", "label": "invoice.pdf", "path": "/docs/invoice.pdf"},
            {"kind": "file", "label": "budget.xlsx", "path": "/docs/budget.xlsx"},
            {"kind": "note", "label": "acme", "path": "projects/acme.md"},
            {"kind": "note", "label": "invoice", "path": "files/invoice-9ea16736.md"},
        ]

    def test_falls_back_to_the_search_result_json_and_respects_the_limit(self):
        result = '[{"name": "a#1", "meta_data": {"path": "/docs/a.txt"}}, {"name": "b#1", "meta_data": {"path": "/docs/b.txt"}}]'
        member = SimpleNamespace(references=None, tools=[tool("search_knowledge_base", {"query": "x"}, result)],
                                 member_responses=None)
        assert [s["label"] for s in ChatSources(limit=1).collect(team_run([member]))] == ["a.txt"]
        broken = SimpleNamespace(references=None, tools=[tool("search_knowledge_base", {}, "not json")], member_responses=None)
        assert ChatSources().collect(team_run([broken])) == []

    def test_failed_reads_are_not_sources(self):
        """Seen live: the agent tried read_document('Acme invoice'), which did not exist."""
        member = SimpleNamespace(references=None, member_responses=None, tools=[
            tool("read_document", {"file_path": "Acme invoice"}, "{'status': 'error', 'message': 'File not found'}"),
            tool("read_concept", {"rel_path": "files/missing.md"}, '{"status": "not_found", "message": "Concept not found"}'),
            tool("read_document", {"file_path": "/docs/a.pdf"}, "{'status': 'ok', 'message': 'Read pdf document'}"),
        ])
        assert [s["path"] for s in ChatSources().collect(team_run([member]))] == ["/docs/a.pdf"]

    def test_answer_without_lookups_has_no_sources(self):
        assert ChatSources().collect(team_run([])) == []
        assert ChatSources().collect(None) == []


class TestChatServiceUsesRealSources:
    """The chat API no longer shows unrelated keyword-search hits as sources."""

    def test_sources_come_from_the_run_not_a_keyword_search(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text(yaml.safe_dump({"scanner": {"watched_folders": [str(tmp_path)]}}), encoding="utf-8")
        app = StewardApp(config_path=cfg, base_dir=tmp_path)
        # A note that a keyword search for "invoice" WOULD find, but the agent never used
        app.okf_bundle.write_concept("files/contract.md", {"type": "file", "title": "invoice contract"}, "invoice")
        member = SimpleNamespace(references=[reference("/docs/invoice.pdf")], tools=[], member_responses=None)
        run = team_run([member], content="4,800 USD")
        agents = SimpleNamespace(team=SimpleNamespace(run=lambda message, **kwargs: run), model=None)
        reply = ChatService(app, agents, rag_index=None).answer("How much is the invoice?")
        assert reply["status"] == "ok"
        assert reply["sources"] == [{"kind": "file", "label": "invoice.pdf", "path": "/docs/invoice.pdf"}]
