"""
PBIRS REST API Client.

Handles authentication (Windows/Token/Service Principal) and provides
methods for all PBIRS REST API v2.0 endpoints used during migration.

Reference: https://learn.microsoft.com/sql/reporting-services/developer/rest-api
"""

import base64
import json
import logging
import os
import ssl
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

# Optional: requests + requests-ntlm for Windows (NTLM/Negotiate) auth
try:
    import requests as _requests
    from requests_ntlm import HttpNtlmAuth as _HttpNtlmAuth
    _HAS_NTLM = True
except ImportError:
    _HAS_NTLM = False


class PBIRSAuthenticationError(urllib.error.HTTPError):
    """PBIRS 401 response with authentication-specific remediation."""

    def __init__(self, error: urllib.error.HTTPError, guidance: str):
        super().__init__(error.url, error.code, guidance, error.headers, error.fp)
        self.original_reason = error.reason


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
        ca_bundle: str | None = None,
        use_windows_cert_store: bool | None = None,
    ):
        self.server_url = server_url.rstrip("/")
        self.username = username or os.environ.get("PBIRS_USERNAME")
        self.password = password or os.environ.get("PBIRS_PASSWORD")
        self.token = token or os.environ.get("PBIRS_TOKEN")
        self.use_windows_auth = use_windows_auth
        cert_store_env = os.environ.get("PBIRS_USE_WINDOWS_CERT_STORE")
        if cert_store_env is not None:
            self.use_windows_cert_store = cert_store_env.lower() in {"1", "true", "yes"}
        elif use_windows_cert_store is not None:
            self.use_windows_cert_store = use_windows_cert_store
        else:
            self.use_windows_cert_store = os.name == "nt"
        self.ca_bundle = (
            ca_bundle
            or os.environ.get("PBIRS_CA_BUNDLE")
            or os.environ.get("REQUESTS_CA_BUNDLE")
            or os.environ.get("SSL_CERT_FILE")
        )
        self._windows_ca_bundle: str | None = None
        self._base_url = f"{self.server_url}/api/{self.API_VERSION}"
        self._session_cookie: str | None = None
        self._session: Any = None  # requests.Session when using NTLM

        if self.use_windows_auth:
            if not _HAS_NTLM:
                raise ImportError(
                    "Windows auth requires 'requests' and 'requests-ntlm'. "
                    "Install with: pip install requests requests-ntlm"
                )
            self._session = _requests.Session()
            self._session.auth = _HttpNtlmAuth(
                self.username, self.password, self._session
            )
            logger.info("Using NTLM authentication via requests-ntlm")

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

        # Use requests-ntlm session for Windows auth
        if self._session is not None:
            return self._request_ntlm(method, url, data, raw)

        body = json.dumps(data).encode("utf-8") if data else None
        headers = self._build_auth_header()

        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            context = self._ssl_context()
            with urllib.request.urlopen(req, timeout=60, context=context) as resp:
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
            if e.code == 401:
                raise PBIRSAuthenticationError(e, self._authentication_guidance()) from e
            raise
        except urllib.error.URLError as e:
            logger.error("Connection error: %s — %s", url, e.reason)
            raise

    def _authentication_guidance(self) -> str:
        """Return a safe remediation message for the configured auth mode."""
        if self.token:
            return (
                "PBIRS authentication failed: the bearer token was rejected. "
                "Acquire a new token with PBIRS audience/scope and retry --token."
            )
        if self.username and self.password:
            return (
                "PBIRS authentication failed: the supplied username/password were rejected. "
                "Verify DOMAIN\\user credentials or use --use-windows-auth."
            )
        if self.use_windows_auth:
            return (
                "PBIRS Windows authentication failed. Browser-integrated authentication "
                "does not automatically carry into Python. Supply DOMAIN\\user credentials, "
                "then retry with --use-windows-auth."
            )
        return (
            "PBIRS requires authentication. The API may work in a browser because the browser "
            "sends your Windows identity automatically. Retry with --use-windows-auth, "
            "or provide --token or --username/--password."
        )

    def _ssl_context(self) -> ssl.SSLContext | None:
        if self.ca_bundle:
            return ssl.create_default_context(cafile=self.ca_bundle)
        if self.use_windows_cert_store:
            return ssl.create_default_context(cafile=self._get_windows_ca_bundle())
        return None

    def _requests_verify(self) -> str | bool:
        if self.ca_bundle:
            return self.ca_bundle
        if self.use_windows_cert_store:
            return self._get_windows_ca_bundle()
        return True

    def _get_windows_ca_bundle(self) -> str:
        """Build a temporary PEM bundle from Windows ROOT and CA stores."""
        if self._windows_ca_bundle:
            return self._windows_ca_bundle

        certificates: list[str] = []
        for store_name in ("ROOT", "CA"):
            try:
                for cert_bytes, encoding, trust in ssl.enum_certificates(store_name):
                    if trust is True or "1.3.6.1.5.5.7.3.1" in trust:
                        if encoding == "x509_asn":
                            certificates.append(ssl.DER_cert_to_PEM_cert(cert_bytes))
                        elif encoding == "x509_pem":
                            certificates.append(cert_bytes.decode("ascii"))
            except OSError:
                continue

        if not certificates:
            raise RuntimeError("No certificates were found in the Windows certificate store")

        handle = tempfile.NamedTemporaryFile(
            "w",
            encoding="ascii",
            prefix="pbirs-windows-ca-",
            suffix=".pem",
            delete=False,
        )
        with handle:
            handle.write("\n".join(certificates))
        self._windows_ca_bundle = handle.name
        return self._windows_ca_bundle

    def _request_ntlm(
        self, method: str, url: str, data: dict | None, raw: bool
    ) -> Any:
        """Execute request using requests-ntlm for Windows authentication."""
        headers = {"Accept": "application/json"}
        kwargs: dict[str, Any] = {"headers": headers, "timeout": 60}
        kwargs["verify"] = self._requests_verify()
        if data is not None:
            headers["Content-Type"] = "application/json"
            kwargs["json"] = data

        resp = self._session.request(method, url, **kwargs)
        if resp.status_code == 401:
            raise PermissionError(self._authentication_guidance())
        resp.raise_for_status()

        if raw:
            return resp.content
        return resp.json() if resp.text else {}

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

    def get_item_policy_details(self, item_id: str) -> dict[str, Any]:
        """Get item policies together with the PBIRS inheritance flag."""
        result = self._get(f"CatalogItems({item_id})/Policies")
        if isinstance(result, list):
            return {"policies": result, "inherit_parent_policy": None}
        return {
            "policies": result.get("Policies", result.get("value", [])),
            "inherit_parent_policy": result.get("InheritParentPolicy"),
        }

    def get_item_policies(self, item_id: str) -> list[dict]:
        """Get security policies (role assignments) for an item."""
        return self.get_item_policy_details(item_id)["policies"]

    def get_system_policies(self) -> list[dict]:
        """Get system-level security policies."""
        result = self._get("System/Policies")
        if isinstance(result, list):
            return result
        return result.get("Policies", result.get("value", []))

    # ------------------------------------------------------------------
    # Cache refresh plans
    # ------------------------------------------------------------------

    def list_cache_refresh_plans(self, item_id: str) -> list[dict]:
        """List cache refresh plans for a catalog item."""
        return self._paginated_get(f"CatalogItems({item_id})/CacheRefreshPlans")
