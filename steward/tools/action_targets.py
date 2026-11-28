"""Checks what a move, archive or delete would touch, for files and whole folders."""

from pathlib import Path


class ProtectedPathError(ValueError):
    """Raised when an action would touch a protected folder (reported as status 'blocked')."""


class ActionTargets:
    """Validates the paths the AI chose for a file action and describes them for the user.

    Used twice: before the approval card (to decline steps that cannot work) and inside
    the tools themselves. Every check raises ValueError with a message for the user.
    """

    def __init__(self, paths, folders):
        """Store the helpers.

        Args:
            paths: ToolPaths (Mac paths -> local paths, existence and write checks).
            folders: FolderActions (files inside a folder, protected folders inside it).
        """
        self.paths = paths
        self.folders = folders

    def move(self, source_path, target_folder):
        """Return (source, destination) for moving a file or folder into target_folder.

        Args:
            source_path: the file or folder to move, as written by the user or the AI.
            target_folder: the folder to move it into.
        """
        src = self.paths.existing(source_path)
        target = Path(self.paths.target(target_folder))
        if Path(src).is_dir() and (target == Path(src) or Path(src) in target.parents):
            raise ValueError(f"Cannot move {source_path} into itself.")
        self._refuse_protected(src, source_path)
        dest = str(target / Path(src).name)
        self.paths.check_writable(src)
        self.paths.check_writable(dest)
        return src, dest

    def delete(self, raw_paths):
        """Return the local files and folders to recycle (a folder goes to the bin as one item).

        Args:
            raw_paths: list of files or folders, as written by the user or the AI.
        """
        items = self.paths.existing_many(raw_paths)
        for item, raw in zip(items, self._as_list(raw_paths)):
            self._refuse_protected(item, raw)
        self.paths.check_all_writable(items)
        return items

    def archive(self, raw_paths):
        """Return (files, folders, skipped): files to zip, folders given, files that stay.

        Args:
            raw_paths: list of files or folders, as written by the user or the AI.
        """
        files, folders, skipped = [], [], []
        for item in self.paths.existing_many(raw_paths):
            if Path(item).is_dir():
                found, left = self.folders.files_to_archive(item)
                files, folders, skipped = files + found, folders + [item], skipped + left
            else:
                files.append(item)
        if not files:
            raise ValueError("Nothing to archive: those folders only hold hidden, private or protected files.")
        self.paths.check_all_writable(files)  # originals are removed after zipping
        return files, folders, skipped

    def check(self, tool_name, args):
        """Return why a paused step cannot work, or None when it can.

        Args:
            tool_name: move_file, archive_files or delete_files.
            args: the arguments the AI chose for that tool.
        """
        try:
            if tool_name == "move_file":
                self.move(args.get("source_path"), args.get("target_folder"))
            elif tool_name == "archive_files":
                self.archive(args.get("file_paths"))
            elif tool_name == "delete_files":
                self.delete(args.get("file_paths"))
        except ValueError as exc:
            return str(exc)
        return None

    def describe(self, raw_paths, tool_name=None):
        """Return {"folders": [names], "file_count": n} for an approval card, or None on bad paths.

        Args:
            raw_paths: the files or folders a step will touch.
            tool_name: archive_files counts only the files that will really be zipped.
        """
        try:
            items = self.paths.existing_many(raw_paths)
            if tool_name == "archive_files":
                files, folders, _ = self.archive(raw_paths)
                return {"folders": [Path(f).name for f in folders], "file_count": len(files)}
        except ValueError:
            return None
        folders = [Path(item).name for item in items if Path(item).is_dir()]
        count = sum(self.folders.count_files(item) if Path(item).is_dir() else 1 for item in items)
        return {"folders": folders, "file_count": count}

    def _refuse_protected(self, local_path, raw_path):
        """Raise ValueError when the path is, sits in, or contains a protected folder."""
        protected = self.folders.protected_inside(local_path)
        if protected is not None:
            shown = self.paths.mapper.to_host(str(protected))
            raise ProtectedPathError(f"Blocked: {raw_path} is or contains the protected folder {shown}; Steward never changes it.")

    @staticmethod
    def _as_list(raw_paths):
        """Return raw_paths as a list (one path string is fine too)."""
        return [raw_paths] if isinstance(raw_paths, str) else list(raw_paths or [])
