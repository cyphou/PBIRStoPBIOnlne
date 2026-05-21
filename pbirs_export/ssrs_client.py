"""
SSRS Client — standard SQL Server Reporting Services support.

Extends PBIRS extraction to handle legacy SSRS servers that use the
older ReportService2010 SOAP endpoint alongside the REST API.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

_SSRS_NAMESPACE = "http://schemas.microsoft.com/sqlserver/reporting/2010/03/01/ReportServer"
_SOAP_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:rs="{ns}">
  <soap:Body>
    <rs:{method}>
      {params}
    </rs:{method}>
  </soap:Body>
</soap:Envelope>"""


class SSRSClient:
    """Client for legacy SSRS servers (ReportService2010 SOAP + REST fallback)."""

    def __init__(self, server_url: str, client: Any):
        self.server_url = server_url.rstrip("/")
        self.client = client
        self.soap_url = f"{self.server_url}/ReportService2010.asmx"
        self.rest_url = f"{self.server_url}/api/v2.0"

    def list_children(self, path: str = "/", recursive: bool = True) -> list[dict]:
        """List catalog items (tries REST first, falls back to SOAP)."""
        try:
            return self._list_via_rest(path, recursive)
        except Exception as e:
            logger.warning("REST API failed, trying SOAP: %s", e)
            return self._list_via_soap(path, recursive)

    def get_item_definition(self, path: str) -> bytes:
        """Download item definition (RDL/PBIX) by path."""
        try:
            url = f"{self.rest_url}/CatalogItems(Path='{path}')/Content/$value"
            return self.client.get_bytes(url)
        except Exception:
            return self._get_definition_soap(path)

    def get_item_policies(self, path: str) -> list[dict]:
        """Get security policies for a catalog item."""
        try:
            url = f"{self.rest_url}/CatalogItems(Path='{path}')/Policies"
            result = self.client.get(url)
            return result.get("value", result.get("Policies", []))
        except Exception:
            return self._get_policies_soap(path)

    def get_datasources(self) -> list[dict]:
        """Get all shared datasources."""
        try:
            url = f"{self.rest_url}/DataSources"
            result = self.client.get(url)
            return result.get("value", [])
        except Exception:
            return self._get_datasources_soap()

    def test_connection(self) -> dict:
        """Test connectivity to the SSRS server."""
        errors: list[str] = []

        # Try REST
        try:
            url = f"{self.rest_url}/System"
            info = self.client.get(url)
            return {
                "status": "connected",
                "api": "REST",
                "server_version": info.get("ProductVersion", "unknown"),
            }
        except Exception as e:
            errors.append(f"REST: {e}")

        # Try SOAP
        try:
            soap = self._build_soap("ListChildren", "<rs:ItemPath>/</rs:ItemPath><rs:Recursive>false</rs:Recursive>")
            self.client.post_xml(self.soap_url, soap)
            return {"status": "connected", "api": "SOAP", "server_version": "unknown"}
        except Exception as e:
            errors.append(f"SOAP: {e}")

        return {"status": "failed", "errors": errors}

    def save_catalog(self, output_dir: str, items: list[dict]) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "ssrs_catalog.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2)
        return path

    # --- REST helpers ---

    def _list_via_rest(self, path: str, recursive: bool) -> list[dict]:
        url = f"{self.rest_url}/CatalogItems"
        if path != "/":
            url += f"?$filter=startswith(Path,'{path}')"
        result = self.client.get(url)
        return result.get("value", [])

    # --- SOAP helpers ---

    def _build_soap(self, method: str, params: str) -> str:
        return _SOAP_TEMPLATE.format(ns=_SSRS_NAMESPACE, method=method, params=params)

    def _list_via_soap(self, path: str, recursive: bool) -> list[dict]:
        soap = self._build_soap(
            "ListChildren",
            f"<rs:ItemPath>{path}</rs:ItemPath>"
            f"<rs:Recursive>{'true' if recursive else 'false'}</rs:Recursive>",
        )
        response = self.client.post_xml(self.soap_url, soap)
        return self._parse_catalog_items(response)

    def _get_definition_soap(self, path: str) -> bytes:
        soap = self._build_soap(
            "GetItemDefinition",
            f"<rs:ItemPath>{path}</rs:ItemPath>",
        )
        return self.client.post_xml_bytes(self.soap_url, soap)

    def _get_policies_soap(self, path: str) -> list[dict]:
        soap = self._build_soap(
            "GetPolicies",
            f"<rs:ItemPath>{path}</rs:ItemPath>",
        )
        response = self.client.post_xml(self.soap_url, soap)
        return self._parse_policies(response)

    def _get_datasources_soap(self) -> list[dict]:
        items = self._list_via_soap("/", True)
        return [i for i in items if i.get("TypeName") == "DataSource"]

    @staticmethod
    def _parse_catalog_items(xml_str: str) -> list[dict]:
        """Parse SOAP response for catalog items."""
        items: list[dict] = []
        try:
            root = ET.fromstring(xml_str)
            for elem in root.iter():
                if "CatalogItem" in elem.tag:
                    item: dict = {}
                    for child in elem:
                        tag = re.sub(r"\{[^}]+\}", "", child.tag)
                        item[tag] = child.text or ""
                    if item:
                        items.append(item)
        except ET.ParseError as e:
            logger.error("Failed to parse SOAP response: %s", e)
        return items

    @staticmethod
    def _parse_policies(xml_str: str) -> list[dict]:
        """Parse SOAP response for security policies."""
        policies: list[dict] = []
        try:
            root = ET.fromstring(xml_str)
            for elem in root.iter():
                if "Policy" in elem.tag:
                    policy: dict = {}
                    for child in elem:
                        tag = re.sub(r"\{[^}]+\}", "", child.tag)
                        policy[tag] = child.text or ""
                    if policy:
                        policies.append(policy)
        except ET.ParseError as e:
            logger.error("Failed to parse policies response: %s", e)
        return policies
