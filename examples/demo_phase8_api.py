"""Manual demo script for Phase 8: AgentOS FastAPI Server and StewardClient.

Starts Steward's real Agno AgentOS FastAPI app in-process (inside data/demo_phase8/)
and exercises every endpoint: /steward/health, /steward/scan, /steward/actions
(approve + undo), /steward/reports, /steward/recommendations, /steward/settings,
and /steward/chat (using real Ollama when available, or pass --offline).

Run with:
    uv run python examples/demo_phase8_api.py
    uv run python examples/demo_phase8_api.py --offline
"""

import argparse
import shutil
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from steward.api import StewardAPIServer
from steward.chunker import HashEmbedder
from steward.config import AppConfig
from steward.main import StewardApp
from steward.rag import RAGIndex


class Phase8ManualDemo:
    """Exercises Steward's AgentOS FastAPI endpoints end-to-end."""

    def __init__(self, offline=False):
        """Configure paths for an isolated Phase 8 demo under data/demo_phase8/."""
        self.project_root = Path(__file__).resolve().parent.parent
        self.main_config = self.project_root / "config.yaml"
        self.demo_root = self.project_root / "data" / "demo_phase8"
        self.docs_dir = self.demo_root / "sample_docs"
        self.config_file = self.demo_root / "demo_config.yaml"
        self.offline = offline

    def prepare_workspace(self):
        """Reset sandbox and write sample documents + isolated config."""
        if self.demo_root.exists():
            shutil.rmtree(self.demo_root)
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        (self.docs_dir / "apollo_launch.md").write_text(
            "# Apollo Launch\nTarget launch is December 15 with full Docker deployment.\n",
            encoding="utf-8",
        )
        (self.docs_dir / "temp_notes.tmp").write_text("temporary scratch", encoding="utf-8")

        base_models = AppConfig(config_path=self.main_config, base_dir=self.project_root).get("models")
        cfg = {
            "app": {"name": "StewardPhase8Demo", "log_level": "INFO"},
            "models": base_models,
            "scanner": {"watched_folders": [str(self.docs_dir)]},
            "safety": {"dry_run": True, "require_confirmation": True, "move_to_recycle_first": True},
        }
        self.config_file.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    def run(self):
        """Boot StewardAPIServer in-process and walk through every HTTP route."""
        print("Running Steward Phase 8 Manual Demo (AgentOS FastAPI + Approval Cards)...")
        self.prepare_workspace()
        app = StewardApp(config_path=self.config_file, base_dir=self.demo_root)
        embedder = HashEmbedder(dimensions=256) if self.offline else None
        rag = RAGIndex(app.config, logger=app.logger, embedder=embedder, reader=app.reader)

        server = StewardAPIServer(app=app, rag_index=rag)
        client = TestClient(server.fastapi_app)

        print("\n=== STEP 1: GET /steward/health ===")
        print(client.get("/steward/health").json())

        print("\n=== STEP 2: POST /steward/scan ===")
        print(client.post("/steward/scan", json={"folders": [str(self.docs_dir)]}).json())

        print("\n=== STEP 3: Approval Card Flow (Approve -> Done -> Undo) ===")
        prop = app.organizer.propose_action("delete", str(self.docs_dir / "temp_notes.tmp"), reason="Clean temp")
        print("Proposed action :", prop)
        print("Approve+Execute :", client.post(f"/steward/actions/{prop['id']}/approve", json={"execute": True, "dry_run": False}).json())
        print("Undo via API    :", client.post(f"/steward/actions/{prop['id']}/undo").json())

        print("\n=== STEP 4: Reports, Recommendations & Settings ===")
        rep = client.post("/steward/reports", json={"period": "weekly", "output_format": "both"}).json()
        print("Report files    :", rep.get("files"))
        print("Settings GET    :", client.get("/steward/settings").json()["safety"])

        if not self.offline:
            print("\n=== STEP 5: POST /steward/chat (Live Ollama) ===")
            chat_res = client.post("/steward/chat", json={"message": "When is the Apollo launch target?"}).json()
            print("Chat reply      :", chat_res.get("reply"))
            print("Cited sources   :", chat_res.get("sources"))

        print("\nTo launch the interactive Streamlit UI locally:")
        print("  Terminal 1: uv run python -m steward.api")
        print("  Terminal 2: uv run streamlit run steward/ui.py")
        print("Phase 8 demo finished successfully!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Steward Phase 8 API manual demo.")
    parser.add_argument("--offline", action="store_true", help="Skip live Ollama calls.")
    Phase8ManualDemo(offline=parser.parse_args().offline).run()
