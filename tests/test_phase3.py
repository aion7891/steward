"""Unit tests for Phase 3: Document reading, privacy guards, chunking, and ChromaDB RAG."""

import yaml
from docx import Document as DocxDocument
from openpyxl import Workbook
from PIL import Image

from steward.chunker import HashEmbedder, TextChunker
from steward.config import AppConfig
from steward.database import DatabaseManager
from steward.rag import RAGIndex
from steward.reader import DocumentReader
from steward.scanner import FileScanner


class Phase3Fixtures:
    """Creates real PDF, DOCX, XLSX, PNG, Markdown, and Python files for testing."""

    @staticmethod
    def write_minimal_pdf(path, text):
        """Write a valid single-page PDF containing the given ASCII text."""
        safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET".encode("latin-1")
        objs = [
            b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n",
            b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
            b"5 0 obj << /Length " + str(len(stream)).encode() + b" >> stream\n"
            + stream + b"\nendstream endobj\n",
        ]
        body = bytearray(b"%PDF-1.4\n")
        offsets = []
        for obj in objs:
            offsets.append(len(body))
            body.extend(obj)
        xref_pos = len(body)
        body.extend(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
        for off in offsets:
            body.extend(f"{off:010d} 00000 n \n".encode())
        body.extend(
            f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
        )
        path.write_bytes(bytes(body))

    @staticmethod
    def build_sample_files(folder):
        """Populate folder with one file of each supported Phase 3 format."""
        folder.mkdir(parents=True, exist_ok=True)
        pdf_path = folder / "tax_guide.pdf"
        Phase3Fixtures.write_minimal_pdf(pdf_path, "Quarterly tax deduction checklist")

        docx_path = folder / "project_plan.docx"
        doc = DocxDocument()
        doc.add_paragraph("Apollo launch milestone schedule and budget review.")
        doc.save(str(docx_path))

        xlsx_path = folder / "expenses.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "Q1"
        ws.append(["Vendor", "Amount"])
        ws.append(["CloudHost", 1250])
        wb.save(str(xlsx_path))
        wb.close()

        md_path = folder / "notes.md"
        md_path.write_text("# Kubernetes Notes\nDeploy Redis cluster with persistent storage.", encoding="utf-8")

        py_path = folder / "backup.py"
        py_path.write_text("def run_backup():\n    return 'archive complete'\n", encoding="utf-8")

        img_path = folder / "diagram.png"
        Image.new("RGB", (120, 80), color="navy").save(str(img_path))
        return {
            "pdf": pdf_path, "docx": docx_path, "xlsx": xlsx_path,
            "md": md_path, "py": py_path, "img": img_path,
        }


class TestDocumentReaderAndChunker:
    """Tests for multi-format extraction, sensitive-file filter, and chunking."""

    def test_reads_all_supported_formats(self, tmp_path):
        """Verify PDF, DOCX, XLSX, Markdown, Python, and PNG metadata extraction."""
        files = Phase3Fixtures.build_sample_files(tmp_path / "docs")
        reader = DocumentReader()

        pdf_doc = reader.read(files["pdf"])
        docx_doc = reader.read(files["docx"])
        xlsx_doc = reader.read(files["xlsx"])
        md_doc = reader.read(files["md"])
        py_doc = reader.read(files["py"])
        img_doc = reader.read(files["img"])

        assert "tax deduction" in pdf_doc.text.lower()
        assert "apollo launch" in docx_doc.text.lower()
        assert "CloudHost" in xlsx_doc.text and "1250" in xlsx_doc.text
        assert "Kubernetes" in md_doc.text and md_doc.file_type == "markdown"
        assert "run_backup" in py_doc.text and py_doc.file_type == "text"
        assert img_doc.metadata["width"] == 120 and img_doc.metadata["height"] == 80

    def test_skips_sensitive_and_oversized_files(self, tmp_path):
        """Verify .env/key files and oversized files are skipped during reading."""
        env_file = tmp_path / ".env"
        env_file.write_text("OPENAI_API_KEY=sk-secret", encoding="utf-8")
        key_file = tmp_path / "server.key"
        key_file.write_text("PRIVATE KEY DATA", encoding="utf-8")
        big_txt = tmp_path / "huge.txt"
        big_txt.write_text("A" * 2048, encoding="utf-8")

        reader = DocumentReader(max_read_mb=0.001)
        assert reader.read(env_file).skipped is True
        assert reader.read(key_file).skipped is True
        assert reader.read(big_txt).skipped is True

    def test_chunker_splits_long_text_with_required_metadata(self, tmp_path):
        """Verify TextChunker creates overlapping chunks with path, file_id, and sha256."""
        long_file = tmp_path / "long.txt"
        long_file.write_text(("Sentence about Steward RAG indexing. " * 40).strip(), encoding="utf-8")
        doc = DocumentReader().read(long_file)

        chunks = TextChunker(chunk_size=250, chunk_overlap=50).chunk_document(doc, content_hash="abc123")
        assert len(chunks) >= 5
        meta = chunks[0]["meta_data"]
        assert meta["file_name"] == "long.txt"
        assert meta["sha256"] == "abc123"
        assert "file_id" in meta and "path" in meta


class TestRAGIndexChroma:
    """End-to-end tests for Agno Knowledge + ChromaDB indexing, updates, and search."""

    def _build_env(self, tmp_path, docs_dir):
        """Create isolated AppConfig, DatabaseManager, and ChromaDB RAGIndex."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            yaml.safe_dump({"scanner": {"watched_folders": [str(docs_dir)]}}),
            encoding="utf-8",
        )
        config = AppConfig(config_path=cfg_file, base_dir=tmp_path)
        config.ensure_directories()
        db = DatabaseManager(config.get_path("db_path"))
        rag = RAGIndex(config, embedder=HashEmbedder(dimensions=256))
        return config, db, rag

    def test_indexes_skips_sensitive_replaces_changed_and_searches(self, tmp_path):
        """Verify ChromaDB indexes 6 files, skips .env, updates changed files, and searches."""
        docs_dir = tmp_path / "docs"
        files = Phase3Fixtures.build_sample_files(docs_dir)
        (docs_dir / ".env").write_text("SECRET_TOKEN=never_index_me", encoding="utf-8")
        config, db, rag = self._build_env(tmp_path, docs_dir)

        FileScanner(config, db).scan_all()
        first_run = rag.index_from_database(db)
        second_run = rag.index_from_database(db)

        assert first_run["indexed"] == 6
        assert first_run["skipped"] == 1
        assert second_run["indexed"] == 0
        assert second_run["skipped"] == 7

        tax_hits = rag.search("quarterly tax deduction checklist", limit=3)
        assert len(tax_hits) >= 1 and tax_hits[0]["file_name"] == "tax_guide.pdf"

        # Modify notes.md and verify old chunks are replaced cleanly in ChromaDB
        files["md"].write_text("# Rust Notes\nAsync Tokio runtime guide.", encoding="utf-8")
        update = rag.index_file(files["md"])
        assert update["status"] == "indexed"
        rust_hits = rag.search("Rust Async Tokio runtime", limit=2)
        assert rust_hits[0]["file_name"] == "notes.md"
        assert "Tokio" in rust_hits[0]["content"]
        assert rag.get_stats()["collection_name"] == "documents"
