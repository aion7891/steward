"""Centralized logging setup for Steward."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


class LoggerFactory:
    """Creates consistent console and rotating-file loggers for Steward."""

    LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

    def __init__(self, config=None):
        """Initialize the logger factory using an optional AppConfig instance."""
        self.config = config
        self.log_level = self._resolve_level()
        self.log_file_path = self._resolve_log_file()
        self.max_bytes = self._get_setting("app.log_max_bytes", 5242880)
        self.backup_count = self._get_setting("app.log_backup_count", 3)

    def _get_setting(self, dotted_key, default):
        """Read a setting from AppConfig when available, otherwise use default."""
        if self.config is None:
            return default
        return self.config.get(dotted_key, default)

    def _resolve_level(self):
        """Convert the configured level name into a Python logging constant."""
        level_name = str(self._get_setting("app.log_level", "INFO")).upper()
        return getattr(logging, level_name, logging.INFO)

    def _resolve_log_file(self):
        """Determine the destination path for the rotating log file."""
        if self.config is None:
            return None
        logs_dir = self.config.get_path("logs_dir")
        file_name = self._get_setting("app.log_file", "steward.log")
        return Path(logs_dir) / file_name

    def _build_formatter(self):
        """Create the shared log line formatter."""
        return logging.Formatter(fmt=self.LOG_FORMAT, datefmt=self.DATE_FORMAT)

    def _build_console_handler(self, formatter):
        """Create a stream handler that prints log entries to stderr."""
        handler = logging.StreamHandler()
        handler.setLevel(self.log_level)
        handler.setFormatter(formatter)
        handler.set_name("steward_console")
        return handler

    def _build_file_handler(self, formatter):
        """Create a rotating file handler, ensuring the log directory exists."""
        if self.log_file_path is None:
            return None
        try:
            self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(
                filename=str(self.log_file_path),
                maxBytes=int(self.max_bytes),
                backupCount=int(self.backup_count),
                encoding="utf-8",
            )
            handler.setLevel(self.log_level)
            handler.setFormatter(formatter)
            handler.set_name("steward_file")
            return handler
        except OSError:
            return None

    def configure_logger(self, name="steward", enable_file=True):
        """Return a configured logger without attaching duplicate handlers."""
        logger = logging.getLogger(name)
        logger.setLevel(self.log_level)
        logger.propagate = False

        existing_names = {handler.get_name() for handler in logger.handlers}
        formatter = self._build_formatter()

        if "steward_console" not in existing_names:
            logger.addHandler(self._build_console_handler(formatter))

        if enable_file and "steward_file" not in existing_names:
            file_handler = self._build_file_handler(formatter)
            if file_handler is not None:
                logger.addHandler(file_handler)

        return logger

    def get_logger(self, name, enable_file=True):
        """Return a named child logger under the Steward hierarchy."""
        full_name = name if name.startswith("steward") else f"steward.{name}"
        return self.configure_logger(name=full_name, enable_file=enable_file)

    @staticmethod
    def clear_handlers(name):
        """Close and remove all handlers on a logger (useful in tests)."""
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)
