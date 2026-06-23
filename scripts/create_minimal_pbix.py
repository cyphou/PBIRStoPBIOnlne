"""Create a minimal .pbix file and upload to PBIRS."""
import io
import json
import zipfile
import base64
import urllib.request
import sys

def create_minimal_pbix(name: str) -> bytes:
    """Create a minimal .pbix that PBIRS might accept."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Version - use 1.0 for maximum compatibility
        zf.writestr("Version", "1.0")
        
        # Content_Types
        content_types = '''<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="json" ContentType="application/json" />
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml" />
  <Default Extension="xml" ContentType="application/xml" />
</Types>'''
        zf.writestr("[Content_Types].xml", content_types)
        
        # Relationships
        rels = '''<?xml version="1.0" encoding="utf-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/metadata/core-properties" Target="/docProps/custom.xml" Id="R1" />
</Relationships>'''
        zf.writestr("_rels/.rels", rels)
        
        # Custom XML
        custom_xml = '''<?xml version="1.0" encoding="utf-8"?>
<Properties xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes" xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties">
  <property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="2" name="PBIDesktopVersion">
    <vt:lpwstr>2.125.816.0</vt:lpwstr>
  </property>
</Properties>'''
        zf.writestr("docProps/custom.xml", custom_xml)
        
        # Settings
        settings = json.dumps({
            "Version": 1,
            "ReportSettings": {},
            "QueriesSettings": {
                "TypeDetectionEnabled": True,
                "RelationshipImportEnabled": True
            }
        })
        zf.writestr("Settings", settings)
        
        # Metadata - pretend it's from PBI Desktop (not Cloud)
        metadata = json.dumps({
            "Version": 3,
            "AutoCreatedRelationships": []
        })
        zf.writestr("Metadata", metadata)
        
        # Connections - empty  
        connections = json.dumps({"Version": 1, "Connections": []})
        zf.writestr("Connections", connections)
        
        # SecurityBindings - empty
        zf.writestr("SecurityBindings", "")
        
        # DiagramLayout - minimal
        diagram = json.dumps({"version": "1.0", "pages": [], "reportLayout": {"id": 0}})
        zf.writestr("DiagramLayout", diagram)
        
        # Report Layout - minimal report with one page
        layout = json.dumps({
            "id": 0,
            "reportId": "00000000-0000-0000-0000-000000000001",
            "config": json.dumps({"version": "1.0", "themeCollection": {}}),
            "filters": "[]",
            "resourcePackages": [],
            "sections": [{
                "id": 0,
                "name": "ReportSection",
                "displayName": name,
                "filters": "[]",
                "ordinal": 0,
                "config": json.dumps({"layouts": [{"id": 0, "position": {"x": 0, "y": 0, "z": 0, "width": 1280, "height": 720, "tabOrder": 0}}]}),
                "visualContainers": [],
                "width": 1280,
                "height": 720,
                "displayOption": 1
            }],
            "pods": []
        })
        zf.writestr("Report/Layout", layout)
        
        # DataModel - minimal ABF-like binary (ABF header signature)
        # ABF files start with a specific binary header  
        # Let's try without DataModel first, then with a minimal one
        
    return buf.getvalue()


def upload_to_pbirs(name: str, path: str, pbix_bytes: bytes) -> bool:
    """Upload .pbix to PBIRS."""
    api_url = "http://ms-len-moa/Reports/api/v2.0"
    b64 = base64.b64encode(pbix_bytes).decode('ascii')
    body = json.dumps({
        "@odata.type": "#Model.PowerBIReport",
        "Content": b64,
        "ContentType": "",
        "Name": name,
        "Path": path,
    }).encode('utf-8')
    
    req = urllib.request.Request(
        f"{api_url}/PowerBIReports",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    # For NTLM auth, we need requests or similar - use PowerShell instead
    return False  # placeholder


# Test 1: No DataModel at all
print("Creating minimal .pbix WITHOUT DataModel...")
pbix1 = create_minimal_pbix("Test No DataModel")
with open("scripts/artifacts/pbix/no_datamodel.pbix", "wb") as f:
    f.write(pbix1)
print(f"  Created: {len(pbix1)} bytes")

# Test 2: With empty DataModel  
print("\nCreating minimal .pbix WITH empty DataModel...")
buf2 = io.BytesIO()
with zipfile.ZipFile(buf2, 'w', zipfile.ZIP_DEFLATED) as zf:
    # Read back the no_datamodel.pbix and add DataModel
    with zipfile.ZipFile(io.BytesIO(pbix1), 'r') as src:
        for item in src.namelist():
            zf.writestr(item, src.read(item))
    # Add empty DataModel
    zf.writestr("DataModel", b'\x00' * 16)

pbix2 = buf2.getvalue()
with open("scripts/artifacts/pbix/empty_datamodel.pbix", "wb") as f:
    f.write(pbix2)
print(f"  Created: {len(pbix2)} bytes")

# Test 3: DataModel with ABF magic bytes
# ABF files typically start with specific binary signatures
print("\nCreating minimal .pbix WITH ABF-header DataModel...")
# Microsoft ABF header: starts with a specific binary pattern
# Let me try the XMLA backup format signature
abf_header = bytes([
    0x08, 0x00, 0x00, 0x00,  # version?
    0x00, 0x00, 0x00, 0x00,  
    0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00,
]) + b'\x00' * 240  # padding

buf3 = io.BytesIO()
with zipfile.ZipFile(buf3, 'w', zipfile.ZIP_DEFLATED) as zf:
    with zipfile.ZipFile(io.BytesIO(pbix1), 'r') as src:
        for item in src.namelist():
            zf.writestr(item, src.read(item))
    zf.writestr("DataModel", abf_header)

pbix3 = buf3.getvalue()
with open("scripts/artifacts/pbix/abf_datamodel.pbix", "wb") as f:
    f.write(pbix3)
print(f"  Created: {len(pbix3)} bytes")

print("\nAll test .pbix files created in scripts/artifacts/pbix/")
print("Now run PowerShell to test uploading each one.")
