"""French accent and fake PBIRS integration tests.

Validates that the entire pipeline handles French diacritics (é, è, ê, ë,
à, ç, ù, ô, î, ï, â, û, ü, ö) correctly — from API extraction through
assessment, conversion, and HTML reporting.

Uses the FakePBIRS in-process HTTP server to exercise the real
PBIRSClient against realistic French-accented data.
"""

import json
from pathlib import Path

import pytest

from pbirs_export.api_client import PBIRSClient
from pbirs_export.assessment import MigrationAssessment, GREEN, YELLOW, RED
from pbi_import.converter import ContentConverter
from pbi_import.permission_mapper import PermissionMapper

from tests.fake_pbirs_server import (
    FakePBIRS,
    ALL_ITEMS,
    POWER_BI_REPORTS,
    PAGINATED_REPORTS,
    FOLDERS,
    DATASETS,
    KPIS,
    DATASOURCES,
    POLICIES,
    SUBSCRIPTIONS,
)


# ---------------------------------------------------------------------------
# Fixture: live fake server
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fake_server():
    """Start a fake PBIRS server for the entire module."""
    with FakePBIRS() as server:
        yield server


@pytest.fixture
def client(fake_server):
    """PBIRSClient pointed at the fake server."""
    return PBIRSClient(fake_server.url, token="test-token")


# ===========================================================================
# 1. PBIRSClient against fake server — accent round-trips
# ===========================================================================


class TestPBIRSClientFrenchAccents:
    """Verify the real HTTP client handles accented names end-to-end."""

    def test_system_info(self, client):
        info = client.get_system_info()
        assert info["ProductName"] == "Power BI Report Server"

    def test_list_all_catalog_items(self, client):
        items = client.list_catalog_items()
        assert len(items) == len(ALL_ITEMS)
        names = [i["Name"] for i in items]
        assert "Résumé des Ventes" in names
        assert "Factures Échues" in names
        assert "Département Finance" in names

    def test_filter_by_accented_folder(self, client):
        """OData filter with accented folder path must return matching items."""
        items = client.list_catalog_items(folder="/Département Finance")
        paths = [i["Path"] for i in items]
        assert all(p.startswith("/Département Finance") for p in paths)
        assert len(items) >= 3  # folder + reports inside it

    def test_filter_folder_with_special_chars(self, client):
        """Folder with É should work."""
        items = client.list_catalog_items(folder="/Équipe Commerciale")
        assert len(items) >= 1
        assert any("Équipe Commerciale" in i["Path"] for i in items)

    def test_get_single_accented_item(self, client):
        item = client.get_catalog_item("pbir-001")
        assert item["Name"] == "Résumé des Ventes"
        assert "chiffre d'affaires" in item["Description"]

    def test_list_powerbi_reports(self, client):
        reports = client.list_powerbi_reports()
        assert len(reports) == len(POWER_BI_REPORTS)
        assert any("Prévisions Budgétaires" == r["Name"] for r in reports)

    def test_list_paginated_reports(self, client):
        reports = client.list_reports()
        assert len(reports) == len(PAGINATED_REPORTS)
        assert any("Évaluation des Employés" == r["Name"] for r in reports)

    def test_list_folders(self, client):
        folders = client.list_folders()
        assert len(folders) == len(FOLDERS)
        names = {f["Name"] for f in folders}
        assert "Contrôle Qualité" in names
        assert "Gestion des Employés" in names

    def test_list_datasets(self, client):
        datasets = client.list_datasets()
        assert any("Données Financières Consolidées" == d["Name"] for d in datasets)

    def test_list_kpis(self, client):
        kpis = client.list_kpis()
        assert any("Taux de Réussite" == k["Name"] for k in kpis)

    def test_datasources_with_accented_connection_string(self, client):
        ds = client.get_powerbi_report_datasources("pbir-003")
        assert len(ds) == 2
        conn_strings = [d["ConnectionString"] for d in ds]
        assert any("Île-de-France" in c or "Régions" in c for c in conn_strings)
        assert any("Côte d'Azur" in c or "côte" in c for c in conn_strings)

    def test_policies_with_accented_groups(self, client):
        policies = client.get_item_policies("pbir-001")
        groups = [p["GroupUserName"] for p in policies]
        assert "CORP\\Département_Finance" in groups
        assert "CORP\\François.Müller" in groups

    def test_download_powerbi_report_content(self, client):
        content = client.download_powerbi_report("pbir-001")
        assert content[:4] == b"PK\x03\x04"  # ZIP header
        assert len(content) > 100

    def test_download_paginated_report_content(self, client):
        content = client.download_report("rdl-001")
        text = content.decode("utf-8")
        assert "<?xml" in text
        assert "éèêëàçùôîïâûüö" in text  # accent stress test in description

    def test_subscriptions_listed(self, client):
        subs = client.list_subscriptions()
        assert len(subs) >= 2
        descs = [s["Description"] for s in subs]
        assert any("Échues" in d for d in descs)
        assert any("Évaluation" in d or "semestrielle" in d for d in descs)

    def test_item_not_found(self, client):
        import urllib.error
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            client.get_catalog_item("nonexistent-id")
        assert exc_info.value.code == 404


# ===========================================================================
# 2. Assessment — accented catalog
# ===========================================================================


class TestAssessmentFrenchAccents:
    """Run MigrationAssessment on an accented catalog built from fake data."""

    @pytest.fixture
    def accented_catalog(self, client):
        """Build a catalog dict from the fake server — all accented."""
        items = []
        for item in ALL_ITEMS:
            entry = dict(item)
            entry["datasources"] = DATASOURCES.get(item["Id"], [])
            entry["policies"] = POLICIES.get(item["Id"], [])
            entry["subscriptions"] = SUBSCRIPTIONS.get(item["Id"], [])
            entry["custom_visuals"] = []
            if item["Type"] == "Report":
                entry["rdl_features"] = set()
            items.append(entry)
        return {"items": items}

    def test_assess_runs_without_encoding_error(self, accented_catalog):
        result = MigrationAssessment().assess(accented_catalog)
        assert "items" in result
        assert "summary" in result

    def test_all_items_scored(self, accented_catalog):
        result = MigrationAssessment().assess(accented_catalog)
        assert len(result["items"]) == len(ALL_ITEMS)

    def test_accented_names_preserved_in_output(self, accented_catalog):
        result = MigrationAssessment().assess(accented_catalog)
        names = [i["name"] for i in result["items"]]
        assert "Résumé des Ventes" in names
        assert "Factures Échues" in names
        assert "Prévisions Budgétaires" in names
        assert "Département Finance" in names

    def test_file_path_datasource_scores_red(self, accented_catalog):
        """The Excel file:// datasource on Île-de-France should score RED."""
        result = MigrationAssessment().assess(accented_catalog)
        regional = next(i for i in result["items"] if i["name"] == "Indicateurs Clés Régionaux")
        assert regional["scores"]["datasource_compatibility"]["score"] == RED

    def test_mobile_report_scores_red(self, accented_catalog):
        """MobileReport (Récapitulatif Mobile) must be RED."""
        result = MigrationAssessment().assess(accented_catalog)
        mobile = next(i for i in result["items"] if i["name"] == "Récapitulatif Mobile")
        overall = mobile["overall"]
        assert overall == RED

    def test_html_report_renders_accents(self, accented_catalog, tmp_path):
        """HTML report must correctly render all French accents."""
        assessment = MigrationAssessment()
        result = assessment.assess(accented_catalog)
        output = str(tmp_path / "rapport_français.html")
        assessment.generate_html_report(result, output)

        html = Path(output).read_text(encoding="utf-8")
        # Check accents are present (not mojibake or escaped)
        assert "Résumé des Ventes" in html
        assert "Prévisions Budgétaires" in html
        assert "Factures Échues" in html
        assert "Département Finance" in html
        assert "Contrôle Qualité" in html
        assert "Évaluation des Employés" in html
        # Ensure no raw unicode escapes leaked
        assert "\\u00e9" not in html
        assert "\\u00e8" not in html

    def test_html_report_has_utf8_charset(self, accented_catalog, tmp_path):
        assessment = MigrationAssessment()
        result = assessment.assess(accented_catalog)
        output = str(tmp_path / "report.html")
        assessment.generate_html_report(result, output)
        html = Path(output).read_text(encoding="utf-8")
        assert 'charset="utf-8"' in html.lower() or "charset=utf-8" in html.lower()

    def test_json_output_preserves_accents(self, accented_catalog, tmp_path):
        """JSON assessment output must round-trip accents."""
        result = MigrationAssessment().assess(accented_catalog)
        json_path = tmp_path / "résultat.json"
        json_path.write_text(
            json.dumps(result, indent=2, default=str, ensure_ascii=False),
            encoding="utf-8",
        )
        reloaded = json.loads(json_path.read_text(encoding="utf-8"))
        names = [i["name"] for i in reloaded["items"]]
        assert "Résumé des Ventes" in names
        assert "Évaluation des Employés" in names


# ===========================================================================
# 3. Converter — accented file names
# ===========================================================================


class TestConverterFrenchAccents:
    """Conversion pipeline with accented report names and paths."""

    def test_convert_accented_pbix(self, tmp_path):
        """PBIX with accented name should convert successfully."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        pbix = input_dir / "Résumé des Ventes.pbix"
        pbix.write_bytes(b"PK\x03\x04" + b"\x00" * 100)

        manifest = {
            "download_results": {
                "success": [{
                    "name": "Résumé des Ventes",
                    "type": "PowerBIReport",
                    "path": str(pbix),
                    "source_path": "/Département Finance/Résumé des Ventes",
                }]
            }
        }
        (input_dir / "export_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )

        converter = ContentConverter(str(input_dir), str(output_dir))
        result = converter.convert_all()

        assert result["converted"] == 1
        assert result["failed"] == 0
        # Output file should exist (filename may be sanitized)
        powerbi_dir = output_dir / "powerbi"
        assert powerbi_dir.exists()
        pbix_files = list(powerbi_dir.glob("*.pbix"))
        assert len(pbix_files) == 1

    def test_convert_accented_rdl(self, tmp_path):
        """RDL with accented name should convert and flag Premium."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        rdl = input_dir / "Factures Échues.rdl"
        rdl.write_text(
            "<Report>Données françaises — éèêëàçùôîïâûüö</Report>",
            encoding="utf-8",
        )

        manifest = {
            "download_results": {
                "success": [{
                    "name": "Factures Échues",
                    "type": "Report",
                    "path": str(rdl),
                    "source_path": "/Département Finance/Factures Échues",
                }]
            }
        }
        (input_dir / "export_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )

        converter = ContentConverter(str(input_dir), str(output_dir))
        result = converter.convert_all()

        assert result["converted"] == 1
        paginated_dir = output_dir / "paginated"
        assert paginated_dir.exists()
        rdl_files = list(paginated_dir.glob("*.rdl"))
        assert len(rdl_files) == 1

        # Metadata should preserve accented source path
        meta_files = list(paginated_dir.glob("*.meta.json"))
        assert len(meta_files) == 1
        meta = json.loads(meta_files[0].read_text(encoding="utf-8"))
        # Converter stores "source" pointing to original file, which has accented name
        assert "Échues" in meta.get("source", "")

    def test_metadata_json_roundtrip_with_accents(self, tmp_path):
        """Metadata JSON must survive write → read with accents intact."""
        meta = {
            "original_name": "Résumé des Données",
            "source_path": "/Département Finance/Résumé des Données",
            "description": "Tableau financier — prévisions & résultats",
            "created_by": "François Müller",
            "notes": ["Côte d'Azur region", "Île-de-France data"],
        }
        path = tmp_path / "méta.json"
        path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        reloaded = json.loads(path.read_text(encoding="utf-8"))
        assert reloaded["original_name"] == "Résumé des Données"
        assert reloaded["created_by"] == "François Müller"
        assert "Côte d'Azur" in reloaded["notes"][0]


# ===========================================================================
# 4. Permission mapper — accented group names
# ===========================================================================


class TestPermissionMapperFrenchAccents:
    """Permission mapping with accented AD group names."""

    def test_accented_group_maps_correctly(self, mock_pbi_client):
        permissions = {
            "item_policies": [{
                "item_path": "/Département Finance/Résumé",
                "policies": [
                    {"GroupUserName": "CORP\\Département_Finance", "Roles": [{"Name": "Browser"}]},
                    {"GroupUserName": "CORP\\François.Müller", "Roles": [{"Name": "Content Manager"}]},
                ]
            }]
        }
        mapper = PermissionMapper(mock_pbi_client)
        result = mapper.map_permissions(permissions, "ws-001", dry_run=True)

        assigned = result["assigned"]
        principals = {a["principal"] for a in assigned}
        assert "CORP\\Département_Finance" in principals
        assert "CORP\\François.Müller" in principals

    def test_accented_group_roles_preserved(self, mock_pbi_client):
        permissions = {
            "item_policies": [{
                "item_path": "/Équipe Commerciale",
                "policies": [
                    {"GroupUserName": "CORP\\Céline.Guérin", "Roles": [{"Name": "Publisher"}]},
                    {"GroupUserName": "CORP\\Équipe_Ventes", "Roles": [{"Name": "Browser"}]},
                ]
            }]
        }
        mapper = PermissionMapper(mock_pbi_client)
        result = mapper.map_permissions(permissions, "ws-001", dry_run=True)

        celine = next(a for a in result["assigned"] if "Céline" in a["principal"])
        assert celine["role"] == "Contributor"

        equipe = next(a for a in result["assigned"] if "Équipe" in a["principal"])
        assert equipe["role"] == "Viewer"


# ===========================================================================
# 5. Hashing and deduplication — accented keys
# ===========================================================================


class TestHashingWithAccents:
    """Verify hash functions produce stable output for accented strings."""

    def test_sha256_accented_string_is_deterministic(self):
        import hashlib
        key = "Résumé des Données|PowerBIReport|/Département Finance"
        h1 = hashlib.sha256(key.encode("utf-8")).hexdigest()
        h2 = hashlib.sha256(key.encode("utf-8")).hexdigest()
        assert h1 == h2
        assert len(h1) == 64

    def test_different_accents_produce_different_hashes(self):
        import hashlib
        h1 = hashlib.sha256("Résumé".encode("utf-8")).hexdigest()
        h2 = hashlib.sha256("Resume".encode("utf-8")).hexdigest()
        assert h1 != h2

    def test_json_dumps_accented_data_stable(self):
        """json.dumps with sort_keys should be deterministic for accented data."""
        data = {"name": "Prévisions Budgétaires", "créé_par": "François"}
        j1 = json.dumps(data, sort_keys=True, ensure_ascii=False)
        j2 = json.dumps(data, sort_keys=True, ensure_ascii=False)
        assert j1 == j2
        assert "Prévisions" in j1


# ===========================================================================
# 6. Full pipeline — fake server → assess → convert
# ===========================================================================


class TestFakePBIRSFullPipeline:
    """End-to-end: extract from fake server, assess, convert."""

    def test_extract_assess_convert(self, client, tmp_path):
        """Full pipeline with all-French data, no encoding errors."""
        # --- Extract ---
        items = client.list_catalog_items()
        assert len(items) > 0

        # Build catalog with datasources and policies
        catalog_items = []
        for item in items:
            entry = dict(item)
            try:
                if item["Type"] == "PowerBIReport":
                    entry["datasources"] = client.get_powerbi_report_datasources(item["Id"])
                elif item["Type"] == "Report":
                    entry["datasources"] = client.get_report_datasources(item["Id"])
                else:
                    entry["datasources"] = []
            except Exception:
                entry["datasources"] = []
            try:
                entry["policies"] = client.get_item_policies(item["Id"])
            except Exception:
                entry["policies"] = []
            entry["subscriptions"] = []
            entry["custom_visuals"] = []
            if item["Type"] == "Report":
                entry["rdl_features"] = set()
            catalog_items.append(entry)

        catalog = {"items": catalog_items}

        # --- Assess ---
        result = MigrationAssessment().assess(catalog)
        assert result["summary"]["total_items"] == len(items)

        # Verify accented names survived
        scored_names = {i["name"] for i in result["items"]}
        assert "Résumé des Ventes" in scored_names
        assert "Factures Échues" in scored_names
        assert "Prévisions Budgétaires" in scored_names

        # --- Download content ---
        export_dir = tmp_path / "export"
        export_dir.mkdir()
        download_results = []
        for item in items:
            if item["Type"] not in ("PowerBIReport", "Report"):
                continue
            try:
                if item["Type"] == "PowerBIReport":
                    content = client.download_powerbi_report(item["Id"])
                    ext = ".pbix"
                else:
                    content = client.download_report(item["Id"])
                    ext = ".rdl"
                fname = f"{item['Name']}{ext}"
                fpath = export_dir / fname
                fpath.write_bytes(content)
                download_results.append({
                    "name": item["Name"],
                    "type": item["Type"],
                    "path": str(fpath),
                    "source_path": item["Path"],
                })
            except Exception:
                pass

        assert len(download_results) >= 4  # 3 PBI + at least 1 paginated

        # Write manifest
        manifest = {"download_results": {"success": download_results}}
        (export_dir / "export_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # --- Convert ---
        output_dir = tmp_path / "converted"
        converter = ContentConverter(str(export_dir), str(output_dir))
        conv_result = converter.convert_all()

        assert conv_result["converted"] == len(download_results)
        assert conv_result["failed"] == 0

        # Verify output files exist
        powerbi_files = list((output_dir / "powerbi").glob("*.pbix"))
        paginated_files = list((output_dir / "paginated").glob("*.rdl"))
        assert len(powerbi_files) >= 3
        assert len(paginated_files) >= 1

        # Verify metadata files have accented content
        for meta_path in (output_dir / "powerbi").glob("*.meta.json"):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            # source field contains the file path with French characters
            assert any(c in meta.get("source", "")
                       for c in "éèêëàçùôîïâûü")

    def test_html_report_from_fake_server(self, client, tmp_path):
        """Generate HTML assessment report from fake server data."""
        items = client.list_catalog_items()
        catalog_items = []
        for item in items:
            entry = dict(item)
            entry["datasources"] = DATASOURCES.get(item["Id"], [])
            entry["policies"] = POLICIES.get(item["Id"], [])
            entry["subscriptions"] = SUBSCRIPTIONS.get(item["Id"], [])
            entry["custom_visuals"] = []
            if item["Type"] == "Report":
                entry["rdl_features"] = set()
            catalog_items.append(entry)

        assessment = MigrationAssessment()
        result = assessment.assess({"items": catalog_items})
        output = str(tmp_path / "rapport_migration.html")
        assessment.generate_html_report(result, output)

        html = Path(output).read_text(encoding="utf-8")

        # No encoding errors — all accents present
        for accent_str in [
            "Résumé", "Département", "Prévisions", "Budgétaires",
            "Échues", "Équipe", "Contrôle", "Évaluation", "Récapitulatif",
        ]:
            assert accent_str in html, f"Missing: {accent_str}"

        # No mojibake patterns
        assert "Ã©" not in html  # UTF-8 read as Latin-1
        assert "Ã¨" not in html
        assert "â€" not in html
