# Build on progress: File tab works, Save As window found
# Now need to navigate inside Save As to find Browse button or file input
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinHelper2 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll", CharSet=CharSet.Auto)] public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder text, int count);
    [DllImport("user32.dll")] public static extern void mouse_event(int dwFlags, int dx, int dy, int dwData, IntPtr dwExtraInfo);
    public const int MOUSEEVENTF_LEFTDOWN = 0x02;
    public const int MOUSEEVENTF_LEFTUP = 0x04;
    public static void Click() {
        mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, IntPtr.Zero);
        System.Threading.Thread.Sleep(50);
        mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, IntPtr.Zero);
    }
    public static string GetFgTitle() {
        var sb = new System.Text.StringBuilder(256);
        GetWindowText(GetForegroundWindow(), sb, 256);
        return sb.ToString();
    }
}
"@

$proc = Get-Process -Id 50544
$hwnd = $proc.MainWindowHandle

# Restore and focus
if ([WinHelper2]::IsIconic($hwnd)) { [WinHelper2]::ShowWindow($hwnd, 9); Start-Sleep -Milliseconds 500 }
[WinHelper2]::SetForegroundWindow($hwnd)
Start-Sleep -Milliseconds 500

$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)

# Select File tab
$fileTab = $root.FindFirst(
    [System.Windows.Automation.TreeScope]::Descendants,
    (New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, "File"
    ))
)
$selPattern = $fileTab.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
$selPattern.Select()
Write-Host "File tab selected" -ForegroundColor Green
Start-Sleep -Seconds 2

# Now find the Save As window element
$saveAsWin = $root.FindFirst(
    [System.Windows.Automation.TreeScope]::Descendants,
    (New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, "Save As"
    ))
)

if ($saveAsWin) {
    Write-Host "Save As window found" -ForegroundColor Green
    
    # Deep search all descendant elements in the Save As window
    Write-Host "`nSave As window contents:"
    $all = $saveAsWin.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.Condition]::TrueCondition
    )
    
    foreach ($elem in $all) {
        $name = $elem.Current.Name
        $type = $elem.Current.ControlType.ProgrammaticName
        $autoId = $elem.Current.AutomationId
        if ($name -or $autoId) {
            Write-Host "  '$name' ($type) [AutoId: $autoId]"
        }
    }
    
    # Look for "Browse" or "Parcourir" button (French)
    $browse = $saveAsWin.FindFirst(
        [System.Windows.Automation.TreeScope]::Descendants,
        (New-Object System.Windows.Automation.OrCondition(
            (New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::NameProperty, "Browse")),
            (New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::NameProperty, "Parcourir")),
            (New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::NameProperty, "This PC")),
            (New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::NameProperty, "Ce PC"))
        ))
    )
    
    if ($browse) {
        Write-Host "`nFound browse/this PC: '$($browse.Current.Name)' ($($browse.Current.ControlType.ProgrammaticName))" -ForegroundColor Green
        $bPatterns = $browse.GetSupportedPatterns()
        Write-Host "Patterns: $($bPatterns | ForEach-Object { $_.ProgrammaticName })"
        
        try {
            $invP = $browse.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
            $invP.Invoke()
            Write-Host "Invoked Browse" -ForegroundColor Green
            Start-Sleep -Seconds 3
        } catch {
            try {
                $cp = $browse.GetClickablePoint()
                [System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point([int]$cp.X, [int]$cp.Y)
                Start-Sleep -Milliseconds 200
                [WinHelper2]::Click()
                Write-Host "Clicked Browse" -ForegroundColor Green
                Start-Sleep -Seconds 3
            } catch {
                Write-Host "Cannot interact with Browse: $_"
            }
        }
        
        # Now the standard file dialog should be open
        $fgTitle = [WinHelper2]::GetFgTitle()
        Write-Host "Foreground after Browse: '$fgTitle'"
        
        if ($fgTitle -like "*Save*" -or $fgTitle -like "*Enregistrer*") {
            $savePath = "C:\Users\pidoudet\Desktop\rs_test.pbix"
            [System.Windows.Forms.Clipboard]::SetText($savePath)
            [System.Windows.Forms.SendKeys]::SendWait("^a")
            Start-Sleep -Milliseconds 200
            [System.Windows.Forms.SendKeys]::SendWait("^v")
            Start-Sleep -Milliseconds 500
            [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
            Start-Sleep -Seconds 5
            
            if (Test-Path $savePath) {
                Write-Host "`nSUCCESS! $savePath ($((Get-Item $savePath).Length) bytes)" -ForegroundColor Green
            } else {
                # Maybe overwrite confirmation
                [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
                Start-Sleep -Seconds 3
                if (Test-Path $savePath) {
                    Write-Host "`nSUCCESS! $savePath ($((Get-Item $savePath).Length) bytes)" -ForegroundColor Green
                } else {
                    Write-Host "`nFile not saved" -ForegroundColor Red
                }
            }
        }
    } else {
        Write-Host "`nBrowse button NOT found" -ForegroundColor Yellow
    }
} else {
    Write-Host "Save As window NOT found" -ForegroundColor Red
}

# Clean up - go back to Home tab
Start-Sleep -Seconds 1
[System.Windows.Forms.SendKeys]::SendWait("{ESCAPE}")
