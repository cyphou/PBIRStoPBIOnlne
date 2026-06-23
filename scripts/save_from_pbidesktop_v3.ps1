# More robust approach - explicitly target PBI Desktop RS window
Add-Type -AssemblyName System.Windows.Forms

Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;

public class WinApi {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
    [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool fAttach);
    [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
    
    public static void ForceSetForeground(IntPtr hWnd) {
        IntPtr fg = GetForegroundWindow();
        uint fgThread, myThread;
        uint fgPid;
        fgThread = GetWindowThreadProcessId(fg, out fgPid);
        myThread = GetCurrentThreadId();
        if (fgThread != myThread) {
            AttachThreadInput(fgThread, myThread, true);
            SetForegroundWindow(hWnd);
            BringWindowToTop(hWnd);
            AttachThreadInput(fgThread, myThread, false);
        } else {
            SetForegroundWindow(hWnd);
            BringWindowToTop(hWnd);
        }
    }
    
    public static string GetTitle(IntPtr hWnd) {
        var sb = new StringBuilder(256);
        GetWindowText(hWnd, sb, 256);
        return sb.ToString();
    }
}
"@

function Get-ForegroundTitle {
    [WinApi]::GetTitle([WinApi]::GetForegroundWindow())
}

# Find PBI Desktop RS window
$proc = Get-Process -Id 50544 -ErrorAction Stop
$hwnd = $proc.MainWindowHandle
Write-Host "PBI Desktop RS PID: 50544, Handle: $hwnd" -ForegroundColor Cyan
Write-Host "Title: $($proc.MainWindowTitle)"

# Close any save dialog from PowerPoint first
Start-Sleep -Milliseconds 500
$fgTitle = Get-ForegroundTitle
Write-Host "Current foreground: '$fgTitle'"
if ($fgTitle -like "*Save*") {
    Write-Host "Closing stale Save dialog..."
    [System.Windows.Forms.SendKeys]::SendWait("{ESCAPE}")
    Start-Sleep -Seconds 1
}

# Force PBI Desktop RS to foreground
Write-Host "Forcing PBI Desktop RS to foreground..."
if ([WinApi]::IsIconic($hwnd)) { [WinApi]::ShowWindow($hwnd, 9) }
[WinApi]::ForceSetForeground($hwnd)
Start-Sleep -Seconds 1

# Verify
$fgTitle = Get-ForegroundTitle
Write-Host "Foreground after force: '$fgTitle'"

if ($fgTitle -notlike "*Power BI Desktop*") {
    Write-Host "WARNING: PBI Desktop RS is NOT in foreground!" -ForegroundColor Yellow
    # Try clicking on the taskbar
    [WinApi]::ShowWindow($hwnd, 5) # SW_SHOW
    Start-Sleep -Milliseconds 500
    [WinApi]::ForceSetForeground($hwnd)
    Start-Sleep -Seconds 1
    $fgTitle = Get-ForegroundTitle
    Write-Host "Retry foreground: '$fgTitle'"
}

if ($fgTitle -notlike "*Power BI Desktop*") {
    Write-Host "Cannot bring PBI Desktop RS to focus. Aborting." -ForegroundColor Red
    exit 1
}

# Now send Ctrl+Shift+S
$savePath = "C:\Users\pidoudet\Desktop\rs_test.pbix"
Write-Host "`nSending Ctrl+Shift+S for Save As..."
[System.Windows.Forms.SendKeys]::SendWait("^+s")
Start-Sleep -Seconds 3

$fgTitle = Get-ForegroundTitle
Write-Host "After save shortcut, foreground: '$fgTitle'"

if ($fgTitle -like "*Save*" -or $fgTitle -like "*Enregistrer*") {
    Write-Host "Save dialog detected!" -ForegroundColor Green
    
    # Clear filename and type new path
    [System.Windows.Forms.SendKeys]::SendWait("^a")
    Start-Sleep -Milliseconds 200
    
    # Use clipboard for safe path insertion
    [System.Windows.Forms.Clipboard]::SetText($savePath)
    Start-Sleep -Milliseconds 200
    [System.Windows.Forms.SendKeys]::SendWait("^v")
    Start-Sleep -Milliseconds 500
    
    Write-Host "Path pasted: $savePath"
    Write-Host "Pressing Enter..."
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
    Start-Sleep -Seconds 5
    
    # Check for overwrite confirmation
    $fgTitle2 = Get-ForegroundTitle
    Write-Host "After Enter, foreground: '$fgTitle2'"
    if ($fgTitle2 -like "*confirm*" -or $fgTitle2 -like "*replace*" -or $fgTitle2 -like "*remplacer*") {
        Write-Host "Confirming overwrite..."
        [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
        Start-Sleep -Seconds 5
    }
} else {
    Write-Host "No save dialog detected. Maybe Ctrl+S works for new files?" -ForegroundColor Yellow
    [System.Windows.Forms.SendKeys]::SendWait("{ESCAPE}")
    Start-Sleep -Seconds 1
    
    # Try File > Save As via Alt+F, then A
    Write-Host "Trying Alt+F, A..."
    [System.Windows.Forms.SendKeys]::SendWait("%f")
    Start-Sleep -Seconds 2
    $fgTitle = Get-ForegroundTitle
    Write-Host "After Alt+F: '$fgTitle'"
}

# Check result
if (Test-Path $savePath) {
    $size = (Get-Item $savePath).Length
    Write-Host "`nSUCCESS! File: $savePath ($size bytes)" -ForegroundColor Green
} else {
    Write-Host "`nFile not found at $savePath" -ForegroundColor Red
    Write-Host "Checking Desktop for any .pbix files..."
    Get-ChildItem "$env:USERPROFILE\Desktop" -Filter "*.pbix" -ErrorAction SilentlyContinue | 
        Select-Object Name,Length,LastWriteTime | Format-Table -AutoSize
    
    Write-Host "Sending Escape to clean up..."
    [System.Windows.Forms.SendKeys]::SendWait("{ESCAPE}")
    Start-Sleep -Milliseconds 500
    [System.Windows.Forms.SendKeys]::SendWait("{ESCAPE}")
}
