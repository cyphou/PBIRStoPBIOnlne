"""Streaming catalog iterator — process huge catalogs without loading all in RAM.

Today every phase keeps the full catalog (`list[dict]`) in memory. For 10k+
items that breaks past a few GB once enrichment data (security, lineage,
RDL XML) joins each row. ``CatalogStream`` exposes an iterator interface so
producers and consumers process one item at a time, with peek/buffer support
for back-pressure-friendly multi-pass consumers.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class CatalogStream:
    """Iterator wrapper for a catalog that may be loaded lazily from disk.

    Supports three sources:
        * an in-memory list   (``CatalogStream.from_list``)
        * a JSON file         (``CatalogStream.from_json``)
        * a JSONL file        (``CatalogStream.from_jsonl``)

    The iterator yields one item dict at a time; callers can also use the
    ``batched(n)`` method to drain in chunks for batched API calls.
    """

    def __init__(self, source: Iterable[dict], total: int | None = None):
        self._source = source
        self._total = total
        self._consumed = 0

    @classmethod
    def from_list(cls, items: list[dict]) -> "CatalogStream":
        return cls(iter(items), total=len(items))

    @classmethod
    def from_json(cls, path: str | Path) -> "CatalogStream":
        """Load a JSON catalog. The file may be a list or a dict-with-items."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "items" in data:
            items = data["items"]
        elif isinstance(data, list):
            items = data
        else:
            raise ValueError(f"Unsupported catalog JSON shape in {path}")
        return cls.from_list(items)

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "CatalogStream":
        """Lazy iterator over a JSON-Lines catalog (one item per line)."""

        def _gen() -> Iterator[dict]:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    yield json.loads(line)

        return cls(_gen(), total=None)

    def __iter__(self) -> Iterator[dict]:
        for item in self._source:
            self._consumed += 1
            yield item

    def batched(self, size: int) -> Iterator[list[dict]]:
        """Yield batches of ``size`` items at a time."""
        if size < 1:
            raise ValueError("batch size must be >= 1")
        batch: list[dict] = []
        for item in self:
            batch.append(item)
            if len(batch) >= size:
                yield batch
                batch = []
        if batch:
            yield batch

    def filter(self, predicate: Callable[[dict], bool]) -> "CatalogStream":
        """Return a new stream filtered by ``predicate`` (still lazy)."""

        def _gen() -> Iterator[dict]:
            for item in self:
                if predicate(item):
                    yield item

        return CatalogStream(_gen(), total=None)

    def map(self, fn: Callable[[dict], dict]) -> "CatalogStream":
        """Apply ``fn`` to each item (lazy)."""

        def _gen() -> Iterator[dict]:
            for item in self:
                yield fn(item)

        return CatalogStream(_gen(), total=self._total)

    def collect(self) -> list[dict]:
        """Materialise the stream as a list (defeats streaming — for tests)."""
        return list(self)

    @property
    def total(self) -> int | None:
        """Best-known total. ``None`` for JSONL or filtered streams."""
        return self._total

    @property
    def consumed(self) -> int:
        return self._consumed


def write_jsonl(items: Iterable[dict[str, Any]], path: str | Path) -> int:
    """Write items to a JSONL file (one item per line). Returns count."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with p.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, default=str) + "\n")
            n += 1
    return n
