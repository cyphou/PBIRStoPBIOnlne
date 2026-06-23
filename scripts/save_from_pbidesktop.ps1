# Use UI Automation to save a blank report from PBI Desktop RS
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName UIAutomationClient

# Find the PBI Desktop RS window
$proc = Get-Process -Id 50544 -ErrorAction SilentlyContinue
if (!$proc) {
    Write-Host "PBI Desktop RS not found at PID 50544" -ForegroundColor Red
    exit 1
}

Write-Host "Found PBI Desktop RS: $($proc.MainWindowTitle)" -ForegroundColor Cyan
Write-Host "Window Handle: $($proc.MainWindowHandle)"

# Bring window to foreground
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
}
"@

$hwnd = $proc.MainWindowHandle
if ([Win32]::IsIconic($hwnd)) {
    [Win32]::ShowWindow($hwnd, 9) # SW_RESTORE
}
[Win32]::SetForegroundWindow($hwnd)
Start-Sleep -Milliseconds 500

# Check current window title to understand state
$proc.Refresh()
Write-Host "Current title: $($proc.MainWindowTitle)"

# Send Ctrl+Shift+S for Save As
Write-Host "Sending Ctrl+Shift+S (Save As)..."
[System.Windows.Forms.SendKeys]::SendWait("^+s")
Start-Sleep -Seconds 2

# The Save As dialog should now be open
# Type the file path
$savePath = "C:\Users\pidoudet\OneDrive - Microsoft\Boulot\PBI SME\OracleToPostgre\PBIReporttoPBIOnline\scripts\artifacts\pbix\rs_blank_report.pbix"
Write-Host "Typing save path: $savePath"

# Clear any existing text in the filename field
[System.Windows.Forms.SendKeys]::SendWait("^a")
Start-Sleep -Milliseconds 200

# Type the path (SendKeys needs special handling for some characters)
# Use clipboard instead of SendKeys for special characters
[System.Windows.Forms.Clipboard]::SetText($savePath)
[System.Windows.Forms.SendKeys]::SendWait("^v")
Start-Sleep -Milliseconds 500

# Press Enter to save
Write-Host "Pressing Enter to save..."
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
Start-Sleep -Seconds 3

# Check if file was created
if (Test-Path $savePath) {
    $size = (Get-Item $savePath).Length
    Write-Host "SUCCESS! File saved: $savePath ($size bytes)" -ForegroundColor Green
} else {
    Write-Host "File not found at expected path. Checking for save dialog..." -ForegroundColor Yellow
    # Maybe there's a confirmation dialog
    Start-Sleep -Seconds 1
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
    Start-Sleep -Seconds 3
    if (Test-Path $savePath) {
        $size = (Get-Item $savePath).Length
        Write-Host "SUCCESS (after confirmation)! File saved: $savePath ($size bytes)" -ForegroundColor Green
    } else {
        Write-Host "FAILED - file not created" -ForegroundColor Red
        # Take a screenshot to see what happened
        Write-Host "Try pressing Escape to close any dialogs..."
        [System.Windows.Forms.SendKeys]::SendWait("{ESCAPE}")
    }
}
