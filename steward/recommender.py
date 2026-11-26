"""Work-pattern mining and proactive cleanup/organization recommendation engine."""

from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path


class PatternMiner:
    """Mines SQLite file, activity, and software history for recurring work habits."""

    WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

    def __init__(self, config, db, memory_manager=None, logger=None):
        """Initialize PatternMiner with config, SQLite DB, and optional OKF MemoryManager."""
        self.config = config
        self.db = db
        self.memory_manager = memory_manager
        self.logger = logger

    def mine_patterns(self, persist_to_okf=True):
        """Discover work patterns and optionally persist them to knowledge/memory/patterns/."""
        files = self.db.list_files()
        events = self.db.list_activity_events(limit=200)
        apps = self.db.list_software()

        patterns = []
        patterns.extend(self._mine_weekday_activity(files, events))
        patterns.extend(self._mine_category_focus(files))
        patterns.extend(self._mine_untouched_folders(files))
        patterns.extend(self._mine_rare_software(apps))

        if persist_to_okf and self.memory_manager is not None:
            for item in patterns:
                rel = self.memory_manager.record_pattern(
                    name=item["name"],
                    description=item["description"],
                    evidence=item.get("evidence", ["sqlite_activity"]),
                    confidence=item.get("confidence", 0.7),
                    tags=item.get("tags", []),
                )
                item["okf_path"] = rel
        return patterns

    def _mine_weekday_activity(self, files, events):
        """Identify the user's busiest weekday across file modifications and downloads."""
        day_counts = Counter()
        for ev in events:
            day = self._parse_weekday(ev.get("timestamp"))
            if day:
                day_counts[day] += 1
        for item in files:
            day = self._parse_weekday(item.get("modified_at"))
            if day:
                day_counts[day] += 1
        if not day_counts:
            return []
        top_day, count = day_counts.most_common(1)[0]
        if count < 2:
            return []
        return [{
            "name": f"Peak Activity on {top_day}",
            "description": f"Highest file and download activity occurs on {top_day} ({count} recorded touchpoints).",
            "confidence": min(0.95, 0.55 + count * 0.05),
            "tags": ["schedule", top_day.lower()],
            "evidence": ["files", "activity_events"],
        }]

    def _mine_category_focus(self, files):
        """Identify the dominant file category the user works with most."""
        counts = Counter(f.get("category") or "other" for f in files if not f.get("is_temp"))
        if not counts:
            return []
        top_cat, count = counts.most_common(1)[0]
        share = round((count / max(1, sum(counts.values()))) * 100)
        return [{
            "name": f"Primary Work Category: {top_cat.title()}",
            "description": f"{top_cat.title()} files make up {share}% of tracked work ({count} files).",
            "confidence": 0.8,
            "tags": ["category", top_cat],
            "evidence": ["files"],
        }]

    def _mine_untouched_folders(self, files):
        """Detect folders where all tracked files have gone untouched past stale_days."""
        stale_days = int(self.config.get("scanner.stale_days", 90))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=stale_days)).isoformat()
        by_folder = {}
        for item in files:
            by_folder.setdefault(item["folder"], []).append(item)

        found = []
        for folder, items in sorted(by_folder.items()):
            latest = max((i.get("modified_at") or "" for i in items), default="")
            if latest and latest <= cutoff:
                name = Path(folder).name or folder
                found.append({
                    "name": f"Inactive Folder: {name}",
                    "description": f"Folder '{name}' ({len(items)} files) has had no changes for over {stale_days} days.",
                    "confidence": 0.85,
                    "tags": ["stale", "archive-candidate"],
                    "evidence": [folder],
                })
        return found[:5]

    def _mine_rare_software(self, apps):
        """Spot clusters of rarely used installed applications."""
        rare = [a["name"] for a in apps if a.get("status") == "rarely_used"]
        if not rare:
            return []
        sample = ", ".join(rare[:5])
        return [{
            "name": "Rarely Used Applications",
            "description": f"{len(rare)} installed app(s) appear rarely used (e.g. {sample}).",
            "confidence": 0.7,
            "tags": ["software", "cleanup"],
            "evidence": ["software"],
        }]

    def _parse_weekday(self, iso_str):
        """Return the English weekday name for an ISO-8601 timestamp string."""
        if not iso_str:
            return None
        try:
            return self.WEEKDAYS[datetime.fromisoformat(str(iso_str)).weekday()]
        except ValueError:
            return None


class RecommenderEngine:
    """Produces prioritized, actionable cleanup and organization suggestions."""

    def __init__(self, config, db, scanner, memory_manager=None, logger=None):
        """Initialize RecommenderEngine with scanner findings and PatternMiner."""
        self.config = config
        self.db = db
        self.scanner = scanner
        self.logger = logger
        self.miner = PatternMiner(config, db, memory_manager=memory_manager, logger=logger)

    def generate_recommendations(self, persist_patterns=True):
        """Mine work patterns and produce prioritized cleanup/grouping suggestions."""
        patterns = self.miner.mine_patterns(persist_to_okf=persist_patterns)
        findings = self.scanner.get_cleanup_findings()
        suggestions = []

        # 1. Duplicate cleanup savings
        dup_bytes = sum(
            sum(int(f["size_bytes"]) for f in group["files"][1:])
            for group in findings["duplicates"]
        )
        if findings["duplicates"]:
            extra_paths = [f["path"] for g in findings["duplicates"] for f in g["files"][1:]]
            suggestions.append(self._make_suggestion(
                "high", "deduplicate",
                f"Remove {len(extra_paths)} duplicate file copy(ies)",
                f"Found {len(findings['duplicates'])} duplicate group(s); recycling extras preserves the oldest copy.",
                dup_bytes, extra_paths[:15],
            ))

        # 2. Temporary files cleanup
        if findings["temp_files"]:
            temp_bytes = sum(int(f["size_bytes"]) for f in findings["temp_files"])
            suggestions.append(self._make_suggestion(
                "high", "clean_temp",
                f"Recycle {len(findings['temp_files'])} temporary file(s)",
                "Temporary or partial files can safely be moved to the recycle bin.",
                temp_bytes, [f["path"] for f in findings["temp_files"][:15]],
            ))

        # 3. Stale files archiving
        if findings["stale_files"]:
            stale_bytes = sum(int(f["size_bytes"]) for f in findings["stale_files"])
            suggestions.append(self._make_suggestion(
                "medium", "archive_stale",
                f"Archive {len(findings['stale_files'])} stale file(s)",
                f"Files untouched for over {self.config.get('scanner.stale_days', 90)} days can be ZIP-archived.",
                stale_bytes, [f["path"] for f in findings["stale_files"][:15]],
            ))

        # 4. Large files review
        if findings["large_files"]:
            large_bytes = sum(int(f["size_bytes"]) for f in findings["large_files"])
            suggestions.append(self._make_suggestion(
                "medium", "review_large",
                f"Review {len(findings['large_files'])} large file(s)",
                f"Files >= {self.config.get('scanner.large_file_mb', 100)} MB dominate disk usage.",
                large_bytes, [f["path"] for f in findings["large_files"][:10]],
            ))

        # 5. Cluttered folders with mixed file types
        folder_cats = {}
        for item in self.db.list_files():
            if not item.get("is_temp"):
                folder_cats.setdefault(item["folder"], set()).add(item.get("category") or "other")
        for folder, cats in sorted(folder_cats.items()):
            if len(cats) >= 3:
                suggestions.append(self._make_suggestion(
                    "low", "group_folder",
                    f"Organize mixed files in '{Path(folder).name}'",
                    f"Contains {len(cats)} different categories ({', '.join(sorted(cats))}); consider organizing by type.",
                    0, [folder],
                ))

        total_mb = round(sum(s["reclaimable_mb"] for s in suggestions), 2)
        return {"patterns": patterns, "suggestions": suggestions, "total_reclaimable_mb": total_mb}

    @staticmethod
    def _make_suggestion(priority, kind, title, reason, size_bytes, paths):
        """Create a standardized recommendation dictionary."""
        return {
            "priority": priority, "kind": kind, "title": title, "reason": reason,
            "reclaimable_mb": round(size_bytes / (1024 * 1024), 2), "paths": paths,
        }
