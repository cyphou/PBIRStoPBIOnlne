"""Lightweight stdlib tracing — spans + optional OTLP HTTP export.

This module gives every phase / per-item operation a tracing span so that
runs can be replayed in a dashboard or shipped to an OTLP collector. The
default behaviour is **in-memory only** so it stays free for unit tests and
small migrations. When ``OTLP_ENDPOINT`` is set (or ``--otlp-endpoint`` is
passed on the CLI) finished spans are flushed as OTLP/HTTP JSON.

Design goals:
    * stdlib-only (urllib for OTLP export)
    * thread-safe
    * zero overhead when disabled (``Tracer(enabled=False)``)
    * compatible with the existing ``event_log`` JSONL stream
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

logger = logging.getLogger(__name__)


@dataclass
class Span:
    """One unit of traced work."""

    name: str
    trace_id: str
    span_id: str
    parent_id: str | None
    start_ns: int
    end_ns: int | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "OK"

    @property
    def duration_ms(self) -> float:
        if self.end_ns is None:
            return 0.0
        return (self.end_ns - self.start_ns) / 1_000_000.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "start_ns": self.start_ns,
            "end_ns": self.end_ns,
            "duration_ms": round(self.duration_ms, 3),
            "attributes": self.attributes,
            "status": self.status,
        }


class Tracer:
    """In-memory tracer with optional OTLP/HTTP export."""

    def __init__(
        self,
        service_name: str = "pbirs-migrate",
        enabled: bool = True,
        otlp_endpoint: str | None = None,
        otlp_headers: dict[str, str] | None = None,
    ):
        self.service_name = service_name
        self.enabled = enabled
        self.otlp_endpoint = otlp_endpoint or os.environ.get("OTLP_ENDPOINT")
        self.otlp_headers = otlp_headers or {}
        self._spans: list[Span] = []
        self._lock = threading.Lock()
        self._local = threading.local()
        self._trace_id = uuid.uuid4().hex

    def _current_span(self) -> Span | None:
        return getattr(self._local, "current", None)

    def _push(self, span: Span) -> None:
        self._local.current = span

    def _pop(self, parent: Span | None) -> None:
        self._local.current = parent

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[Span]:
        """Open a span as a context manager.

        Nested ``span()`` calls automatically inherit the parent's span id
        so the resulting trace is a proper tree.
        """
        if not self.enabled:
            # Yield a throwaway no-op span so callers can still set attrs.
            yield Span(name=name, trace_id="", span_id="", parent_id=None, start_ns=0)
            return

        parent = self._current_span()
        span = Span(
            name=name,
            trace_id=self._trace_id,
            span_id=uuid.uuid4().hex[:16],
            parent_id=parent.span_id if parent else None,
            start_ns=time.monotonic_ns(),
            attributes=dict(attributes),
        )
        self._push(span)
        try:
            yield span
        except BaseException as exc:
            span.status = "ERROR"
            span.attributes["error"] = repr(exc)
            raise
        finally:
            span.end_ns = time.monotonic_ns()
            self._pop(parent)
            with self._lock:
                self._spans.append(span)

    def spans(self) -> list[Span]:
        with self._lock:
            return list(self._spans)

    def summary(self) -> dict:
        with self._lock:
            spans = list(self._spans)
        by_name: dict[str, dict] = {}
        for s in spans:
            entry = by_name.setdefault(
                s.name, {"count": 0, "total_ms": 0.0, "errors": 0}
            )
            entry["count"] += 1
            entry["total_ms"] += s.duration_ms
            if s.status == "ERROR":
                entry["errors"] += 1
        for v in by_name.values():
            v["total_ms"] = round(v["total_ms"], 3)
            v["avg_ms"] = round(v["total_ms"] / max(v["count"], 1), 3)
        return {
            "service": self.service_name,
            "trace_id": self._trace_id,
            "total_spans": len(spans),
            "by_name": by_name,
        }

    def write_json(self, path: str) -> None:
        """Write all spans + summary to a JSON file."""
        payload = {
            "service": self.service_name,
            "trace_id": self._trace_id,
            "spans": [s.to_dict() for s in self.spans()],
            "summary": self.summary(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def flush_otlp(self) -> int:
        """POST collected spans to ``otlp_endpoint`` as OTLP/HTTP JSON.

        Returns the number of spans flushed (0 if no endpoint configured).
        """
        if not self.otlp_endpoint or not self._spans:
            return 0

        import urllib.error
        import urllib.request

        with self._lock:
            spans = list(self._spans)
            self._spans.clear()

        otlp_payload = self._to_otlp(spans)
        body = json.dumps(otlp_payload).encode("utf-8")
        headers = {"Content-Type": "application/json", **self.otlp_headers}
        req = urllib.request.Request(self.otlp_endpoint, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                logger.info("OTLP export: %d spans → %s (HTTP %d)",
                            len(spans), self.otlp_endpoint, resp.status)
        except (urllib.error.URLError, OSError) as e:
            logger.warning("OTLP export failed: %s", e)
        return len(spans)

    def _to_otlp(self, spans: list[Span]) -> dict:
        """Convert internal spans to OTLP/HTTP-JSON envelope."""
        otlp_spans = []
        for s in spans:
            otlp_spans.append({
                "traceId": s.trace_id,
                "spanId": s.span_id,
                "parentSpanId": s.parent_id or "",
                "name": s.name,
                "startTimeUnixNano": str(s.start_ns),
                "endTimeUnixNano": str(s.end_ns or s.start_ns),
                "attributes": [
                    {"key": k, "value": {"stringValue": str(v)}}
                    for k, v in s.attributes.items()
                ],
                "status": {"code": 1 if s.status == "OK" else 2},
            })
        return {
            "resourceSpans": [{
                "resource": {
                    "attributes": [
                        {"key": "service.name",
                         "value": {"stringValue": self.service_name}},
                    ],
                },
                "scopeSpans": [{
                    "scope": {"name": "pbirs-migrate", "version": "1.7.0"},
                    "spans": otlp_spans,
                }],
            }],
        }


_NOOP = Tracer(enabled=False)


def noop() -> Tracer:
    """Return a tracer that records nothing — used when tracing disabled."""
    return _NOOP
