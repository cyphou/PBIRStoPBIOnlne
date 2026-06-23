"""Content-hash idempotency — skip already-published items on re-run.

Even with ``--resume`` the existing pipeline checkpoint only remembers whole
phases. If the import phase failed half-way through, a re-run still re-pushes
every previously-completed item. ``ContentHashStore`` stores a stable SHA1
of each item's content + target workspace, so the publisher can skip items
that haven't changed and have already shipped successfully.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_HASH_FILE = "publish.hashes.json"


def hash_item(item: dict, workspace_id: str | None = None) -> str:
    """Return a stable SHA1 hash for an item / workspace combo."""
    stable = {
        "name": item.get("name") or item.get("Name"),
        "type": item.get("type") or item.get("Type"),
        "size_bytes": item.get("size_bytes") or item.get("Size"),
        "modified": (
            item.get("modified")
            or item.get("ModifiedDate")
            or item.get("modified_at")
        ),
        "path": item.get("Path") or item.get("path"),
        "workspace_id": workspace_id,
    }
    payload = json.dumps(stable, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha1(payload, usedforsecurity=False).hexdigest()


def hash_file(path: str | Path, workspace_id: str | None = None) -> str:
    """Hash a file (e.g. .pbix) plus its target workspace."""
    h = hashlib.sha1(usedforsecurity=False)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    h.update((workspace_id or "").encode("utf-8"))
    return h.hexdigest()


class ContentHashStore:
    """Persisted map of item-key → {hash, workspace_id, published_at}."""

    def __init__(self, root_dir: str | Path):
        self.root = Path(root_dir)
        self.path = self.root / _HASH_FILE
        self._lock = threading.Lock()
        self._data: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            with self.path.open(encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Corrupt hash store at %s, starting fresh: %s",
                           self.path, e)
            return {}

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, default=str)
            try:
                tmp.replace(self.path)
            except OSError:
                if self.path.exists():
                    self.path.unlink()
                tmp.rename(self.path)

    def key_for(self, item: dict, workspace_id: str | None = None) -> str:
        name = item.get("name") or item.get("Name") or "?"
        path = item.get("Path") or item.get("path") or ""
        return f"{workspace_id or '-'}::{path}::{name}"

    def is_published(
        self,
        item: dict,
        workspace_id: str | None = None,
        file_path: str | Path | None = None,
    ) -> bool:
        """Return True iff the item was previously published at this hash."""
        key = self.key_for(item, workspace_id)
        with self._lock:
            entry = self._data.get(key)
        if not entry:
            return False
        current = (
            hash_file(file_path, workspace_id) if file_path
            else hash_item(item, workspace_id)
        )
        return entry.get("hash") == current

    def record(
        self,
        item: dict,
        workspace_id: str | None = None,
        file_path: str | Path | None = None,
        result: dict | None = None,
    ) -> None:
        """Persist a successful publish for skip-on-rerun."""
        key = self.key_for(item, workspace_id)
        h = (
            hash_file(file_path, workspace_id) if file_path
            else hash_item(item, workspace_id)
        )
        with self._lock:
            self._data[key] = {
                "hash": h,
                "workspace_id": workspace_id,
                "published_at": _now(),
                "result": result or {},
            }

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total": len(self._data),
                "path": str(self.path),
            }

    def reset(self) -> None:
        with self._lock:
            self._data = {}
            if self.path.exists():
                self.path.unlink()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
