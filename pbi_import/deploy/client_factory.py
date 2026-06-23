"""
Client Factory — build a configured :class:`PBIClient` from CLI args or env.

Resolution order for each value: explicit kwarg → CLI namespace → env var
(``AZURE_TENANT_ID``, ``AZURE_CLIENT_ID``, ``AZURE_CLIENT_SECRET``,
``PBI_ACCESS_TOKEN``).
"""

import logging
import os
from typing import Any

from pbi_import.deploy.auth import PBIAuth
from pbi_import.deploy.pbi_client import PBIClient

logger = logging.getLogger(__name__)


class PbiClientFactory:
    """Resolve credentials and instantiate a token-backed :class:`PBIClient`."""

    @staticmethod
    def from_args(args: Any) -> PBIClient:
        """Build a :class:`PBIClient` from an argparse namespace."""
        token = getattr(args, "pbi_token", None) or os.environ.get("PBI_ACCESS_TOKEN")
        if token:
            logger.info("Using pre-acquired PBI access token")
            return PBIClient(access_token=token)

        tenant_id = getattr(args, "tenant_id", None) or os.environ.get("AZURE_TENANT_ID")
        client_id = getattr(args, "client_id", None) or os.environ.get("AZURE_CLIENT_ID")
        client_secret = getattr(args, "client_secret", None) or os.environ.get("AZURE_CLIENT_SECRET")

        if not tenant_id or not client_id:
            raise RuntimeError(
                "PBI Online auth requires --tenant-id and --client-id "
                "(or AZURE_TENANT_ID / AZURE_CLIENT_ID env vars), or a --pbi-token."
            )

        flow = "service principal" if client_secret else "device code"
        logger.info("Acquiring PBI Online token via %s flow", flow)

        auth = PBIAuth(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
        return PBIClient(token_provider=auth.get_token)
