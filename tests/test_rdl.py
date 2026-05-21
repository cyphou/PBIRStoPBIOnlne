"""Tests for RdlAnalyser and RdlModifier."""

import xml.etree.ElementTree as ET
import pytest

from pbirs_export.rdl_analyser import RdlAnalyser
from pbi_import.rdl_modifier import RdlModifier


RDL_NS = "http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition"

SAMPLE_RDL = f"""<?xml version="1.0" encoding="utf-8"?>
<Report xmlns="{RDL_NS}">
  <Code>
    Public Function FormatCurrency(val As Decimal) As String
      Return String.Format("{{0:C}}", val)
    End Function
  </Code>
  <CodeModules>
    <CodeModule>MyAssembly, Version=1.0.0.0</CodeModule>
  </CodeModules>
  <Classes>
    <Class>
      <ClassName>MyAssembly.Helper</ClassName>
      <InstanceName>m_helper</InstanceName>
    </Class>
  </Classes>
  <DataSources>
    <DataSource Name="SalesDB">
      <ConnectionProperties>
        <DataProvider>SQL</DataProvider>
        <ConnectString>Data Source=sql01;Initial Catalog=Sales</ConnectString>
      </ConnectionProperties>
    </DataSource>
  </DataSources>
  <ReportParameters>
    <ReportParameter Name="StartDate">
      <DataType>DateTime</DataType>
    </ReportParameter>
    <ReportParameter Name="Region">
      <DataType>String</DataType>
    </ReportParameter>
  </ReportParameters>
  <Body>
    <ReportItems>
      <Tablix Name="tbl1"/>
      <Tablix Name="tbl2"/>
      <Chart Name="chart1"/>
      <Subreport Name="sub1">
        <ReportName>DetailReport</ReportName>
        <SubreportParameter Name="ID"/>
      </Subreport>
    </ReportItems>
  </Body>
  <PageBreak/>
</Report>
"""

MINIMAL_RDL = f"""<?xml version="1.0" encoding="utf-8"?>
<Report xmlns="{RDL_NS}">
  <Body>
    <ReportItems>
      <Tablix Name="tbl1"/>
    </ReportItems>
  </Body>
</Report>
"""


@pytest.fixture
def sample_rdl(tmp_path):
    p = tmp_path / "sample.rdl"
    p.write_text(SAMPLE_RDL, encoding="utf-8")
    return p


@pytest.fixture
def minimal_rdl(tmp_path):
    p = tmp_path / "minimal.rdl"
    p.write_text(MINIMAL_RDL, encoding="utf-8")
    return p


class TestRdlAnalyser:

    def test_detect_custom_code(self, sample_rdl):
        result = RdlAnalyser(sample_rdl).analyse()
        assert result["custom_code"]["present"] is True
        assert result["custom_code"]["block_count"] == 1

    def test_detect_custom_assemblies(self, sample_rdl):
        result = RdlAnalyser(sample_rdl).analyse()
        assert result["custom_assemblies"]["present"] is True
        assert "MyAssembly, Version=1.0.0.0" in result["custom_assemblies"]["assemblies"]
        assert len(result["custom_assemblies"]["classes"]) == 1

    def test_detect_subreports(self, sample_rdl):
        result = RdlAnalyser(sample_rdl).analyse()
        subs = result["subreports"]
        assert len(subs) == 1
        assert subs[0]["report_name"] == "DetailReport"
        assert "ID" in subs[0]["parameters"]

    def test_detect_datasources(self, sample_rdl):
        result = RdlAnalyser(sample_rdl).analyse()
        ds = result["datasources"]
        assert len(ds) == 1
        assert ds[0]["name"] == "SalesDB"
        assert ds[0]["provider"] == "SQL"

    def test_count_data_regions(self, sample_rdl):
        result = RdlAnalyser(sample_rdl).analyse()
        assert result["data_regions"]["Tablix"] == 2
        assert result["data_regions"]["Chart"] == 1

    def test_detect_parameters(self, sample_rdl):
        result = RdlAnalyser(sample_rdl).analyse()
        params = result["parameters"]
        assert len(params) == 2
        names = {p["name"] for p in params}
        assert names == {"StartDate", "Region"}

    def test_unsupported_features(self, sample_rdl):
        result = RdlAnalyser(sample_rdl).analyse()
        feature_names = {f["feature"] for f in result["unsupported_features"]}
        assert "Code" in feature_names
        assert "CodeModules" in feature_names
        assert "Classes" in feature_names

    def test_minimal_rdl_no_issues(self, minimal_rdl):
        result = RdlAnalyser(minimal_rdl).analyse()
        assert result["custom_code"]["present"] is False
        assert result["custom_assemblies"]["present"] is False
        assert len(result["subreports"]) == 0
        assert len(result["unsupported_features"]) == 0


class TestRdlModifier:

    def test_strips_custom_code(self, sample_rdl, tmp_path):
        out = tmp_path / "modified.rdl"
        result = RdlModifier(sample_rdl).modify(out)
        assert result["change_count"] >= 1
        # Verify the output has no <Code> element
        tree = ET.parse(out)
        code_els = list(tree.iter(f"{{{RDL_NS}}}Code"))
        assert len(code_els) == 0

    def test_strips_assemblies(self, sample_rdl, tmp_path):
        out = tmp_path / "modified.rdl"
        RdlModifier(sample_rdl).modify(out)
        tree = ET.parse(out)
        assert len(list(tree.iter(f"{{{RDL_NS}}}CodeModules"))) == 0

    def test_strips_classes(self, sample_rdl, tmp_path):
        out = tmp_path / "modified.rdl"
        RdlModifier(sample_rdl).modify(out)
        tree = ET.parse(out)
        assert len(list(tree.iter(f"{{{RDL_NS}}}Classes"))) == 0

    def test_preserves_data_regions(self, sample_rdl, tmp_path):
        out = tmp_path / "modified.rdl"
        RdlModifier(sample_rdl).modify(out)
        tree = ET.parse(out)
        assert len(list(tree.iter(f"{{{RDL_NS}}}Tablix"))) == 2
        assert len(list(tree.iter(f"{{{RDL_NS}}}Chart"))) == 1

    def test_minimal_no_changes(self, minimal_rdl, tmp_path):
        out = tmp_path / "modified.rdl"
        result = RdlModifier(minimal_rdl).modify(out)
        assert result["change_count"] == 0

    def test_changes_list(self, sample_rdl, tmp_path):
        out = tmp_path / "modified.rdl"
        result = RdlModifier(sample_rdl).modify(out)
        assert any("Code" in c for c in result["changes"])
        assert any("CodeModules" in c for c in result["changes"])
