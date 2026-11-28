"""Answers chat questions with the Agno team and reports the outcome honestly."""

from agno.agent import Agent

from steward.chat_approvals import ChatApprovals
from steward.chat_notices import ChatNotices
from steward.chat_sources import ChatSources


class ChatService:
    """Runs chat questions through the orchestrator team, one conversation per session_id.

    Every reply is {"status", "reply", "sources", "session_id"}. Sources are
    {"kind", "label", "path"} for the files and notes the agents really used. Status is:
    - "ok": a normal answer
    - "error": the model failed (for example Ollama is not running)
    - "approval": an agent wants to change files; the reply also has "run_id" and "approvals"
      (one plain-language step each). Answer with decide(run_id, approve).
    """

    def __init__(self, steward_app, agents, rag_index, mapper=None):
        """Store the services used to answer questions.

        Args:
            steward_app: StewardApp (for the OKF knowledge bundle and config).
            agents: StewardAgents holding the team and the chat model.
            rag_index: RAGIndex used for document passages.
            mapper: optional PathMapper that shows Docker paths as Mac paths.
        """
        self.steward_app = steward_app
        self.agents = agents
        self.rag_index = rag_index
        self.mapper = mapper
        self.sources = ChatSources()
        self.notices = ChatNotices()
        # Steps that cannot work (missing path, read-only folder) are declined before asking
        self.approvals = ChatApprovals(
            steward_app.config,
            preflight=lambda name, args: self.agents.organizer_tools.preflight(name, args),
            summarize=lambda paths, tool: self.agents.organizer_tools.describe_targets(paths, tool),
        )

    def answer(self, message, session_id=None):
        """Answer one question inside a conversation.

        Args:
            message: the user's question (already checked to be non-empty).
            session_id: the browser's conversation id (a new conversation when omitted).
        """
        def run():
            reply = self.agents.team.run(message, session_id=session_id)
            if "does not support tools" in str(getattr(reply, "content", "")).lower():
                return self._answer_without_tools(message)
            return reply, None
        return self._respond(run, session_id)

    def decide(self, run_id, approve, note=None):
        """Approve or reject the steps a paused run is waiting for, then let the AI continue.

        Args:
            run_id: id from the approval card.
            approve: True to allow the file changes, False to refuse them.
            note: optional reason passed to the AI on rejection.
        Raises:
            KeyError: when nothing is waiting for that run_id.
        """
        paused = self.approvals.pop(run_id)
        self.approvals.decide(paused, bool(approve), note)

        def run():
            return self.agents.team.continue_run(run_response=paused, requirements=paused.requirements), None
        return self._respond(run, getattr(paused, "session_id", None))

    def _respond(self, run, session_id, notes=None, auto_continues=0):
        """Call run() and turn its result into the chat reply format (never raises).

        Args:
            run: function returning (agno run, fallback sources or None).
            session_id: the conversation id.
            notes: Steward's own notes collected so far (shown under the answer).
            auto_continues: how often a run was resumed without asking (limit 2).
        """
        notes = list(notes or [])
        try:
            reply, fallback_sources = run()
        except Exception as exc:
            return self._show({"status": "error", "reply": f"Model unavailable: {exc}", "sources": [],
                               "session_id": session_id})
        text = str(getattr(reply, "content", "") or "")
        result = {"session_id": getattr(reply, "session_id", None) or session_id, "sources": []}
        # Agno reports model failures and approval pauses in the run status, not as exceptions
        status = self.run_status(reply)
        if status == "ERROR":
            result.update(status="error", reply=text or "The model failed to answer.")
        elif status == "PAUSED" and self.approvals.open_requirements(reply):
            return self._paused(reply, result, notes, auto_continues)
        elif status == "PAUSED":
            result.update(status="error", reply="The AI paused for input Steward cannot collect in chat yet.")
        else:
            sources = fallback_sources if fallback_sources is not None else self.sources.collect(reply)
            notes += [note for note in self.notices.collect(reply) if note not in notes]
            if notes:
                text = f"{text}\n\n{ChatNotices.as_markdown(notes)}".strip()
            result.update(status="ok", reply=text, sources=sources)
        return self._show(result)

    def _paused(self, reply, result, notes, auto_continues):
        """Show the approval card, after declining the steps that cannot work."""
        notes = notes + [n for n in self.approvals.reject_impossible(reply) if n not in notes]
        if not self.approvals.open_requirements(reply):
            # Nothing left to ask the user: let the AI finish its answer, with the reasons below it
            if auto_continues >= 2:
                result.update(status="ok", reply=ChatNotices.as_markdown(notes))
                return self._show(result)

            def run():
                return self.agents.team.continue_run(run_response=reply, requirements=reply.requirements), None
            return self._respond(run, result["session_id"], notes, auto_continues + 1)
        result.update(status="approval", run_id=self.approvals.add(reply), approvals=self.approvals.describe(reply),
                      notices=notes, reply="Steward wants to change files and needs your approval.")
        return self._show(result)

    def _show(self, result):
        """Show Docker paths in the result as the user's Mac paths."""
        return self.mapper.to_host_deep(result) if self.mapper is not None else result

    def _answer_without_tools(self, message):
        """For models without tool support: search first, paste the hits into one prompt.

        Returns (run, sources); here the sources are exactly what the model was shown.
        """
        okf_hits = self.steward_app.okf_bundle.search_concepts(message, limit=3)
        rag_hits = self.rag_index.search(message, limit=3) if not okf_hits else []
        okf_part = [(h["rel_path"], h["frontmatter"].get("description")) for h in okf_hits]
        rag_part = [(h["file_name"], h["content"][:200]) for h in rag_hits]
        prompt = (
            "Answer concisely citing file names or OKF paths.\n"
            f"OKF: {okf_part}\nRAG: {rag_part}\n\nQuestion: {message}"
        )
        sources = [ChatSources.note_source(h["rel_path"]) for h in okf_hits]
        sources += [ChatSources.file_source(h["path"]) for h in rag_hits if h.get("path")]
        return Agent(model=self.agents.model, markdown=True).run(prompt), sources

    @staticmethod
    def run_status(reply):
        """Return an Agno run's status as an upper-case string ('COMPLETED', 'ERROR', 'PAUSED', ...)."""
        status = getattr(reply, "status", "")
        return str(getattr(status, "value", status) or "").upper()
