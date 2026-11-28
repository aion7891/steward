"""Backups made when Steward's own data is cleared from Settings, so a "Clear" can be undone."""

import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path


class DataBackups:
    """Keeps backups in one folder: chats as JSON, knowledge notes as a ZIP of Markdown files.

    A backup id is its file name, for example "chats-20261128-101500.json". Only names that match
    NAME are accepted, so a request can never point outside the backup folder.
    """

    NAME = re.compile(r"^(chats|knowledge|topics)-\d{8}-\d{6}(-\d+)?\.(json|zip)$")
    LABELS = {"chats": "Chats", "knowledge": "Knowledge notes", "topics": "Topics"}

    def __init__(self, folder):
        """Remember the backup folder (created when the first backup is saved).

        Args:
            folder: Path of the backup folder, for example data/backups.
        """
        self.folder = Path(folder)

    def save_json(self, kind, payload):
        """Save a JSON backup and return its id.

        Args:
            kind: "chats".
            payload: dict that can be written as JSON.
        """
        path = self._new_path(kind, "json")
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path.name

    def save_zip(self, kind, root, files):
        """Zip files (kept relative to root) into a backup and return its id.

        Args:
            kind: "knowledge" or "topics".
            root: folder the files belong to (the knowledge folder).
            files: list of Paths inside root.
        """
        path = self._new_path(kind, "zip")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in files:
                archive.write(file, Path(file).relative_to(root).as_posix())
        return path.name

    def list(self):
        """Return the backups, newest first: id, kind, label, size_bytes, items, created_at."""
        if not self.folder.exists():
            return []
        found = [self._describe(p) for p in self.folder.iterdir() if self.NAME.match(p.name)]
        return sorted(found, key=lambda b: b["created_at"], reverse=True)

    def read_json(self, backup_id):
        """Return the content of a JSON backup.

        Args:
            backup_id: the backup's file name.
        """
        return json.loads(self.path_for(backup_id).read_text(encoding="utf-8"))

    def extract_markdown(self, backup_id, root):
        """Put the Markdown files of a ZIP backup back under root; return how many were restored.

        Args:
            backup_id: the backup's file name.
            root: the knowledge folder.
        """
        root = Path(root).resolve()
        restored = 0
        with zipfile.ZipFile(self.path_for(backup_id)) as archive:
            for name in archive.namelist():
                target = (root / name).resolve()
                # Only Markdown notes, and never outside the knowledge folder
                if not name.endswith(".md") or not target.is_relative_to(root):
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
                restored += 1
        return restored

    def delete(self, backup_id):
        """Delete a backup for good.

        Args:
            backup_id: the backup's file name.
        """
        self.path_for(backup_id).unlink()

    def path_for(self, backup_id):
        """Return the path of an existing backup, or raise KeyError / ValueError.

        Args:
            backup_id: the backup's file name.
        """
        if not self.NAME.match(str(backup_id)):
            raise ValueError("That is not a Steward backup name.")
        path = self.folder / str(backup_id)
        if not path.is_file():
            raise KeyError(f"Backup {backup_id} was not found. It may have been deleted already.")
        return path

    def _new_path(self, kind, extension):
        """Return a free backup path such as chats-20261128-101500.json."""
        self.folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path, number = self.folder / f"{kind}-{stamp}.{extension}", 1
        while path.exists():
            number += 1
            path = self.folder / f"{kind}-{stamp}-{number}.{extension}"
        return path

    def _describe(self, path):
        """Describe one backup file for the Settings page."""
        kind = path.name.split("-", 1)[0]
        try:
            if path.suffix == ".zip":
                with zipfile.ZipFile(path) as archive:
                    items = len(archive.namelist())
            else:
                items = len(json.loads(path.read_text(encoding="utf-8")).get("conversations", []))
        except (OSError, ValueError, zipfile.BadZipFile):
            items = None  # damaged backups are still listed, so they can be deleted
        created = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        return {"id": path.name, "kind": kind, "label": self.LABELS.get(kind, kind),
                "size_bytes": path.stat().st_size, "items": items, "created_at": created}
