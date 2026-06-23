<#
.SYNOPSIS
    Download a real sample .pbix and upload 5 copies to PBIRS folders.
    
.DESCRIPTION
    Since PBI Desktop RS's lightweight msmdsrv does not support the Backup
    command, we cannot create .pbix programmatically via AMO. Instead, we
    download a known-good .pbix sample from Microsoft and upload copies
    with different names to the PBIRS folders.
#>

$ErrorActionPreference = "Stop"
$apiUrl = "http://ms-len-moa/Reports/api/v2.0"
$outputDir = Join-Path $PSScriptRoot "artifacts\pbix"

if (-not (Test-Path $outputDir)) { New-Item -ItemType Directory -Path $outputDir -Force | Out-Null }

# ─── 1. Download a sample .pbix ──────────────────────────────────
$samplePbix = Join-Path $outputDir "sample.pbix"

if (-not (Test-Path $samplePbix)) {
    Write-Host "=== Downloading sample .pbix ===" -ForegroundColor Cyan
    
    # Try multiple sources for a small sample .pbix
    $urls = @(
        "https://github.com/microsoft/powerbi-desktop-samples/raw/main/Sample%20Reports/Sales%20%26%20Returns%20Sample%20v201912.pbix",
        "https://github.com/microsoft/powerbi-desktop-samples/raw/refs/heads/main/Monthly%20Desktop%20Blog%20Samples/2024/Getting%20Started.pbix"
    )
    
    $downloaded = $false
    foreach ($url in $urls) {
        Write-Host "  Trying: $url"
        try {
            Invoke-WebRequest -Uri $url -OutFile $samplePbix -UseBasicParsing -TimeoutSec 60
            $size = (Get-Item $samplePbix).Length
            if ($size -gt 10KB) {
                Write-Host "  Downloaded: $([math]::Round($size/1MB, 1))MB" -ForegroundColor Green
                $downloaded = $true
                break
            } else {
                Remove-Item $samplePbix -Force
                Write-Host "  File too small, trying next..." -ForegroundColor Yellow
            }
        } catch {
            Write-Host "  Failed: $_" -ForegroundColor Yellow
        }
    }
    
    if (-not $downloaded) {
        Write-Host "`n  Direct download failed. Trying to create a minimal .pbix using PBI Desktop RS..." -ForegroundColor Yellow
        
        # Last resort: Find any .pbix file on this machine
        Write-Host "  Searching for existing .pbix files on disk..."
        $existingPbix = Get-ChildItem "C:\Users\pidoudet" -Filter "*.pbix" -Recurse -Depth 5 -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($existingPbix) {
            Write-Host "  Found: $($existingPbix.FullName)" -ForegroundColor Green
            Copy-Item $existingPbix.FullName $samplePbix
            $downloaded = $true
        }
    }
    
    if (-not $downloaded) {
        Write-Error "Could not obtain a sample .pbix file. Please place a .pbix file at: $samplePbix"
        exit 1
    }
} else {
    Write-Host "Using existing sample: $samplePbix ($([math]::Round((Get-Item $samplePbix).Length/1MB, 1))MB)" -ForegroundColor Green
}

# ─── 2. Define reports and target folders ─────────────────────────
$reports = @(
    @{ Name = "Analyse des Ventes";  Folder = "/Équipe Commerciale" },
    @{ Name = "Suivi Budgétaire";    Folder = "/Département Finance" },
    @{ Name = "Tableau RH";          Folder = "/RH - Ressources Humaines" },
    @{ Name = "Dashboard IT";        Folder = "/IT Operations" },
    @{ Name = "KPI Direction";       Folder = "/Direction Générale" }
)

# ─── 3. Upload each report ───────────────────────────────────────
Write-Host "`n=== Uploading 5 reports to PBIRS ===" -ForegroundColor Cyan

$bytes = [System.IO.File]::ReadAllBytes($samplePbix)
$base64 = [Convert]::ToBase64String($bytes)
Write-Host "  File size: $([math]::Round($bytes.Length/1KB))KB, Base64 length: $($base64.Length)"

$successCount = 0

foreach ($report in $reports) {
    $name = $report.Name
    $folder = $report.Folder
    
    Write-Host "`n  Uploading '$name' to '$folder'..."
    
    $body = @{
        "@odata.type" = "#Model.PowerBIReport"
        "Content" = $base64
        "ContentType" = ""
        "Name" = $name
        "Path" = "$folder/$name"
    } | ConvertTo-Json -Depth 5
    
    try {
        $resp = Invoke-RestMethod -Uri "$apiUrl/PowerBIReports" `
            -Method Post `
            -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) `
            -ContentType "application/json; charset=utf-8" `
            -UseDefaultCredentials `
            -TimeoutSec 120
        
        Write-Host "  OK: $name (Id: $($resp.Id))" -ForegroundColor Green
        $successCount++
    } catch {
        $code = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { "?" }
        Write-Host "  FAILED ($code): $_" -ForegroundColor Red
        
        if ($_.Exception.Response) {
            try {
                $errStream = $_.Exception.Response.GetResponseStream()
                $reader = New-Object System.IO.StreamReader($errStream)
                Write-Host "  Error: $($reader.ReadToEnd())" -ForegroundColor Red
            } catch {}
        }
    }
}

Write-Host "`n=== Results: $successCount / $($reports.Count) uploaded ===" -ForegroundColor $(if ($successCount -eq $reports.Count) {"Green"} else {"Yellow"})

# ─── 4. Verify uploads ───────────────────────────────────────────
Write-Host "`n=== Verifying on PBIRS ===" -ForegroundColor Cyan
try {
    $pbiReports = Invoke-RestMethod -Uri "$apiUrl/PowerBIReports" `
        -Method Get `
        -UseDefaultCredentials `
        -ContentType "application/json"
    
    Write-Host "  Total PowerBI reports on server: $($pbiReports.value.Count)"
    foreach ($r in $pbiReports.value) {
        Write-Host "    - $($r.Name) @ $($r.Path)" -ForegroundColor Green
    }
} catch {
    Write-Host "  Verification failed: $_" -ForegroundColor Yellow
}
