"""Agno tools to find files by name and list what is inside a folder (no scan needed)."""

from pathlib import Path

from agno.tools import Toolkit

from steward.tools.file_search import FileSearch
from steward.tools.tool_paths import ToolPaths


class FinderTools(Toolkit):
    """Answers "find my invoice" and "what is in ~/Desktop/docs?" straight from the disk and the index."""

    MAX_ITEMS = 60

    def __init__(self, config, db, paths=None):
        """Register the finder tools.

        Args:
            config: AppConfig (watched and ignored folders).
            db: DatabaseManager with Steward's file index.
            paths: ToolPaths that turns the user's Mac paths into paths Steward can open.
        """
        self.paths = paths or ToolPaths()
        self.search = FileSearch(config, db)
        super().__init__(name="finder_tools", tools=[self.find_files, self.list_folder])

    def find_files(self, name, limit=20):
        """Find files by (part of) their name, e.g. "invoice" or "*.pdf", in the watched folders.

        Args:
            name: part of the file name, or a pattern such as *.pdf.
            limit: maximum number of files.
        """
        try:
            files = self.search.find(name, limit)
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}
        message = f"Found {len(files)} file(s) matching '{name}'." if files else (
            f"No file matching '{name}' in the watched folders.")
        return {"status": "ok", "message": message, "files": files}

    def list_folder(self, folder_path):
        """List the files and sub-folders directly inside one folder, e.g. ~/Desktop/docs.

        Args:
            folder_path: the folder exactly as the user wrote it.
        """
        try:
            folder = Path(self.paths.folder(folder_path))
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}
        visible = sorted(p for p in folder.iterdir() if not p.name.startswith("."))
        items = [self._item(p) for p in visible[: self.MAX_ITEMS]]
        more = f" (showing the first {self.MAX_ITEMS})" if len(visible) > self.MAX_ITEMS else ""
        return {"status": "ok", "message": f"{folder_path} holds {len(visible)} item(s){more}.", "items": items}

    @staticmethod
    def _item(path):
        """Describe one entry of a folder."""
        if path.is_dir():
            return {"name": path.name, "kind": "folder", "path": str(path)}
        try:
            size = path.stat().st_size
        except OSError:
            size = None
        return {"name": path.name, "kind": "file", "path": str(path), "size_bytes": size}
