param(
    [string]$FilePath = (Join-Path $PSScriptRoot "artifacts\pbix\sample.pbix")
)

$api = "http://localhost/reports/api/v2.0"
$name = "Probe-Diag-" + (Get-Date -Format "yyyyMMddHHmmss")

if (-not (Test-Path $FilePath)) {
    Write-Host "MISSING $FilePath"
    exit 1
}

$bytes = [IO.File]::ReadAllBytes($FilePath)
$b64 = [Convert]::ToBase64String($bytes)
$body = @{
    '@odata.type' = '#Model.PowerBIReport'
    Content       = $b64
    ContentType   = ''
    Name          = $name
    Path          = "/Migration PBI/$name"
} | ConvertTo-Json -Depth 6

$response = Invoke-WebRequest -Uri "$api/PowerBIReports" -Method Post -UseDefaultCredentials -AllowUnencryptedAuthentication -Body ([Text.Encoding]::UTF8.GetBytes($body)) -ContentType 'application/json; charset=utf-8' -TimeoutSec 180 -SkipHttpErrorCheck
Write-Host "STATUS: $([int]$response.StatusCode)"
Write-Host "BODY_START"
Write-Host $response.Content
Write-Host "BODY_END"

if ([int]$response.StatusCode -ge 400) {
    exit 2
}
