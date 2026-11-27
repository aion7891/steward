"""Validates folder paths typed by the user and maps Mac paths to Docker paths."""

import os
import re
from pathlib import Path


class PathMapper:
    """Turns a folder path typed in the UI into a safe, scannable absolute path.

    Inside Docker, the user's folders are mounted under /data/... but the user
    naturally types the Mac path (/Users/me/Documents/Acme). The STEWARD_HOST_*
    environment variables tell us which Mac folder sits behind which mount.
    """

    # Refused as the folder itself AND anything inside them
    SYSTEM_TREES = ("/System", "/usr", "/bin", "/sbin", "/etc", "/private/etc", "/dev", "/proc", "/sys")
    # Refused only as the exact folder (too broad), sub-folders are fine
    BROAD_ROOTS = ("/", "/Users", "/home", "/Library", "/private", "/var", "/Volumes")
    HOST_ENV_MAP = (
        ("STEWARD_HOST_DOCUMENTS_DIR", "/data/Documents"),
        ("STEWARD_HOST_DOWNLOADS_DIR", "/data/Downloads"),
        ("STEWARD_HOST_DESKTOP_DIR", "/data/Desktop"),
        ("STEWARD_HOST_EXTRA_DIR", "/data/Extra"),
    )

    def __init__(self, config, env=None, mappings=None):
        """Load host-to-container folder mappings.

        Args:
            config: AppConfig, used for watched folders when not in Docker.
            env: optional dict replacing os.environ (handy in tests).
            mappings: optional list of (host_prefix, container_prefix) pairs.
        """
        self.config = config
        self.env = os.environ if env is None else env
        self.mappings = list(mappings) if mappings is not None else self._load_mappings()
        self.in_docker = bool(self.mappings)

    def _load_mappings(self):
        """Read (host_prefix, container_prefix) pairs from STEWARD_HOST_* variables."""
        pairs = []
        for env_key, container in self.HOST_ENV_MAP:
            host = str(self.env.get(env_key, "")).strip().rstrip("/")
            if host:
                pairs.append((host, container))
        # Longest prefix first, so /Users/me/Documents wins over /Users/me
        return sorted(pairs, key=lambda pair: -len(pair[0]))

    def resolve(self, raw_path):
        """Return a validated absolute Path for a folder, or raise ValueError.

        Args:
            raw_path: the folder as typed by the user (Mac path, ~ path, or /data path).
        """
        # Users often paste paths wrapped in quotes or with a trailing slash
        text = str(raw_path or "").strip().strip('"').strip("'").strip()
        if len(text) > 1:
            text = text.rstrip("/")
        if not text:
            raise ValueError("Please enter a folder path.")
        text = self._expand_home(text)
        if not os.path.isabs(text):
            raise ValueError("Please enter a full folder path, for example /Users/you/Documents/Projects.")

        path = Path(self.to_container(text)).resolve()
        self._refuse_system_folder(path)
        if not path.exists():
            raise ValueError(self._not_found_message(text))
        if not path.is_dir():
            raise ValueError(f"'{text}' is a file, not a folder.")
        if not os.access(path, os.R_OK | os.X_OK):
            raise ValueError(f"Steward does not have permission to read '{text}'.")
        return path

    def to_local(self, raw_path):
        """Clean a typed path (quotes, trailing /, ~) and return the path Steward can open.

        No checks are made here: the path may not exist (for example a move destination).

        Args:
            raw_path: a Mac path, ~ path or /data path, as written by the user or the AI.
        """
        text = str(raw_path or "").strip().strip('"').strip("'").strip()
        if len(text) > 1:
            text = text.rstrip("/")
        return self.to_container(self._expand_home(text)) if text else ""

    def to_container(self, host_path):
        """Translate a Mac path to its mounted Docker path (unchanged if no mapping matches)."""
        text = str(host_path)
        for host, container in self.mappings:
            if text == host or text.startswith(host + "/"):
                return container + text[len(host):]
        return text

    def to_host(self, container_path):
        """Translate a mounted Docker path back to the Mac path the user knows."""
        text = str(container_path)
        for host, container in self.mappings:
            if text == container or text.startswith(container + "/"):
                return host + text[len(container):]
        return text

    def to_host_deep(self, value):
        """Return a copy of value with every Docker path shown as the user's Mac path.

        Works on nested dicts/lists and also rewrites paths inside sentences, such as
        "Duplicate of /data/Documents/a.pdf" or a chat answer. Does nothing outside Docker.

        Args:
            value: any JSON-like value (dict, list, str, number, None).
        """
        if not self.mappings:
            return value
        if isinstance(value, dict):
            return {key: self.to_host_deep(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.to_host_deep(item) for item in value]
        if isinstance(value, str):
            for host, container in self.mappings:
                # Only whole path prefixes: /data/Extra or /data/Extra/..., never /data/ExtraStuff
                value = re.sub(re.escape(container) + r"(?=/|\b|$)", lambda _m, h=host: h, value)
        return value

    def list_roots(self):
        """Return the folders Steward can scan, for quick-pick buttons in the UI."""
        if self.in_docker:
            entries = [(host, container) for host, container in self.mappings]
        else:
            entries = [(str(p), str(p)) for p in self.config.get_watched_folders()]
        roots = []
        for host, container in entries:
            roots.append({
                "label": Path(host).name or host,
                "host_path": host,
                "path": container,
                "available": Path(container).is_dir(),
            })
        return roots

    def _expand_home(self, text):
        """Expand a leading ~ using the Mac home folder when running in Docker."""
        if not text.startswith("~"):
            return text
        host_home = str(self.env.get("STEWARD_HOST_HOME", "")).strip().rstrip("/")
        if self.in_docker and host_home:
            return host_home + text[1:]
        return os.path.expanduser(text)

    def _refuse_system_folder(self, path):
        """Raise ValueError for operating-system folders and overly broad roots."""
        as_text = str(path)
        if as_text in self.BROAD_ROOTS:
            raise ValueError(f"'{as_text}' is too broad to scan. Pick a more specific folder.")
        for tree in self.SYSTEM_TREES:
            if as_text == tree or as_text.startswith(tree + "/"):
                raise ValueError(f"'{as_text}' is a system folder and cannot be scanned.")

    def _not_found_message(self, text):
        """Explain why a folder was not found, with Docker-specific help."""
        if not self.in_docker:
            return f"Folder not found: {text}"
        visible = ", ".join(host for host, _ in self.mappings) or "none"
        return (
            f"Folder not found: {text}. Steward runs in Docker and can only see these folders: "
            f"{visible}. To scan another folder, set STEWARD_EXTRA_DIR in .env and restart."
        )
