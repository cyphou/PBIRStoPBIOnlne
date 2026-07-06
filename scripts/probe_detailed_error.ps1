param(
    [string]$FilePath = "<USER_HOME>\OneDrive - Organization\test.pbix"
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

try {
    $result = Invoke-RestMethod -Uri "$api/PowerBIReports" -Method Post -UseDefaultCredentials -AllowUnencryptedAuthentication -Body ([Text.Encoding]::UTF8.GetBytes($body)) -ContentType 'application/json; charset=utf-8' -TimeoutSec 180
    Write-Host "OK"
    $result | ConvertTo-Json -Depth 8
}
catch {
    $resp = $_.Exception.Response
    if ($resp) {
        Write-Host "STATUS: $([int]$resp.StatusCode)"
        $txt = ""
        if ($resp -is [System.Net.Http.HttpResponseMessage]) {
            $txt = $resp.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        }
        elseif ($resp.PSObject.Methods.Name -contains "GetResponseStream") {
            $reader = New-Object IO.StreamReader($resp.GetResponseStream())
            $txt = $reader.ReadToEnd()
            $reader.Close()
        }
        Write-Host "BODY_START"
        Write-Host $txt
        Write-Host "BODY_END"
    }
    else {
        Write-Host "ERROR: $($_.Exception.Message)"
    }
    exit 2
}
