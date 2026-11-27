"""Answers chat questions with the Agno team and reports the outcome honestly."""

from agno.agent import Agent


class ChatService:
    """Runs one chat question through the orchestrator team.

    It returns {"status", "reply", "sources"} where status is:
    - "ok": a normal answer
    - "error": the model failed (for example Ollama is not running)
    - "paused": an agent stopped to wait for an approval (not supported from chat yet)
    """

    def __init__(self, steward_app, agents, rag_index, mapper=None):
        """Store the services used to answer questions.

        Args:
            steward_app: StewardApp (for the OKF knowledge bundle).
            agents: StewardAgents holding the team and the chat model.
            rag_index: RAGIndex used for document passages.
            mapper: optional PathMapper that shows Docker paths as Mac paths.
        """
        self.steward_app = steward_app
        self.agents = agents
        self.rag_index = rag_index
        self.mapper = mapper

    def answer(self, message):
        """Answer one question and show any Docker paths in it as the user's Mac paths.

        Args:
            message: the user's question (already checked to be non-empty).
        """
        result = self._answer(message)
        return self.mapper.to_host_deep(result) if self.mapper is not None else result

    def _answer(self, message):
        """Run the team, with an OKF+RAG fallback if the model cannot call tools."""
        okf_hits = self.steward_app.okf_bundle.search_concepts(message, limit=3)
        sources = [h["rel_path"] for h in okf_hits]
        try:
            # Inside the try: RAG search embeds the question, which fails when Ollama is down
            rag_hits = self.rag_index.search(message, limit=3) if not okf_hits else []
            sources += [h["file_name"] for h in rag_hits]
            reply = self.agents.team.run(message)
            text = str(getattr(reply, "content", reply))
            if "does not support tools" in text.lower():
                reply = self._answer_without_tools(message, okf_hits, rag_hits)
                text = str(getattr(reply, "content", reply))
            # Agno reports model failures and approval pauses in the run status, not as exceptions
            status = self.run_status(reply)
            if status == "ERROR":
                return {"status": "error", "reply": text or "The model failed to answer.", "sources": []}
            if status == "PAUSED":
                return {"status": "paused", "reply": text, "sources": []}
            return {"status": "ok", "reply": text, "sources": sources}
        except Exception as exc:
            return {"status": "error", "reply": f"Model unavailable: {exc}", "sources": []}

    def _answer_without_tools(self, message, okf_hits, rag_hits):
        """Ask the model directly with the found notes and passages pasted into the prompt."""
        okf_part = [(h["rel_path"], h["frontmatter"].get("description")) for h in okf_hits]
        rag_part = [(h["file_name"], h["content"][:200]) for h in rag_hits]
        prompt = (
            "Answer concisely citing file names or OKF paths.\n"
            f"OKF: {okf_part}\nRAG: {rag_part}\n\nQuestion: {message}"
        )
        return Agent(model=self.agents.model, markdown=True).run(prompt)

    @staticmethod
    def run_status(reply):
        """Return an Agno run's status as an upper-case string ('COMPLETED', 'ERROR', 'PAUSED', ...)."""
        status = getattr(reply, "status", "")
        return str(getattr(status, "value", status) or "").upper()
