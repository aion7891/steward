"""OKF v0.3 knowledge bundle manager: read, write, validate, and search Markdown concepts."""

import re
from datetime import datetime, timezone
from pathlib import Path

import yaml


class OKFValidationError(Exception):
    """Raised when an OKF concept fails schema or secret-safety validation."""


class OKFBundle:
    """Manages a folder of OKF v0.3 Markdown concepts with YAML frontmatter."""

    SUBDIRS = (
        "files", "folders", "projects", "software", "topics",
        "memory/preferences", "memory/patterns", "memory/decisions", "reports",
    )
    SECRET_PATTERNS = (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
        re.compile(r"(?i)(api[_-]?key|password|secret[_-]?token)\s*[:=]\s*['\"]?[^\s'\"]{8,}"),
    )

    def __init__(self, root_dir, logger=None):
        """Initialize the OKF bundle directory structure and index.md."""
        self.root_dir = Path(root_dir).expanduser().resolve()
        self.logger = logger
        self.initialize_layout()

    def initialize_layout(self):
        """Create the standard OKF directory tree and index.md if missing."""
        self.root_dir.mkdir(parents=True, exist_ok=True)
        for rel_dir in self.SUBDIRS:
            (self.root_dir / rel_dir).mkdir(parents=True, exist_ok=True)
        if not (self.root_dir / "index.md").exists():
            self.refresh_index()

    def validate_concept(self, frontmatter, body=""):
        """Validate required OKF fields and reject potential secret leaks."""
        if not isinstance(frontmatter, dict):
            raise OKFValidationError("Frontmatter must be a YAML mapping.")
        if not str(frontmatter.get("type", "")).strip():
            raise OKFValidationError("OKF concept requires a non-empty 'type' field.")
        if not str(frontmatter.get("title", "")).strip():
            raise OKFValidationError("OKF concept requires a non-empty 'title' field.")
        tags = frontmatter.get("tags", [])
        if tags is not None and not isinstance(tags, list):
            raise OKFValidationError("'tags' must be a list of strings.")

        serialized = yaml.safe_dump(frontmatter, sort_keys=False) + "\n" + (body or "")
        for pattern in self.SECRET_PATTERNS:
            if pattern.search(serialized):
                raise OKFValidationError("Refusing to write potential secret into OKF bundle.")

    def write_concept(self, rel_path, frontmatter, body):
        """Validate and atomically write a concept; keep old file untouched on failure."""
        target = self._resolve_concept_path(rel_path)
        meta = dict(frontmatter)
        meta.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        meta.setdefault("tags", [])
        meta.setdefault("sources", [])
        try:
            self.validate_concept(meta, body)
        except OKFValidationError as exc:
            self._log_warning(f"Skipping invalid OKF concept '{rel_path}': {exc}")
            raise

        target.parent.mkdir(parents=True, exist_ok=True)
        yaml_block = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip()
        content = f"---\n{yaml_block}\n---\n\n{(body or '').strip()}\n"
        tmp_path = target.with_suffix(".md.tmp")
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(target)
        return self._to_rel(target)

    def read_concept(self, rel_path):
        """Read and parse one OKF Markdown file into frontmatter, body, and rel_path."""
        target = self._resolve_concept_path(rel_path)
        if not target.exists():
            return None
        fm, body = self._parse_markdown(target.read_text(encoding="utf-8"))
        return {"rel_path": self._to_rel(target), "path": str(target), "frontmatter": fm, "body": body}

    def update_concept(self, rel_path, frontmatter_updates=None, body=None):
        """Merge frontmatter updates and/or replace body of an existing concept."""
        existing = self.read_concept(rel_path)
        if existing is None:
            raise FileNotFoundError(f"OKF concept not found: {rel_path}")
        merged = dict(existing["frontmatter"])
        if frontmatter_updates:
            merged.update(frontmatter_updates)
        merged["timestamp"] = datetime.now(timezone.utc).isoformat()
        return self.write_concept(rel_path, merged, existing["body"] if body is None else body)

    def delete_concept(self, rel_path):
        """Delete an OKF concept file if it exists and return True if removed."""
        target = self._resolve_concept_path(rel_path)
        if target.exists() and target.is_file():
            target.unlink()
            return True
        return False

    def list_concepts(self, subdir=None, concept_type=None):
        """List parsed OKF concepts across the bundle or within one subfolder."""
        base = self.root_dir / subdir if subdir else self.root_dir
        if not base.exists():
            return []
        concepts = []
        for path in sorted(base.rglob("*.md")):
            if path.name == "index.md":
                continue
            item = self.read_concept(self._to_rel(path))
            if item and (not concept_type or item["frontmatter"].get("type") == concept_type):
                concepts.append(item)
        return concepts

    def search_concepts(self, query, limit=10, concept_type=None):
        """Keyword-score OKF concepts across title, description, tags, and body."""
        tokens = [t for t in re.findall(r"[a-z0-9_]+", (query or "").lower()) if len(t) > 1]
        if not tokens:
            return []
        scored = []
        for item in self.list_concepts(concept_type=concept_type):
            fm = item["frontmatter"]
            fields = (
                (str(fm.get("title", "")).lower(), 4),
                (" ".join(str(t).lower() for t in fm.get("tags", [])), 3),
                (str(fm.get("description", "")).lower(), 2),
                (item["body"].lower(), 1),
            )
            score = sum(w for text, w in fields for tok in tokens if tok in text)
            if score > 0:
                scored.append(dict(item, score=score))
        scored.sort(key=lambda x: (-x["score"], x["rel_path"]))
        return scored[: int(limit)]

    def refresh_index(self):
        """Regenerate knowledge/index.md linking every curated concept by folder."""
        concepts = self.list_concepts()
        grouped = {}
        for item in concepts:
            grouped.setdefault(str(Path(item["rel_path"]).parent), []).append(item)

        lines = ["# Steward Knowledge Index", "", f"Total curated concepts: {len(concepts)}", ""]
        for folder in sorted(grouped.keys()):
            lines.append(f"## {folder}")
            for item in grouped[folder]:
                fm = item["frontmatter"]
                desc = f" — {fm['description']}" if fm.get("description") else ""
                lines.append(f"- [{fm.get('title', item['rel_path'])}]({item['rel_path']}){desc}")
            lines.append("")

        fm = {
            "type": "index", "title": "Steward Knowledge Index",
            "description": "Entry point for Steward's OKF v0.3 knowledge graph.",
            "tags": ["index", "steward"], "x-steward-concept-count": len(concepts),
        }
        return self.write_concept("index.md", fm, "\n".join(lines))

    def _resolve_concept_path(self, rel_path):
        """Resolve a relative path safely inside root_dir."""
        target = (self.root_dir / str(rel_path)).resolve()
        if self.root_dir != target and self.root_dir not in target.parents:
            raise OKFValidationError(f"Path escapes OKF bundle root: {rel_path}")
        return target

    def _to_rel(self, path):
        """Return POSIX-style path relative to the OKF bundle root."""
        return Path(path).resolve().relative_to(self.root_dir).as_posix()

    @staticmethod
    def _parse_markdown(raw_text):
        """Split YAML frontmatter and Markdown body from a concept file."""
        if raw_text.startswith("---\n"):
            parts = raw_text.split("\n---\n", 1)
            if len(parts) == 2:
                return yaml.safe_load(parts[0][4:]) or {}, parts[1].strip()
        return {}, raw_text.strip()

    @staticmethod
    def slugify(text):
        """Turn an arbitrary name into a clean lowercase filename slug."""
        return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:64] or "concept"

    def _log_warning(self, message):
        """Log a warning message when a logger is attached."""
        if self.logger is not None:
            self.logger.warning(message)
