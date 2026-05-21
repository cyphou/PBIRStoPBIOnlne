"""
Deploy Config — deployment configuration loader for PBI Online migration.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DeployConfig:
    """Load and validate deployment configuration."""

    REQUIRED_KEYS = ("tenant_id", "client_id", "workspace_name")

    def __init__(self, config: dict):
        self._config = config

    @classmethod
    def from_file(cls, path: str) -> "DeployConfig":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    @classmethod
    def from_env(cls) -> "DeployConfig":
        return cls({
            "tenant_id": os.environ.get("AZURE_TENANT_ID", ""),
            "client_id": os.environ.get("AZURE_CLIENT_ID", ""),
            "client_secret": os.environ.get("AZURE_CLIENT_SECRET", ""),
            "workspace_name": os.environ.get("PBI_WORKSPACE_NAME", ""),
            "capacity_id": os.environ.get("PBI_CAPACITY_ID", ""),
        })

    def validate(self) -> list[str]:
        errors = []
        for key in self.REQUIRED_KEYS:
            if not self._config.get(key):
                errors.append(f"Missing required config: {key}")
        return errors

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    @property
    def tenant_id(self) -> str:
        return self._config.get("tenant_id", "")

    @property
    def client_id(self) -> str:
        return self._config.get("client_id", "")

    @property
    def client_secret(self) -> str:
        return self._config.get("client_secret", "")

    @property
    def workspace_name(self) -> str:
        return self._config.get("workspace_name", "")

    @property
    def capacity_id(self) -> str:
        return self._config.get("capacity_id", "")
