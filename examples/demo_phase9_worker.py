"""Manual demo script for Phase 9: Host Software Export & Background Scheduler Worker.

Demonstrates how Steward runs continuously in Docker:
  1. Exports host installed apps to a JSON file (host-inventory/apps.json)
  2. Verifies SoftwareDetector loads that read-only inventory inside a container
  3. Starts StewardWorker with APScheduler jobs (scan, cleanup, report)
  4. Runs one full background cycle (run_once) and shuts down cleanly

Run with:
    uv run python examples/demo_phase9_worker.py
"""

import shutil
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.export_host_inventory import HostInventoryExporter
from steward.chunker import HashEmbedder
from steward.main import StewardApp
from steward.rag import RAGIndex
from steward.software import SoftwareDetector
from steward.worker import StewardWorker


class Phase9ManualDemo:
    """Runs a safe sandbox walkthrough of Phase 9 host inventory and APScheduler worker."""

    def __init__(self):
        """Set up isolated sandbox directories under data/demo_phase9/."""
        self.project_root = Path(__file__).resolve().parent.parent
        self.demo_root = self.project_root / "data" / "demo_phase9"
        self.docs_dir = self.demo_root / "mounted_docs"
        self.inventory_json = self.demo_root / "host-inventory" / "apps.json"
        self.config_file = self.demo_root / "demo_config.yaml"

    def prepare_sandbox(self):
        """Populate mounted sample files and isolated worker config."""
        if self.demo_root.exists():
            shutil.rmtree(self.demo_root)
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        (self.docs_dir / "docker_notes.md").write_text(
            "# Docker Deployment\nMount Documents read-only and knowledge/ read-write.\n",
            encoding="utf-8",
        )
        (self.docs_dir / "scratch.tmp").write_text("temp file", encoding="utf-8")

        cfg = {
            "app": {"name": "StewardPhase9Demo", "log_level": "INFO"},
            "paths": {"host_inventory_file": str(self.inventory_json)},
            "scanner": {"watched_folders": [str(self.docs_dir)], "downloads_folder": str(self.docs_dir)},
            "scheduler": {"scan_interval_minutes": 30, "cleanup_interval_hours": 12, "report_day": "sunday"},
        }
        self.config_file.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    def run(self):
        """Run host inventory export, container load, and one scheduled worker cycle."""
        print("Running Steward Phase 9 Manual Demo (Host Inventory + APScheduler Worker)...")
        self.prepare_sandbox()

        print("\n=== STEP 1: Export Host Installed Software Inventory ===")
        exported = HostInventoryExporter(
            config_path=self.config_file, output_path=self.inventory_json
        ).export()
        print("Exported inventory :", exported)

        print("\n=== STEP 2: Load Read-Only Inventory (as Docker container does) ===")
        app = StewardApp(config_path=self.config_file, base_dir=self.demo_root)
        detector = SoftwareDetector(app.config, app.db, inventory_file=self.inventory_json)
        apps = detector.detect_and_save()
        print(f"Container loaded {len(apps)} app(s) from {self.inventory_json.name}")

        print("\n=== STEP 3: StewardWorker APScheduler Jobs & Single Background Cycle ===")
        rag = RAGIndex(app.config, embedder=HashEmbedder(dimensions=256), reader=app.reader)
        worker = StewardWorker(app=app, rag_index=rag, enable_watcher=False)
        print("Registered scheduled jobs:")
        for job in worker.list_jobs():
            print(f"  - {job['id']}: {job['trigger']}")

        worker.start()
        try:
            cycle = worker.run_once()
            print("Scan step OK    :", cycle["scan"].content["scan"]["files_seen"], "file(s)")
            print("Cleanup step OK :", cycle["cleanup"].content["proposals_count"], "proposal(s)")
            print("Report step OK  :", cycle["report"].content["files"])
        finally:
            worker.stop()

        print("\nTo start the full 4-container stack with Docker Compose:")
        print("  uv run python scripts/export_host_inventory.py")
        print("  docker compose up -d --build")
        print("Phase 9 demo finished successfully!")


if __name__ == "__main__":
    Phase9ManualDemo().run()
