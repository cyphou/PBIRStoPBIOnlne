"""
PBIRS REST API Client.

Handles authentication (Windows/Token/Service Principal) and provides
methods for all PBIRS REST API v2.0 endpoints used during migration.

Reference: https://learn.microsoft.com/sql/reporting-services/developer/rest-api
"""

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


class PBIRSClient:
    """Client for Power BI Report Server REST API v2.0."""

    API_VERSION = "v2.0"

    def __init__(
        self,
        server_url: str,
        username: str | None = None,
        password: str | None = None,
        token: str | None = None,
        use_windows_auth: bool = False,
    ):
        self.server_url = server_url.rstrip("/")
        self.username = username
        self.password = password
        self.token = token
        self.use_windows_auth = use_windows_auth
        self._base_url = f"{self.server_url}/api/{self.API_VERSION}"
        self._session_cookie: str | None = None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _build_auth_header(self) -> dict[str, str]:
        """Build authentication headers."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        elif self.username and self.password:
            creds = base64.b64encode(
                f"{self.username}:{self.password}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {creds}"
        # Windows auth handled by urllib with NTLM if available

        if self._session_cookie:
            headers["Cookie"] = self._session_cookie

        return headers

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        endpoint: str,
        data: dict | None = None,
        params: dict | None = None,
        raw: bool = False,
    ) -> Any:
        """Execute an HTTP request against the PBIRS API."""
        url = f"{self._base_url}/{endpoint.lstrip('/')}"
        if params:
            url += "?" + urllib.parse.urlencode(params)

        body = json.dumps(data).encode("utf-8") if data else None
        headers = self._build_auth_header()

        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                # Capture session cookie
                cookie = resp.headers.get("Set-Cookie")
                if cookie:
                    self._session_cookie = cookie.split(";")[0]

                if raw:
                    return resp.read()
                content = resp.read().decode("utf-8")
                return json.loads(content) if content else {}
        except urllib.error.HTTPError as e:
            logger.error("HTTP %d %s: %s %s", e.code, e.reason, method, url)
            raise
        except urllib.error.URLError as e:
            logger.error("Connection error: %s — %s", url, e.reason)
            raise

    def _get(self, endpoint: str, params: dict | None = None) -> Any:
        return self._request("GET", endpoint, params=params)

    def _post(self, endpoint: str, data: dict | None = None) -> Any:
        return self._request("POST", endpoint, data=data)

    def _get_raw(self, endpoint: str) -> bytes:
        return self._request("GET", endpoint, raw=True)

    def _paginated_get(self, endpoint: str, params: dict | None = None) -> list[dict]:
        """Fetch all pages of a paginated API response."""
        all_items: list[dict] = []
        skip = 0
        page_size = 100
        base_params = dict(params or {})

        while True:
            page_params = {**base_params, "$skip": skip, "$top": page_size}
            response = self._get(endpoint, params=page_params)
            items = response.get("value", response if isinstance(response, list) else [])
            if not items:
                break
            all_items.extend(items)
            if len(items) < page_size:
                break
            skip += page_size

        return all_items

    # ------------------------------------------------------------------
    # System info
    # ------------------------------------------------------------------

    def get_system_info(self) -> dict:
        """Get PBIRS system information."""
        return self._get("System")

    def get_system_properties(self) -> dict:
        """Get PBIRS system properties."""
        return self._get("System/Properties")

    # ------------------------------------------------------------------
    # Catalog items
    # ------------------------------------------------------------------

    def list_catalog_items(self, folder: str | None = None) -> list[dict]:
        """List all catalog items, optionally filtered by folder path."""
        params = {}
        if folder:
            # OData filter on Path
            safe_folder = folder.replace("'", "''")
            params["$filter"] = f"startswith(Path,'{safe_folder}')"
        return self._paginated_get("CatalogItems", params=params)

    def get_catalog_item(self, item_id: str) -> dict:
        """Get a single catalog item by ID."""
        return self._get(f"CatalogItems({item_id})")

    def get_catalog_item_content(self, item_id: str) -> bytes:
        """Download the content (file) of a catalog item."""
        return self._get_raw(f"CatalogItems({item_id})/Content/$value")

    # ------------------------------------------------------------------
    # Power BI Reports
    # ------------------------------------------------------------------

    def list_powerbi_reports(self) -> list[dict]:
        """List all Power BI reports."""
        return self._paginated_get("PowerBIReports")

    def get_powerbi_report(self, report_id: str) -> dict:
        """Get Power BI report metadata."""
        return self._get(f"PowerBIReports({report_id})")

    def download_powerbi_report(self, report_id: str) -> bytes:
        """Download a Power BI report (.pbix) content."""
        return self._get_raw(f"PowerBIReports({report_id})/Content/$value")

    def get_powerbi_report_datasources(self, report_id: str) -> list[dict]:
        """Get datasources for a Power BI report."""
        return self._paginated_get(f"PowerBIReports({report_id})/DataSources")

    # ------------------------------------------------------------------
    # Paginated Reports (RDL/SSRS)
    # ------------------------------------------------------------------

    def list_reports(self) -> list[dict]:
        """List all paginated reports."""
        return self._paginated_get("Reports")

    def get_report(self, report_id: str) -> dict:
        """Get paginated report metadata."""
        return self._get(f"Reports({report_id})")

    def download_report(self, report_id: str) -> bytes:
        """Download a paginated report (.rdl) content."""
        return self._get_raw(f"Reports({report_id})/Content/$value")

    def get_report_parameters(self, report_id: str) -> list[dict]:
        """Get parameters for a paginated report."""
        return self._paginated_get(f"Reports({report_id})/ParameterDefinitions")

    def get_report_datasources(self, report_id: str) -> list[dict]:
        """Get datasources for a paginated report."""
        return self._paginated_get(f"Reports({report_id})/DataSources")

    # ------------------------------------------------------------------
    # Datasets (Shared)
    # ------------------------------------------------------------------

    def list_datasets(self) -> list[dict]:
        """List all shared datasets."""
        return self._paginated_get("DataSets")

    def get_dataset(self, dataset_id: str) -> dict:
        """Get dataset metadata."""
        return self._get(f"DataSets({dataset_id})")

    def download_dataset(self, dataset_id: str) -> bytes:
        """Download dataset definition."""
        return self._get_raw(f"DataSets({dataset_id})/Content/$value")

    # ------------------------------------------------------------------
    # KPIs
    # ------------------------------------------------------------------

    def list_kpis(self) -> list[dict]:
        """List all KPIs."""
        return self._paginated_get("Kpis")

    def get_kpi(self, kpi_id: str) -> dict:
        """Get KPI metadata."""
        return self._get(f"Kpis({kpi_id})")

    # ------------------------------------------------------------------
    # Folders
    # ------------------------------------------------------------------

    def list_folders(self) -> list[dict]:
        """List all folders."""
        return self._paginated_get("Folders")

    def get_folder(self, folder_id: str) -> dict:
        """Get folder metadata."""
        return self._get(f"Folders({folder_id})")

    # ------------------------------------------------------------------
    # Data Sources
    # ------------------------------------------------------------------

    def list_datasources(self) -> list[dict]:
        """List all shared data sources."""
        return self._paginated_get("DataSources")

    def get_datasource(self, ds_id: str) -> dict:
        """Get data source details."""
        return self._get(f"DataSources({ds_id})")

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def list_subscriptions(self) -> list[dict]:
        """List all subscriptions."""
        return self._paginated_get("Subscriptions")

    def get_subscription(self, sub_id: str) -> dict:
        """Get subscription details."""
        return self._get(f"Subscriptions({sub_id})")

    # ------------------------------------------------------------------
    # Schedules
    # ------------------------------------------------------------------

    def list_schedules(self) -> list[dict]:
        """List all schedules."""
        return self._paginated_get("Schedules")

    def get_schedule(self, schedule_id: str) -> dict:
        """Get schedule details."""
        return self._get(f"Schedules({schedule_id})")

    # ------------------------------------------------------------------
    # Policies (Permissions)
    # ------------------------------------------------------------------

    def get_item_policies(self, item_id: str) -> list[dict]:
        """Get security policies (role assignments) for an item."""
        result = self._get(f"CatalogItems({item_id})/Policies")
        return result.get("Policies", result if isinstance(result, list) else [])

    def get_system_policies(self) -> list[dict]:
        """Get system-level security policies."""
        result = self._get("System/Policies")
        return result.get("Policies", result if isinstance(result, list) else [])

    # ------------------------------------------------------------------
    # Cache refresh plans
    # ------------------------------------------------------------------

    def list_cache_refresh_plans(self, item_id: str) -> list[dict]:
        """List cache refresh plans for a catalog item."""
        return self._paginated_get(f"CatalogItems({item_id})/CacheRefreshPlans")
