param(
    [Parameter(Mandatory = $true)]
    [string[]]$Files
)

$api = "http://localhost/reports/api/v2.0"

foreach ($f in $Files) {
    if (-not (Test-Path $f)) {
        Write-Host "MISSING $f"
        continue
    }

    $name = [IO.Path]::GetFileNameWithoutExtension($f)
    $bytes = [IO.File]::ReadAllBytes($f)
    $b64 = [Convert]::ToBase64String($bytes)

    $body = @{
        '@odata.type' = '#Model.PowerBIReport'
        Content       = $b64
        ContentType   = ''
        Name          = "Probe-$name"
        Path          = "/Migration PBI/Probe-$name"
    } | ConvertTo-Json -Depth 6

    try {
        Invoke-RestMethod -Uri "$api/PowerBIReports" -Method Post -UseDefaultCredentials -AllowUnencryptedAuthentication -Body ([Text.Encoding]::UTF8.GetBytes($body)) -ContentType 'application/json; charset=utf-8' -TimeoutSec 180 | Out-Null
        Write-Host "PROBE_OK $f"
    }
    catch {
        if ($_.Exception.Response) {
            Write-Host "PROBE_FAIL_HTTP_$([int]$_.Exception.Response.StatusCode) $f"
        }
        else {
            Write-Host "PROBE_FAIL $f"
        }
    }
}
