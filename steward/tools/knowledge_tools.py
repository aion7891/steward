"""Agno Toolkits for OKF knowledge graph operations, recommendations, and reporting."""

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
            "type": concept_type, "title": title, "description": description,
            "tags": list(tags or []), "sources": list(sources or []),
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
                "rel_path": h["rel_path"], "type": h["frontmatter"].get("type"),
                "title": h["frontmatter"].get("title"),
                "description": h["frontmatter"].get("description", ""),
                "sources": h["frontmatter"].get("sources", []), "score": h.get("score", 0),
            }
            for h in hits
        ]
        return {"status": "ok", "message": f"Found {len(compact)} OKF concept(s) matching '{query}'.", "results": compact}

    def neighbors(self, rel_path, depth=1):
        """Return linked neighboring concepts from the OKF NetworkX graph."""
        related = self.graph.get_neighbors(rel_path, depth=depth)
        return {"status": "ok", "message": f"Found {len(related)} neighbor(s) for {rel_path}.", "neighbors": related}


class ReportTools(Toolkit):
    """Agno Toolkit for recommendations, system stats, and Markdown/HTML Jinja2 reports."""

    def __init__(self, config, db, scanner, graph, recommender=None, reporter=None):
        """Register recommendation and reporting tool functions."""
        self.config = config
        self.db = db
        self.scanner = scanner
        self.graph = graph
        if recommender is None:
            from steward.recommender import RecommenderEngine
            recommender = RecommenderEngine(config, db, scanner)
        if reporter is None:
            from steward.reporter import ReportGenerator
            reporter = ReportGenerator(config, db, scanner, graph, recommender)
        self.recommender = recommender
        self.reporter = reporter
        super().__init__(
            name="report_tools",
            tools=[self.collect_stats, self.get_recommendations, self.render_report],
        )

    def collect_stats(self):
        """Collect disk usage, category counts, activity timeline, software, and suggestions."""
        data = self.reporter.collect_report_data(period="snapshot", persist_patterns=False)
        return {"status": "ok", "message": "Collected system statistics.", "stats": data}

    def get_recommendations(self, persist_patterns=True):
        """Mine work patterns into OKF and return prioritized cleanup/grouping suggestions."""
        rec = self.recommender.generate_recommendations(persist_patterns=persist_patterns)
        return {
            "status": "ok",
            "message": f"Generated {len(rec['suggestions'])} suggestion(s) ({rec['total_reclaimable_mb']} MB reclaimable).",
            "patterns": rec["patterns"],
            "suggestions": rec["suggestions"],
            "total_reclaimable_mb": rec["total_reclaimable_mb"],
        }

    def render_report(self, period="weekly", output_format="markdown", title="Steward Activity Report"):
        """Render a Markdown, HTML, or dual report to reports/ and log it in SQLite."""
        return self.reporter.generate_report(
            period=period, output_format=output_format, title=title, save_okf=False
        )
