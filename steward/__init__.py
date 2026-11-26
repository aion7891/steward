"""Steward package root."""

from steward.config import AppConfig, ConfigError
from steward.database import DatabaseManager
from steward.logger import LoggerFactory
from steward.models import ModelConfigError, ModelFactory
from steward.scanner import FileCategorizer, FileScanner
from steward.software import SoftwareDetector
from steward.watcher import DownloadsWatcher

__version__ = "0.2.0"

__all__ = [
    "AppConfig",
    "ConfigError",
    "DatabaseManager",
    "DownloadsWatcher",
    "FileCategorizer",
    "FileScanner",
    "LoggerFactory",
    "ModelConfigError",
    "ModelFactory",
    "SoftwareDetector",
    "__version__",
]
