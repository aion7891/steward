"""Steward package root."""

from steward.chunker import HashEmbedder, TextChunker
from steward.config import AppConfig, ConfigError
from steward.database import DatabaseManager
from steward.logger import LoggerFactory
from steward.models import ModelConfigError, ModelFactory
from steward.rag import RAGIndex
from steward.reader import DocumentContent, DocumentReader
from steward.scanner import FileCategorizer, FileScanner
from steward.software import SoftwareDetector
from steward.watcher import DownloadsWatcher

__version__ = "0.3.0"

__all__ = [
    "AppConfig",
    "ConfigError",
    "DatabaseManager",
    "DocumentContent",
    "DocumentReader",
    "DownloadsWatcher",
    "FileCategorizer",
    "FileScanner",
    "HashEmbedder",
    "LoggerFactory",
    "ModelConfigError",
    "ModelFactory",
    "RAGIndex",
    "SoftwareDetector",
    "TextChunker",
    "__version__",
]
