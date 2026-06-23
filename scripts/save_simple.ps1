# Simple approach: Ctrl+Shift+S to Save As (PowerPoint is now killed)
Add-Type -AssemblyName System.Windows.Forms

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class FocusHelper {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool fAttach);
    [DllImport("user32.dll", CharSet=CharSet.Auto)] public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder text, int count);
    
    public static string GetTitle(IntPtr hwnd) {
        var sb = new System.Text.StringBuilder(256);
        GetWindowText(hwnd, sb, 256);
        return sb.ToString();
    }
    
    public static bool ForceForeground(IntPtr hwnd) {
        IntPtr fg = GetForegroundWindow();
        uint pid;
        uint fgThread = GetWindowThreadProcessId(fg, out pid);
        uint curThread = GetCurrentThreadId();
        if (fgThread != curThread) {
            AttachThreadInput(curThread, fgThread, true);
            SetForegroundWindow(hwnd);
            AttachThreadInput(curThread, fgThread, false);
        } else {
            SetForegroundWindow(hwnd);
        }
        System.Threading.Thread.Sleep(200);
        return GetForegroundWindow() == hwnd;
    }
}
"@

$proc = Get-Process -Id 8048
$hwnd = $proc.MainWindowHandle
Write-Host "PBI Desktop RS: PID=$($proc.Id), Handle=$hwnd"

# Force to foreground
$result = [FocusHelper]::ForceForeground($hwnd)
Write-Host "Foreground: $result"
Start-Sleep -Seconds 1

# Verify foreground
$fg = [FocusHelper]::GetForegroundWindow()
$fgTitle = [FocusHelper]::GetTitle($fg)
Write-Host "Foreground window: '$fgTitle'"

if ($fgTitle -like "*Power BI Desktop*") {
    Write-Host "PBI Desktop RS has focus" -ForegroundColor Green
    
    # Send Ctrl+Shift+S for Save As
    Write-Host "Sending Ctrl+Shift+S..."
    [System.Windows.Forms.SendKeys]::SendWait("^+s")
    Start-Sleep -Seconds 3
    
    # Check what's now in foreground
    $fg2 = [FocusHelper]::GetForegroundWindow()
    $fg2Title = [FocusHelper]::GetTitle($fg2)
    Write-Host "Foreground after Ctrl+Shift+S: '$fg2Title'"
    
    if ($fg2Title -like "*Save*" -or $fg2Title -like "*Enregistrer*") {
        Write-Host "Save As dialog opened!" -ForegroundColor Green
        $savePath = "C:\Users\pidoudet\Desktop\rs_test.pbix"
        Start-Sleep -Milliseconds 500
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
            # Maybe overwrite prompt
            [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
            Start-Sleep -Seconds 3
            if (Test-Path $savePath) {
                $sz = (Get-Item $savePath).Length
                Write-Host "SUCCESS! Saved: $savePath ($sz bytes)" -ForegroundColor Green
            } else {
                Write-Host "File not saved" -ForegroundColor Red
            }
        }
    } else {
        Write-Host "Save As dialog did NOT open. Might need backstage nav." -ForegroundColor Yellow
        
        # Check if backstage opened instead (PBI's File menu)
        # Try using UIAutomation to find elements
        Add-Type -AssemblyName UIAutomationClient
        Add-Type -AssemblyName UIAutomationTypes
        
        $root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
        
        # Search for Save-related elements
        $allElems = $root.FindAll(
            [System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.Condition]::TrueCondition
        )
        
        Write-Host "`nAll named elements (first 80):"
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
    }
} else {
    Write-Host "Could not get focus on PBI Desktop RS. Foreground: '$fgTitle'" -ForegroundColor Red
}
