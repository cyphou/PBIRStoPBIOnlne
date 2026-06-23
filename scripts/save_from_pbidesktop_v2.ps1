# Simpler approach: save to Desktop with shorter path
Add-Type -AssemblyName System.Windows.Forms

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Helper {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
    [DllImport("user32.dll", SetLastError=true)] public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder text, int count);
}
"@

$proc = Get-Process -Id 50544
$hwnd = $proc.MainWindowHandle

# Restore and bring to front
if ([Win32Helper]::IsIconic($hwnd)) { [Win32Helper]::ShowWindow($hwnd, 9) }
[Win32Helper]::SetForegroundWindow($hwnd)
Start-Sleep -Seconds 1

# Verify it's in foreground
$fgHwnd = [Win32Helper]::GetForegroundWindow()
$sb = New-Object System.Text.StringBuilder(256)
[Win32Helper]::GetWindowText($fgHwnd, $sb, 256) | Out-Null
Write-Host "Foreground window: $($sb.ToString())" -ForegroundColor Cyan

# Save As
$savePath = "C:\Users\pidoudet\Desktop\rs_test.pbix"
Write-Host "Sending Ctrl+Shift+S..."
[System.Windows.Forms.SendKeys]::SendWait("^+s")
Start-Sleep -Seconds 3

# Check foreground window again (should be Save dialog)
$fgHwnd2 = [Win32Helper]::GetForegroundWindow()
$sb2 = New-Object System.Text.StringBuilder(256)
[Win32Helper]::GetWindowText($fgHwnd2, $sb2, 256) | Out-Null
Write-Host "After Ctrl+Shift+S, foreground: $($sb2.ToString())" -ForegroundColor Cyan

# Type path directly (no clipboard, simpler)
[System.Windows.Forms.SendKeys]::SendWait("^a")
Start-Sleep -Milliseconds 200

# Type each character  
foreach ($char in $savePath.ToCharArray()) {
    $sendChar = $char.ToString()
    # Handle special characters for SendKeys
    switch ($sendChar) {
        '+' { $sendChar = '{+}' }
        '^' { $sendChar = '{^}' }
        '%' { $sendChar = '{%}' }
        '~' { $sendChar = '{~}' }
        '(' { $sendChar = '{(}' }
        ')' { $sendChar = '{)}' }
        '{' { $sendChar = '{{}' }
        '}' { $sendChar = '{}}' }
    }
    [System.Windows.Forms.SendKeys]::SendWait($sendChar)
}
Start-Sleep -Milliseconds 500

Write-Host "Typed path: $savePath"
Write-Host "Pressing Enter..."
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
Start-Sleep -Seconds 5

if (Test-Path $savePath) {
    $size = (Get-Item $savePath).Length
    Write-Host "SUCCESS! File: $savePath ($size bytes)" -ForegroundColor Green
    
    # Check structure
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($savePath)
    Write-Host "Entries:"
    foreach ($e in $zip.Entries) {
        Write-Host "  $($e.FullName) ($($e.Length) bytes)"
    }
    $zip.Dispose()
} else {
    Write-Host "File not found. Pressing Enter again in case of overwrite confirm..."
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
    Start-Sleep -Seconds 5
    if (Test-Path $savePath) {
        Write-Host "SUCCESS (after confirm)! $((Get-Item $savePath).Length) bytes" -ForegroundColor Green
    } else {
        Write-Host "FAILED" -ForegroundColor Red
        # Check foreground window for clues
        $fgHwnd3 = [Win32Helper]::GetForegroundWindow()
        $sb3 = New-Object System.Text.StringBuilder(256)
        [Win32Helper]::GetWindowText($fgHwnd3, $sb3, 256) | Out-Null
        Write-Host "Current foreground: $($sb3.ToString())"
    }
}
