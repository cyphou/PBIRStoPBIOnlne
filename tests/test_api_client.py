"""Tests for PBIRSClient API client."""

import json
import urllib.error
import pytest
from unittest.mock import patch, MagicMock
from pbirs_export.api_client import PBIRSClient


class TestPBIRSClient:

    def test_init_basic_auth(self):
        client = PBIRSClient("https://pbirs.local/reports", username="user", password="pass")
        assert client._base_url == "https://pbirs.local/reports/api/v2.0"
        assert client.username == "user"

    def test_init_bearer_auth(self):
        client = PBIRSClient("https://pbirs.local/reports", token="tok123")
        assert client.token == "tok123"

    def test_init_loads_auth_from_environment(self, monkeypatch):
        monkeypatch.setenv("PBIRS_USERNAME", "DOMAIN\\migration.user")
        monkeypatch.setenv("PBIRS_PASSWORD", "secret")

        client = PBIRSClient("https://pbirs.local/reports", use_windows_auth=True)

        assert client.username == "DOMAIN\\migration.user"
        assert client.password == "secret"

    def test_init_strips_trailing_slash(self):
        client = PBIRSClient("https://pbirs.local/reports/", use_windows_auth=True)
        assert client._base_url == "https://pbirs.local/reports/api/v2.0"

    @patch("urllib.request.urlopen")
    def test_get_system_info(self, mock_urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps({"ProductName": "PBIRS"}).encode()
        response.headers = MagicMock()
        response.headers.get.return_value = None
        response.__enter__ = lambda s: s
        response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = response

        client = PBIRSClient("https://pbirs.local/reports", token="tok")
        info = client.get_system_info()
        assert info["ProductName"] == "PBIRS"

    def test_get_system_policies_accepts_odata_value_envelope(self):
        policies = [
            {
                "GroupUserName": "DOMAIN\\Admins",
                "Roles": [{"Name": "System Administrator"}],
            },
        ]
        client = PBIRSClient("https://pbirs.local/reports", token="tok")
        client._get = MagicMock(return_value={"@odata.context": "metadata", "value": policies})

        assert client.get_system_policies() == policies

    def test_get_item_policy_details_preserves_inheritance_flag(self):
        policies = [
            {
                "GroupUserName": "DOMAIN\\Readers",
                "Roles": [{"Name": "Browser"}],
            },
        ]
        client = PBIRSClient("https://pbirs.local/reports", token="tok")
        client._get = MagicMock(return_value={
            "InheritParentPolicy": True,
            "Policies": policies,
        })

        assert client.get_item_policy_details("item-1") == {
            "policies": policies,
            "inherit_parent_policy": True,
        }

    @patch("urllib.request.urlopen")
    def test_list_catalog_items(self, mock_urlopen):
        items = [{"Id": "1", "Name": "Report1", "Type": "PowerBIReport"}]
        response = MagicMock()
        response.read.return_value = json.dumps({"value": items}).encode()
        response.headers = MagicMock()
        response.headers.get.return_value = None
        response.__enter__ = lambda s: s
        response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = response

        client = PBIRSClient("https://pbirs.local/reports", token="tok")
        result = client.list_catalog_items()
        assert len(result) == 1
        assert result[0]["Name"] == "Report1"

    @patch("urllib.request.urlopen")
    def test_unauthenticated_401_explains_windows_auth(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://pbirs.local/reports/api/v2.0/CatalogItems",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=None,
        )

        client = PBIRSClient("https://pbirs.local/reports")
        with pytest.raises(urllib.error.HTTPError, match="--use-windows-auth"):
            client.list_catalog_items()

    @patch("urllib.request.urlopen")
    def test_bearer_401_explains_token_replacement(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://pbirs.local/reports/api/v2.0/CatalogItems",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=None,
        )

        client = PBIRSClient("https://pbirs.local/reports", token="expired")
        with pytest.raises(urllib.error.HTTPError, match="token was rejected"):
            client.list_catalog_items()

    def test_ntlm_401_explains_explicit_windows_credentials(self):
        client = PBIRSClient("https://pbirs.local/reports", use_windows_auth=True)
        response = MagicMock(status_code=401, text="Unauthorized")
        response.raise_for_status.side_effect = RuntimeError("401 Unauthorized")
        client._session = MagicMock()
        client._session.request.return_value = response

        with pytest.raises(PermissionError, match=r"DOMAIN\\user"):
            client.list_catalog_items()
