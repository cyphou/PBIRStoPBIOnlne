"""Pre-flight check — validate PBIRS, PBI Online, gateways, and workspace access
before a long-running ``--full`` migration.

Returns a list of ``(name, status, detail)`` tuples plus a single bool ``ok``.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PreflightResult:
    def __init__(self) -> None:
        self.checks: list[dict] = []

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.checks.append({"name": name, "status": status, "detail": detail})

    @property
    def ok(self) -> bool:
        return all(c["status"] != "fail" for c in self.checks)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "checks": self.checks,
            "failures": [c for c in self.checks if c["status"] == "fail"],
            "warnings": [c for c in self.checks if c["status"] == "warn"],
        }


class PreflightRunner:
    """Validate connectivity and configuration prior to migration."""

    def __init__(self, args: Any):
        self.args = args

    def run(self) -> PreflightResult:
        result = PreflightResult()
        self._check_pbirs(result)
        self._check_pbi_online(result)
        self._check_workspace(result)
        self._check_gateway_mapping(result)
        self._check_folder_mapping(result)
        return result

    # --- individual checks -------------------------------------------------

    def _check_pbirs(self, result: PreflightResult) -> None:
        if not getattr(self.args, "server", None):
            result.add("pbirs.connection", "skip", "no --server provided")
            return
        try:
            from pbirs_export.api_client import PBIRSClient
            client = PBIRSClient(
                server_url=self.args.server,
                username=getattr(self.args, "username", None),
                password=getattr(self.args, "password", None),
                token=getattr(self.args, "token", None),
                use_windows_auth=getattr(self.args, "use_windows_auth", False),
            )
            info = client.get_system_info()
            result.add("pbirs.connection", "ok", str(info.get("ProductName", "PBIRS")))
        except Exception as e:
            result.add("pbirs.connection", "fail", f"{type(e).__name__}: {e}")

    def _check_pbi_online(self, result: PreflightResult) -> None:
        need_pbi = bool(getattr(self.args, "do_import", False)
                        or getattr(self.args, "validate", False)
                        or getattr(self.args, "full", False))
        if not need_pbi:
            result.add("pbi.auth", "skip", "no import/validate/full phase")
            return
        try:
            from pbi_import.deploy.client_factory import PbiClientFactory
            client = PbiClientFactory.from_args(self.args)
            workspaces = client.list_workspaces()
            result.add("pbi.auth", "ok", f"{len(workspaces)} workspaces visible")
        except (RuntimeError, ImportError) as e:
            result.add("pbi.auth", "fail", f"{type(e).__name__}: {e}")
        except Exception as e:
            result.add("pbi.auth", "fail", f"{type(e).__name__}: {e}")

    def _check_workspace(self, result: PreflightResult) -> None:
        ws_id = getattr(self.args, "workspace_id", None)
        if not ws_id:
            result.add("pbi.workspace", "skip", "no --workspace-id")
            return
        try:
            from pbi_import.deploy.client_factory import PbiClientFactory
            client = PbiClientFactory.from_args(self.args)
            workspaces = client.list_workspaces()
            match = next((w for w in workspaces if w.get("id") == ws_id), None)
            if match:
                result.add("pbi.workspace", "ok",
                           f"'{match.get('name', ws_id)}' accessible")
            else:
                result.add("pbi.workspace", "fail",
                           f"workspace {ws_id} not found in token's tenant")
        except Exception as e:
            result.add("pbi.workspace", "fail", f"{type(e).__name__}: {e}")

    def _check_gateway_mapping(self, result: PreflightResult) -> None:
        path = getattr(self.args, "map_gateway", None)
        if not path:
            result.add("pbi.gateways", "skip", "no --map-gateway")
            return
        p = Path(path)
        if not p.exists():
            result.add("pbi.gateways", "fail", f"file not found: {path}")
            return
        try:
            mapping = json.loads(p.read_text(encoding="utf-8"))
            count = len(mapping) if isinstance(mapping, (list, dict)) else 0
            result.add("pbi.gateways", "ok", f"{count} mapping entries")
        except json.JSONDecodeError as e:
            result.add("pbi.gateways", "fail", f"invalid JSON: {e}")

    def _check_folder_mapping(self, result: PreflightResult) -> None:
        path = getattr(self.args, "map_folder", None)
        if not path:
            result.add("pbi.folder_map", "skip", "no --map-folder")
            return
        p = Path(path)
        if not p.exists():
            result.add("pbi.folder_map", "fail", f"file not found: {path}")
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            rules = data if isinstance(data, list) else data.get("rules", [])
            result.add("pbi.folder_map", "ok", f"{len(rules)} folder rules")
        except json.JSONDecodeError as e:
            result.add("pbi.folder_map", "fail", f"invalid JSON: {e}")
