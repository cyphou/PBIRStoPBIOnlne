$ErrorActionPreference = "Stop"

$file = "c:\Users\pidoudet\OneDrive - Microsoft\Boulot\PBI SME\OracleToPostgre\PBIReporttoPBIOnline\scripts\artifacts\pbix\AdventureWorks Sales.pbix"
$name = "AdventureWorks_Sample"
$folder = "/Direction Générale"
$apiUrl = "http://ms-len-moa/Reports/api/v2.0/PowerBIReports"

if (-not (Test-Path $file)) {
    Write-Host "UPLOAD_FAILED STATUS=0"
    Write-Host "File not found: $file"
    exit 1
}

$bytes = [System.IO.File]::ReadAllBytes($file)
$base64 = [Convert]::ToBase64String($bytes)

$body = @{
    "@odata.type" = "#Model.PowerBIReport"
    "Content" = $base64
    "ContentType" = ""
    "Name" = $name
    "Path" = "$folder/$name"
} | ConvertTo-Json -Depth 5

try {
    $resp = Invoke-RestMethod -Uri $apiUrl `
        -Method Post `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) `
        -ContentType "application/json; charset=utf-8" `
        -UseDefaultCredentials `
        -TimeoutSec 180

    Write-Host "UPLOAD_OK"
    Write-Host ("ID=" + $resp.Id)
    Write-Host ("NAME=" + $resp.Name)
    Write-Host ("PATH=" + $resp.Path)
} catch {
    $statusCode = 0
    if ($_.Exception.Response) { $statusCode = [int]$_.Exception.Response.StatusCode }
    Write-Host ("UPLOAD_FAILED STATUS=" + $statusCode)
    if ($_.Exception.Response) {
        $stream = $_.Exception.Response.GetResponseStream()
        if ($stream) {
            $reader = New-Object System.IO.StreamReader($stream)
            Write-Host $reader.ReadToEnd()
        }
    }
    exit 1
}
