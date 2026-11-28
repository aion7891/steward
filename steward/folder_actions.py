"""Lets file actions work on whole folders: list their files safely and tidy up afterwards."""

import fnmatch
import os
from pathlib import Path


class FolderActions:
    """Helpers for archiving, recycling or moving a whole folder.

    Archiving a folder zips its files one by one. Hidden files (.DS_Store), private files
    (.env, keys, anything named like a password) and protected files are never zipped:
    they stay where they are and are reported as skipped.
    """

    MAX_FILES = 5000  # a guard against zipping a whole disk by accident

    def __init__(self, config):
        """Read the ignored folders and private-file patterns from the config.

        Args:
            config: AppConfig.
        """
        self.config = config
        self.ignored_dirs = set(config.get("scanner.ignored_dirs", []) or [])
        self.private_patterns = tuple(str(p).lower() for p in config.get("rag.sensitive_patterns", []) or [])

    def protected_inside(self, local_path):
        """Return the protected folder that local_path is, sits in, or contains; else None.

        Moving or recycling a folder also moves everything inside it, so a protected folder
        inside it counts too.

        Args:
            local_path: a file or folder path Steward can open.
        """
        path = Path(local_path).resolve()
        for protected in self.config.get_protected_paths():
            if path == protected or protected in path.parents or path in protected.parents:
                return protected
        return None

    def files_to_archive(self, folder):
        """Return (files, skipped) inside folder: files to zip, and files that must stay.

        Args:
            folder: a folder path Steward can open.
        """
        files, skipped = [], []
        for root, dirs, names in os.walk(folder):
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in self.ignored_dirs)
            for name in sorted(names):
                path = Path(root) / name
                if self._must_stay(path):
                    skipped.append(str(path))
                elif path.is_file() and not path.is_symlink():
                    files.append(str(path))
            if len(files) > self.MAX_FILES:
                raise ValueError(f"{folder} has more than {self.MAX_FILES} files. Pick a smaller folder.")
        return files, skipped

    def count_files(self, folder):
        """Return how many files a folder holds (all files, for the approval card).

        Args:
            folder: a folder path Steward can open.
        """
        return sum(len(names) for _, _, names in os.walk(folder))

    @staticmethod
    def remove_emptied_folders(archived_files, folder):
        """Remove folders that became empty because their files were archived.

        Only folders that held archived files are touched (up to and including folder), so
        folders that were already empty stay. Undo recreates the folders it needs.

        Args:
            archived_files: the file paths that were zipped and removed.
            folder: the folder the user asked to archive.
        """
        root = Path(folder).resolve()
        candidates = set()
        for file_path in archived_files:
            parent = Path(file_path).resolve().parent
            while parent == root or root in parent.parents:
                candidates.add(parent)
                parent = parent.parent
        for candidate in sorted(candidates, key=lambda p: -len(p.parts)):  # deepest first
            if candidate.is_dir() and not any(candidate.iterdir()):
                candidate.rmdir()

    def _must_stay(self, path):
        """True for hidden, private or protected files, which are never archived."""
        name = path.name.lower()
        if name.startswith("."):
            return True
        if any(fnmatch.fnmatch(name, pattern) for pattern in self.private_patterns):
            return True
        return self.config.is_protected_path(path)
