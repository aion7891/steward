"""Long-term OKF memory manager for preferences, learned patterns, and decisions."""

from datetime import datetime, timedelta, timezone


class MemoryManager:
    """Decides what becomes long-term OKF memory, updates entries, and expires stale items."""

    MEMORY_FOLDERS = {
        "preference": "memory/preferences",
        "pattern": "memory/patterns",
        "decision": "memory/decisions",
    }
    DEFAULT_TTL_DAYS = {
        "preference": 365,
        "pattern": 60,
        "decision": 180,
    }

    def __init__(self, bundle, graph=None, logger=None):
        """Initialize memory manager with an OKFBundle and optional OKFGraph."""
        self.bundle = bundle
        self.graph = graph
        self.logger = logger

    def should_remember(self, text, min_length=6):
        """Return True if a candidate memory statement is meaningful and non-trivial."""
        cleaned = (text or "").strip()
        if len(cleaned) < min_length:
            return False
        trivial = {"ok", "yes", "no", "thanks", "thank you", "done", "hi", "hello"}
        return cleaned.lower() not in trivial

    def record_preference(self, key, rule_text, sources=None, tags=None, ttl_days=None):
        """Store or update a user preference under knowledge/memory/preferences/."""
        if not self.should_remember(rule_text):
            return None
        slug = self.bundle.slugify(key)
        rel_path = f"{self.MEMORY_FOLDERS['preference']}/{slug}.md"
        ttl = int(ttl_days or self.DEFAULT_TTL_DAYS["preference"])
        now = datetime.now(timezone.utc)
        frontmatter = {
            "type": "preference",
            "title": key.strip(),
            "description": rule_text.strip()[:160],
            "tags": sorted(set(["preference"] + list(tags or []))),
            "timestamp": now.isoformat(),
            "sources": list(sources or ["user"]),
            "x-steward-confidence": 1.0,
            "x-steward-freshness": "fresh",
            "x-steward-ttl-days": ttl,
            "x-steward-expires-at": (now + timedelta(days=ttl)).isoformat(),
        }
        body = f"# {key.strip()}\n\nUser preference: {rule_text.strip()}"
        return self._write_and_sync(rel_path, frontmatter, body)

    def record_pattern(self, name, description, evidence=None, confidence=0.7, tags=None, ttl_days=None):
        """Store or reinforce a learned work pattern under knowledge/memory/patterns/."""
        if not self.should_remember(description):
            return None
        slug = self.bundle.slugify(name)
        rel_path = f"{self.MEMORY_FOLDERS['pattern']}/{slug}.md"
        existing = self.bundle.read_concept(rel_path)
        seen_count = 1
        if existing is not None:
            seen_count = int(existing["frontmatter"].get("x-steward-observations", 1)) + 1

        ttl = int(ttl_days or self.DEFAULT_TTL_DAYS["pattern"])
        now = datetime.now(timezone.utc)
        frontmatter = {
            "type": "pattern",
            "title": name.strip(),
            "description": description.strip()[:160],
            "tags": sorted(set(["pattern"] + list(tags or []))),
            "timestamp": now.isoformat(),
            "sources": list(evidence or ["activity_history"]),
            "x-steward-confidence": round(min(1.0, float(confidence)), 2),
            "x-steward-observations": seen_count,
            "x-steward-freshness": "fresh",
            "x-steward-ttl-days": ttl,
            "x-steward-expires-at": (now + timedelta(days=ttl)).isoformat(),
        }
        body = (
            f"# {name.strip()}\n\n{description.strip()}\n\n"
            f"- Observations: {seen_count}\n"
            f"- Confidence: {frontmatter['x-steward-confidence']}"
        )
        return self._write_and_sync(rel_path, frontmatter, body)

    def record_decision(self, action_type, target_path, reason, outcome="proposed", linked_concepts=None):
        """Log an organize, archive, or delete decision under knowledge/memory/decisions/."""
        now = datetime.now(timezone.utc)
        stamp = now.strftime("%Y%m%d-%H%M%S")
        slug = self.bundle.slugify(f"{stamp}-{action_type}-{target_path.split('/')[-1]}")
        rel_path = f"{self.MEMORY_FOLDERS['decision']}/{slug}.md"
        ttl = self.DEFAULT_TTL_DAYS["decision"]

        frontmatter = {
            "type": "decision",
            "title": f"{action_type.title()}: {target_path.split('/')[-1]}",
            "description": reason.strip()[:160],
            "tags": ["decision", action_type.lower(), outcome.lower()],
            "timestamp": now.isoformat(),
            "sources": [str(target_path)],
            "x-steward-action": action_type.lower(),
            "x-steward-outcome": outcome.lower(),
            "x-steward-freshness": "fresh",
            "x-steward-ttl-days": ttl,
            "x-steward-expires-at": (now + timedelta(days=ttl)).isoformat(),
        }
        lines = [
            f"# {frontmatter['title']}",
            "",
            f"- Action: `{action_type}`",
            f"- Target: `{target_path}`",
            f"- Outcome: `{outcome}`",
            f"- Reason: {reason.strip()}",
        ]
        if linked_concepts:
            lines.append("")
            lines.append("## Related Concepts")
            for label, link in linked_concepts:
                lines.append(f"- [{label}]({link})")
        return self._write_and_sync(rel_path, frontmatter, "\n".join(lines))

    def list_memories(self, kind=None):
        """Return memory concepts across all memory subfolders or one specific kind."""
        if kind in self.MEMORY_FOLDERS:
            return self.bundle.list_concepts(subdir=self.MEMORY_FOLDERS[kind])
        return self.bundle.list_concepts(subdir="memory")

    def find_stale_memories(self, now=None):
        """Return memory concepts whose x-steward-expires-at timestamp has passed."""
        ref_time = now or datetime.now(timezone.utc)
        stale = []
        for item in self.list_memories():
            expires_raw = item["frontmatter"].get("x-steward-expires-at")
            if not expires_raw:
                continue
            try:
                expires_at = datetime.fromisoformat(str(expires_raw))
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if expires_at <= ref_time:
                    stale.append(item)
            except ValueError:
                continue
        return stale

    def expire_stale_memories(self, now=None, delete=False):
        """Mark stale memories as expired (or remove them if delete=True)."""
        stale = self.find_stale_memories(now=now)
        affected = []
        for item in stale:
            rel_path = item["rel_path"]
            if delete:
                self.bundle.delete_concept(rel_path)
            else:
                self.bundle.update_concept(rel_path, {"x-steward-freshness": "stale"})
            if self.graph is not None:
                self.graph.update_node(rel_path)
            affected.append(rel_path)
        self._log_info(f"Processed {len(affected)} stale memory entries (delete={delete}).")
        return affected

    def _write_and_sync(self, rel_path, frontmatter, body):
        """Write a memory concept, refresh graph node, and return its rel_path."""
        saved = self.bundle.write_concept(rel_path, frontmatter, body)
        if self.graph is not None:
            self.graph.update_node(saved)
        return saved

    def _log_info(self, message):
        """Write an informational log message when a logger is attached."""
        if self.logger is not None:
            self.logger.info(message)
