# Use PostMessage to send keys directly to PBI Desktop RS window (bypasses foreground issue)
Add-Type -AssemblyName System.Windows.Forms

Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;

public class DirectInput {
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);
    
    [DllImport("user32.dll")] public static extern IntPtr FindWindowEx(IntPtr hwndParent, IntPtr hwndChildAfter, string lpszClass, string lpszWindow);
    [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr window, EnumWindowsProc callback, IntPtr lParam);
    
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    
    public const uint WM_KEYDOWN = 0x0100;
    public const uint WM_KEYUP = 0x0101;
    public const uint WM_CHAR = 0x0102;
    public const uint WM_SYSCOMMAND = 0x0112;
    public const uint SC_RESTORE = 0xF120;
    
    public static string GetTitle(IntPtr hWnd) {
        var sb = new StringBuilder(256);
        GetWindowText(hWnd, sb, 256);
        return sb.ToString();
    }
}
"@

$proc = Get-Process -Id 50544 -ErrorAction Stop
$hwnd = $proc.MainWindowHandle
Write-Host "PBI Desktop RS Handle: $hwnd, Title: $($proc.MainWindowTitle)" -ForegroundColor Cyan

# Alternative approach: use Alt+F4 style menu access
# In PBI Desktop RS, File > Save As is accessible via the Backstage view
# Let's try Ctrl+S which should trigger Save As for unsaved files

# First, ensure it's visible
if ([DirectInput]::IsIconic($hwnd)) {
    [DirectInput]::ShowWindow($hwnd, 9)
    Start-Sleep -Milliseconds 500
}

# Try PostMessage approach
Write-Host "`nSending WM_KEYDOWN for Ctrl+S directly to PBI Desktop..."
# Need to find the active child window that accepts input

# List child windows
$children = New-Object System.Collections.ArrayList
$callback = [DirectInput+EnumWindowsProc]{
    param($h, $l)
    $title = [DirectInput]::GetTitle($h)
    if ($title) { 
        $null = $script:children.Add(@{ Handle = $h; Title = $title })
    }
    return $true
}
[DirectInput]::EnumChildWindows($hwnd, $callback, [IntPtr]::Zero) | Out-Null
Write-Host "Found $($children.Count) child windows with titles:"
$children | ForEach-Object { Write-Host "  $($_.Handle): $($_.Title)" }

# Instead of PostMessage, let's try a more reliable approach:
# Use the .NET Process.Start to invoke PBI Desktop RS with a file to open,
# then save it. But PBI Desktop RS might not accept files to open via CLI.

# ALTERNATIVE: Use Accessibility/UIAutomation to click the File menu
Write-Host "`n=== Trying UIAutomation approach ==="

# Use UIAutomation to find and click buttons
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$auto = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
Write-Host "UIAutomation element found: $($auto.Current.Name)"

# Find the File tab/button in the ribbon
$fileTab = $auto.FindFirst(
    [System.Windows.Automation.TreeScope]::Descendants,
    (New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, "File"
    ))
)

if ($fileTab) {
    Write-Host "Found 'File' element: $($fileTab.Current.ControlType.ProgrammaticName)" -ForegroundColor Green
    # Try to invoke it
    try {
        $invokePattern = $fileTab.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
        $invokePattern.Invoke()
        Write-Host "Invoked File menu/tab"
        Start-Sleep -Seconds 2
    } catch {
        Write-Host "Cannot invoke directly: $_"
        # Try expand pattern
        try {
            $expandPattern = $fileTab.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
            $expandPattern.Expand()
            Write-Host "Expanded File menu"
            Start-Sleep -Seconds 2
        } catch {
            Write-Host "Cannot expand either: $_"
        }
    }
} else {
    Write-Host "No 'File' element found. Searching for similar..."
    # Search for any element with "fichier" (French) or "save"
    $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
    $child = $walker.GetFirstChild($auto)
    $count = 0
    while ($child -and $count -lt 30) {
        $name = $child.Current.Name
        $type = $child.Current.ControlType.ProgrammaticName
        if ($name) { Write-Host "  Child: '$name' ($type)" }
        $child = $walker.GetNextSibling($child)
        $count++
    }
}

# Check if any .pbix was saved recently
Write-Host "`nChecking for recently created .pbix files..."
Get-ChildItem "$env:USERPROFILE\Desktop","$env:USERPROFILE\Documents" -Filter "*.pbix" -ErrorAction SilentlyContinue -Depth 0 |
    Where-Object { $_.LastWriteTime -gt (Get-Date).AddMinutes(-5) } |
    Select-Object FullName,Length,LastWriteTime
