$ErrorActionPreference = "Stop"
$base = "$env:LOCALAPPDATA\Microsoft\Power BI Desktop SSRS"
$userZip = Join-Path $base "User.zip"
$backupDir = Join-Path $base ("Backup_" + (Get-Date -Format "yyyyMMdd_HHmmss"))

New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

if (Test-Path $userZip) {
    Copy-Item $userZip (Join-Path $backupDir "User.zip.bak") -Force
    Remove-Item $userZip -Force
    Write-Host "RESET_USERZIP_OK"
}
else {
    Write-Host "RESET_USERZIP_MISSING"
}

foreach ($d in @("TempSaves", "AnalysisServicesWorkspaces", "WebView2", "WebView2Elevated")) {
    $p = Join-Path $base $d
    if (Test-Path $p) {
        $dst = Join-Path $backupDir $d
        Move-Item $p $dst -Force
        Write-Host "RESET_MOVED_$d"
    }
    else {
        Write-Host "RESET_MISSING_$d"
    }
}

Get-Process PBIDesktop -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Write-Host "PBIDESKTOP_RESTART_READY"
Write-Host "BACKUP_DIR=$backupDir"
