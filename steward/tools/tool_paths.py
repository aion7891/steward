"""Turns paths written in the chat into paths the tools can open, with clear errors."""

import os
from pathlib import Path

from steward.path_mapper import PathMapper


class ToolPaths:
    """Checks every path an agent passes to a tool.

    The user (and so the AI) writes Mac paths like /Users/you/Desktop/docs or ~/Desktop/docs,
    but inside Docker that folder is /data/Desktop/docs. Every method raises ValueError with
    a message written for the user, which the tools return as {"status": "error"}.
    """

    # The .env switch that makes each shared folder writable (Downloads is always writable)
    ACCESS_VARS = {
        "/data/Desktop": "STEWARD_DESKTOP_ACCESS",
        "/data/Documents": "STEWARD_DOCUMENTS_ACCESS",
        "/data/Extra": "STEWARD_EXTRA_ACCESS",
    }

    def __init__(self, mapper=None):
        """Store the PathMapper used for translation.

        Args:
            mapper: PathMapper; by default one built from the STEWARD_HOST_* variables.
        """
        self.mapper = mapper or PathMapper(config=None)

    def target(self, raw_path):
        """Return the local path for a destination that may not exist yet.

        Args:
            raw_path: path as written by the user or the AI.
        """
        local = self.mapper.to_local(raw_path)
        if not local:
            raise ValueError("Please give a file or folder path.")
        if not os.path.isabs(local):
            raise ValueError(f"'{raw_path}' is not a full path. Use one like /Users/you/Desktop/docs or ~/Desktop/docs.")
        return str(Path(local).resolve())

    def existing(self, raw_path):
        """Return the local path of a file or folder that must exist.

        Args:
            raw_path: path as written by the user or the AI.
        """
        local = self.target(raw_path)
        if not Path(local).exists():
            raise ValueError(self._missing_message(raw_path))
        return local

    def existing_many(self, raw_paths):
        """Return local paths for a list of existing files or folders (one path is fine too).

        Args:
            raw_paths: list of paths, or a single path string.
        """
        items = [raw_paths] if isinstance(raw_paths, str) else list(raw_paths or [])
        if not items:
            raise ValueError("Please give at least one file or folder.")
        return [self.existing(item) for item in items]

    def folder(self, raw_path):
        """Return the local path of a folder that exists and can be read.

        Args:
            raw_path: folder path as written by the user or the AI.
        """
        return str(self.mapper.resolve(raw_path))

    def check_writable(self, local_path):
        """Raise ValueError when Steward may not change files at local_path.

        Moving or recycling a file changes the folder it sits in, so the nearest existing
        folder must be writable. Docker mounts Desktop and Documents read-only by default.

        Args:
            local_path: a path returned by target(), existing() or folder().
        """
        folder = Path(local_path)
        if folder.is_file() or not folder.exists():
            folder = folder.parent
        while not folder.exists() and folder != folder.parent:
            folder = folder.parent
        if not os.access(folder, os.W_OK):
            raise ValueError(self._read_only_message(str(folder)))

    def check_all_writable(self, local_paths):
        """Run check_writable on each path.

        Args:
            local_paths: list of paths returned by existing_many().
        """
        for path in local_paths:
            self.check_writable(path)

    def _missing_message(self, raw_path):
        """Explain a missing path, listing the folders Steward can see in Docker."""
        if not self.mapper.in_docker:
            return f"Not found: {raw_path}. Check the spelling and that the file or folder still exists."
        visible = ", ".join(host for host, _ in self.mapper.mappings)
        return (
            f"Not found: {raw_path}. Steward runs in Docker and can only see these folders: {visible}. "
            "Check the spelling, or share another folder with STEWARD_EXTRA_DIR in .env."
        )

    def _read_only_message(self, local_folder):
        """Explain a read-only folder and how to allow changes there."""
        shown = self.mapper.to_host(local_folder)
        for container, env_var in self.ACCESS_VARS.items():
            if local_folder == container or local_folder.startswith(container + "/"):
                return (
                    f"Steward can only read {shown}: that folder is shared read-only. To let Steward "
                    f"change files there, set {env_var}=rw in .env and run 'docker compose up -d'."
                )
        return f"Steward does not have permission to change files in {shown}."
