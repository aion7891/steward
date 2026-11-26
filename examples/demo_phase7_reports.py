"""Manual demo script for Phase 7: Pattern Mining, Recommendations, and Markdown/HTML Reports.

Creates a realistic sandbox in data/demo_phase7/ with mixed categories, duplicates, a
large file, a 120-day-old project folder, temp files, and software records. Runs
PatternMiner + RecommenderEngine + ReportGenerator to produce both a Markdown report
and a styled HTML report you can open in your browser.

Run with:
    uv run python examples/demo_phase7_reports.py
"""

import os
import shutil
import time
from pathlib import Path

import yaml
from PIL import Image

from steward.main import StewardApp


class Phase7ManualDemo:
    """Runs an end-to-end walkthrough of Steward's pattern miner, recommender, and reports."""

    def __init__(self):
        """Set up isolated sandbox directories under data/demo_phase7/."""
        self.project_root = Path(__file__).resolve().parent.parent
        self.demo_root = self.project_root / "data" / "demo_phase7"
        self.active_dir = self.demo_root / "Downloads_Active"
        self.stale_dir = self.demo_root / "Old_2024_Client"
        self.config_file = self.demo_root / "demo_config.yaml"

    def prepare_sandbox(self):
        """Populate realistic files, timestamps, and an isolated config."""
        if self.demo_root.exists():
            shutil.rmtree(self.demo_root)
        self.active_dir.mkdir(parents=True, exist_ok=True)
        self.stale_dir.mkdir(parents=True, exist_ok=True)

        (self.active_dir / "invoice_oct.md").write_text("# October Invoice\nConsulting invoice.", encoding="utf-8")
        (self.active_dir / "invoice_oct_copy.md").write_text("# October Invoice\nConsulting invoice.", encoding="utf-8")
        Image.new("RGB", (320, 200), color="steelblue").save(str(self.active_dir / "design_mockup.png"))
        (self.active_dir / "etl_script.py").write_text("print('sync data')\n", encoding="utf-8")
        (self.active_dir / "browser_cache.tmp").write_text("temporary cache", encoding="utf-8")
        (self.active_dir / "demo_recording.mp4").write_bytes(b"0" * (2 * 1024 * 1024))

        old_doc = self.stale_dir / "archived_contract.md"
        old_doc.write_text("# 2024 Contract Notes\nCompleted project.", encoding="utf-8")
        old_ts = time.time() - (120 * 24 * 3600)
        os.utime(old_doc, (old_ts, old_ts))

        cfg = {
            "app": {"name": "StewardPhase7Demo", "log_level": "INFO"},
            "scanner": {
                "watched_folders": [str(self.active_dir), str(self.stale_dir)],
                "large_file_mb": 1,
                "stale_days": 60,
            },
        }
        self.config_file.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    def run(self):
        """Scan sandbox, mine OKF patterns, print suggestions, and generate MD + HTML reports."""
        print("Running Steward Phase 7 Manual Demo (Patterns, Recommendations & Reports)...")
        self.prepare_sandbox()
        app = StewardApp(config_path=self.config_file, base_dir=self.demo_root)

        app.scanner.scan_all()
        app.knowledge_builder.build_from_database(app.db)
        app.db.upsert_software({
            "name": "VSCode", "path": "/Applications/Visual Studio Code.app",
            "version": "1.95", "extensions": [".py", ".md"], "status": "recent",
        })
        app.db.upsert_software({
            "name": "LegacyInstaller", "path": "/Applications/LegacyInstaller.app",
            "version": "0.9", "extensions": [".old"], "status": "rarely_used",
        })
        app.db.record_activity_event("download_created", str(self.active_dir / "invoice_oct.md"), "document", "~/Documents")

        print("\n=== STEP 1: Learned Work Patterns (Saved to OKF memory/patterns/) ===")
        rec = app.recommender.generate_recommendations(persist_patterns=True)
        for pat in rec["patterns"]:
            print(f"  - {pat['name']}: {pat['description']}  [OKF: {pat.get('okf_path')}]")

        print(f"\n=== STEP 2: Proactive Suggestions ({rec['total_reclaimable_mb']} MB Reclaimable) ===")
        for sug in rec["suggestions"]:
            print(f"  - [{sug['priority'].upper():<6}] {sug['title']} ({sug['reclaimable_mb']} MB) -> {sug['reason']}")

        print("\n=== STEP 3: Generate Dual Markdown + Styled HTML Reports (Jinja2) ===")
        report = app.reporter.generate_report(period="weekly", output_format="both")
        print("Markdown report :", report["files"]["markdown"])
        print("HTML report     :", report["files"]["html"])
        print("OKF concept     :", report["okf_concept"])

        print("\n--- Markdown Report Preview ---")
        print(Path(report["files"]["markdown"]).read_text(encoding="utf-8"))
        print("Phase 7 demo finished successfully!")


if __name__ == "__main__":
    Phase7ManualDemo().run()
