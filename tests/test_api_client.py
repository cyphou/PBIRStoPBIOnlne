"""Tests for PBIRSClient API client."""

import json
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
