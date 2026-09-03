"""Tests for PBIRSClient API client."""

import json
import urllib.error
import pytest
from unittest.mock import patch, MagicMock
import pbirs_export.api_client as api_client
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
        monkeypatch.setenv("PBIRS_CA_BUNDLE", "C:/certs/corp-root.pem")
        monkeypatch.setenv("PBIRS_USE_WINDOWS_CERT_STORE", "true")

        client = PBIRSClient("https://pbirs.local/reports", use_windows_auth=True)

        assert client.username == "DOMAIN\\migration.user"
        assert client.password == "secret"
        assert client.ca_bundle == "C:/certs/corp-root.pem"
        assert client.use_windows_cert_store is True

    def test_init_strips_trailing_slash(self):
        client = PBIRSClient("https://pbirs.local/reports/", use_windows_auth=True)
        assert client._base_url == "https://pbirs.local/reports/api/v2.0"

    def test_ntlm_auth_uses_current_windows_logon_by_default(self, monkeypatch):
        monkeypatch.delenv("PBIRS_USERNAME", raising=False)
        monkeypatch.delenv("PBIRS_PASSWORD", raising=False)

        client = PBIRSClient("https://pbirs.local/reports", use_windows_auth=True)

        assert client._session.auth.username is None
        assert client._session.auth.password is None

    def test_windows_cert_store_defaults_on_windows(self, monkeypatch):
        monkeypatch.delenv("PBIRS_USE_WINDOWS_CERT_STORE", raising=False)
        monkeypatch.setattr(api_client.os, "name", "nt")

        client = PBIRSClient("https://pbirs.local/reports", use_windows_auth=True)

        assert client.use_windows_cert_store is True

    def test_windows_cert_store_can_be_disabled(self, monkeypatch):
        monkeypatch.delenv("PBIRS_USE_WINDOWS_CERT_STORE", raising=False)
        monkeypatch.setattr(api_client.os, "name", "nt")

        client = PBIRSClient(
            "https://pbirs.local/reports",
            use_windows_auth=True,
            use_windows_cert_store=False,
        )

        assert client.use_windows_cert_store is False

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

    def test_ntlm_request_uses_ca_bundle(self):
        client = PBIRSClient(
            "https://pbirs.local/reports",
            token="tok",
            use_windows_auth=True,
            ca_bundle="C:/certs/corp-root.pem",
        )
        response = MagicMock(status_code=200, text='{"value": []}')
        response.raise_for_status.return_value = None
        response.json.return_value = {"value": []}
        client._session = MagicMock()
        client._session.request.return_value = response

        assert client.list_catalog_items() == []

        _, _, kwargs = client._session.request.mock_calls[0]
        assert kwargs["verify"] == "C:/certs/corp-root.pem"

    def test_ntlm_request_can_use_windows_cert_store(self):
        client = PBIRSClient(
            "https://pbirs.local/reports",
            token="tok",
            use_windows_auth=True,
            use_windows_cert_store=True,
        )
        client._get_windows_ca_bundle = MagicMock(return_value="C:/Temp/windows-ca.pem")
        response = MagicMock(status_code=200, text='{"value": []}')
        response.raise_for_status.return_value = None
        response.json.return_value = {"value": []}
        client._session = MagicMock()
        client._session.request.return_value = response

        assert client.list_catalog_items() == []

        _, _, kwargs = client._session.request.mock_calls[0]
        assert kwargs["verify"] == "C:/Temp/windows-ca.pem"
