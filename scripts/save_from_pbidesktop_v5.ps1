# Use UIAutomation SelectionItemPattern for File tab
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
}
"@

$proc = Get-Process -Id 50544 -ErrorAction Stop
$hwnd = $proc.MainWindowHandle

# Ensure visible
if ([Win]::IsIconic($hwnd)) { [Win]::ShowWindow($hwnd, 9); Start-Sleep -Milliseconds 500 }
[Win]::SetForegroundWindow($hwnd)
Start-Sleep -Milliseconds 500

$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)

# Find File tab and use SelectionItemPattern
$fileTab = $root.FindFirst(
    [System.Windows.Automation.TreeScope]::Descendants,
    (New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, "File"
    ))
)

if ($fileTab) {
    Write-Host "File tab: $($fileTab.Current.ControlType.ProgrammaticName)" -ForegroundColor Cyan
    
    # List supported patterns
    $patterns = $fileTab.GetSupportedPatterns()
    Write-Host "Supported patterns: $($patterns | ForEach-Object { $_.ProgrammaticName })"
    
    # Try SelectionItemPattern
    try {
        $selPattern = $fileTab.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
        Write-Host "Selecting File tab..."
        $selPattern.Select()
        Start-Sleep -Seconds 3
        Write-Host "File tab selected" -ForegroundColor Green
    } catch {
        Write-Host "SelectionItemPattern failed: $_" -ForegroundColor Yellow
    }
    
    # Try LegacyIAccessiblePattern if available
    # Or try clicking it
    try {
        $clickable = $fileTab.GetClickablePoint()
        Write-Host "Clickable point: $($clickable.X), $($clickable.Y)"
        # Move mouse and click
        [System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point([int]$clickable.X, [int]$clickable.Y)
        Start-Sleep -Milliseconds 200
        
        Add-Type @"
using System;
using System.Runtime.InteropServices;
public class MouseClick {
    [DllImport("user32.dll")] public static extern void mouse_event(int dwFlags, int dx, int dy, int dwData, IntPtr dwExtraInfo);
    public const int MOUSEEVENTF_LEFTDOWN = 0x02;
    public const int MOUSEEVENTF_LEFTUP = 0x04;
    public static void Click() {
        mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, IntPtr.Zero);
        mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, IntPtr.Zero);
    }
}
"@
        [MouseClick]::Click()
        Write-Host "Clicked File tab" -ForegroundColor Green
        Start-Sleep -Seconds 2
    } catch {
        Write-Host "Click failed: $_" -ForegroundColor Yellow
    }
    
    # Now look for Save As in the backstage view
    Write-Host "`nSearching for Save As / Enregistrer sous..."
    $saveAs = $root.FindFirst(
        [System.Windows.Automation.TreeScope]::Descendants,
        (New-Object System.Windows.Automation.OrCondition(
            (New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::NameProperty, "Save as")),
            (New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::NameProperty, "Enregistrer sous")),
            (New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::NameProperty, "Save As"))
        ))
    )
    
    if ($saveAs) {
        Write-Host "Found 'Save As': $($saveAs.Current.ControlType.ProgrammaticName)" -ForegroundColor Green
        $saPatterns = $saveAs.GetSupportedPatterns()
        Write-Host "Patterns: $($saPatterns | ForEach-Object { $_.ProgrammaticName })"
        
        try {
            $invokeP = $saveAs.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
            $invokeP.Invoke()
            Write-Host "Invoked Save As" -ForegroundColor Green
            Start-Sleep -Seconds 3
        } catch {
            # Try clicking
            try {
                $cp = $saveAs.GetClickablePoint()
                [System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point([int]$cp.X, [int]$cp.Y)
                Start-Sleep -Milliseconds 200
                [MouseClick]::Click()
                Write-Host "Clicked Save As" -ForegroundColor Green
                Start-Sleep -Seconds 3
            } catch {
                Write-Host "Cannot click Save As: $_"
            }
        }
        
        # Now handle the file save dialog
        $savePath = "C:\Users\pidoudet\Desktop\rs_test.pbix"
        Write-Host "Typing save path..."
        [System.Windows.Forms.Clipboard]::SetText($savePath)
        [System.Windows.Forms.SendKeys]::SendWait("^a")
        Start-Sleep -Milliseconds 200
        [System.Windows.Forms.SendKeys]::SendWait("^v")
        Start-Sleep -Milliseconds 500
        [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
        Start-Sleep -Seconds 5
        
        if (Test-Path $savePath) {
            Write-Host "SUCCESS! $savePath ($((Get-Item $savePath).Length) bytes)" -ForegroundColor Green
        } else {
            Write-Host "File not saved yet..." -ForegroundColor Yellow
            [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
            Start-Sleep -Seconds 3
            if (Test-Path $savePath) {
                Write-Host "SUCCESS! $savePath ($((Get-Item $savePath).Length) bytes)" -ForegroundColor Green
            }
        }
    } else {
        Write-Host "Save As not found. Listing backstage elements..."
        $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
        $child = $walker.GetFirstChild($root)
        $visited = 0
        while ($child -and $visited -lt 50) {
            $n = $child.Current.Name
            $t = $child.Current.ControlType.ProgrammaticName
            if ($n -and $n.Length -gt 0) { Write-Host "  '$n' ($t)" }
            $child = $walker.GetNextSibling($child)
            $visited++
        }
    }
}

# Close backstage if still open
Start-Sleep -Seconds 1
[System.Windows.Forms.SendKeys]::SendWait("{ESCAPE}")
