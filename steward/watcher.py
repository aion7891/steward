"""Real-time Downloads folder watcher and destination recommender."""

import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from steward.scanner import FileCategorizer


class DownloadsEventHandler(FileSystemEventHandler):
    """Handles file creation and move events inside the watched Downloads folder."""

    def __init__(self, watcher):
        """Bind the watchdog event handler to its parent DownloadsWatcher."""
        super().__init__()
        self.watcher = watcher

    def on_created(self, event):
        """Process newly created files in Downloads."""
        if not event.is_directory:
            self.watcher.inspect_file(event.src_path, event_type="download_created")

    def on_moved(self, event):
        """Process completed downloads renamed from temporary browser files."""
        if not event.is_directory:
            self.watcher.inspect_file(event.dest_path, event_type="download_completed")


class DownloadsWatcher:
    """Watches the Downloads folder in real time and suggests destinations."""

    def __init__(
        self,
        config,
        db,
        logger=None,
        categorizer=None,
        watch_dir=None,
        on_suggestion=None,
    ):
        """Initialize the Downloads watcher with config, database, and callback."""
        self.config = config
        self.db = db
        self.logger = logger
        self.categorizer = categorizer or FileCategorizer()
        raw_dir = watch_dir or config.get("scanner.downloads_folder", "~/Downloads")
        self.watch_dir = Path(str(raw_dir)).expanduser().resolve()
        self.ignored_extensions = {
            ext.lower() for ext in config.get("scanner.ignored_extensions", [])
        }
        self.on_suggestion = on_suggestion
        self.observer = None

    def inspect_file(self, file_path, event_type="download_detected"):
        """Categorize a file, suggest a destination, and log an activity event."""
        path = Path(file_path).resolve()
        if not path.exists() or path.is_dir():
            return None
        if self._should_ignore(path):
            self._log_debug(f"Ignoring in-progress or hidden file: {path.name}")
            return None

        category = self.categorizer.categorize(path)
        suggested_dest = self.categorizer.suggest_destination(path)
        suggestion = {
            "event_type": event_type,
            "path": str(path),
            "name": path.name,
            "category": category,
            "suggested_destination": suggested_dest,
        }
        self.db.record_activity_event(
            event_type=event_type,
            path=str(path),
            category=category,
            suggested_destination=suggested_dest,
            details=f"Suggested moving '{path.name}' to '{suggested_dest}'",
        )
        self._log_info(
            f"Download detected: {path.name} [{category}] -> {suggested_dest}"
        )
        if self.on_suggestion is not None:
            self.on_suggestion(suggestion)
        return suggestion

    def scan_existing(self):
        """Inspect all files currently sitting in the Downloads folder."""
        if not self.watch_dir.exists():
            return []
        suggestions = []
        for entry in sorted(self.watch_dir.iterdir()):
            if entry.is_file():
                result = self.inspect_file(entry, event_type="download_existing")
                if result is not None:
                    suggestions.append(result)
        return suggestions

    def start(self):
        """Start the background filesystem observer for the Downloads folder."""
        if not self.watch_dir.exists():
            raise FileNotFoundError(
                f"Downloads folder does not exist: {self.watch_dir}"
            )
        handler = DownloadsEventHandler(self)
        self.observer = Observer()
        self.observer.schedule(handler, str(self.watch_dir), recursive=False)
        self.observer.start()
        self._log_info(f"Watching Downloads folder: {self.watch_dir}")

    def stop(self):
        """Stop the background filesystem observer cleanly."""
        if self.observer is not None:
            self.observer.stop()
            self.observer.join(timeout=5)
            self.observer = None
            self._log_info("Stopped Downloads watcher.")

    def run_forever(self, poll_seconds=1.0):
        """Start watching and block until interrupted with Ctrl+C."""
        self.start()
        try:
            while True:
                time.sleep(poll_seconds)
        except KeyboardInterrupt:
            self._log_info("Received interrupt signal; shutting down watcher.")
        finally:
            self.stop()

    def _should_ignore(self, path):
        """Return True for hidden files or browser in-progress download extensions."""
        if path.name.startswith("."):
            return True
        return path.suffix.lower() in self.ignored_extensions

    def _log_info(self, message):
        """Log an info message when a logger is attached."""
        if self.logger is not None:
            self.logger.info(message)

    def _log_debug(self, message):
        """Log a debug message when a logger is attached."""
        if self.logger is not None:
            self.logger.debug(message)
