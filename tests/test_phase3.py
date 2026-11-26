"""Unit tests for Phase 3: Document reading, text chunking, and LanceDB RAG."""

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
        header = b"%PDF-1.4\n"
        offsets = []
        body = bytearray(header)
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
    """Tests for multi-format extraction and overlapping passage chunking."""

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
        assert "120x80" in img_doc.text

    def test_chunker_splits_long_text_with_overlap(self, tmp_path):
        """Verify TextChunker creates overlapping chunks with metadata."""
        reader = DocumentReader()
        long_file = tmp_path / "long.txt"
        long_file.write_text(("Sentence about Steward RAG indexing. " * 40).strip(), encoding="utf-8")
        doc = reader.read(long_file)

        chunker = TextChunker(chunk_size=250, chunk_overlap=50)
        chunks = chunker.chunk_document(doc, content_hash="abc123")

        assert len(chunks) >= 5
        assert chunks[0]["meta_data"]["file_name"] == "long.txt"
        assert chunks[0]["meta_data"]["total_chunks"] == len(chunks)


class TestRAGIndex:
    """End-to-end tests for Agno Knowledge + LanceDB indexing and semantic search."""

    def _build_env(self, tmp_path, docs_dir):
        """Create isolated AppConfig, DatabaseManager, and RAGIndex with HashEmbedder."""
        cfg_file = tmp_path / "config.yaml"
        cfg_data = {"scanner": {"watched_folders": [str(docs_dir)]}}
        cfg_file.write_text(yaml.safe_dump(cfg_data), encoding="utf-8")
        config = AppConfig(config_path=cfg_file, base_dir=tmp_path)
        config.ensure_directories()
        db = DatabaseManager(config.get_path("db_path"))
        rag = RAGIndex(config, embedder=HashEmbedder(dimensions=256))
        return config, db, rag

    def test_indexes_scanned_files_skips_unchanged_and_searches(self, tmp_path):
        """Verify end-to-end scan -> index -> skip unchanged -> semantic search."""
        docs_dir = tmp_path / "docs"
        Phase3Fixtures.build_sample_files(docs_dir)
        config, db, rag = self._build_env(tmp_path, docs_dir)

        FileScanner(config, db).scan_all()
        first_run = rag.index_from_database(db)
        second_run = rag.index_from_database(db)

        assert first_run["indexed"] == 6
        assert first_run["errors"] == 0
        assert second_run["indexed"] == 0
        assert second_run["skipped"] == 6

        tax_hits = rag.search("quarterly tax deduction checklist", limit=3)
        k8s_hits = rag.search("kubernetes redis persistent storage", limit=3)

        assert len(tax_hits) >= 1
        assert tax_hits[0]["file_name"] == "tax_guide.pdf"
        assert len(k8s_hits) >= 1
        assert k8s_hits[0]["file_name"] == "notes.md"
        assert rag.get_stats()["indexed_files"] == 6
