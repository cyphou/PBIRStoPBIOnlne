"""
Web UI — lightweight migration dashboard using stdlib http.server.

Serves a single-page HTML dashboard showing migration progress, phase status,
and per-item results. No external dependencies — pure stdlib.
"""

import html
import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

logger = logging.getLogger(__name__)


class DashboardState:
    """Thread-safe migration state container for the dashboard."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._phases: dict[str, dict] = {}
        self._items: list[dict] = []
        self._log: list[str] = []

    def update_phase(self, phase: str, status: str, detail: str = "") -> None:
        with self._lock:
            self._phases[phase] = {"status": status, "detail": detail}

    def add_item(self, item: dict) -> None:
        with self._lock:
            self._items.append(item)

    def add_log(self, message: str) -> None:
        with self._lock:
            self._log.append(message)
            if len(self._log) > 500:
                self._log = self._log[-500:]

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "phases": dict(self._phases),
                "items": list(self._items),
                "log": list(self._log[-100:]),
                "summary": {
                    "total": len(self._items),
                    "success": sum(1 for i in self._items if i.get("status") == "success"),
                    "failed": sum(1 for i in self._items if i.get("status") == "failed"),
                    "pending": sum(1 for i in self._items if i.get("status") == "pending"),
                },
            }


class _DashboardHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the migration dashboard."""

    state: DashboardState  # injected by factory

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/status":
            self._json_response(self.state.snapshot())
        elif self.path == "/":
            self._html_response(_DASHBOARD_HTML)
        else:
            self.send_error(404)

    def _json_response(self, data: dict) -> None:
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html_response(self, content: str) -> None:
        body = content.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        # Suppress default stderr logging
        pass


class MigrationDashboard:
    """Simple HTTP dashboard for migration progress monitoring."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8050):
        self.host = host
        self.port = port
        self.state = DashboardState()
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the dashboard server in a background thread."""
        handler_class = type(
            "_BoundHandler",
            (_DashboardHandler,),
            {"state": self.state},
        )
        self._server = HTTPServer((self.host, self.port), handler_class)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info("Dashboard running at http://%s:%d", self.host, self.port)

    def stop(self) -> None:
        """Stop the dashboard server."""
        if self._server:
            self._server.shutdown()
            logger.info("Dashboard stopped")

    def update_phase(self, phase: str, status: str, detail: str = "") -> None:
        self.state.update_phase(phase, status, detail)

    def add_item(self, item: dict) -> None:
        self.state.add_item(item)

    def add_log(self, message: str) -> None:
        self.state.add_log(message)


_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>PBIRS Migration Dashboard</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;background:#0d1117;color:#c9d1d9;padding:20px}
h1{color:#58a6ff;margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:24px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px}
.card h3{font-size:14px;color:#8b949e;margin-bottom:8px}
.card .value{font-size:28px;font-weight:bold}
.success{color:#3fb950}.failed{color:#f85149}.pending{color:#d29922}
.phases{margin-bottom:24px}
.phase{display:flex;align-items:center;padding:8px 12px;background:#161b22;border:1px solid #30363d;border-radius:6px;margin-bottom:6px}
.phase .dot{width:10px;height:10px;border-radius:50%;margin-right:12px}
.dot.running{background:#d29922;animation:pulse 1s infinite}
.dot.complete{background:#3fb950}.dot.pending{background:#484f58}.dot.failed{background:#f85149}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.log{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px;max-height:300px;overflow-y:auto;font-family:monospace;font-size:13px;line-height:1.6}
</style>
</head>
<body>
<h1>&#x1F504; PBIRS &#x2192; PBI Online Migration</h1>
<div class="grid" id="summary"></div>
<h2 style="margin-bottom:12px">Phases</h2>
<div class="phases" id="phases"></div>
<h2 style="margin-bottom:12px">Log</h2>
<div class="log" id="log"></div>
<script>
async function refresh(){
  try{
    const r=await fetch('/api/status');
    const d=await r.json();
    document.getElementById('summary').innerHTML=
      `<div class="card"><h3>Total</h3><div class="value">${d.summary.total}</div></div>
       <div class="card"><h3>Success</h3><div class="value success">${d.summary.success}</div></div>
       <div class="card"><h3>Failed</h3><div class="value failed">${d.summary.failed}</div></div>
       <div class="card"><h3>Pending</h3><div class="value pending">${d.summary.pending}</div></div>`;
    const ph=Object.entries(d.phases).map(([k,v])=>
      `<div class="phase"><div class="dot ${v.status}"></div><b>${k}</b>&nbsp;— ${v.detail||v.status}</div>`
    ).join('');
    document.getElementById('phases').innerHTML=ph;
    document.getElementById('log').innerHTML=d.log.map(l=>'<div>'+l+'</div>').join('');
  }catch(e){}
}
setInterval(refresh,2000);refresh();
</script>
</body>
</html>"""
