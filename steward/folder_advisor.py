"""Cleanup findings, suggestions and proposals for one folder (or the whole machine)."""

from pathlib import Path

from steward.proposals import ProposalService
from steward.recommender import RecommenderEngine

MB = 1024 * 1024


class FolderAdvisor:
    """Turns scanner findings into a clear "what needs to be done" list.

    Pass folder=None to any method to get advice for every tracked file.
    Files that no longer exist on disk are ignored, so deleted files never
    show up as cleanup candidates.
    """

    ITEM_LIMIT = 50

    def __init__(self, app, proposals=None):
        """Store the StewardApp services this advisor reads from.

        Args:
            app: StewardApp with scanner, db, config and organizer.
            proposals: optional ProposalService (built from app when omitted).
        """
        self.app = app
        self.proposals = proposals or ProposalService(app.config, app.db, app.organizer)

    def findings_for(self, folder=None):
        """Return duplicates, temp, stale and large files that live inside folder.

        Args:
            folder: Path of the folder, or None for everything.
        """
        raw = self.app.scanner.get_cleanup_findings()
        keep = lambda record: self._is_inside(record["path"], folder) and Path(record["path"]).exists()
        groups = []
        for group in raw["duplicates"]:
            copies = [f for f in group["files"] if Path(f["path"]).exists()]
            # The oldest copy is kept; every later copy inside the folder is an "extra"
            extras = [f for f in copies[1:] if self._is_inside(f["path"], folder)]
            if len(copies) > 1 and any(self._is_inside(f["path"], folder) for f in copies):
                groups.append({"sha256": group["sha256"], "copies": copies, "extras": extras})
        return {
            "duplicates": groups,
            "temp_files": [f for f in raw["temp_files"] if keep(f)],
            "stale_files": [f for f in raw["stale_files"] if keep(f)],
            "large_files": [f for f in raw["large_files"] if keep(f)],
        }

    def summarize(self, findings):
        """Return small, UI-friendly counts and example items for each finding type.

        Args:
            findings: the dict returned by findings_for().
        """
        extras = [f for g in findings["duplicates"] for f in g["extras"]]
        return {
            "duplicates": {
                "count": len(findings["duplicates"]),
                "extra_copies": len(extras),
                "total_mb": self._mb(extras),
                "total_bytes": self._bytes(extras),
                "items": [
                    {"sha256": g["sha256"], "copies": [self._compact(f) for f in g["copies"]]}
                    for g in findings["duplicates"][: self.ITEM_LIMIT]
                ],
            },
            "temp_files": self._section(findings["temp_files"]),
            "stale_files": self._section(findings["stale_files"]),
            "large_files": self._section(findings["large_files"]),
        }

    def suggestions_for(self, folder, findings):
        """Return prioritised suggestions plus the space that could really be freed.

        Args:
            folder: Path of the folder, or None for everything.
            findings: the dict returned by findings_for().
        """
        make = RecommenderEngine._make_suggestion
        extras = [f for g in findings["duplicates"] for f in g["extras"]]
        temp, stale, large = findings["temp_files"], findings["stale_files"], findings["large_files"]
        stale_days = self.app.config.get("scanner.stale_days", 90)
        large_mb = self.app.config.get("scanner.large_file_mb", 100)
        suggestions = []
        if extras:
            suggestions.append(make("high", "deduplicate", f"Remove {len(extras)} duplicate copy(ies)",
                                    "Identical copies exist; the oldest copy is kept.",
                                    self._bytes(extras), [f["path"] for f in extras[:15]]))
        if temp:
            suggestions.append(make("high", "clean_temp", f"Recycle {len(temp)} temporary file(s)",
                                    "Temporary or half-downloaded files are safe to recycle.",
                                    self._bytes(temp), [f["path"] for f in temp[:15]]))
        if stale:
            suggestions.append(make("medium", "archive_stale", f"Archive {len(stale)} old file(s)",
                                    f"Not changed for more than {stale_days} days; a ZIP archive saves space.",
                                    self._bytes(stale), [f["path"] for f in stale[:15]]))
        if large:
            # Big files are not automatically wasted space, so they free 0 MB here
            suggestions.append(make("medium", "review_large", f"Review {len(large)} large file(s)",
                                    f"Each is at least {large_mb} MB ({self._mb(large)} MB in total).",
                                    0, [f["path"] for f in large[:10]]))
        suggestions.extend(self._mixed_folder_suggestions(folder))
        freeable = extras + temp + stale
        return {"suggestions": suggestions, "reclaimable_mb": self._mb(freeable),
                "reclaimable_bytes": self._bytes(freeable)}

    def create_proposals(self, findings):
        """Create 'proposed' recycle actions for temp files and extra duplicate copies.

        Args:
            findings: the dict returned by findings_for().
        """
        items = [
            {"action_type": "delete", "source_path": f["path"], "reason": "Temporary file candidate"}
            for f in findings["temp_files"]
        ]
        for group in findings["duplicates"]:
            for extra in group["extras"]:
                original = group["copies"][0]["path"]
                items.append({"action_type": "delete", "source_path": extra["path"],
                              "reason": f"Duplicate of {original}"})
        return self.proposals.propose_many(items)

    def _mixed_folder_suggestions(self, folder, limit=5):
        """Suggest organising folders that mix three or more file categories."""
        by_folder = {}
        for record in self.app.db.list_files():
            if record.get("is_temp") or not self._is_inside(record["path"], folder):
                continue
            by_folder.setdefault(record["folder"], set()).add(record.get("category") or "other")
        mixed = sorted((f for f, cats in by_folder.items() if len(cats) >= 3), key=lambda f: -len(by_folder[f]))
        make = RecommenderEngine._make_suggestion
        return [
            make("low", "group_folder", f"Organize mixed files in '{Path(f).name}'",
                 f"Contains {len(by_folder[f])} kinds of files ({', '.join(sorted(by_folder[f]))}).", 0, [f])
            for f in mixed[:limit]
        ]

    def _section(self, records):
        """Return count, total MB and compact example items for one finding list."""
        return {"count": len(records), "total_mb": self._mb(records), "total_bytes": self._bytes(records),
                "items": [self._compact(r) for r in records[: self.ITEM_LIMIT]]}

    @staticmethod
    def _compact(record):
        """Keep only the fields the UI needs from a files-table row."""
        size = int(record.get("size_bytes") or 0)
        return {"path": record["path"], "name": record["name"], "category": record.get("category"),
                "size_bytes": size, "size_mb": round(size / MB, 2),
                "modified_at": record.get("modified_at")}

    @staticmethod
    def _bytes(records):
        """Sum file sizes, counting each path only once."""
        return sum({r["path"]: int(r.get("size_bytes") or 0) for r in records}.values())

    def _mb(self, records):
        """Sum file sizes in MB, counting each path only once."""
        return round(self._bytes(records) / MB, 2)

    @staticmethod
    def _is_inside(path, folder):
        """Return True if path is the folder itself or anywhere below it."""
        if folder is None:
            return True
        candidate, root = Path(path), Path(folder)
        return candidate == root or root in candidate.parents
