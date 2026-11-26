"""Agno Toolkits for OKF knowledge graph operations and reporting."""

from datetime import datetime, timezone
from pathlib import Path

from agno.tools import Toolkit

from steward.okf_bundle import OKFValidationError
from steward.okf_graph import OKFGraph


class OKFTools(Toolkit):
    """Agno Toolkit for reading, writing, linking, and searching OKF v0.3 concepts."""

    def __init__(self, bundle, graph):
        """Register OKF bundle and NetworkX graph tool functions."""
        self.bundle = bundle
        self.graph = graph
        super().__init__(
            name="okf_tools",
            tools=[
                self.read_concept,
                self.write_concept,
                self.link_concepts,
                self.search_concepts,
                self.neighbors,
            ],
        )

    def read_concept(self, rel_path):
        """Read one curated OKF Markdown concept by its relative bundle path."""
        concept = self.bundle.read_concept(rel_path)
        if concept is None:
            return {"status": "not_found", "message": f"Concept not found: {rel_path}"}
        return {"status": "ok", "message": f"Loaded {rel_path}.", "concept": concept}

    def write_concept(self, rel_path, concept_type, title, description, body, tags=None, sources=None):
        """Validate and write a curated OKF concept, updating the NetworkX graph."""
        frontmatter = {
            "type": concept_type,
            "title": title,
            "description": description,
            "tags": list(tags or []),
            "sources": list(sources or []),
        }
        try:
            saved = self.bundle.write_concept(rel_path, frontmatter, body)
            self.graph.update_node(saved)
            return {"status": "ok", "message": f"Saved OKF concept {saved}.", "rel_path": saved}
        except OKFValidationError as exc:
            return {"status": "error", "message": str(exc)}

    def link_concepts(self, from_rel_path, to_rel_path, label=""):
        """Append a relative Markdown link from one OKF concept to another."""
        source = self.bundle.read_concept(from_rel_path)
        target = self.bundle.read_concept(to_rel_path)
        if source is None or target is None:
            return {"status": "not_found", "message": "Source or target concept does not exist."}
        rel_link = OKFGraph.relative_link(from_rel_path, to_rel_path)
        link_title = label or target["frontmatter"].get("title", to_rel_path)
        link_line = f"- Related: [{link_title}]({rel_link})"
        new_body = source["body"] if rel_link in source["body"] else f"{source['body']}\n{link_line}"
        self.bundle.update_concept(from_rel_path, body=new_body)
        self.graph.update_node(from_rel_path)
        return {"status": "ok", "message": f"Linked {from_rel_path} -> {to_rel_path}."}

    def search_concepts(self, query, limit=5, concept_type=None):
        """Search curated OKF concepts before falling back to raw RAG passages."""
        hits = self.bundle.search_concepts(query, limit=limit, concept_type=concept_type)
        compact = [
            {
                "rel_path": h["rel_path"],
                "type": h["frontmatter"].get("type"),
                "title": h["frontmatter"].get("title"),
                "description": h["frontmatter"].get("description", ""),
                "sources": h["frontmatter"].get("sources", []),
                "score": h.get("score", 0),
            }
            for h in hits
        ]
        return {
            "status": "ok",
            "message": f"Found {len(compact)} OKF concept(s) matching '{query}'.",
            "results": compact,
        }

    def neighbors(self, rel_path, depth=1):
        """Return linked neighboring concepts from the OKF NetworkX graph."""
        related = self.graph.get_neighbors(rel_path, depth=depth)
        return {
            "status": "ok",
            "message": f"Found {len(related)} neighbor(s) for {rel_path}.",
            "neighbors": related,
        }


class ReportTools(Toolkit):
    """Agno Toolkit for collecting system statistics and rendering Markdown reports."""

    def __init__(self, config, db, scanner, graph):
        """Register statistics aggregation and report rendering tools."""
        self.config = config
        self.db = db
        self.scanner = scanner
        self.graph = graph
        super().__init__(
            name="report_tools",
            tools=[self.collect_stats, self.render_report],
        )

    def collect_stats(self):
        """Collect disk usage, category counts, software stats, and cleanup findings."""
        files = self.db.list_files()
        by_category = {}
        total_bytes = 0
        for item in files:
            size = int(item.get("size_bytes", 0))
            total_bytes += size
            cat = item.get("category") or "other"
            by_category[cat] = by_category.get(cat, 0) + 1

        findings = self.scanner.get_cleanup_findings()
        apps = self.db.list_software()
        stats = {
            "total_files": len(files),
            "total_size_mb": round(total_bytes / (1024 * 1024), 2),
            "by_category": by_category,
            "duplicate_groups": len(findings["duplicates"]),
            "large_files": len(findings["large_files"]),
            "stale_files": len(findings["stale_files"]),
            "temp_files": len(findings["temp_files"]),
            "installed_apps": len(apps),
            "okf_graph": self.graph.stats(),
        }
        return {"status": "ok", "message": "Collected system statistics.", "stats": stats}

    def render_report(self, period="weekly", title="Steward Activity Report"):
        """Render a Markdown report to reports/ and log it in SQLite."""
        stats = self.collect_stats()["stats"]
        now = datetime.now(timezone.utc)
        stamp = now.strftime("%Y%m%d-%H%M%S")
        reports_dir = self.config.get_path("reports_dir")
        reports_dir.mkdir(parents=True, exist_ok=True)
        out_path = Path(reports_dir) / f"steward_{period}_{stamp}.md"

        lines = [
            f"# {title} ({period})",
            "",
            f"- Generated: `{now.isoformat()}`",
            f"- Tracked files: **{stats['total_files']}** ({stats['total_size_mb']} MB)",
            f"- Installed apps: **{stats['installed_apps']}**",
            f"- OKF knowledge graph: **{stats['okf_graph']['nodes']} nodes, {stats['okf_graph']['edges']} edges**",
            "",
            "## Cleanup Summary",
            f"- Duplicate groups: {stats['duplicate_groups']}",
            f"- Large files: {stats['large_files']}",
            f"- Stale files: {stats['stale_files']}",
            f"- Temporary files: {stats['temp_files']}",
            "",
            "## File Categories",
        ]
        for cat, count in sorted(stats["by_category"].items()):
            lines.append(f"- `{cat}`: {count}")

        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.db.record_report(period, str(out_path))
        return {
            "status": "ok",
            "message": f"Saved {period} report to {out_path.name}.",
            "report_path": str(out_path),
            "stats": stats,
        }
