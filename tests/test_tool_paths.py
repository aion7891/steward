"""Chat tools accept the user's Mac paths and explain missing or read-only folders clearly."""

import os

from steward.path_mapper import PathMapper
from steward.tools import DocumentReaderTools, FileScannerTools, OrganizerTools
from steward.tools.tool_paths import ToolPaths
from tests.test_phase5 import Phase5TestHelper


class ToolPathsHelper:
    """Pretends to run in Docker: the Mac folder /Users/you/Desktop is mounted at tmp/Desktop."""

    @staticmethod
    def build(tmp_path):
        """Return (app, tools paths, docs folder inside the fake Desktop mount)."""
        app, _, _, _ = Phase5TestHelper.build_app(tmp_path)
        desktop = tmp_path / "Desktop"
        docs = desktop / "docs"
        docs.mkdir(parents=True)
        (docs / "notes.txt").write_text("Meeting notes about the Apollo launch.", encoding="utf-8")
        (docs / "old.tmp").write_text("scratch", encoding="utf-8")
        mapper = PathMapper(None, env={"STEWARD_HOST_HOME": "/Users/you"},
                            mappings=[("/Users/you/Desktop", str(desktop.resolve()))])
        return app, ToolPaths(mapper), docs.resolve()


class TestToolPaths:
    """ToolPaths translates and checks every path an agent passes to a tool."""

    def test_mac_tilde_and_container_paths_all_work(self, tmp_path):
        """A Mac path, a ~ path (with quotes and a trailing /) and the local path give the same folder."""
        _, paths, docs = ToolPathsHelper.build(tmp_path)
        assert paths.existing("/Users/you/Desktop/docs") == str(docs)
        assert paths.existing("'~/Desktop/docs/'") == str(docs)
        assert paths.existing(str(docs)) == str(docs)
        assert paths.existing_many("/Users/you/Desktop/docs/notes.txt") == [str(docs / "notes.txt")]

    def test_missing_and_relative_paths_explain_the_fix(self, tmp_path):
        """A missing path lists the folders Steward can see; a relative path asks for a full one."""
        _, paths, _ = ToolPathsHelper.build(tmp_path)
        for bad, expected in (("/Users/you/Projects/x", "can only see these folders: /Users/you/Desktop"),
                              ("docs", "not a full path"), ("", "Please give")):
            try:
                paths.existing(bad)
                raise AssertionError(f"{bad!r} should be refused")
            except ValueError as exc:
                assert expected in str(exc)

    def test_read_only_folder_is_refused_with_the_env_switch(self, tmp_path):
        """A folder Steward cannot write to is refused; Docker mounts name the .env switch."""
        _, paths, docs = ToolPathsHelper.build(tmp_path)
        paths.check_writable(str(docs / "notes.txt"))  # writable: no error
        os.chmod(docs, 0o555)
        try:
            try:
                paths.check_writable(str(docs / "notes.txt"))
                raise AssertionError("read-only folder should be refused")
            except ValueError as exc:
                assert "/Users/you/Desktop/docs" in str(exc)
        finally:
            os.chmod(docs, 0o755)
        message = paths._read_only_message("/data/Desktop/docs")
        assert "STEWARD_DESKTOP_ACCESS=rw" in message and "read-only" in message


class TestToolsUseMacPaths:
    """The scanner, reader and organizer tools accept the paths users type in the chat."""

    def test_scan_folder_with_mac_path_scans_the_mounted_folder(self, tmp_path):
        """Scanning ~/Desktop/docs finds its 2 files; an unknown folder is an error, not '0 files'."""
        app, paths, _ = ToolPathsHelper.build(tmp_path)
        tools = FileScannerTools(app.scanner, app.db, app.config, paths=paths)
        result = tools.scan_folder("~/Desktop/docs")
        assert result["status"] == "ok" and result["summary"]["files_seen"] == 2
        missing = tools.scan_folder("/Users/you/Desktop/nope")
        assert missing["status"] == "error" and "can only see" in missing["message"]

    def test_reader_opens_a_mac_path(self, tmp_path):
        """read_document translates the path and reports missing files clearly."""
        app, paths, _ = ToolPathsHelper.build(tmp_path)
        tools = DocumentReaderTools(app.reader, paths=paths)
        assert "Apollo" in tools.read_document("/Users/you/Desktop/docs/notes.txt")["preview"]
        assert tools.extract_text("/Users/you/Desktop/gone.txt")["status"] == "error"

    def test_organizer_uses_mac_paths_and_refuses_read_only(self, tmp_path):
        """Delete and move work on Mac paths (dry-run); a read-only folder gets a clear error."""
        app, paths, docs = ToolPathsHelper.build(tmp_path)
        org = OrganizerTools(app.config, app.db, organizer=app.organizer, paths=paths)
        deleted = org.delete_files(["~/Desktop/docs/old.tmp"])
        assert deleted["status"] == "dry_run" and (docs / "old.tmp").exists()
        moved = org.propose_move("/Users/you/Desktop/docs/notes.txt", "~/Desktop/archive")
        assert moved["status"] == "proposed" and moved["target_path"].endswith("Desktop/archive/notes.txt")
        os.chmod(docs, 0o555)
        try:
            refused = org.archive_files(["/Users/you/Desktop/docs/notes.txt"])
        finally:
            os.chmod(docs, 0o755)
        assert refused["status"] == "error" and "permission" in refused["message"]
        assert org.delete_files(["/Users/you/Desktop/missing.txt"])["status"] == "error"
