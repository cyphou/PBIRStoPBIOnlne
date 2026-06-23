# Test uploading the 3 minimal .pbix variants + the modified real one
$apiUrl = "http://ms-len-moa/Reports/api/v2.0"
$basePath = "c:\Users\pidoudet\OneDrive - Microsoft\Boulot\PBI SME\OracleToPostgre\PBIReporttoPBIOnline\scripts\artifacts\pbix"

$testFiles = @(
    @{ File = "$basePath\no_datamodel.pbix"; Name = "Test_NoDataModel" },
    @{ File = "$basePath\empty_datamodel.pbix"; Name = "Test_EmptyDM" },
    @{ File = "$basePath\abf_datamodel.pbix"; Name = "Test_ABFHeader" },
    @{ File = "$basePath\sample.pbix"; Name = "Test_GitHubSample" }
)

foreach ($test in $testFiles) {
    $bytes = [System.IO.File]::ReadAllBytes($test.File)
    $base64 = [Convert]::ToBase64String($bytes)
    $sizeMB = [math]::Round($bytes.Length / 1MB, 2)
    
    $body = @{
        "@odata.type" = "#Model.PowerBIReport"
        "Content" = $base64
        "ContentType" = ""
        "Name" = $test.Name
        "Path" = "/IT Operations/$($test.Name)"
    } | ConvertTo-Json -Depth 5
    
    Write-Host "=== $($test.Name) (${sizeMB}MB) ===" -ForegroundColor Cyan
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
        $result = $respReader.ReadToEnd()
        $respReader.Close()
        Write-Host "  SUCCESS!" -ForegroundColor Green
        Write-Host "  $result"
    } catch [System.Net.WebException] {
        $errResp = $_.Exception.Response
        $code = if ($errResp) { [int]$errResp.StatusCode } else { "?" }
        Write-Host "  FAILED ($code)" -ForegroundColor Red
        if ($errResp) {
            $errStream = $errResp.GetResponseStream()
            $errReader = New-Object System.IO.StreamReader($errStream)
            $errBody = $errReader.ReadToEnd()
            $errReader.Close()
            # Truncate long error bodies
            if ($errBody.Length -gt 300) { $errBody = $errBody.Substring(0, 300) + "..." }
            Write-Host "  $errBody"
        }
    }
    Write-Host ""
}
