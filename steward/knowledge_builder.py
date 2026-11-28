"""Transforms SQLite scans, software inventory, and summaries into OKF concepts."""

import hashlib
import re
from pathlib import Path

from steward.okf_bundle import OKFValidationError
from steward.okf_graph import OKFGraph


class KnowledgeBuilder:
    """Builds linked OKF concepts for files, folders, projects, software, and topics."""

    STOP_WORDS = {
        "the", "and", "for", "with", "that", "this", "from", "have", "your",
        "into", "page", "sheet", "file", "image", "mode", "size", "format",
        "notes", "data", "steward", "local", "files", "about", "after",
    }

    def __init__(self, bundle, graph, reader=None, logger=None, summarizer=None):
        """Initialize with OKFBundle, OKFGraph, optional DocumentReader and summarizer."""
        self.bundle = bundle
        self.graph = graph
        self.reader = reader
        self.logger = logger
        self.summarizer = summarizer

    def build_from_database(self, db, limit=None):
        """Generate linked OKF concepts from SQLite files and software tables."""
        stats = {"files": 0, "folders": 0, "projects": 0, "software": 0, "topics": 0, "skipped": 0}
        sw_by_ext = self._build_software_concepts(db, stats)
        folder_files = {}

        for record in db.list_files(limit=limit):
            if record.get("is_temp") or record.get("status") == "unreadable":
                stats["skipped"] += 1
                continue
            if self.reader is not None and self.reader.is_sensitive(record["path"]):
                stats["skipped"] += 1
                continue
            file_rel = self._build_file_concept(record, sw_by_ext, stats)
            if file_rel is None:
                stats["skipped"] += 1
                continue
            folder_files.setdefault(record["folder"], []).append((record["name"], file_rel))

        self._build_folder_and_project_concepts(folder_files, stats)
        self.bundle.refresh_index()
        self.graph.rebuild()
        self._log_info(f"OKF knowledge build complete: {stats}")
        return stats

    def _build_software_concepts(self, db, stats):
        """Create software concepts and return an extension -> (name, rel_path) lookup."""
        ext_map = {}
        for app in db.list_software():
            rel_path = f"software/{self.bundle.slugify(app['name'])}.md"
            exts = app.get("extensions", [])
            fm = {
                "type": "software", "title": app["name"],
                "description": f"Installed app ({app.get('status', 'unknown')}) handling {len(exts)} file type(s).",
                "tags": ["software", app.get("status", "unknown")],
                "sources": [app.get("path", "")],
                "x-steward-version": app.get("version", ""),
                "x-steward-status": app.get("status", "unknown"),
                "x-steward-extensions": exts,
            }
            body = (
                f"# {app['name']}\n\n- Version: `{app.get('version') or 'unknown'}`\n"
                f"- Usage status: `{app.get('status', 'unknown')}`\n"
                f"- Supported extensions: {', '.join(exts) if exts else 'none recorded'}"
            )
            try:
                saved = self.bundle.write_concept(rel_path, fm, body)
                stats["software"] += 1
                for ext in exts:
                    ext_map.setdefault(ext.lower(), []).append((app["name"], saved))
            except OKFValidationError:
                stats["skipped"] += 1
        return ext_map

    def _build_file_concept(self, record, sw_by_ext, stats):
        """Distill a scanned file into a curated OKF concept with relative links."""
        path = Path(record["path"])
        short_id = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:8]
        rel_path = f"files/{self.bundle.slugify(path.stem)}-{short_id}.md"
        summary, topics = self._summarize_and_tag(record)

        folder_name = Path(record["folder"]).name
        slug = self.bundle.slugify(folder_name)
        folder_rel, project_rel = f"folders/{slug}.md", f"projects/{slug}.md"
        topic_links = [
            (t.title(), OKFGraph.relative_link(rel_path, self._ensure_topic_concept(t, stats)))
            for t in topics
        ]
        app_links = [
            (name, OKFGraph.relative_link(rel_path, sw_rel))
            for name, sw_rel in sw_by_ext.get((record.get("extension") or "").lower(), [])[:3]
        ]

        fm = {
            "type": "file", "title": path.name, "description": summary[:180],
            "tags": sorted(set([record.get("category", "other")] + topics)),
            "sources": [str(path)], "x-steward-path": str(path),
            "x-steward-sha256": record.get("sha256", ""),
            "x-steward-size-bytes": int(record.get("size_bytes", 0)),
            "x-steward-category": record.get("category", "other"),
            "x-steward-freshness": "fresh",
        }
        lines = [
            f"# {path.name}", "", summary, "",
            f"- Folder: [{folder_name}]({OKFGraph.relative_link(rel_path, folder_rel)})",
            f"- Project: [{folder_name}]({OKFGraph.relative_link(rel_path, project_rel)})",
        ]
        if app_links:
            lines.append("- Opened with: " + ", ".join(f"[{n}]({lnk})" for n, lnk in app_links))
        if topic_links:
            lines.append("- Topics: " + ", ".join(f"[{n}]({lnk})" for n, lnk in topic_links))

        try:
            saved = self.bundle.write_concept(rel_path, fm, "\n".join(lines))
            stats["files"] += 1
            return saved
        except OKFValidationError:
            return None

    def _build_folder_and_project_concepts(self, folder_files, stats):
        """Create linked folder and inferred project concepts for each scanned directory."""
        for folder_path, file_entries in sorted(folder_files.items()):
            name = Path(folder_path).name or "root"
            slug = self.bundle.slugify(name)
            folder_rel, project_rel = f"folders/{slug}.md", f"projects/{slug}.md"
            count = len(file_entries)

            f_links = [f"- [{n}]({OKFGraph.relative_link(folder_rel, f)})" for n, f in sorted(file_entries)[:25]]
            p_links = [f"- [{n}]({OKFGraph.relative_link(project_rel, f)})" for n, f in sorted(file_entries)[:25]]

            self.bundle.write_concept(
                folder_rel,
                {
                    "type": "folder", "title": name,
                    "description": f"Folder containing {count} tracked file(s).",
                    "tags": ["folder", slug], "sources": [folder_path],
                    "x-steward-path": folder_path, "x-steward-file-count": count,
                },
                f"# {name}\n\nAssociated project: [{name}]({OKFGraph.relative_link(folder_rel, project_rel)})\n\n## Files\n" + "\n".join(f_links),
            )
            self.bundle.write_concept(
                project_rel,
                {
                    "type": "project", "title": f"{name} Project",
                    "description": f"Inferred project grouping {count} related file(s) from {name}.",
                    "tags": ["project", slug], "sources": [folder_path], "x-steward-file-count": count,
                },
                f"# {name} Project\n\nPrimary folder: [{name}]({OKFGraph.relative_link(project_rel, folder_rel)})\n\n## Related Files\n" + "\n".join(p_links),
            )
            stats["folders"] += 1
            stats["projects"] += 1

    def _ensure_topic_concept(self, topic, stats):
        """Create a topic concept if it does not already exist in knowledge/topics/."""
        rel_path = f"topics/{self.bundle.slugify(topic)}.md"
        if self.bundle.read_concept(rel_path) is not None:
            return rel_path
        fm = {
            "type": "topic", "title": topic.title(),
            "description": f"Recurring subject extracted across user documents: {topic}.",
            "tags": ["topic", topic], "sources": ["knowledge_builder"],
        }
        saved = self.bundle.write_concept(rel_path, fm, f"# {topic.title()}\n\nDocuments referencing `{topic}`.")
        stats["topics"] += 1
        return saved

    def _summarize_and_tag(self, record):
        """Distill a short summary and up to 3 topics without copying raw file contents."""
        extracted = ""
        if self.reader is not None and self.reader.is_supported(record["path"]):
            doc = self.reader.read(record["path"])
            if not doc.error and not doc.skipped:
                extracted = doc.text

        if self.summarizer is not None and extracted:
            summary = str(self.summarizer(record["name"], extracted)).strip()
        elif extracted:
            summary = f"Distilled preview of {record['name']}: {' '.join(extracted.split())[:180]}"
        else:
            summary = f"{record.get('category', 'file').title()} file ({record.get('size_bytes', 0)} bytes)."

        words = re.findall(r"[a-z]{4,}", (record["name"] + " " + extracted[:1000]).lower())
        counts = {}
        for word in words:
            if word not in self.STOP_WORDS:
                counts[word] = counts.get(word, 0) + 1
        return summary, [w for w, _ in sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:3]]

    def _log_info(self, message):
        """Write an informational log message when a logger is attached."""
        if self.logger is not None:
            self.logger.info(message)
