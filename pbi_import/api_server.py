"""
API Server — stdlib REST API for programmatic migration control.

Provides a lightweight HTTP API (stdlib http.server) for triggering
migrations, querying status, and retrieving results from external tools.
"""

import json
import logging
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)


class MigrationAPIHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the migration API."""

    server: "MigrationAPIServer"  # type: ignore[assignment]

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        routes: dict[str, Callable[..., dict]] = {
            "/api/status": self._handle_status,
            "/api/health": self._handle_health,
            "/api/runs": self._handle_runs,
            "/api/registry": self._handle_registry,
        }

        handler = routes.get(path)
        if handler:
            result = handler(params)
            self._json_response(200, result)
        elif path == "/":
            self._json_response(200, {
                "service": "PBIRS Migration API",
                "version": "1.0.0",
                "endpoints": list(routes.keys()) + ["/api/migrate"],
            })
        else:
            self._json_response(404, {"error": "Not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length)) if content_length else {}

        if path == "/api/migrate":
            result = self._handle_migrate(body)
            self._json_response(202, result)
        else:
            self._json_response(404, {"error": "Not found"})

    def _handle_status(self, params: dict) -> dict:
        return self.server.state.get("status", {"status": "idle"})

    def _handle_health(self, params: dict) -> dict:
        return {"status": "healthy", "uptime_seconds": time.time() - self.server.start_time}

    def _handle_runs(self, params: dict) -> dict:
        return {"runs": self.server.state.get("runs", [])}

    def _handle_registry(self, params: dict) -> dict:
        registry_fn = self.server.callbacks.get("registry")
        if registry_fn:
            return registry_fn()
        return {"error": "Registry not configured"}

    def _handle_migrate(self, body: dict) -> dict:
        migrate_fn = self.server.callbacks.get("migrate")
        if not migrate_fn:
            return {"error": "Migration callback not configured"}

        # Run async
        run_id = f"run_{int(time.time())}"

        def _run() -> None:
            try:
                self.server.state["status"] = {"status": "running", "run_id": run_id}
                result = migrate_fn(body)
                self.server.state.setdefault("runs", []).append({
                    "run_id": run_id,
                    "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "result": result,
                })
                self.server.state["status"] = {"status": "idle", "last_run": run_id}
            except Exception as e:
                self.server.state["status"] = {
                    "status": "error",
                    "run_id": run_id,
                    "error": str(e),
                }

        thread = threading.Thread(target=_run, daemon=True, name=f"migrate-{run_id}")
        thread.start()

        return {"run_id": run_id, "status": "accepted"}

    def _json_response(self, status: int, data: dict) -> None:
        body = json.dumps(data, indent=2, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug("API: %s", format % args)


class MigrationAPIServer(HTTPServer):
    """Migration API HTTP server with state and callbacks."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8080):
        super().__init__((host, port), MigrationAPIHandler)
        self.state: dict[str, Any] = {"status": {"status": "idle"}}
        self.callbacks: dict[str, Callable[..., Any]] = {}
        self.start_time = time.time()

    def register_callback(self, name: str, callback: Callable[..., Any]) -> None:
        """Register a callback for API operations."""
        self.callbacks[name] = callback

    def start(self) -> threading.Thread:
        """Start the server in a background thread."""
        thread = threading.Thread(target=self.serve_forever, daemon=True, name="api-server")
        thread.start()
        logger.info("API server started on %s:%d", *self.server_address)
        return thread

    def stop(self) -> None:
        """Stop the server."""
        self.shutdown()
        logger.info("API server stopped")
