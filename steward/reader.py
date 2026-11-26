"""Document content and metadata reader for common local file formats."""

from pathlib import Path

from docx import Document as DocxDocument
from openpyxl import load_workbook
from PIL import ExifTags, Image
from pypdf import PdfReader


class DocumentContent:
    """Holds extracted text, metadata, and status for a single parsed file."""

    def __init__(self, path, file_type, text="", metadata=None, error=None):
        """Store parsed document content and metadata."""
        self.path = str(path)
        self.file_type = file_type
        self.text = text or ""
        self.metadata = metadata or {}
        self.char_count = len(self.text)
        self.error = error

    def to_dict(self):
        """Return a plain dictionary representation of the extracted document."""
        return {
            "path": self.path,
            "file_type": self.file_type,
            "text": self.text,
            "metadata": self.metadata,
            "char_count": self.char_count,
            "error": self.error,
        }


class DocumentReader:
    """Reads PDF, DOCX, XLSX, text, Markdown, code files, and image metadata."""

    TEXT_EXTENSIONS = {
        ".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".log",
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
        ".c", ".cpp", ".h", ".html", ".css", ".json", ".yaml", ".yml",
        ".toml", ".ini", ".cfg", ".sql", ".sh", ".xml",
    }
    IMAGE_EXTENSIONS = {
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif",
    }

    def __init__(self, config=None, logger=None, max_chars=None):
        """Initialize the reader with an optional AppConfig and max character cap."""
        self.config = config
        self.logger = logger
        default_limit = (
            config.get("rag.max_file_chars", 100000) if config is not None else 100000
        )
        self.max_chars = int(max_chars if max_chars is not None else default_limit)

    def is_supported(self, file_path):
        """Return True if this reader knows how to inspect the file extension."""
        ext = Path(file_path).suffix.lower()
        return ext in (
            {".pdf", ".docx", ".xlsx"} | self.TEXT_EXTENSIONS | self.IMAGE_EXTENSIONS
        )

    def read(self, file_path):
        """Read a file and return a DocumentContent object with text and metadata."""
        path = Path(file_path).expanduser().resolve()
        ext = path.suffix.lower()
        if not path.exists() or not path.is_file():
            return DocumentContent(path, ext or "unknown", error="File not found")

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
            return DocumentContent(path, ext or "unknown", error="Unsupported file type")
        except Exception as exc:
            self._log_warning(f"Failed reading {path.name}: {exc}")
            return DocumentContent(path, ext or "unknown", error=str(exc))

    def _read_pdf(self, path):
        """Extract page text and PDF document properties via pypdf."""
        reader = PdfReader(str(path))
        pages_text = []
        for idx, page in enumerate(reader.pages, start=1):
            extracted = (page.extract_text() or "").strip()
            if extracted:
                pages_text.append(f"[Page {idx}]\n{extracted}")
        info = reader.metadata or {}
        metadata = {
            "pages": len(reader.pages),
            "title": str(info.get("/Title", "") or ""),
            "author": str(info.get("/Author", "") or ""),
        }
        return DocumentContent(
            path, "pdf", self._trim("\n\n".join(pages_text)), metadata
        )

    def _read_docx(self, path):
        """Extract paragraphs and table text from a Word .docx file."""
        doc = DocxDocument(str(path))
        blocks = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    blocks.append(" | ".join(cells))
        metadata = {"paragraphs": len(doc.paragraphs), "tables": len(doc.tables)}
        return DocumentContent(path, "docx", self._trim("\n\n".join(blocks)), metadata)

    def _read_xlsx(self, path):
        """Extract sheet names and cell rows from an Excel .xlsx workbook."""
        workbook = load_workbook(filename=str(path), read_only=True, data_only=True)
        sections = []
        row_count = 0
        try:
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                lines = [f"[Sheet: {sheet_name}]"]
                for row in sheet.iter_rows(values_only=True):
                    values = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
                    if values:
                        lines.append(" | ".join(values))
                        row_count += 1
                if len(lines) > 1:
                    sections.append("\n".join(lines))
            metadata = {"sheets": list(workbook.sheetnames), "rows": row_count}
        finally:
            workbook.close()
        return DocumentContent(
            path, "xlsx", self._trim("\n\n".join(sections)), metadata
        )

    def _read_text(self, path):
        """Read plain text, Markdown, or source code with UTF-8 fallback."""
        raw = path.read_text(encoding="utf-8", errors="replace")
        trimmed = self._trim(raw)
        metadata = {
            "extension": path.suffix.lower(),
            "lines": raw.count("\n") + (1 if raw else 0),
        }
        file_type = "markdown" if path.suffix.lower() in (".md", ".markdown") else "text"
        return DocumentContent(path, file_type, trimmed, metadata)

    def _read_image_metadata(self, path):
        """Extract image dimensions, format, and EXIF metadata into searchable text."""
        with Image.open(str(path)) as img:
            width, height = img.size
            exif_clean = {}
            raw_exif = img.getexif() if hasattr(img, "getexif") else {}
            for tag_id, value in (raw_exif or {}).items():
                tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                exif_clean[str(tag_name)] = str(value)[:120]
            metadata = {
                "format": img.format or path.suffix.lstrip(".").upper(),
                "mode": img.mode,
                "width": width,
                "height": height,
                "exif": exif_clean,
            }
        lines = [
            f"Image file: {path.name}",
            f"Format: {metadata['format']} | Mode: {metadata['mode']} | Size: {width}x{height}",
        ]
        for key, value in exif_clean.items():
            lines.append(f"EXIF {key}: {value}")
        return DocumentContent(path, "image", "\n".join(lines), metadata)

    def _trim(self, text):
        """Cap extracted text at max_chars to keep indexing bounded."""
        if len(text) <= self.max_chars:
            return text
        return text[: self.max_chars]

    def _log_warning(self, message):
        """Log a warning message when a logger is attached."""
        if self.logger is not None:
            self.logger.warning(message)
