$ErrorActionPreference = "Stop"
$target = "C:\GitHub Project\PBIReporttoPBIOnline\scripts\artifacts\pbix"
New-Item -ItemType Directory -Force -Path $target | Out-Null

$urls = @(
    "https://github.com/microsoft/powerbi-desktop-samples/raw/main/Sample%20Reports/Sales%20%26%20Returns%20Sample%20v201912.pbix",
    "https://github.com/microsoft/powerbi-desktop-samples/raw/main/Sample%20Reports/Customer%20Profitability%20Sample%20PBIX.pbix",
    "https://github.com/microsoft/powerbi-desktop-samples/raw/main/Monthly%20Desktop%20Blog%20Samples/2024/Getting%20Started.pbix",
    "https://github.com/microsoft/powerbi-desktop-samples/raw/main/Monthly%20Desktop%20Blog%20Samples/2023/June/Introduction%20to%20DAX%20Query%20View.pbix",
    "https://github.com/microsoft/powerbi-desktop-samples/raw/main/Monthly%20Desktop%20Blog%20Samples/2022/December/Fields%20Parameters.pbix"
)

$downloaded = @()
foreach ($u in $urls) {
    try {
        $name = ($u.Split('/')[-1] -replace '%20', ' ')
        if (-not $name.ToLower().EndsWith('.pbix')) { $name += '.pbix' }
        $out = Join-Path $target $name
        Invoke-WebRequest -Uri $u -OutFile $out -UseBasicParsing -TimeoutSec 120
        $len = (Get-Item $out).Length
        if ($len -gt 100000) {
            $downloaded += $out
            Write-Host "DOWNLOADED_OK $name $len"
        }
        else {
            Remove-Item $out -Force -ErrorAction SilentlyContinue
            Write-Host "DOWNLOADED_TOO_SMALL $name $len"
        }
    }
    catch {
        Write-Host "DOWNLOAD_FAIL $u"
    }
}

$api = "http://localhost/reports/api/v2.0"
$folder = "/Migration PBI"

try {
    $folders = (Invoke-RestMethod -Uri "$api/Folders" -Method Get -UseDefaultCredentials -AllowUnencryptedAuthentication -TimeoutSec 60).value
    if (-not ($folders | Where-Object { $_.Path -eq $folder })) {
        $body = @{
            '@odata.type' = '#Model.Folder'
            Name = 'Migration PBI'
            Description = 'Internet PBIX probes'
            Path = '/'
        } | ConvertTo-Json -Depth 5

        Invoke-RestMethod -Uri "$api/Folders" -Method Post -UseDefaultCredentials -AllowUnencryptedAuthentication -Body ([Text.Encoding]::UTF8.GetBytes($body)) -ContentType 'application/json; charset=utf-8' -TimeoutSec 60 | Out-Null
    }
}
catch {
    Write-Host "FOLDER_CHECK_FAIL $($_.Exception.Message)"
}

$success = $null
foreach ($f in $downloaded) {
    $name = [IO.Path]::GetFileNameWithoutExtension($f)
    $probePath = "/Migration PBI/Probe-$name"
    $bytes = [IO.File]::ReadAllBytes($f)
    $b64 = [Convert]::ToBase64String($bytes)

    $body = @{
        '@odata.type' = '#Model.PowerBIReport'
        Content = $b64
        ContentType = ''
        Name = "Probe-$name"
        Path = $probePath
    } | ConvertTo-Json -Depth 6

    try {
        Invoke-RestMethod -Uri "$api/PowerBIReports" -Method Post -UseDefaultCredentials -AllowUnencryptedAuthentication -Body ([Text.Encoding]::UTF8.GetBytes($body)) -ContentType 'application/json; charset=utf-8' -TimeoutSec 180 | Out-Null
        Write-Host "PROBE_OK $f"
        $success = $f
        break
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

if ($success) {
    Write-Host "COMPATIBLE_FOUND $success"
}
else {
    Write-Host "COMPATIBLE_NOT_FOUND"
}
