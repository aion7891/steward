"""Host-side script that exports installed apps to host-inventory/apps.json for Docker.

Run this script on your macOS or Linux host so the isolated Docker container can read
your installed applications through a read-only volume mount (/app/host-inventory).

Usage:
    uv run python scripts/export_host_inventory.py
"""

import argparse
import json
from pathlib import Path

from steward.config import AppConfig
from steward.database import DatabaseManager
from steward.software import SoftwareDetector


class HostInventoryExporter:
    """Scans installed host applications and writes them to a shared JSON file."""

    def __init__(self, config_path="config.yaml", output_path="host-inventory/apps.json", app_dirs=None):
        """Configure source config, output JSON path, and optional custom app_dirs."""
        self.project_root = Path(__file__).resolve().parent.parent
        self.config_path = Path(config_path)
        if not self.config_path.is_absolute():
            self.config_path = self.project_root / self.config_path
        self.output_path = Path(output_path)
        if not self.output_path.is_absolute():
            self.output_path = self.project_root / self.output_path
        self.app_dirs = app_dirs

    def export(self):
        """Discover host software and atomically write host-inventory/apps.json."""
        config = AppConfig(config_path=self.config_path, base_dir=self.project_root)
        config.ensure_directories()
        db = DatabaseManager(config.get_path("db_path"))
        detector = SoftwareDetector(config, db, app_dirs=self.app_dirs)
        records = detector.discover_software()

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.output_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
        tmp_path.replace(self.output_path)
        return {"output_path": str(self.output_path), "app_count": len(records)}


def main(argv=None):
    """CLI entry point for exporting host software inventory."""
    parser = argparse.ArgumentParser(description="Export host installed apps for Steward Docker.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    parser.add_argument("--output", default="host-inventory/apps.json", help="Output JSON path.")
    args = parser.parse_args(argv)
    result = HostInventoryExporter(config_path=args.config, output_path=args.output).export()
    print(f"Exported {result['app_count']} installed app(s) to {result['output_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
