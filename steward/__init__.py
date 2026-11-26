"""Steward package root."""

from steward.chunker import HashEmbedder, TextChunker
from steward.config import AppConfig, ConfigError
from steward.database import DatabaseManager
from steward.knowledge_builder import KnowledgeBuilder
from steward.logger import LoggerFactory
from steward.memory import MemoryManager
from steward.models import ModelConfigError, ModelFactory
from steward.okf_bundle import OKFBundle, OKFValidationError
from steward.okf_graph import OKFGraph
from steward.rag import RAGIndex
from steward.reader import DocumentContent, DocumentReader
from steward.scanner import FileCategorizer, FileScanner
from steward.software import SoftwareDetector
from steward.watcher import DownloadsWatcher

__version__ = "0.4.0"

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
    "KnowledgeBuilder",
    "LoggerFactory",
    "MemoryManager",
    "ModelConfigError",
    "ModelFactory",
    "OKFBundle",
    "OKFGraph",
    "OKFValidationError",
    "RAGIndex",
    "SoftwareDetector",
    "TextChunker",
    "__version__",
]
