param(
    [string]$OutputPath = "C:\GitHub Project\PBIReporttoPBIOnline\scripts\artifacts\pbix\rs_fresh.pbix"
)

Add-Type -AssemblyName System.Windows.Forms

$ErrorActionPreference = "Stop"

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinApi {
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
}
"@

$exe = "C:\Program Files\Microsoft Power BI Desktop RS\bin\PBIDesktop.exe"
$proc = Get-Process -Name "PBIDesktop" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc) {
    if (-not (Test-Path $exe)) { throw "PBIDesktop RS not found at $exe" }
    Start-Process $exe | Out-Null
    Start-Sleep -Seconds 12
    $proc = Get-Process -Name "PBIDesktop" -ErrorAction SilentlyContinue | Select-Object -First 1
}
if (-not $proc) { throw "PBIDesktop process not found" }

for ($i = 0; $i -lt 20 -and ($proc.MainWindowHandle -eq 0); $i++) {
    Start-Sleep -Milliseconds 500
    $proc.Refresh()
}
if ($proc.MainWindowHandle -eq 0) { throw "PBIDesktop main window handle unavailable" }

$dir = Split-Path $OutputPath -Parent
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
if (Test-Path $OutputPath) { Remove-Item $OutputPath -Force }

[WinApi]::ShowWindow($proc.MainWindowHandle, 9) | Out-Null
Start-Sleep -Milliseconds 300
[WinApi]::SetForegroundWindow($proc.MainWindowHandle) | Out-Null
Start-Sleep -Milliseconds 500

# Dismiss common blocking dialog(s)
[System.Windows.Forms.SendKeys]::SendWait("{ESC}")
Start-Sleep -Milliseconds 300
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
Start-Sleep -Seconds 1

$attempts = @("^+s", "{F12}", "%fa")
foreach ($shortcut in $attempts) {
    [WinApi]::SetForegroundWindow($proc.MainWindowHandle) | Out-Null
    Start-Sleep -Milliseconds 250

    [System.Windows.Forms.SendKeys]::SendWait($shortcut)
    Start-Sleep -Seconds 2

    [System.Windows.Forms.Clipboard]::SetText($OutputPath)
    [System.Windows.Forms.SendKeys]::SendWait("^a")
    Start-Sleep -Milliseconds 150
    [System.Windows.Forms.SendKeys]::SendWait("^v")
    Start-Sleep -Milliseconds 300
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
    Start-Sleep -Seconds 4

    # Confirm overwrite dialog if it appeared
    [System.Windows.Forms.SendKeys]::SendWait("{LEFT}")
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
    Start-Sleep -Seconds 1

    if (Test-Path $OutputPath) {
        $f = Get-Item $OutputPath
        Write-Host "SAVED_OK: $($f.FullName) ($($f.Length) bytes)"
        exit 0
    }

    # Try to close any leftover modal and retry
    [System.Windows.Forms.SendKeys]::SendWait("{ESC}")
    Start-Sleep -Milliseconds 500
}

Write-Host "SAVED_FAIL"
exit 1
