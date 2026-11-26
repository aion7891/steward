"""Steward package root."""

from steward.agents import StewardAgents
from steward.api import StewardAPIServer, create_api_app
from steward.chunker import HashEmbedder, TextChunker
from steward.client import StewardClient
from steward.config import AppConfig, ConfigError
from steward.database import DatabaseManager
from steward.knowledge_builder import KnowledgeBuilder
from steward.logger import LoggerFactory
from steward.memory import MemoryManager
from steward.models import ModelConfigError, ModelFactory
from steward.okf_bundle import OKFBundle, OKFValidationError
from steward.okf_graph import OKFGraph
from steward.organizer import FileOrganizer
from steward.rag import RAGIndex
from steward.reader import DocumentContent, DocumentReader
from steward.recommender import PatternMiner, RecommenderEngine
from steward.recycle import RecycleManager
from steward.reporter import ReportGenerator
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
from steward.worker import StewardWorker
from steward.workflows import StewardWorkflows

__version__ = "0.9.0"

__all__ = [
    "AppConfig", "ConfigError", "DatabaseManager", "DocumentContent", "DocumentReader",
    "DocumentReaderTools", "DownloadsWatcher", "FileCategorizer", "FileOrganizer",
    "FileScanner", "FileScannerTools", "HashEmbedder", "KnowledgeBuilder",
    "LoggerFactory", "MemoryManager", "ModelConfigError", "ModelFactory", "OKFBundle",
    "OKFGraph", "OKFTools", "OKFValidationError", "OrganizerTools", "PatternMiner",
    "RAGIndex", "RecommenderEngine", "RecycleManager", "ReportGenerator",
    "ReportTools", "SoftwareDetector", "SoftwareTools", "StewardAPIServer",
    "StewardAgents", "StewardClient", "StewardWorker", "StewardWorkflows",
    "TextChunker", "create_api_app", "__version__",
]
