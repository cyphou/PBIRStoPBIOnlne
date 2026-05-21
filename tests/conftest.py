"""Shared test fixtures."""

import json
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def sample_catalog():
    """Sample PBIRS catalog for testing."""
    return {
        "server_info": {"ProductName": "Power BI Report Server", "ProductVersion": "15.0.1"},
        "items": [
            {
                "Id": "id-001",
                "Name": "Sales Dashboard",
                "Path": "/Finance/Sales Dashboard",
                "Type": "PowerBIReport",
                "datasources": [
                    {"ConnectionString": "Data Source=sqlserver.corp.local;Initial Catalog=SalesDB", "DataSourceType": "SQL"}
                ],
                "policies": [
                    {"GroupUserName": "DOMAIN\\ReportViewers", "Roles": [{"Name": "Browser"}]}
                ],
                "subscriptions": [],
                "custom_visuals": [],
            },
            {
                "Id": "id-002",
                "Name": "Invoice Report",
                "Path": "/Finance/Invoice Report",
                "Type": "Report",
                "datasources": [
                    {"ConnectionString": "Data Source=sqlserver.corp.local;Initial Catalog=InvoiceDB"}
                ],
                "policies": [],
                "subscriptions": [
                    {"Description": "Weekly Invoice", "DeliveryExtension": "Report Server Email", "IsDataDriven": False}
                ],
                "rdl_features": set(),
                "custom_visuals": [],
            },
            {
                "Id": "id-003",
                "Name": "KPI Overview",
                "Path": "/KPIs/KPI Overview",
                "Type": "Kpi",
                "datasources": [],
                "policies": [],
                "subscriptions": [],
                "custom_visuals": [],
            },
        ],
        "folders": [
            {"path": "/Finance", "items": []},
            {"path": "/KPIs", "items": []},
        ],
        "total_count": 3,
    }


@pytest.fixture
def sample_assessment(sample_catalog):
    """Pre-computed assessment result."""
    from pbirs_export.assessment import MigrationAssessment
    return MigrationAssessment().assess(sample_catalog)


@pytest.fixture
def mock_pbi_client():
    """Mock PBI Online REST API client."""
    client = MagicMock()
    client.list_workspaces.return_value = []
    client.create_workspace.return_value = {"id": "ws-001", "name": "Test Workspace"}
    client.list_reports.return_value = []
    client.list_datasets.return_value = []
    client.list_gateways.return_value = []
    client.import_pbix.return_value = {"id": "import-001", "datasets": [{"id": "ds-001"}]}
    return client


@pytest.fixture
def mock_pbirs_client():
    """Mock PBIRS API client."""
    client = MagicMock()
    client.get_system_info.return_value = {"ProductName": "Power BI Report Server"}
    client.list_catalog_items.return_value = []
    client.list_subscriptions.return_value = []
    client.list_schedules.return_value = []
    return client


@pytest.fixture
def tmp_output(tmp_path):
    """Temporary output directory."""
    return tmp_path / "output"
