"""AgentOS FastAPI server exposing Agno agents, team, workflows, and /steward/* routes."""

import os

import uvicorn
from agno.os import AgentOS
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from steward.chat_routes import ChatRoutes
from steward.chat_service import ChatService
from steward.main import StewardApp
from steward.path_mapper import PathMapper
from steward.web_routes import WebRoutes


class StewardAPIServer:
    """Builds the FastAPI app combining Agno AgentOS and Steward management endpoints."""

    def __init__(self, app=None, config_path=None, rag_index=None, model=None):
        """Initialize StewardApp, Agno agents/workflows, and register all HTTP routes."""
        self.steward_app = app or StewardApp(config_path=config_path)
        self.rag_index = rag_index or self.steward_app.get_rag_index()
        self.agents = self.steward_app.get_agents(model=model, rag_index=self.rag_index)
        self.workflows = self.steward_app.get_workflows(rag_index=self.rag_index)
        # One mapper shows Docker paths (/data/...) as the user's Mac paths in every response
        self.path_mapper = PathMapper(self.steward_app.config)
        self.chat = ChatService(self.steward_app, self.agents, self.rag_index, mapper=self.path_mapper)
        self.fastapi_app = self._build_app()

    def _build_app(self):
        """Mount custom /steward/* routes onto an Agno AgentOS FastAPI application."""
        base_app = FastAPI(title="Steward API", version=str(self.steward_app.config.get("app.version", "0.9.0")))
        self._register_steward_routes(base_app)
        self.web_routes = WebRoutes(self.steward_app, mapper=self.path_mapper, on_model_change=self._rebuild_agents)
        self.web_routes.register(base_app)
        # Background chat jobs: answers survive tab switches and reloads, with live steps
        self.chat_routes = ChatRoutes(self.steward_app, self.chat, mapper=self.path_mapper)
        self.chat_routes.register(base_app)
        # Only the Vite dev server needs CORS; in Docker nginx serves UI and API from one origin
        origins = os.getenv("STEWARD_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173")
        base_app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in origins.split(",") if o.strip()],
                                allow_methods=["*"], allow_headers=["*"])
        agent_os = AgentOS(
            id="steward-os",
            name="Steward",
            description="Local-first personal file and knowledge assistant.",
            agents=list(self.agents.list_agents().values()),
            teams=[self.agents.team],
            workflows=[
                self.workflows.scan_workflow,
                self.workflows.cleanup_workflow,
                self.workflows.report_workflow,
            ],
            base_app=base_app,
            on_route_conflict="preserve_base_app",
            telemetry=False,
        )
        return agent_os.get_app()

    def _register_steward_routes(self, api):
        """Attach Steward's custom health, scan and chat routes, then the action/report routes."""
        self._register_action_routes(api)
        self._register_settings_routes(api)

        @api.get("/steward/health")
        def health():
            status = self.steward_app.health_check()
            pending = len(self.steward_app.organizer.list_actions(status="proposed"))
            return {"status": "ok", "pending_actions": pending, **status}

        @api.post("/steward/scan")
        def trigger_scan(payload=Body(default=None)):
            data = payload or {}
            extra = {"folders": data["folders"]} if data.get("folders") else {}
            res = self.workflows.run_workflow("scan", additional_data=extra)
            return {"status": "ok", "result": getattr(res, "content", res)}

        self._register_chat_routes(api)

    def _register_chat_routes(self, api):
        """Attach chat questions and approve/reject decisions for paused chat runs."""

        @api.post("/steward/chat")
        def chat(payload=Body(...)):
            data = payload or {}
            message = str(data.get("message", "")).strip()
            if not message:
                raise HTTPException(status_code=400, detail="'message' is required.")
            return self.chat.answer(message, session_id=data.get("session_id") or None)

        @api.post("/steward/chat/{run_id}/decision")
        def chat_decision(run_id, payload=Body(...)):
            data = payload or {}
            if not isinstance(data.get("approve"), bool):
                raise HTTPException(status_code=400, detail="'approve' must be true or false.")
            try:
                return self.chat.decide(run_id, data["approve"], note=data.get("note"))
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc

    def _register_action_routes(self, api):
        """Attach the actions, reports, recommendations and settings routes."""

        @api.get("/steward/actions")
        def list_actions(status=None, limit=50):
            actions = self.steward_app.organizer.list_actions(status=status, limit=int(limit))
            return {"status": "ok", "actions": self.path_mapper.to_host_deep(actions)}

        @api.post("/steward/actions/{action_id}/approve")
        def approve_action(action_id, payload=Body(default=None)):
            data = payload or {}
            approved = self.steward_app.organizer.approve_action(int(action_id))
            if approved["status"] != "approved":
                return approved
            if data.get("execute", True):
                return self.steward_app.organizer.execute_action(int(action_id), dry_run=data.get("dry_run"))
            return approved

        @api.post("/steward/actions/{action_id}/reject")
        def reject_action(action_id, payload=Body(default=None)):
            reason = (payload or {}).get("reason", "Rejected via UI")
            return self.steward_app.organizer.reject_action(int(action_id), reason=reason)

        @api.post("/steward/actions/{action_id}/undo")
        def undo_action(action_id):
            return self.steward_app.organizer.undo_action(int(action_id))

        @api.get("/steward/reports")
        def list_reports(limit=20):
            return {"status": "ok", "reports": self.steward_app.db.list_reports(limit=int(limit))}

        @api.post("/steward/reports")
        def create_report(payload=Body(default=None)):
            data = payload or {}
            return self.steward_app.reporter.generate_report(
                period=data.get("period", "weekly"),
                output_format=data.get("output_format", "markdown"),
            )

    def _register_settings_routes(self, api):
        """Attach the recommendations route (settings routes live in web_routes.py)."""

        @api.get("/steward/recommendations")
        def recommendations():
            return {"status": "ok", **self.steward_app.recommender.generate_recommendations(persist_patterns=False)}

    def _rebuild_agents(self):
        """Rebuild the agents and team after the model was changed in Settings."""
        model = self.steward_app.model_factory.create_chat_model()
        self.agents = self.steward_app.get_agents(model=model, rag_index=self.rag_index)
        self.chat.agents = self.agents


def create_api_app(config_path=None, app=None, rag_index=None, model=None):
    """Factory function returning the configured FastAPI/AgentOS application."""
    server = StewardAPIServer(app=app, config_path=config_path, rag_index=rag_index, model=model)
    return server.fastapi_app


def main():
    """Start the Steward AgentOS FastAPI server with uvicorn."""
    cfg_path = os.getenv("STEWARD_CONFIG_PATH")
    server = StewardAPIServer(config_path=cfg_path)
    host = os.getenv("STEWARD_API_HOST", server.steward_app.config.get("server.host", "127.0.0.1"))
    port = int(os.getenv("STEWARD_API_PORT", server.steward_app.config.get("server.port", 7777)))
    uvicorn.run(server.fastapi_app, host=host, port=port)


if __name__ == "__main__":
    main()
