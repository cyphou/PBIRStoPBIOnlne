Add-Type -AssemblyName System.Windows.Forms

$outPath = "C:\GitHub Project\PBIReporttoPBIOnline\scripts\artifacts\pbix\rs_fresh.pbix"
$outDir = Split-Path $outPath -Parent
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
if (Test-Path $outPath) { Remove-Item $outPath -Force }

$proc = Get-Process -Name "PBIDesktop" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc) {
    $exe = "C:\Program Files\Microsoft Power BI Desktop RS\bin\PBIDesktop.exe"
    Start-Process $exe
    Start-Sleep -Seconds 10
    $proc = Get-Process -Name "PBIDesktop" -ErrorAction SilentlyContinue | Select-Object -First 1
}
if (-not $proc) { Write-Host "NO_PBIDESKTOP"; exit 1 }

# Focus app and open Save As
$ws = New-Object -ComObject WScript.Shell
$null = $ws.AppActivate($proc.Id)
Start-Sleep -Milliseconds 600
[System.Windows.Forms.SendKeys]::SendWait("^+s")
Start-Sleep -Seconds 2

# Try multiple ways to target filename box and save
[System.Windows.Forms.Clipboard]::SetText($outPath)

# 1) File name accelerator then paste
[System.Windows.Forms.SendKeys]::SendWait("%n")
Start-Sleep -Milliseconds 300
[System.Windows.Forms.SendKeys]::SendWait("^a")
Start-Sleep -Milliseconds 120
[System.Windows.Forms.SendKeys]::SendWait("^v")
Start-Sleep -Milliseconds 350
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
Start-Sleep -Seconds 3

if (-not (Test-Path $outPath)) {
    # 2) Paste directly and force Save button accelerator
    [System.Windows.Forms.SendKeys]::SendWait("^a")
    Start-Sleep -Milliseconds 120
    [System.Windows.Forms.SendKeys]::SendWait("^v")
    Start-Sleep -Milliseconds 350
    [System.Windows.Forms.SendKeys]::SendWait("%s")
    Start-Sleep -Seconds 3
}

if (-not (Test-Path $outPath)) {
    # 3) Confirm overwrite if prompted
    [System.Windows.Forms.SendKeys]::SendWait("{LEFT}")
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
    Start-Sleep -Seconds 2
}

if (Test-Path $outPath) {
    $f = Get-Item $outPath
    Write-Host "SAVED_OK: $($f.FullName) ($($f.Length) bytes)"
    exit 0
}

Write-Host "SAVED_FAIL"
exit 1
