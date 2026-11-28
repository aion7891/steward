"""Text chunking and deterministic local embedding helper for RAG."""

import hashlib
import math
import re
from pathlib import Path

from agno.knowledge.embedder.base import Embedder


class TextChunker:
    """Splits long document text into overlapping passages for vector indexing."""

    def __init__(self, chunk_size=800, chunk_overlap=120):
        """Configure chunk target length and overlap size in characters."""
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive.")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be >= 0 and smaller than chunk_size.")
        self.chunk_size = int(chunk_size)
        self.chunk_overlap = int(chunk_overlap)

    def chunk_document(self, doc_content, content_hash=""):
        """Split a DocumentContent object into metadata-enriched passage dictionaries."""
        cleaned = self._normalize_text(doc_content.text)
        if not cleaned:
            return []

        raw_chunks = self.split_text(cleaned)
        path = Path(doc_content.path)
        total = len(raw_chunks)
        chunks = []
        for idx, passage in enumerate(raw_chunks):
            chunk_id = self._build_chunk_id(doc_content.path, idx, passage)
            chunks.append(
                {
                    "id": chunk_id,
                    "name": f"{path.name}#chunk-{idx + 1}",
                    "content": passage,
                    "meta_data": {
                        "file_id": hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16],
                        "path": str(path),
                        "source_path": str(path),
                        "file_name": path.name,
                        "file_type": doc_content.file_type,
                        "chunk_index": idx,
                        "total_chunks": total,
                        "sha256": content_hash,
                    },
                }
            )
        return chunks

    def split_text(self, text):
        """Split text into overlapping segments preferring paragraph/sentence breaks."""
        cleaned = self._normalize_text(text)
        if not cleaned:
            return []
        if len(cleaned) <= self.chunk_size:
            return [cleaned]

        segments = []
        start = 0
        length = len(cleaned)
        while start < length:
            end = min(start + self.chunk_size, length)
            if end < length:
                split_at = self._find_break(cleaned, start, end)
                if split_at > start:
                    end = split_at
            piece = cleaned[start:end].strip()
            if piece:
                segments.append(piece)
            if end >= length:
                break
            next_start = max(end - self.chunk_overlap, start + 1)
            start = next_start
        return segments

    def _find_break(self, text, start, end):
        """Find a clean break point (newline or space) near the end of a window."""
        window = text[start:end]
        min_keep = int(len(window) * 0.5)
        for separator in ("\n\n", "\n", ". ", " "):
            pos = window.rfind(separator)
            if pos >= min_keep:
                return start + pos + len(separator)
        return end

    @staticmethod
    def _normalize_text(text):
        """Collapse excessive blank lines and trim outer whitespace."""
        if not text:
            return ""
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()

    @staticmethod
    def _build_chunk_id(path, index, passage):
        """Create a stable chunk identifier from path, index, and text."""
        raw = f"{path}:{index}:{passage[:64]}".encode("utf-8", errors="ignore")
        return hashlib.sha256(raw).hexdigest()[:24]


class HashEmbedder(Embedder):
    """Offline deterministic Agno Embedder for tests and Ollama-free demos.

    Uses token feature hashing into an L2-normalized vector so Agno Knowledge
    and LanceDb can run real cosine vector search without an external server.
    """

    TOKEN_RE = re.compile(r"[a-z0-9_]+")

    def __init__(self, dimensions=256):
        """Initialize the local hash embedder with a fixed vector dimension."""
        self.dimensions = int(dimensions)
        self.enable_batch = False
        self.batch_size = 100

    def get_embedding(self, text):
        """Convert text into an L2-normalized dense float vector."""
        vector = [0.0] * self.dimensions
        tokens = self.TOKEN_RE.findall((text or "").lower())
        if not tokens:
            return vector

        features = list(tokens)
        for idx in range(len(tokens) - 1):
            features.append(f"{tokens[idx]}_{tokens[idx + 1]}")

        for token in features:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dimensions
            sign = 1.0 if (digest[4] & 1) == 0 else -1.0
            vector[bucket] += sign

        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector

    def get_embedding_and_usage(self, text):
        """Return both the embedding vector and a minimal usage dictionary."""
        return self.get_embedding(text), {"tokens": len((text or "").split())}

    async def async_get_embedding(self, text):
        """Async wrapper around get_embedding for Agno async paths."""
        return self.get_embedding(text)

    async def async_get_embedding_and_usage(self, text):
        """Async wrapper around get_embedding_and_usage."""
        return self.get_embedding_and_usage(text)
