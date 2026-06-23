"""
Auth — Azure AD / Entra ID authentication for PBI Online REST API.

Supports service principal (client_credentials) and user-delegated (device_code) flows.
Tokens are cached with their ``expires_in`` lifetime and re-acquired before
expiry (60-second safety margin) on the next :meth:`get_token` call.
"""

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

PBI_RESOURCE = "https://analysis.windows.net/powerbi/api"
PBI_SCOPE = f"{PBI_RESOURCE}/.default"
EXPIRY_MARGIN_SECONDS = 60


class PBIAuth:
    """Acquire Azure AD tokens for Power BI REST API."""

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str | None = None,
        authority: str | None = None,
    ):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.authority = authority or f"https://login.microsoftonline.com/{tenant_id}"
        self._token: str | None = None
        self._expires_at: float = 0.0

    def get_token(self) -> str:
        """Return a valid access token, refreshing if expired or near-expiry.

        A token set directly on ``self._token`` (e.g. via tests or callers
        injecting a pre-acquired bearer) is honoured even when no expiry has
        been recorded yet.
        """
        if self._token:
            if self._expires_at == 0.0:
                return self._token
            if time.monotonic() < self._expires_at - EXPIRY_MARGIN_SECONDS:
                return self._token

        if self.client_secret:
            self._token, lifetime = self._acquire_sp_token()
        else:
            self._token, lifetime = self._acquire_device_code_token()

        self._expires_at = time.monotonic() + lifetime
        return self._token

    def _acquire_sp_token(self) -> tuple[str, float]:
        """Acquire token using client credentials (service principal)."""
        try:
            from msal import ConfidentialClientApplication
        except ImportError:
            raise ImportError("msal is required for service principal auth — pip install msal")

        app = ConfidentialClientApplication(
            self.client_id,
            authority=self.authority,
            client_credential=self.client_secret,
        )

        result = app.acquire_token_for_client(scopes=[PBI_SCOPE])
        if "access_token" not in result:
            raise RuntimeError(f"Token acquisition failed: {result.get('error_description', result)}")

        return result["access_token"], float(result.get("expires_in", 3600))

    def _acquire_device_code_token(self) -> tuple[str, float]:
        """Acquire token using device code flow (interactive)."""
        try:
            from msal import PublicClientApplication
        except ImportError:
            raise ImportError("msal is required for device code auth — pip install msal")

        app = PublicClientApplication(self.client_id, authority=self.authority)
        flow = app.initiate_device_flow(scopes=[PBI_SCOPE])
        if "user_code" not in flow:
            raise RuntimeError(f"Device flow initiation failed: {flow}")

        logger.info("To sign in, visit %s and enter code: %s", flow["verification_uri"], flow["user_code"])
        print(f"\nTo sign in, visit {flow['verification_uri']} and enter code: {flow['user_code']}\n")

        result = app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise RuntimeError(f"Token acquisition failed: {result.get('error_description', result)}")

        return result["access_token"], float(result.get("expires_in", 3600))

    @classmethod
    def from_env(cls) -> "PBIAuth":
        """Create PBIAuth from environment variables."""
        return cls(
            tenant_id=os.environ["AZURE_TENANT_ID"],
            client_id=os.environ["AZURE_CLIENT_ID"],
            client_secret=os.environ.get("AZURE_CLIENT_SECRET"),
        )