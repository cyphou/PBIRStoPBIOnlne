"""Fake PBIRS Server — in-process simulator for integration tests.

Simulates a Power BI Report Server REST API v2.0 using stdlib
http.server.  Starts on a random free port and serves realistic
catalog items, datasources, policies, and downloadable content.

Usage in tests
--------------
>>> from tests.fake_pbirs_server import FakePBIRS
>>> with FakePBIRS() as server:
...     client = PBIRSClient(server.url, token="test")
...     items = client.list_catalog_items()

All item names, folder paths, and descriptions deliberately include
French accents (é, è, ê, ë, à, ç, ù, ô, î, ï, â, û, ü) to validate
the full encoding pipeline.
"""

import io
import json
import re
import threading
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any
from urllib.parse import urlparse, parse_qs, unquote

# ---------------------------------------------------------------------------
# Realistic French-accented test data
# ---------------------------------------------------------------------------

FOLDERS = [
    {"Id": "f-001", "Name": "Département Finance",
     "Path": "/Département Finance", "Type": "Folder",
     "Description": "Rapports financiers — résumé trimestriel"},
    {"Id": "f-002", "Name": "Équipe Commerciale",
     "Path": "/Équipe Commerciale", "Type": "Folder",
     "Description": "Données de l'équipe des ventes"},
    {"Id": "f-003", "Name": "Contrôle Qualité",
     "Path": "/Contrôle Qualité", "Type": "Folder",
     "Description": "Métriques qualité et traçabilité"},
    {"Id": "f-004", "Name": "Gestion des Employés",
     "Path": "/Gestion des Employés", "Type": "Folder",
     "Description": "Suivi des congés et évaluations"},
]

POWER_BI_REPORTS = [
    {
        "Id": "pbir-001",
        "Name": "Résumé des Ventes",
        "Path": "/Département Finance/Résumé des Ventes",
        "Type": "PowerBIReport",
        "Description": "Tableau de bord interactif — chiffre d'affaires",
        "CreatedBy": "François Müller",
        "ModifiedBy": "Hélène Béréziat",
        "HasDataSources": True,
        "Size": 2_500_000,
    },
    {
        "Id": "pbir-002",
        "Name": "Prévisions Budgétaires",
        "Path": "/Département Finance/Prévisions Budgétaires",
        "Type": "PowerBIReport",
        "Description": "Prévisions à 12 mois — scénarios optimiste/pessimiste",
        "CreatedBy": "André Lefèvre",
        "ModifiedBy": "André Lefèvre",
        "HasDataSources": True,
        "Size": 1_800_000,
    },
    {
        "Id": "pbir-003",
        "Name": "Indicateurs Clés Régionaux",
        "Path": "/Équipe Commerciale/Indicateurs Clés Régionaux",
        "Type": "PowerBIReport",
        "Description": "KPIs par région — Île-de-France, Rhône-Alpes, Côte d'Azur",
        "CreatedBy": "Céline Guérin",
        "ModifiedBy": "Noël Étienne",
        "HasDataSources": True,
        "Size": 3_200_000,
    },
]

PAGINATED_REPORTS = [
    {
        "Id": "rdl-001",
        "Name": "Factures Échues",
        "Path": "/Département Finance/Factures Échues",
        "Type": "Report",
        "Description": "Rapport paginé — factures en retard > 30 jours",
        "CreatedBy": "Benoît Crépeau",
        "HasParameters": True,
    },
    {
        "Id": "rdl-002",
        "Name": "Évaluation des Employés",
        "Path": "/Gestion des Employés/Évaluation des Employés",
        "Type": "Report",
        "Description": "Grille d'évaluation semestrielle",
        "CreatedBy": "Stéphanie Noël",
        "HasParameters": False,
    },
]

DATASETS = [
    {
        "Id": "ds-001",
        "Name": "Données Financières Consolidées",
        "Path": "/Département Finance/Données Financières Consolidées",
        "Type": "DataSet",
        "Description": "Modèle de données — comptes généraux & analytiques",
    },
]

KPIS = [
    {
        "Id": "kpi-001",
        "Name": "Taux de Réussite",
        "Path": "/Contrôle Qualité/Taux de Réussite",
        "Type": "Kpi",
        "Description": "Pourcentage de conformité — objectif ≥ 95%",
    },
]

MOBILE_REPORTS = [
    {
        "Id": "mob-001",
        "Name": "Récapitulatif Mobile",
        "Path": "/Équipe Commerciale/Récapitulatif Mobile",
        "Type": "MobileReport",
        "Description": "Rapport mobile (déprécié) — à migrer manuellement",
    },
]

ALL_ITEMS = FOLDERS + POWER_BI_REPORTS + PAGINATED_REPORTS + DATASETS + KPIS + MOBILE_REPORTS

DATASOURCES = {
    "pbir-001": [
        {
            "Id": "dsrc-001",
            "Name": "SQLServer Données Finance",
            "ConnectionString": "Data Source=sql-paris.corp.local;Initial Catalog=Données_Finance",
            "DataSourceType": "SQL",
            "IsEnabled": True,
            "CredentialsByUser": {"DisplayText": "François Müller"},
        }
    ],
    "pbir-002": [
        {
            "Id": "dsrc-002",
            "Name": "Azure SQL Prévisions",
            "ConnectionString": "Data Source=previsions.database.windows.net;Initial Catalog=BudgetDB",
            "DataSourceType": "SQL",
            "IsEnabled": True,
        }
    ],
    "pbir-003": [
        {
            "Id": "dsrc-003",
            "Name": "Excel Région Île-de-France",
            "ConnectionString": "file://\\\\serveur-données\\Partage\\Régions\\IDF.xlsx",
            "DataSourceType": "EXCEL",
            "IsEnabled": True,
        },
        {
            "Id": "dsrc-004",
            "Name": "Oracle Côte d'Azur",
            "ConnectionString": "Data Source=oracle-nice;User ID=ventes_côte",
            "DataSourceType": "ORACLE",
            "IsEnabled": True,
        },
    ],
    "rdl-001": [
        {
            "Id": "dsrc-005",
            "Name": "SQL Factures",
            "ConnectionString": "Data Source=sql-paris.corp.local;Initial Catalog=Comptabilité",
            "DataSourceType": "SQL",
        }
    ],
    "rdl-002": [
        {
            "Id": "dsrc-006",
            "Name": "SQL Employés",
            "ConnectionString": "Data Source=sql-rh.corp.local;Initial Catalog=GestionRH_Évaluations",
            "DataSourceType": "SQL",
        }
    ],
}

POLICIES = {
    "pbir-001": [
        {"GroupUserName": "CORP\\Département_Finance", "Roles": [{"Name": "Browser"}]},
        {"GroupUserName": "CORP\\François.Müller", "Roles": [{"Name": "Content Manager"}]},
    ],
    "pbir-003": [
        {"GroupUserName": "CORP\\Équipe_Ventes", "Roles": [{"Name": "Browser"}]},
        {"GroupUserName": "CORP\\Céline.Guérin", "Roles": [{"Name": "Publisher"}]},
    ],
    "rdl-001": [
        {"GroupUserName": "CORP\\Comptabilité", "Roles": [{"Name": "Report Builder"}]},
    ],
    "rdl-002": [
        {"GroupUserName": "CORP\\RH_Équipe", "Roles": [{"Name": "Browser"}, {"Name": "Publisher"}]},
    ],
}

SUBSCRIPTIONS = {
    "rdl-001": [
        {
            "Id": "sub-001",
            "Description": "Envoi hebdomadaire — Factures Échues",
            "DeliveryExtension": "Report Server Email",
            "IsDataDriven": False,
            "Schedule": {"ScheduleID": "sched-001", "Definition": {"StartDateTime": "2024-01-08T08:00:00"}},
        },
    ],
    "rdl-002": [
        {
            "Id": "sub-002",
            "Description": "Évaluation semestrielle — données confidentielles",
            "DeliveryExtension": "Report Server FileShare",
            "IsDataDriven": True,
            "Schedule": {"ScheduleID": "sched-002"},
        },
    ],
}

# Fake .pbix content — valid ZIP header + marker
FAKE_PBIX = b"PK\x03\x04" + b"\x00" * 20 + b"FakePBIX-\xc3\xa9\xc3\xa0\xc3\xa7" + b"\x00" * 200
# Fake .rdl content — XML with accented chars
FAKE_RDL = """\
<?xml version="1.0" encoding="utf-8"?>
<Report xmlns="http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition">
  <Description>Rapport de test — données avec accents: éèêëàçùôîïâûüö</Description>
  <DataSources>
    <DataSource Name="SQL_Données">
      <ConnectionProperties>
        <DataProvider>SQL</DataProvider>
        <ConnectString>Data Source=sql-paris;Initial Catalog=Données_Finance</ConnectString>
      </ConnectionProperties>
    </DataSource>
  </DataSources>
  <Body>
    <ReportItems>
      <Tablix Name="Résumé_Financier">
        <TablixBody>
          <TablixColumns><TablixColumn><Width>5cm</Width></TablixColumn></TablixColumns>
          <TablixRows><TablixRow><Height>0.6cm</Height></TablixRow></TablixRows>
        </TablixBody>
      </Tablix>
    </ReportItems>
  </Body>
</Report>
""".encode("utf-8")


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

class _FakePBIRSHandler(BaseHTTPRequestHandler):
    """Handles PBIRS REST API v2.0 requests with French-accented data."""

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        qs = parse_qs(parsed.query)

        # Strip API prefix
        api_path = re.sub(r"^/api/v2\.0/", "", path)

        # --- System endpoints ---
        if api_path == "System":
            self._json_ok({
                "ProductName": "Power BI Report Server",
                "ProductVersion": "15.0.1103.260",
                "BuildVersion": "15.0.1103.260",
                "Edition": "Developer (64-bit)",
            })
            return

        if api_path == "System/Properties":
            self._json_ok({
                "SiteName": "Serveur de Rapports — Développement",
                "ReportServerUrl": self.server.base_url,
            })
            return

        # --- Catalog items ---
        if api_path == "CatalogItems":
            items = list(ALL_ITEMS)
            filt = qs.get("$filter", [None])[0]
            if filt:
                match = re.search(r"startswith\(Path,'(.+?)'\)", filt)
                if match:
                    prefix = match.group(1).replace("''", "'")
                    items = [i for i in items if i["Path"].startswith(prefix)]
            items = self._paginate(items, qs)
            self._json_ok({"value": items})
            return

        # CatalogItems({id})/...
        m = re.match(r"CatalogItems\(([^)]+)\)(.*)", api_path)
        if m:
            item_id = m.group(1)
            suffix = m.group(2)
            item = self._find(item_id)
            if not item:
                self._error(404, f"Item {item_id} not found")
                return
            if suffix == "":
                self._json_ok(item)
            elif suffix == "/Content/$value":
                self._send_content(item)
            elif suffix == "/Policies":
                policies = POLICIES.get(item_id, [])
                self._json_ok({"Policies": policies})
            elif suffix == "/DataSources":
                ds = DATASOURCES.get(item_id, [])
                self._json_ok({"value": ds})
            elif suffix == "/CacheRefreshPlans":
                self._json_ok({"value": []})
            else:
                self._error(404, f"Unknown suffix: {suffix}")
            return

        # --- Typed endpoints ---
        if api_path == "PowerBIReports":
            self._json_ok({"value": self._paginate(POWER_BI_REPORTS, qs)})
            return
        if api_path == "Reports":
            self._json_ok({"value": self._paginate(PAGINATED_REPORTS, qs)})
            return
        if api_path == "DataSets":
            self._json_ok({"value": self._paginate(DATASETS, qs)})
            return
        if api_path == "Kpis":
            self._json_ok({"value": self._paginate(KPIS, qs)})
            return
        if api_path == "Folders":
            self._json_ok({"value": self._paginate(FOLDERS, qs)})
            return
        if api_path == "DataSources":
            all_ds = [ds for dsl in DATASOURCES.values() for ds in dsl]
            self._json_ok({"value": self._paginate(all_ds, qs)})
            return
        if api_path == "Subscriptions":
            all_subs = [s for sl in SUBSCRIPTIONS.values() for s in sl]
            self._json_ok({"value": self._paginate(all_subs, qs)})
            return

        # --- Per-item typed endpoints ---
        for prefix, collection in [
            ("PowerBIReports", POWER_BI_REPORTS),
            ("Reports", PAGINATED_REPORTS),
            ("DataSets", DATASETS),
            ("Kpis", KPIS),
        ]:
            m = re.match(rf"{prefix}\(([^)]+)\)(.*)", api_path)
            if m:
                item_id, suffix = m.group(1), m.group(2)
                item = next((i for i in collection if i["Id"] == item_id), None)
                if not item:
                    self._error(404, f"{prefix} {item_id} not found")
                    return
                if suffix == "":
                    self._json_ok(item)
                elif suffix == "/Content/$value":
                    self._send_content(item)
                elif suffix == "/DataSources":
                    ds = DATASOURCES.get(item_id, [])
                    self._json_ok({"value": ds})
                elif suffix == "/ParameterDefinitions":
                    self._json_ok({"value": []})
                elif suffix == "/Policies":
                    policies = POLICIES.get(item_id, [])
                    self._json_ok({"Policies": policies})
                else:
                    self._error(404, f"Unknown suffix: {suffix}")
                return

        self._error(404, f"Unknown endpoint: {api_path}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find(self, item_id: str) -> dict | None:
        return next((i for i in ALL_ITEMS if i["Id"] == item_id), None)

    def _send_content(self, item: dict) -> None:
        """Return fake binary content for an item."""
        item_type = item.get("Type", "")
        if item_type == "PowerBIReport":
            data = FAKE_PBIX
            ctype = "application/octet-stream"
        elif item_type == "Report":
            data = FAKE_RDL
            ctype = "application/xml; charset=utf-8"
        elif item_type == "DataSet":
            data = b"<SharedDataSet/>"
            ctype = "application/xml"
        else:
            self._error(400, f"No content for type {item_type}")
            return

        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _paginate(self, items: list, qs: dict) -> list:
        skip = int(qs.get("$skip", [0])[0])
        top = int(qs.get("$top", [100])[0])
        return items[skip : skip + top]

    def _json_ok(self, data: Any) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, code: int, msg: str) -> None:
        body = json.dumps({"error": {"code": str(code), "message": msg}}).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress request logging during tests."""
        pass


# ---------------------------------------------------------------------------
# Server wrapper
# ---------------------------------------------------------------------------

class FakePBIRS:
    """Context manager that runs a fake PBIRS server in a background thread.

    >>> with FakePBIRS() as server:
    ...     print(server.url)        # http://127.0.0.1:{port}
    ...     print(server.api_url)    # http://127.0.0.1:{port}/api/v2.0
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self._server = HTTPServer((host, port), _FakePBIRSHandler)
        self._server.base_url = f"http://{host}:{self._server.server_address[1]}"
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return self._server.base_url

    @property
    def api_url(self) -> str:
        return f"{self.url}/api/v2.0"

    def __enter__(self) -> "FakePBIRS":
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._server.shutdown()
        if self._thread:
            self._thread.join(timeout=5)


# ---------------------------------------------------------------------------
# Quick smoke test when run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    with FakePBIRS() as server:
        print(f"Fake PBIRS running at {server.url}")
        import urllib.request
        url = f"{server.api_url}/CatalogItems"
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        print(f"  {len(data['value'])} catalog items")
        for item in data["value"]:
            print(f"  - [{item['Type']}] {item['Name']}  ({item['Path']})")
        print("\nAll items have French accents ✓")
