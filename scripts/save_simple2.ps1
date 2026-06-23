# Save blank report using Alt key trick for foreground + Ctrl+Shift+S
Add-Type -AssemblyName System.Windows.Forms

Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Threading;

public class FG {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool fAttach);
    [DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);
    [DllImport("user32.dll", CharSet=CharSet.Auto)] public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder text, int count);
    
    public const byte VK_MENU = 0x12;
    public const uint KEYEVENTF_KEYUP = 0x0002;
    
    public static string GetTitle(IntPtr hwnd) {
        var sb = new System.Text.StringBuilder(256);
        GetWindowText(hwnd, sb, 256);
        return sb.ToString();
    }
    
    public static bool BringToFront(IntPtr hwnd) {
        // Show the window first
        ShowWindow(hwnd, 9); // SW_RESTORE
        Thread.Sleep(200);
        
        // Press and release Alt to allow SetForegroundWindow from background
        keybd_event(VK_MENU, 0, 0, UIntPtr.Zero);
        keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, UIntPtr.Zero);
        Thread.Sleep(100);
        
        IntPtr fg = GetForegroundWindow();
        uint pid;
        uint fgThread = GetWindowThreadProcessId(fg, out pid);
        uint curThread = GetCurrentThreadId();
        
        AttachThreadInput(curThread, fgThread, true);
        SetForegroundWindow(hwnd);
        AttachThreadInput(curThread, fgThread, false);
        
        Thread.Sleep(500);
        return GetForegroundWindow() == hwnd;
    }
}
"@

$proc = Get-Process -Name "PBIDesktop" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc) {
    $pbiExe = "C:\Program Files\Microsoft Power BI Desktop RS\bin\PBIDesktop.exe"
    if (-not (Test-Path $pbiExe)) {
        Write-Host "PBI Desktop RS executable not found: $pbiExe" -ForegroundColor Red
        exit 1
    }
    Write-Host "Starting PBI Desktop RS..."
    Start-Process $pbiExe
    Start-Sleep -Seconds 12
    $proc = Get-Process -Name "PBIDesktop" -ErrorAction SilentlyContinue | Select-Object -First 1
}

if (-not $proc) {
    Write-Host "PBI Desktop RS process not found" -ForegroundColor Red
    exit 1
}

$hwnd = $proc.MainWindowHandle
if (-not $hwnd -or $hwnd -eq 0) {
    Start-Sleep -Seconds 2
    $proc.Refresh()
    $hwnd = $proc.MainWindowHandle
}
Write-Host "PBI Desktop RS: PID=$($proc.Id), Handle=$hwnd"

# Bring to front
$ok = [FG]::BringToFront($hwnd)
Write-Host "BringToFront result: $ok"

$fg = [FG]::GetForegroundWindow()
$title = [FG]::GetTitle($fg)
Write-Host "Foreground: '$title'"

if (!$ok) {
    Write-Host "Retry..."
    Start-Sleep -Milliseconds 500
    [FG]::BringToFront($hwnd) | Out-Null
    Start-Sleep -Milliseconds 500
    $fg = [FG]::GetForegroundWindow()
    $title = [FG]::GetTitle($fg)
    Write-Host "Foreground after retry: '$title'"
}

if ($title -like "*Power BI Desktop*") {
    Write-Host "PBI Desktop RS has focus!" -ForegroundColor Green
    Start-Sleep -Seconds 1
    
    # Send Ctrl+Shift+S for Save As
    Write-Host "Sending Ctrl+Shift+S..."
    [System.Windows.Forms.SendKeys]::SendWait("^+s")
    Start-Sleep -Seconds 4
    
    # Check foreground
    $fg2 = [FG]::GetForegroundWindow()
    $title2 = [FG]::GetTitle($fg2)
    Write-Host "After Ctrl+Shift+S: '$title2'"

    if ($title2 -like "*Something went wrong*") {
        Write-Host "Error dialog detected. Dismissing and retrying Save As..." -ForegroundColor Yellow
        [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
        Start-Sleep -Seconds 2
        [System.Windows.Forms.SendKeys]::SendWait("^+s")
        Start-Sleep -Seconds 3
        $fg2 = [FG]::GetForegroundWindow()
        $title2 = [FG]::GetTitle($fg2)
        Write-Host "After retry Ctrl+Shift+S: '$title2'"
    }
    
    if ($title2 -like "*Save*" -or $title2 -like "*Enregistrer*") {
        Write-Host "Save dialog opened!" -ForegroundColor Green
        $savePath = "C:\Users\pidoudet\OneDrive - Microsoft\Boulot\PBI SME\OracleToPostgre\PBIReporttoPBIOnline\scripts\artifacts\pbix\rs_test.pbix"
        $saveDir = Split-Path $savePath -Parent
        if (-not (Test-Path $saveDir)) {
            New-Item -ItemType Directory -Path $saveDir -Force | Out-Null
        }
        Start-Sleep -Milliseconds 500
        
        # Type save path using clipboard
        [System.Windows.Forms.Clipboard]::SetText($savePath)
        [System.Windows.Forms.SendKeys]::SendWait("^a")
        Start-Sleep -Milliseconds 200
        [System.Windows.Forms.SendKeys]::SendWait("^v")
        Start-Sleep -Milliseconds 500
        [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
        Start-Sleep -Seconds 5
        
        if (Test-Path $savePath) {
            $sz = (Get-Item $savePath).Length
            Write-Host "SUCCESS! Saved: $savePath ($sz bytes)" -ForegroundColor Green
        } else {
            [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
            Start-Sleep -Seconds 3
            if (Test-Path $savePath) {
                $sz = (Get-Item $savePath).Length
                Write-Host "SUCCESS! Saved: $savePath ($sz bytes)" -ForegroundColor Green
            } else {
                Write-Host "File not saved" -ForegroundColor Red
            }
        }
    } elseif ($title2 -like "*Power BI*") {
        # Ctrl+Shift+S may have opened backstage instead of dialog
        Write-Host "Backstage may have opened. Exploring..."
        
        Add-Type -AssemblyName UIAutomationClient
        Add-Type -AssemblyName UIAutomationTypes
        
        $root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
        $allElems = $root.FindAll(
            [System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.Condition]::TrueCondition
        )
        
        Write-Host "`nNamed elements:"
        $count = 0
        foreach ($elem in $allElems) {
            $name = $elem.Current.Name
            $type = $elem.Current.ControlType.ProgrammaticName -replace 'ControlType\.', ''
            if ($name -and $name.Length -gt 0 -and $name.Length -lt 100) {
                Write-Host "  [$type] '$name'"
                $count++
                if ($count -ge 80) { break }
            }
        }
        
        # Press Escape to close backstage
        [System.Windows.Forms.SendKeys]::SendWait("{ESCAPE}")
    } else {
        Write-Host "Unexpected foreground: '$title2'" -ForegroundColor Yellow
    }
} else {
    Write-Host "Could not focus PBI Desktop RS" -ForegroundColor Red
}
