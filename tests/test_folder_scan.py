"""Unit tests for the web-UI backend: PathMapper, ProposalService, FolderAdvisor, FolderScanJobs."""

import os
import time

import pytest
import yaml

from steward.folder_advisor import FolderAdvisor
from steward.main import StewardApp
from steward.path_mapper import PathMapper
from steward.proposals import ProposalService
from steward.scan_jobs import FolderScanJobs, ScanBusyError


class FolderScanHelper:
    """Builds an isolated StewardApp with a folder full of planted cleanup candidates."""

    @staticmethod
    def build_app(tmp_path):
        """Create duplicates, a temp file, an old temp file, and a protected folder."""
        home = tmp_path / "home"
        docs, protected, other = home / "docs", home / "clients", tmp_path / "elsewhere"
        for folder in (docs, protected, other):
            folder.mkdir(parents=True)
        (docs / "a.txt").write_text("same content", encoding="utf-8")
        (docs / "b.txt").write_text("same content", encoding="utf-8")
        (docs / "scratch.tmp").write_text("temp data", encoding="utf-8")
        old_tmp = docs / "old.tmp"
        old_tmp.write_text("old temp data!", encoding="utf-8")
        stamp = time.time() - 200 * 86400
        os.utime(old_tmp, (stamp, stamp))
        (protected / "c1.tmp").write_text("client temp", encoding="utf-8")
        (other / "outside.tmp").write_text("not in the chosen folder", encoding="utf-8")

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.safe_dump({
            "scanner": {"watched_folders": [str(home), str(other)]},
            "safety": {"dry_run": True, "protected_paths": [str(protected)]},
        }), encoding="utf-8")
        app = StewardApp(config_path=cfg_file, base_dir=tmp_path)
        return app, home, docs, protected, other


class TestPathMapper:
    """Validation and Mac-to-Docker path translation of user-typed folders."""

    def test_rejects_bad_input_with_clear_messages(self, tmp_path):
        """Empty, relative, missing, file, system and broad paths all raise ValueError."""
        app, home, docs, _, _ = FolderScanHelper.build_app(tmp_path)
        mapper = PathMapper(app.config, env={})
        cases = {
            "": "enter a folder path", "relative/dir": "full folder path",
            str(tmp_path / "missing"): "not found", str(docs / "a.txt"): "is a file",
            "/": "too broad", "/usr/local": "system folder",
        }
        for raw, expected in cases.items():
            with pytest.raises(ValueError, match=expected):
                mapper.resolve(raw)
        # Quotes and a trailing slash are tolerated
        assert mapper.resolve(f'"{docs}/"') == docs.resolve()

    def test_unreadable_folder_is_rejected(self, tmp_path):
        """A folder without read permission raises a permission ValueError."""
        if os.geteuid() == 0:
            pytest.skip("root can read every folder")
        app, _, docs, _, _ = FolderScanHelper.build_app(tmp_path)
        locked = docs / "locked"
        locked.mkdir()
        locked.chmod(0)
        try:
            with pytest.raises(ValueError, match="permission"):
                PathMapper(app.config, env={}).resolve(str(locked))
        finally:
            locked.chmod(0o755)

    def test_maps_mac_paths_to_docker_mounts_and_back(self, tmp_path):
        """Mac paths under a mount map to the container path; others get Docker help text."""
        app, _, docs, _, _ = FolderScanHelper.build_app(tmp_path)
        mapper = PathMapper(app.config, mappings=[("/Users/me/Documents", str(docs))])
        assert mapper.in_docker is True
        (docs / "Acme").mkdir()
        assert mapper.resolve("/Users/me/Documents/Acme") == (docs / "Acme").resolve()
        assert mapper.to_host(str(docs / "Acme")) == "/Users/me/Documents/Acme"
        with pytest.raises(ValueError, match="can only see these folders: /Users/me/Documents"):
            mapper.resolve("/Users/me/Pictures")
        assert mapper.list_roots()[0]["host_path"] == "/Users/me/Documents"

    def test_reads_mappings_and_home_from_environment(self, tmp_path):
        """STEWARD_HOST_* variables create mappings; ~ uses the Mac home inside Docker."""
        app, _, _, _, _ = FolderScanHelper.build_app(tmp_path)
        env = {"STEWARD_HOST_HOME": "/Users/me", "STEWARD_HOST_DOCUMENTS_DIR": "/Users/me/Documents/"}
        mapper = PathMapper(app.config, env=env)
        assert mapper.to_container("/Users/me/Documents/x") == "/data/Documents/x"
        assert mapper._expand_home("~/Documents/x") == "/Users/me/Documents/x"
        assert PathMapper(app.config, env={}).in_docker is False


class TestFolderAdvisorAndProposals:
    """Folder-scoped findings, suggestions and safe, deduplicated proposals."""

    def test_findings_and_suggestions_are_scoped_to_the_folder(self, tmp_path):
        """Only files inside the chosen folder count; each file's size counts once."""
        app, _, docs, _, other = FolderScanHelper.build_app(tmp_path)
        app.scanner.scan_all()
        advisor = FolderAdvisor(app)
        findings = advisor.findings_for(docs.resolve())
        temp_names = sorted(f["name"] for f in findings["temp_files"])
        assert temp_names == ["old.tmp", "scratch.tmp"]
        assert len(findings["duplicates"]) == 1 and len(findings["duplicates"][0]["extras"]) == 1
        advice = advisor.suggestions_for(docs.resolve(), findings)
        kinds = {s["kind"] for s in advice["suggestions"]}
        assert {"deduplicate", "clean_temp", "archive_stale"} <= kinds
        # old.tmp is both temp AND stale: counted once (12 + 9 + 14 bytes)
        assert advice["reclaimable_bytes"] == len("same content") + len("temp data") + len("old temp data!")
        assert all("outside" not in f["path"] for f in advisor.findings_for(docs.resolve())["temp_files"])
        assert any("outside" in f["path"] for f in advisor.findings_for(None)["temp_files"])

    def test_deleted_files_are_ignored(self, tmp_path):
        """A file removed after the scan never shows up as a cleanup candidate."""
        app, _, docs, _, _ = FolderScanHelper.build_app(tmp_path)
        app.scanner.scan_all()
        (docs / "scratch.tmp").unlink()
        names = [f["name"] for f in FolderAdvisor(app).findings_for(docs.resolve())["temp_files"]]
        assert names == ["old.tmp"]

    def test_proposals_skip_protected_and_never_duplicate(self, tmp_path):
        """Protected files get no proposal; re-proposing returns already_open; nothing is approved."""
        app, home, _, _, _ = FolderScanHelper.build_app(tmp_path)
        app.scanner.scan_all()
        advisor = FolderAdvisor(app)
        first = advisor.create_proposals(advisor.findings_for(home.resolve()))
        assert len(first["created"]) == 3  # 2 temp + 1 duplicate extra
        assert [p["source_path"].endswith("c1.tmp") for p in first["skipped_protected"]] == [True]
        second = advisor.create_proposals(advisor.findings_for(home.resolve()))
        assert len(second["created"]) == 0 and len(second["already_open"]) == 3
        assert {a["status"] for a in app.organizer.list_actions()} == {"proposed"}
        with pytest.raises(ValueError):
            ProposalService(app.config, app.db, app.organizer).propose_once("delete", "")


class TestFolderScanJobs:
    """Background job lifecycle: results, busy guard, and failure reporting."""

    def test_job_runs_all_steps_and_returns_results(self, tmp_path):
        """An inline job scans, analyses and proposes, ending with status done."""
        app, _, docs, _, _ = FolderScanHelper.build_app(tmp_path)
        jobs = FolderScanJobs(app, FolderAdvisor(app), PathMapper(app.config, env={}), run_inline=True)
        job = jobs.start(str(docs), create_proposals=True)
        assert job["status"] == "done" and job["progress"] == 100
        result = job["result"]
        assert result["scan"]["files_seen"] == 4
        assert result["findings"]["temp_files"]["count"] == 2
        assert len(result["proposals"]["created"]) == 3
        assert jobs.list_recent()[0]["id"] == job["id"] and "result" not in jobs.list_recent()[0]

    def test_second_job_while_running_is_refused(self, tmp_path):
        """Starting a scan while another is running raises ScanBusyError."""
        app, _, docs, _, _ = FolderScanHelper.build_app(tmp_path)
        jobs = FolderScanJobs(app, FolderAdvisor(app), PathMapper(app.config, env={}), run_inline=True)
        jobs.jobs["busy"] = {"id": "busy", "status": "running", "created_at": "2026-01-01"}
        with pytest.raises(ScanBusyError):
            jobs.start(str(docs))

    def test_failed_job_reports_its_error(self, tmp_path, monkeypatch):
        """An exception inside a step marks the job failed instead of crashing."""
        app, _, docs, _, _ = FolderScanHelper.build_app(tmp_path)

        def broken_scan(folders=None):
            raise RuntimeError("disk exploded")

        monkeypatch.setattr(app.scanner, "scan_all", broken_scan)
        jobs = FolderScanJobs(app, FolderAdvisor(app), PathMapper(app.config, env={}), run_inline=True)
        job = jobs.start(str(docs))
        assert job["status"] == "failed" and "disk exploded" in job["error"]
