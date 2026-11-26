"""Steward package root."""

from steward.agents import StewardAgents
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
from steward.tools import (
    DocumentReaderTools,
    FileScannerTools,
    OKFTools,
    OrganizerTools,
    ReportTools,
    SoftwareTools,
)
from steward.watcher import DownloadsWatcher
from steward.workflows import StewardWorkflows

__version__ = "0.5.0"

__all__ = [
    "AppConfig", "ConfigError", "DatabaseManager", "DocumentContent", "DocumentReader",
    "DocumentReaderTools", "DownloadsWatcher", "FileCategorizer", "FileScanner",
    "FileScannerTools", "HashEmbedder", "KnowledgeBuilder", "LoggerFactory",
    "MemoryManager", "ModelConfigError", "ModelFactory", "OKFBundle", "OKFGraph",
    "OKFTools", "OKFValidationError", "OrganizerTools", "RAGIndex", "ReportTools",
    "SoftwareDetector", "SoftwareTools", "StewardAgents", "StewardWorkflows",
    "TextChunker", "__version__",
]
