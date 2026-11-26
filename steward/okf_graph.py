"""NetworkX knowledge graph built by parsing Markdown links in an OKF bundle."""

import os
import re
from pathlib import Path

import networkx as nx


class OKFGraph:
    """Parses OKF concept links into a NetworkX DiGraph for neighbor and topic queries."""

    LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+\.md)\)")

    def __init__(self, bundle, logger=None):
        """Initialize the graph from an OKFBundle and load all existing concepts."""
        self.bundle = bundle
        self.logger = logger
        self.graph = nx.DiGraph()
        self.rebuild()

    def rebuild(self):
        """Clear and rebuild the full directed graph from all OKF concept files."""
        self.graph.clear()
        concepts = self.bundle.list_concepts()
        for concept in concepts:
            self._add_node_from_concept(concept)
        for concept in concepts:
            self._add_edges_from_concept(concept)
        self._log_info(
            f"OKFGraph built: {self.graph.number_of_nodes()} nodes, "
            f"{self.graph.number_of_edges()} edges."
        )
        return self.stats()

    def update_node(self, rel_path):
        """Refresh one concept node and its outgoing Markdown link edges."""
        normalized = self._normalize_rel(rel_path)
        concept = self.bundle.read_concept(normalized)
        if concept is None:
            if normalized in self.graph:
                self.graph.remove_node(normalized)
            return False

        if normalized in self.graph:
            for target in list(self.graph.successors(normalized)):
                self.graph.remove_edge(normalized, target)
        self._add_node_from_concept(concept)
        self._add_edges_from_concept(concept)
        return True

    def get_neighbors(self, rel_path, depth=1):
        """Return directly or transitively linked outgoing concepts up to depth hops."""
        start = self._normalize_rel(rel_path)
        if start not in self.graph:
            return []
        visited = set()
        frontier = {start}
        results = []
        for hop in range(1, max(1, int(depth)) + 1):
            next_frontier = set()
            for node in frontier:
                for neighbor in self.graph.successors(node):
                    if neighbor != start and neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.add(neighbor)
                        results.append(self._node_summary(neighbor, hop=hop))
            frontier = next_frontier
            if not frontier:
                break
        return results

    def get_incoming(self, rel_path):
        """Return concepts that link into the given concept."""
        target = self._normalize_rel(rel_path)
        if target not in self.graph:
            return []
        return [
            self._node_summary(src, hop=1)
            for src in sorted(self.graph.predecessors(target))
        ]

    def find_related(self, rel_path, limit=10):
        """Return related concepts across both outgoing and incoming edges."""
        start = self._normalize_rel(rel_path)
        if start not in self.graph:
            return []
        undirected = self.graph.to_undirected()
        distances = nx.single_source_shortest_path_length(undirected, start, cutoff=2)
        related = []
        for node, dist in sorted(distances.items(), key=lambda pair: (pair[1], pair[0])):
            if node == start:
                continue
            related.append(self._node_summary(node, hop=dist))
            if len(related) >= int(limit):
                break
        return related

    def find_by_type(self, concept_type):
        """Return all graph nodes matching a specific OKF 'type'."""
        return [
            self._node_summary(node)
            for node, attrs in sorted(self.graph.nodes(data=True))
            if attrs.get("type") == concept_type
        ]

    def find_by_tag(self, tag):
        """Return all graph nodes carrying the requested tag (case-insensitive)."""
        wanted = str(tag).strip().lower()
        return [
            self._node_summary(node)
            for node, attrs in sorted(self.graph.nodes(data=True))
            if wanted in {str(t).lower() for t in attrs.get("tags", [])}
        ]

    def stats(self):
        """Return node, edge, and concept-type counts for the OKF graph."""
        by_type = {}
        for _, attrs in self.graph.nodes(data=True):
            ctype = attrs.get("type", "unknown")
            by_type[ctype] = by_type.get(ctype, 0) + 1
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "by_type": by_type,
        }

    def _add_node_from_concept(self, concept):
        """Insert or update a node's metadata from a parsed OKF concept."""
        fm = concept["frontmatter"]
        self.graph.add_node(
            concept["rel_path"],
            type=fm.get("type", "unknown"),
            title=fm.get("title", concept["rel_path"]),
            description=fm.get("description", ""),
            tags=list(fm.get("tags") or []),
            timestamp=fm.get("timestamp", ""),
        )

    def _add_edges_from_concept(self, concept):
        """Parse Markdown links in the body and connect valid bundle targets."""
        source = concept["rel_path"]
        source_dir = (self.bundle.root_dir / source).parent
        for label, raw_target in self.LINK_PATTERN.findall(concept["body"]):
            if raw_target.startswith(("http://", "https://")):
                continue
            resolved = (source_dir / raw_target).resolve()
            if self.bundle.root_dir not in resolved.parents:
                continue
            target_rel = resolved.relative_to(self.bundle.root_dir).as_posix()
            if target_rel == source:
                continue
            if target_rel not in self.graph:
                self.graph.add_node(target_rel, type="unresolved", title=label, tags=[])
            self.graph.add_edge(source, target_rel, label=label)

    def _node_summary(self, node, hop=0):
        """Build a clean summary dict for a graph node."""
        attrs = self.graph.nodes[node]
        return {
            "rel_path": node,
            "type": attrs.get("type", "unknown"),
            "title": attrs.get("title", node),
            "description": attrs.get("description", ""),
            "tags": attrs.get("tags", []),
            "hop": hop,
        }

    @staticmethod
    def _normalize_rel(rel_path):
        """Normalize path separators for consistent graph node lookups."""
        return Path(str(rel_path)).as_posix().lstrip("./")

    @staticmethod
    def relative_link(from_rel, to_rel):
        """Compute a POSIX relative Markdown link from one concept to another."""
        start_dir = Path(from_rel).parent.as_posix() or "."
        return Path(os.path.relpath(to_rel, start=start_dir)).as_posix()

    def _log_info(self, message):
        """Write an informational log message when a logger is attached."""
        if self.logger is not None:
            self.logger.info(message)
