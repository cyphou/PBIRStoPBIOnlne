"""Tests for ContentConverter."""

import json
import pytest
from pbi_import.converter import ContentConverter


class TestContentConverter:

    def test_convert_no_manifest(self, tmp_path):
        converter = ContentConverter(str(tmp_path / "input"), str(tmp_path / "output"))
        result = converter.convert_all()
        assert result["converted"] == 0

    def test_convert_pbix_dry_run(self, tmp_path):
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        # Create a fake pbix file
        pbix_path = input_dir / "Sales.pbix"
        pbix_path.write_bytes(b"PK\x03\x04fake")

        # Write manifest
        manifest = {
            "download_results": {
                "success": [
                    {"name": "Sales", "type": "PowerBIReport", "path": str(pbix_path), "source_path": "/Sales"}
                ]
            }
        }
        (input_dir / "export_manifest.json").write_text(json.dumps(manifest))

        converter = ContentConverter(str(input_dir), str(output_dir))
        result = converter.convert_all(dry_run=True)
        assert result["converted"] == 1

    def test_convert_pbix(self, tmp_path):
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        pbix_path = input_dir / "Report.pbix"
        pbix_path.write_bytes(b"PK\x03\x04fake")

        manifest = {
            "download_results": {
                "success": [
                    {"name": "Report", "type": "PowerBIReport", "path": str(pbix_path), "source_path": "/Report"}
                ]
            }
        }
        (input_dir / "export_manifest.json").write_text(json.dumps(manifest))

        converter = ContentConverter(str(input_dir), str(output_dir))
        result = converter.convert_all()
        assert result["converted"] == 1
        assert (output_dir / "powerbi" / "Report.pbix").exists()
