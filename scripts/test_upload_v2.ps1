# Detailed upload test with full error body capture
$apiUrl = "http://ms-len-moa/Reports/api/v2.0"
$testFile = "C:\Users\pidoudet\Downloads\FCA_Core_Report.pbix"

Write-Host "File: $testFile ($([math]::Round((Get-Item $testFile).Length/1MB,1))MB)"

$bytes = [System.IO.File]::ReadAllBytes($testFile)
$base64 = [Convert]::ToBase64String($bytes)

# Also check the version of the .pbix
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($testFile)
foreach ($entry in $zip.Entries) {
    if ($entry.FullName -in @("Version", "Settings", "Metadata", "Connections")) {
        $stream = $entry.Open()
        $reader = New-Object System.IO.StreamReader($stream)
        $content = $reader.ReadToEnd()
        $reader.Close()
        Write-Host "`n--- $($entry.FullName) ---"
        Write-Host $content
    }
}
$zip.Dispose()

# Test 1: Standard API
Write-Host "`n=== Test 1: Standard PowerBIReports API ==="
$body1 = @{
    "@odata.type" = "#Model.PowerBIReport"
    "Content" = $base64
    "ContentType" = ""
    "Name" = "TestUpload"
    "Path" = "/TestUpload"
} | ConvertTo-Json -Depth 5

try {
    $webReq = [System.Net.WebRequest]::Create("$apiUrl/PowerBIReports")
    $webReq.Method = "POST"
    $webReq.ContentType = "application/json; charset=utf-8"
    $webReq.Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials
    $webReq.Timeout = 120000
    $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($body1)
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
    Write-Host "FAILED $([int]$errResp.StatusCode) $($errResp.StatusDescription)" -ForegroundColor Red
    $errStream = $errResp.GetResponseStream()
    $errReader = New-Object System.IO.StreamReader($errStream)
    $errBody = $errReader.ReadToEnd()
    $errReader.Close()
    Write-Host "Error body: $errBody"
}

# Test 2: Try multipart upload (like the portal)
Write-Host "`n=== Test 2: Multipart upload to CatalogItems ==="
$boundary = [System.Guid]::NewGuid().ToString()
$multipartBody = @"
--$boundary
Content-Disposition: form-data; name="file"; filename="TestUpload.pbix"
Content-Type: application/octet-stream

"@ + [System.Text.Encoding]::UTF8.GetString($bytes) + @"

--$boundary--
"@

try {
    $webReq2 = [System.Net.WebRequest]::Create("$apiUrl/CatalogItems")
    $webReq2.Method = "POST"
    $webReq2.ContentType = "multipart/form-data; boundary=$boundary"
    $webReq2.Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials
    $webReq2.Timeout = 120000
    $bodyBytes2 = [System.Text.Encoding]::UTF8.GetBytes($multipartBody)
    $webReq2.ContentLength = $bodyBytes2.Length
    $reqStream2 = $webReq2.GetRequestStream()
    $reqStream2.Write($bodyBytes2, 0, $bodyBytes2.Length)
    $reqStream2.Close()
    $response2 = $webReq2.GetResponse()
    $respStream2 = $response2.GetResponseStream()
    $respReader2 = New-Object System.IO.StreamReader($respStream2)
    Write-Host "SUCCESS: $($respReader2.ReadToEnd())" -ForegroundColor Green
    $respReader2.Close()
} catch [System.Net.WebException] {
    $errResp2 = $_.Exception.Response
    Write-Host "FAILED $([int]$errResp2.StatusCode) $($errResp2.StatusDescription)" -ForegroundColor Red
    $errStream2 = $errResp2.GetResponseStream()
    $errReader2 = New-Object System.IO.StreamReader($errStream2)
    $errBody2 = $errReader2.ReadToEnd()
    $errReader2.Close()
    Write-Host "Error body: $errBody2"
}

# Test 3: portal-style upload URL
Write-Host "`n=== Test 3: Portal upload endpoint ==="
try {
    $webReq3 = [System.Net.WebRequest]::Create("http://ms-len-moa/Reports/api/v2.0/PowerBIReports(Path='/TestUpload')")
    $webReq3.Method = "PUT"
    $webReq3.ContentType = "application/json; charset=utf-8"
    $webReq3.Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials
    $webReq3.Timeout = 120000
    $bodyBytes3 = [System.Text.Encoding]::UTF8.GetBytes($body1)
    $webReq3.ContentLength = $bodyBytes3.Length
    $reqStream3 = $webReq3.GetRequestStream()
    $reqStream3.Write($bodyBytes3, 0, $bodyBytes3.Length)
    $reqStream3.Close()
    $response3 = $webReq3.GetResponse()
    $respStream3 = $response3.GetResponseStream()
    $respReader3 = New-Object System.IO.StreamReader($respStream3)
    Write-Host "SUCCESS: $($respReader3.ReadToEnd())" -ForegroundColor Green
    $respReader3.Close()
} catch [System.Net.WebException] {
    $errResp3 = $_.Exception.Response
    Write-Host "FAILED $([int]$errResp3.StatusCode) $($errResp3.StatusDescription)" -ForegroundColor Red
    $errStream3 = $errResp3.GetResponseStream()
    $errReader3 = New-Object System.IO.StreamReader($errStream3)
    $errBody3 = $errReader3.ReadToEnd()
    $errReader3.Close()
    Write-Host "Error body: $errBody3"
}
