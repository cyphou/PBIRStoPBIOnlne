"""Tests for PermissionMapper."""

import pytest
from pbi_import.permission_mapper import PermissionMapper, ROLE_MAP


class TestPermissionMapper:

    def test_map_empty_permissions(self, mock_pbi_client):
        mapper = PermissionMapper(mock_pbi_client)
        result = mapper.map_permissions({"item_policies": []}, "ws-001")
        assert result["assigned"] == []

    def test_map_browser_to_viewer(self, mock_pbi_client):
        permissions = {
            "item_policies": [{
                "item_path": "/Reports/Test",
                "policies": [{
                    "GroupUserName": "user@corp.com",
                    "Roles": [{"Name": "Browser"}],
                }],
            }]
        }
        mapper = PermissionMapper(mock_pbi_client)
        result = mapper.map_permissions(permissions, "ws-001")
        assert len(result["assigned"]) == 1
        assert result["assigned"][0]["role"] == "Viewer"

    def test_map_content_manager_to_admin(self, mock_pbi_client):
        permissions = {
            "item_policies": [{
                "item_path": "/Reports/Admin",
                "policies": [{
                    "GroupUserName": "admin@corp.com",
                    "Roles": [{"Name": "Content Manager"}],
                }],
            }]
        }
        mapper = PermissionMapper(mock_pbi_client)
        result = mapper.map_permissions(permissions, "ws-001")
        assert result["assigned"][0]["role"] == "Admin"

    def test_highest_role_wins(self, mock_pbi_client):
        permissions = {
            "item_policies": [
                {
                    "item_path": "/A",
                    "policies": [{
                        "GroupUserName": "multi@corp.com",
                        "Roles": [{"Name": "Browser"}],
                    }],
                },
                {
                    "item_path": "/B",
                    "policies": [{
                        "GroupUserName": "multi@corp.com",
                        "Roles": [{"Name": "Content Manager"}],
                    }],
                },
            ]
        }
        mapper = PermissionMapper(mock_pbi_client)
        result = mapper.map_permissions(permissions, "ws-001")
        assert len(result["assigned"]) == 1
        assert result["assigned"][0]["role"] == "Admin"

    def test_dry_run(self, mock_pbi_client):
        permissions = {
            "item_policies": [{
                "item_path": "/Reports/Test",
                "policies": [{
                    "GroupUserName": "user@corp.com",
                    "Roles": [{"Name": "Browser"}],
                }],
            }]
        }
        mapper = PermissionMapper(mock_pbi_client)
        result = mapper.map_permissions(permissions, "ws-001", dry_run=True)
        assert result["assigned"][0]["dry_run"] is True
        mock_pbi_client.add_workspace_user.assert_not_called()

    def test_generate_mapping_report(self, mock_pbi_client):
        permissions = {
            "item_policies": [{
                "item_path": "/Reports/Test",
                "policies": [{
                    "GroupUserName": "user@corp.com",
                    "Roles": [{"Name": "Browser"}, {"Name": "Publisher"}],
                }],
            }]
        }
        mapper = PermissionMapper(mock_pbi_client)
        report = mapper.generate_mapping_report(permissions)
        assert report["total"] == 2
