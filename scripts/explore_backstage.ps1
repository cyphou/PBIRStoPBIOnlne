# Explore backstage view elements after File tab selection
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class W3 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
}
"@

$proc = Get-Process -Id 50544
$hwnd = $proc.MainWindowHandle
if ([W3]::IsIconic($hwnd)) { [W3]::ShowWindow($hwnd, 9); Start-Sleep -Milliseconds 500 }
[W3]::SetForegroundWindow($hwnd)
Start-Sleep -Seconds 1

$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)

# Select File tab
$fileTab = $root.FindFirst(
    [System.Windows.Automation.TreeScope]::Descendants,
    (New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, "File"))
)

if (!$fileTab) {
    Write-Host "File tab not found!" -ForegroundColor Red
    exit 1
}

$selP = $fileTab.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
$selP.Select()
Write-Host "File tab selected" -ForegroundColor Green
Start-Sleep -Seconds 3

# Now list ALL descendants of the root window
Write-Host "`nAll named elements in window:"
$allElements = $root.FindAll(
    [System.Windows.Automation.TreeScope]::Descendants,
    [System.Windows.Automation.Condition]::TrueCondition
)

$interesting = @()
foreach ($elem in $allElements) {
    $name = $elem.Current.Name
    $type = $elem.Current.ControlType.ProgrammaticName
    $autoId = $elem.Current.AutomationId
    $className = $elem.Current.ClassName
    
    if ($name -and $name.Length -gt 0 -and $name.Length -lt 100) {
        $interesting += [PSCustomObject]@{
            Name = $name
            Type = $type -replace 'ControlType\.', ''
            AutoId = $autoId
            Class = $className
        }
    }
}

# Show relevant ones - filter for save-related
Write-Host "`n--- Save/file related elements ---"
$interesting | Where-Object { 
    $_.Name -match 'save|enregistrer|browse|parcourir|this pc|ce pc|recent|fichier|file|export|copy|new|info|open|ouvrir' 
} | Format-Table -AutoSize

Write-Host "`n--- All button/menu elements ---"
$interesting | Where-Object { 
    $_.Type -match 'Button|MenuItem|ListItem|Hyperlink|Tab' 
} | Format-Table -AutoSize

# Also check first 40 named elements
Write-Host "`n--- First 40 named elements ---"
$interesting | Select-Object -First 40 | Format-Table -AutoSize

# Go back
Start-Sleep -Seconds 1
[System.Windows.Forms.SendKeys]::SendWait("{ESCAPE}")
