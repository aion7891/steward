"""Local RAG vector index built on Agno Knowledge and ChromaDB."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from agno.knowledge.document import Document
from agno.knowledge.knowledge import Knowledge
from agno.vectordb.chroma import ChromaDb
from agno.vectordb.search import SearchType

from steward.chunker import TextChunker
from steward.models import ModelFactory
from steward.reader import DocumentReader


class RAGIndex:
    """Indexes raw document chunks into ChromaDB via Agno Knowledge for passage search."""

    def __init__(self, config, logger=None, embedder=None, reader=None, chunker=None, collection_name=None):
        """Initialize persistent ChromaDB vector store, Agno Knowledge, reader, and chunker."""
        self.config = config
        self.logger = logger
        self.vector_dir = config.get_path("vector_store_dir")
        self.vector_dir.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name or config.get("rag.collection_name", "documents")
        self.manifest_path = self.vector_dir / f"{self.collection_name}_manifest.json"
        self.manifest = self._load_manifest()

        self.reader = reader or DocumentReader(config=config, logger=logger)
        self.chunker = chunker or TextChunker(
            chunk_size=config.get("rag.chunk_size", 800),
            chunk_overlap=config.get("rag.chunk_overlap", 120),
        )
        self.embedder = embedder or ModelFactory(config, logger=logger).create_embedder()
        self.vector_db = ChromaDb(
            collection=self.collection_name,
            path=str(self.vector_dir),
            persistent_client=True,
            search_type=SearchType.vector,
            embedder=self.embedder,
        )
        self.knowledge = Knowledge(
            name="steward_rag",
            description="Raw document passages indexed by Steward for local search.",
            vector_db=self.vector_db,
            max_results=int(config.get("rag.default_top_k", 5)),
        )

    def index_file(self, file_path, content_hash=None, force=False, db=None):
        """Read, chunk, embed, and upsert one document into ChromaDB."""
        path = Path(file_path).expanduser().resolve()
        path_key = str(path)
        if not path.exists() or not path.is_file():
            return {"path": path_key, "status": "error", "reason": "File not found"}
        if self.reader.is_sensitive(path):
            return {"path": path_key, "status": "skipped", "reason": "Sensitive file"}
        if not self.reader.is_supported(path):
            return {"path": path_key, "status": "skipped", "reason": "Unsupported type"}

        file_hash = content_hash or self._hash_file(path)
        existing = self.manifest.get(path_key)
        if not force and existing and existing.get("sha256") == file_hash:
            return {"path": path_key, "status": "skipped", "reason": "Unchanged"}

        content = self.reader.read(path)
        if content.skipped:
            return {"path": path_key, "status": "skipped", "reason": content.error}
        if content.error:
            if db is not None:
                db.update_file_status(path_key, "unreadable")
            return {"path": path_key, "status": "error", "reason": content.error}

        chunks = self.chunker.chunk_document(content, content_hash=file_hash)
        if not chunks:
            return {"path": path_key, "status": "empty", "reason": "No extractable text"}

        self.vector_db.create()
        # Delete old chunks whenever a file changes so stale passages never linger
        if existing is not None:
            self.vector_db.delete_by_metadata({"path": path_key})

        agno_docs = [
            Document(id=c["id"], name=c["name"], content=c["content"], meta_data=c["meta_data"])
            for c in chunks
        ]
        failure = self._safe_upsert(path, file_hash, agno_docs)
        if failure is not None:
            return {"path": path_key, "status": "error", "reason": failure}

        self.manifest[path_key] = {
            "sha256": file_hash, "file_type": content.file_type,
            "chunks": len(agno_docs), "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_manifest()
        self._log_info(f"Indexed {path.name} ({len(agno_docs)} chunk(s)) into ChromaDB.")
        return {"path": path_key, "status": "indexed", "chunks": len(agno_docs)}

    def _safe_upsert(self, path, file_hash, agno_docs):
        """Embed and store chunks; return an error message instead of raising (e.g. Ollama is off)."""
        try:
            self.vector_db.upsert(content_hash=file_hash, documents=agno_docs)
            return None
        except Exception as exc:
            if self.logger is not None:
                self.logger.warning(f"Could not embed {path.name}: {exc}")
            return f"Embedding failed: {exc}"

    def index_from_database(self, db, force=False):
        """Index all supported, non-temporary files recorded in SQLite."""
        self.manifest = self._load_manifest()  # the index may have been cleared in another process (Settings)
        summary = {"indexed": 0, "skipped": 0, "empty": 0, "errors": 0, "total_chunks": 0}
        for record in db.list_files():
            if record.get("is_temp") or record.get("status") == "unreadable":
                summary["skipped"] += 1
                continue
            result = self.index_file(
                record["path"], content_hash=record.get("sha256") or None, force=force, db=db
            )
            status = result["status"]
            if status == "indexed":
                summary["indexed"] += 1
                summary["total_chunks"] += result.get("chunks", 0)
            elif status in ("skipped", "empty"):
                summary[status] += 1
            else:
                summary["errors"] += 1
        return summary

    def search(self, query, limit=None, filters=None):
        """Search indexed passages semantically using Agno Knowledge and ChromaDB."""
        if not query or not str(query).strip():
            return []
        if not self.vector_db.exists() or self.vector_db.get_count() == 0:
            return []
        top_k = min(int(limit or self.config.get("rag.default_top_k", 5)), self.vector_db.get_count())
        docs = self.knowledge.search(query=query, max_results=top_k, filters=filters)
        results = []
        for doc in docs:
            meta = doc.meta_data or {}
            results.append({
                "content": doc.content,
                "path": meta.get("path", meta.get("source_path", "")),
                "source_path": meta.get("source_path", meta.get("path", "")),
                "file_name": meta.get("file_name", doc.name or ""),
                "file_type": meta.get("file_type", ""),
                "sha256": meta.get("sha256", ""),
                "chunk_index": meta.get("chunk_index", 0),
                "meta_data": meta,
            })
        return results

    def clear(self):
        """Delete every indexed document; the next index run starts from scratch. Returns how many files were indexed."""
        count = len(self._load_manifest())
        if self.vector_db.exists():
            self.vector_db.drop()
        self.manifest = {}
        self._save_manifest()
        return count

    def get_knowledge(self):
        """Return the underlying Agno Knowledge object for Phase 5 agents."""
        return self.knowledge

    def get_stats(self):
        """Return summary statistics about the local ChromaDB RAG index."""
        return {
            "vector_store_dir": str(self.vector_dir),
            "collection_name": self.collection_name,
            "indexed_files": len(self.manifest),
            "total_chunks": sum(item.get("chunks", 0) for item in self.manifest.values()),
            "embedder": self.embedder.__class__.__name__,
        }

    def _load_manifest(self):
        """Load the indexed-file manifest JSON from disk if it exists."""
        try:  # a missing or broken manifest means nothing is indexed yet
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_manifest(self):
        """Persist the indexed-file manifest JSON to disk."""
        self.manifest_path.write_text(json.dumps(self.manifest, indent=2, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _hash_file(path):
        """Compute SHA-256 hash of a file for change detection."""
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            while chunk := handle.read(65536):
                digest.update(chunk)
        return digest.hexdigest()

    def _log_info(self, message):
        """Write an informational log message when a logger is attached."""
        if self.logger is not None:
            self.logger.info(message)
