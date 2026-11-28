"""Document content and metadata reader with sensitive-file and size guards."""

import fnmatch
from pathlib import Path

from docx import Document as DocxDocument
from openpyxl import load_workbook
from PIL import ExifTags, Image
from pypdf import PdfReader


class DocumentContent:
    """Holds extracted text, metadata, and status for a single parsed file."""

    def __init__(self, path, file_type, text="", metadata=None, error=None, skipped=False):
        """Store parsed document content, metadata, and skip/error flags."""
        self.path = str(path)
        self.file_type = file_type
        self.text = text or ""
        self.metadata = metadata or {}
        self.char_count = len(self.text)
        self.error = error
        self.skipped = skipped

    def to_dict(self):
        """Return a plain dictionary representation of the extracted document."""
        return {
            "path": self.path, "file_type": self.file_type, "text": self.text,
            "metadata": self.metadata, "char_count": self.char_count,
            "error": self.error, "skipped": self.skipped,
        }


class DocumentReader:
    """Reads PDF, DOCX, XLSX, text, Markdown, code, and image metadata safely."""

    TEXT_EXTENSIONS = {
        ".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".log",
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
        ".c", ".cpp", ".h", ".html", ".css", ".json", ".yaml", ".yml",
        ".toml", ".ini", ".cfg", ".sql", ".sh", ".xml",
    }
    IMAGE_EXTENSIONS = {
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif",
    }
    DEFAULT_SENSITIVE = (
        ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx",
        "id_rsa*", "*password*", "*secret*", "*credentials*",
    )

    def __init__(self, config=None, logger=None, max_chars=None, max_read_mb=None):
        """Initialize the reader with char cap, file size cap, and privacy filter."""
        self.config = config
        self.logger = logger
        cfg_chars = config.get("rag.max_file_chars", 100000) if config else 100000
        cfg_mb = config.get("rag.max_read_mb", 20) if config else 20
        cfg_sens = config.get("rag.sensitive_patterns", self.DEFAULT_SENSITIVE) if config else self.DEFAULT_SENSITIVE
        self.max_chars = int(max_chars if max_chars is not None else cfg_chars)
        self.max_read_bytes = int(float(max_read_mb if max_read_mb is not None else cfg_mb) * 1024 * 1024)
        self.sensitive_patterns = tuple(cfg_sens)

    def is_sensitive(self, file_path):
        """Return True if filename matches a sensitive pattern (.env, keys, secrets)."""
        name = Path(file_path).name.lower()
        return any(fnmatch.fnmatch(name, pat.lower()) for pat in self.sensitive_patterns)

    def is_supported(self, file_path):
        """Return True if this reader knows how to inspect the file extension."""
        ext = Path(file_path).suffix.lower()
        return ext in ({".pdf", ".docx", ".xlsx"} | self.TEXT_EXTENSIONS | self.IMAGE_EXTENSIONS)

    def read(self, file_path):
        """Read a file safely, enforcing sensitive-file and size limits."""
        path = Path(file_path).expanduser().resolve()
        ext = path.suffix.lower()
        if not path.exists() or not path.is_file():
            return DocumentContent(path, ext or "unknown", error="File not found")
        if self.is_sensitive(path):
            return DocumentContent(path, ext or "sensitive", error="Skipped sensitive file", skipped=True)
        if path.stat().st_size > self.max_read_bytes:
            return DocumentContent(path, ext or "oversized", error="Skipped oversized file", skipped=True)

        try:
            if ext == ".pdf":
                return self._read_pdf(path)
            if ext == ".docx":
                return self._read_docx(path)
            if ext == ".xlsx":
                return self._read_xlsx(path)
            if ext in self.IMAGE_EXTENSIONS:
                return self._read_image_metadata(path)
            if ext in self.TEXT_EXTENSIONS:
                return self._read_text(path)
            return DocumentContent(path, ext or "unknown", error="Unsupported file type", skipped=True)
        except Exception as exc:
            self._log_warning(f"Failed reading {path.name}: {exc}")
            return DocumentContent(path, ext or "unknown", error=str(exc))

    def _read_pdf(self, path):
        """Extract page text and PDF document properties via pypdf."""
        reader = PdfReader(str(path))
        pages = []
        for idx, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(f"[Page {idx}]\n{text}")
        info = reader.metadata or {}
        meta = {
            "pages": len(reader.pages),
            "title": str(info.get("/Title", "") or ""),
            "author": str(info.get("/Author", "") or ""),
        }
        return DocumentContent(path, "pdf", self._trim("\n\n".join(pages)), meta)

    def _read_docx(self, path):
        """Extract paragraphs and table text from a Word .docx file."""
        doc = DocxDocument(str(path))
        blocks = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    blocks.append(" | ".join(cells))
        meta = {"paragraphs": len(doc.paragraphs), "tables": len(doc.tables)}
        return DocumentContent(path, "docx", self._trim("\n\n".join(blocks)), meta)

    def _read_xlsx(self, path):
        """Extract sheet names and cell rows from an Excel .xlsx workbook."""
        workbook = load_workbook(filename=str(path), read_only=True, data_only=True)
        sections, row_count = [], 0
        try:
            for name in workbook.sheetnames:
                lines = [f"[Sheet: {name}]"]
                for row in workbook[name].iter_rows(values_only=True):
                    vals = [str(c).strip() for c in row if c is not None and str(c).strip()]
                    if vals:
                        lines.append(" | ".join(vals))
                        row_count += 1
                if len(lines) > 1:
                    sections.append("\n".join(lines))
            meta = {"sheets": list(workbook.sheetnames), "rows": row_count}
        finally:
            workbook.close()
        return DocumentContent(path, "xlsx", self._trim("\n\n".join(sections)), meta)

    def _read_text(self, path):
        """Read plain text, Markdown, or source code with UTF-8 fallback."""
        raw = path.read_text(encoding="utf-8", errors="replace")
        meta = {"extension": path.suffix.lower(), "lines": raw.count("\n") + (1 if raw else 0)}
        ftype = "markdown" if path.suffix.lower() in (".md", ".markdown") else "text"
        return DocumentContent(path, ftype, self._trim(raw), meta)

    def _read_image_metadata(self, path):
        """Extract image dimensions, format, and EXIF metadata into searchable text."""
        with Image.open(str(path)) as img:
            width, height = img.size
            exif_clean = {}
            raw_exif = img.getexif() if hasattr(img, "getexif") else {}
            for tag_id, value in (raw_exif or {}).items():
                exif_clean[str(ExifTags.TAGS.get(tag_id, tag_id))] = str(value)[:120]
            meta = {
                "format": img.format or path.suffix.lstrip(".").upper(),
                "mode": img.mode, "width": width, "height": height, "exif": exif_clean,
            }
        lines = [
            f"Image file: {path.name}",
            f"Format: {meta['format']} | Mode: {meta['mode']} | Size: {width}x{height}",
        ] + [f"EXIF {k}: {v}" for k, v in exif_clean.items()]
        return DocumentContent(path, "image", "\n".join(lines), meta)

    def _trim(self, text):
        """Cap extracted text at max_chars to keep indexing bounded."""
        return text if len(text) <= self.max_chars else text[: self.max_chars]

    def _log_warning(self, message):
        """Log a warning message when a logger is attached."""
        if self.logger is not None:
            self.logger.warning(message)
