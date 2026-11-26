"""Recycle bin and compressed ZIP archive manager with full undo support."""

import json
import shutil
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


class RecycleManager:
    """Manages recoverable recycle-bin deletes and manifest-backed ZIP archives."""

    MANIFEST_NAME = "steward_manifest.json"

    def __init__(self, recycle_dir, archive_dir, logger=None):
        """Initialize recycle and archive storage directories."""
        self.recycle_dir = Path(recycle_dir).expanduser().resolve()
        self.archive_dir = Path(archive_dir).expanduser().resolve()
        self.logger = logger
        self.recycle_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def move_to_recycle(self, file_path):
        """Move a file into recycle_dir and write a sidecar metadata file for undo."""
        src = Path(file_path).expanduser().resolve()
        if not src.exists() or not src.is_file():
            raise FileNotFoundError(f"Cannot recycle missing file: {src}")

        self.recycle_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        dest = self.collision_safe_path(self.recycle_dir / f"{stamp}_{src.name}")
        shutil.move(str(src), str(dest))

        meta = {
            "original_path": str(src),
            "recycled_path": str(dest),
            "recycled_at": datetime.now(timezone.utc).isoformat(),
            "size_bytes": dest.stat().st_size,
        }
        self._meta_path(dest).write_text(json.dumps(meta, indent=2), encoding="utf-8")
        self._log_info(f"Recycled {src.name} -> {dest.name}")
        return meta

    def restore_from_recycle(self, recycled_path, original_path=None):
        """Restore a recycled file back to its original path (collision-safe)."""
        recycled = Path(recycled_path).expanduser().resolve()
        if not recycled.exists():
            raise FileNotFoundError(f"Recycled file not found: {recycled}")

        meta_file = self._meta_path(recycled)
        target_raw = original_path
        if not target_raw and meta_file.exists():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            target_raw = meta.get("original_path")
        if not target_raw:
            raise ValueError("Original path unknown; cannot restore recycled file.")

        dest = self.collision_safe_path(Path(target_raw).expanduser().resolve())
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(recycled), str(dest))
        if meta_file.exists():
            meta_file.unlink()
        self._log_info(f"Restored {recycled.name} -> {dest}")
        return str(dest)

    def list_recycled(self):
        """List all items currently in the recycle bin with metadata and age in days."""
        if not self.recycle_dir.exists():
            return []
        now = datetime.now(timezone.utc)
        items = []
        for meta_file in sorted(self.recycle_dir.glob("*.meta.json")):
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                recycled_at = datetime.fromisoformat(meta["recycled_at"])
                if recycled_at.tzinfo is None:
                    recycled_at = recycled_at.replace(tzinfo=timezone.utc)
                meta["age_days"] = max(0, (now - recycled_at).days)
                meta["exists"] = Path(meta["recycled_path"]).exists()
                items.append(meta)
            except (OSError, KeyError, ValueError, json.JSONDecodeError):
                continue
        return items

    def purge_expired(self, older_than_days=30, confirmed=False, now=None):
        """Permanently delete recycled files older than retention days ONLY if confirmed."""
        ref_now = now or datetime.now(timezone.utc)
        cutoff = ref_now - timedelta(days=int(older_than_days))
        candidates = []
        for item in self.list_recycled():
            recycled_at = datetime.fromisoformat(item["recycled_at"])
            if recycled_at.tzinfo is None:
                recycled_at = recycled_at.replace(tzinfo=timezone.utc)
            if recycled_at <= cutoff:
                candidates.append(item)

        if not confirmed:
            return {
                "status": "confirmation_required",
                "message": f"{len(candidates)} recycled file(s) eligible for purge. Pass confirmed=True to delete permanently.",
                "candidates": candidates,
            }

        purged = []
        for item in candidates:
            recycled = Path(item["recycled_path"])
            meta_file = self._meta_path(recycled)
            if recycled.exists():
                recycled.unlink()
            if meta_file.exists():
                meta_file.unlink()
            purged.append(item["original_path"])
        self._log_info(f"Permanently purged {len(purged)} expired recycle-bin file(s).")
        return {"status": "ok", "purged_count": len(purged), "purged": purged}

    def create_zip_archive(self, file_paths, archive_name="archive"):
        """Compress files into a verified ZIP with a manifest, then remove originals."""
        resolved_files = [Path(p).expanduser().resolve() for p in file_paths if Path(p).exists()]
        if not resolved_files:
            raise FileNotFoundError("No existing files provided to archive.")

        self.archive_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in archive_name)
        zip_path = self.collision_safe_path(self.archive_dir / f"{safe_name}_{stamp}.zip")

        manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "entries": []}
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for idx, src in enumerate(resolved_files):
                arcname = f"{idx:03d}_{src.name}"
                zf.write(src, arcname=arcname)
                manifest["entries"].append({"arcname": arcname, "original_path": str(src)})
            zf.writestr(self.MANIFEST_NAME, json.dumps(manifest, indent=2))

        with zipfile.ZipFile(zip_path, "r") as zf:
            bad = zf.testzip()
            if bad is not None:
                zip_path.unlink(missing_ok=True)
                raise OSError(f"Archive verification failed on member: {bad}")

        for src in resolved_files:
            src.unlink()
        self._log_info(f"Created ZIP archive {zip_path.name} with {len(resolved_files)} file(s).")
        return {"archive_path": str(zip_path), "file_count": len(resolved_files), "entries": manifest["entries"]}

    def restore_zip_archive(self, zip_path):
        """Extract all files in a Steward ZIP archive back to their original paths."""
        archive = Path(zip_path).expanduser().resolve()
        if not archive.exists():
            raise FileNotFoundError(f"ZIP archive not found: {archive}")
        restored = []
        with zipfile.ZipFile(archive, "r") as zf:
            manifest = json.loads(zf.read(self.MANIFEST_NAME).decode("utf-8"))
            for entry in manifest.get("entries", []):
                dest = self.collision_safe_path(Path(entry["original_path"]).expanduser().resolve())
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(entry["arcname"]) as src_stream, open(dest, "wb") as out_stream:
                    shutil.copyfileobj(src_stream, out_stream)
                restored.append(str(dest))
        archive.unlink()
        self._log_info(f"Restored {len(restored)} file(s) from {archive.name}.")
        return restored

    @staticmethod
    def collision_safe_path(target_path):
        """Return target_path if unused, otherwise append _1, _2, ... before suffix."""
        path = Path(target_path)
        if not path.exists():
            return path
        counter = 1
        while True:
            candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    @staticmethod
    def _meta_path(recycled_path):
        """Return the sidecar .meta.json path for a recycled file."""
        return Path(f"{recycled_path}.meta.json")

    def _log_info(self, message):
        """Write an informational log message when a logger is attached."""
        if self.logger is not None:
            self.logger.info(message)
