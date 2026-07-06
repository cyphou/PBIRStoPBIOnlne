$api = "http://localhost/reports/api/v2.0"
$file = "C:\GitHub Project\PBIReporttoPBIOnline\scripts\artifacts\pbix\rs_test.pbix"

$bytes = [IO.File]::ReadAllBytes($file)
$b64 = [Convert]::ToBase64String($bytes)
$body = @{
    '@odata.type' = '#Model.PowerBIReport'
    Content       = $b64
    ContentType   = ''
    Name          = 'Probe-rs_test'
    Path          = '/Migration PBI/Probe-rs_test'
} | ConvertTo-Json -Depth 6

try {
    Invoke-RestMethod -Uri "$api/PowerBIReports" -Method Post -UseDefaultCredentials -AllowUnencryptedAuthentication -Body ([Text.Encoding]::UTF8.GetBytes($body)) -ContentType 'application/json; charset=utf-8' -TimeoutSec 180 | Out-Null
    Write-Host "PROBE_OK"
}
catch {
    if ($_.Exception.Response) {
        Write-Host "PROBE_FAIL_HTTP_$([int]$_.Exception.Response.StatusCode)"
    }
    else {
        Write-Host "PROBE_FAIL_$($_.Exception.Message)"
    }
}
