# Approach 1: Modify .pbix metadata to make it look RS-compatible
# Approach 2: Try SOAP endpoint for upload
Add-Type -AssemblyName System.IO.Compression.FileSystem

$srcFile = "C:\Users\pidoudet\Downloads\SAP_O2C_V3 (1).pbix"
$modifiedFile = "C:\Users\pidoudet\OneDrive - Microsoft\Boulot\PBI SME\OracleToPostgre\PBIReporttoPBIOnline\scripts\artifacts\pbix\modified_test.pbix"

# Copy and modify the .pbix
Copy-Item $srcFile $modifiedFile -Force
Write-Host "Copied $([math]::Round((Get-Item $modifiedFile).Length/1MB,1))MB" -ForegroundColor Cyan

# Update to use ZipArchive for in-place modification
$zip = [System.IO.Compression.ZipFile]::Open($modifiedFile, [System.IO.Compression.ZipArchiveMode]::Update)

# Fix Version -> "1.0" (PBIRS RS typically uses 1.0)
$versionEntry = $zip.GetEntry("Version")
if ($versionEntry) {
    $versionEntry.Delete()
    $newVersion = $zip.CreateEntry("Version")
    $writer = New-Object System.IO.StreamWriter($newVersion.Open())
    $writer.Write("1.0")
    $writer.Close()
    Write-Host "Updated Version to 1.0"
}

# Fix Metadata - remove Cloud origin
$metaEntry = $zip.GetEntry("Metadata")
if ($metaEntry) {
    $metaEntry.Delete()
    $newMeta = $zip.CreateEntry("Metadata")
    $writer = New-Object System.IO.StreamWriter($newMeta.Open())
    $writer.Write('{"Version":3,"AutoCreatedRelationships":[]}')
    $writer.Close()
    Write-Host "Updated Metadata (removed Cloud origin)"
}

# Fix Settings - downgrade version
$settingsEntry = $zip.GetEntry("Settings")
if ($settingsEntry) {
    $settingsEntry.Delete()
    $newSettings = $zip.CreateEntry("Settings")
    $writer = New-Object System.IO.StreamWriter($newSettings.Open())
    $writer.Write('{"Version":1,"ReportSettings":{},"QueriesSettings":{"TypeDetectionEnabled":true,"RelationshipImportEnabled":true}}')
    $writer.Close()
    Write-Host "Updated Settings (removed version info)"
}

$zip.Dispose()
Write-Host "Modified .pbix saved" -ForegroundColor Green

# Try uploading modified version
$apiUrl = "http://ms-len-moa/Reports/api/v2.0"
$bytes = [System.IO.File]::ReadAllBytes($modifiedFile)
$base64 = [Convert]::ToBase64String($bytes)

Write-Host "`n=== Upload modified .pbix ==="
$body = @{
    "@odata.type" = "#Model.PowerBIReport"
    "Content" = $base64
    "ContentType" = ""
    "Name" = "TestModified"
    "Path" = "/IT Operations/TestModified"
} | ConvertTo-Json -Depth 5

try {
    $webReq = [System.Net.WebRequest]::Create("$apiUrl/PowerBIReports")
    $webReq.Method = "POST"
    $webReq.ContentType = "application/json; charset=utf-8"
    $webReq.Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials
    $webReq.Timeout = 120000
    $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($body)
    $webReq.ContentLength = $bodyBytes.Length
    $reqStream = $webReq.GetRequestStream()
    $reqStream.Write($bodyBytes, 0, $bodyBytes.Length)
    $reqStream.Close()
    $response = $webReq.GetResponse()
    $respStream = $response.GetResponseStream()
    $respReader = New-Object System.IO.StreamReader($respStream)
    Write-Host "SUCCESS: $($respReader.ReadToEnd())" -ForegroundColor Green
    $respReader.Close()
} catch [System.Net.WebException] {
    $errResp = $_.Exception.Response
    Write-Host "FAILED $([int]$errResp.StatusCode): " -NoNewline -ForegroundColor Red
    $errStream = $errResp.GetResponseStream()
    $errReader = New-Object System.IO.StreamReader($errStream)
    Write-Host $errReader.ReadToEnd()
    $errReader.Close()
}

# Approach 2: SOAP endpoint
Write-Host "`n=== SOAP CreateCatalogItem ==="
$soapBody = @"
<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <CreateCatalogItem xmlns="http://schemas.microsoft.com/sqlserver/reporting/2010/03/01/ReportServer">
      <ItemType>PowerBIReport</ItemType>
      <Name>TestSOAP</Name>
      <Parent>/IT Operations</Parent>
      <Overwrite>true</Overwrite>
      <Definition>$base64</Definition>
      <Properties />
    </CreateCatalogItem>
  </soap:Body>
</soap:Envelope>
"@

try {
    $webReq2 = [System.Net.WebRequest]::Create("http://ms-len-moa/ReportServer/ReportService2010.asmx")
    $webReq2.Method = "POST"
    $webReq2.ContentType = "text/xml; charset=utf-8"
    $webReq2.Headers.Add("SOAPAction", "http://schemas.microsoft.com/sqlserver/reporting/2010/03/01/ReportServer/CreateCatalogItem")
    $webReq2.Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials
    $webReq2.Timeout = 120000
    $soapBytes = [System.Text.Encoding]::UTF8.GetBytes($soapBody)
    $webReq2.ContentLength = $soapBytes.Length
    $reqStream2 = $webReq2.GetRequestStream()
    $reqStream2.Write($soapBytes, 0, $soapBytes.Length)
    $reqStream2.Close()
    $response2 = $webReq2.GetResponse()
    $respStream2 = $response2.GetResponseStream()
    $respReader2 = New-Object System.IO.StreamReader($respStream2)
    Write-Host "SUCCESS: $($respReader2.ReadToEnd())" -ForegroundColor Green
    $respReader2.Close()
} catch [System.Net.WebException] {
    $errResp2 = $_.Exception.Response
    if ($errResp2) {
        Write-Host "FAILED $([int]$errResp2.StatusCode): " -NoNewline -ForegroundColor Red
        $errStream2 = $errResp2.GetResponseStream()
        $errReader2 = New-Object System.IO.StreamReader($errStream2)
        $body2 = $errReader2.ReadToEnd()
        # Extract just the fault string
        if ($body2 -match '<faultstring>(.*?)</faultstring>') { Write-Host $matches[1] }
        else { Write-Host ($body2.Substring(0, [Math]::Min(500, $body2.Length))) }
        $errReader2.Close()
    } else {
        Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    }
}
