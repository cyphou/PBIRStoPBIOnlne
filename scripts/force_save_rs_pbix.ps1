Add-Type -AssemblyName System.Windows.Forms

$savePath = "C:\Users\pidoudet\OneDrive - Microsoft\Boulot\PBI SME\OracleToPostgre\PBIReporttoPBIOnline\scripts\artifacts\pbix\rs_test.pbix"
$saveDir = Split-Path $savePath -Parent
if (-not (Test-Path $saveDir)) { New-Item -ItemType Directory -Path $saveDir -Force | Out-Null }
if (Test-Path $savePath) { Remove-Item $savePath -Force }

$ws = New-Object -ComObject WScript.Shell

# Ensure PBI Desktop RS is running
$p = Get-Process -Name PBIDesktop -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $p) {
    $exe = "C:\Program Files\Microsoft Power BI Desktop RS\bin\PBIDesktop.exe"
    if (-not (Test-Path $exe)) { Write-Host "PBI Desktop RS not found"; exit 1 }
    Start-Process $exe
    Start-Sleep -Seconds 12
}

# Focus Power BI window
$activated = $ws.AppActivate("Power BI Desktop")
Write-Host "AppActivate: $activated"
Start-Sleep -Milliseconds 500

# Dismiss any blocking dialog
[System.Windows.Forms.SendKeys]::SendWait("{ESC}")
Start-Sleep -Milliseconds 500
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
Start-Sleep -Seconds 1

# Try Save As shortcuts
[System.Windows.Forms.SendKeys]::SendWait("^+s")
Start-Sleep -Seconds 2
[System.Windows.Forms.SendKeys]::SendWait("{F12}")
Start-Sleep -Seconds 2

# Paste full path and save
[System.Windows.Forms.Clipboard]::SetText($savePath)
[System.Windows.Forms.SendKeys]::SendWait("^a")
Start-Sleep -Milliseconds 200
[System.Windows.Forms.SendKeys]::SendWait("^v")
Start-Sleep -Milliseconds 400
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
Start-Sleep -Seconds 4

# Confirm overwrite if prompted
[System.Windows.Forms.SendKeys]::SendWait("{LEFT}")
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
Start-Sleep -Seconds 2

if (Test-Path $savePath) {
    $f = Get-Item $savePath
    Write-Host "SAVED_OK: $($f.FullName) ($($f.Length) bytes)"
    exit 0
}

Write-Host "SAVED_FAIL"
exit 1
