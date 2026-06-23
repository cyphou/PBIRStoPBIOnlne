Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$savePath = "C:\Users\pidoudet\OneDrive - Microsoft\Boulot\PBI SME\OracleToPostgre\PBIReporttoPBIOnline\scripts\artifacts\pbix\rs_test.pbix"
$saveDir = Split-Path $savePath -Parent
if (-not (Test-Path $saveDir)) { New-Item -ItemType Directory -Path $saveDir -Force | Out-Null }
if (Test-Path $savePath) { Remove-Item $savePath -Force }

$p = Get-Process -Name PBIDesktop -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $p) {
    $exe = "C:\Program Files\Microsoft Power BI Desktop RS\bin\PBIDesktop.exe"
    Start-Process $exe
    Start-Sleep -Seconds 12
    $p = Get-Process -Name PBIDesktop -ErrorAction SilentlyContinue | Select-Object -First 1
}
if (-not $p) { Write-Host "No PBIDesktop process"; exit 1 }

$root = [System.Windows.Automation.AutomationElement]::FromHandle($p.MainWindowHandle)
if (-not $root) { Write-Host "No automation root"; exit 1 }

# Try dismissing 'Something went wrong' pop-up by invoking its Close button.
$condWindow = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::NameProperty,
    "Something went wrong"
)
$errWin = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condWindow)
if ($errWin) {
    $closeCond = New-Object System.Windows.Automation.AndCondition(
        (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)),
        (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, "Close"))
    )
    $closeBtn = $errWin.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $closeCond)
    if ($closeBtn) {
        $invoke = $closeBtn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
        if ($invoke) { $invoke.Invoke(); Start-Sleep -Seconds 1 }
    } else {
        [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
        Start-Sleep -Seconds 1
    }
}

# Click Save button on ribbon
$saveCond = New-Object System.Windows.Automation.AndCondition(
    (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)),
    (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, "Save"))
)
$saveBtn = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $saveCond)
if ($saveBtn) {
    $invoke = $saveBtn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    if ($invoke) {
        $invoke.Invoke()
        Start-Sleep -Seconds 2
    }
}

# Fill Save dialog path using SendKeys
[System.Windows.Forms.Clipboard]::SetText($savePath)
[System.Windows.Forms.SendKeys]::SendWait("^a")
Start-Sleep -Milliseconds 200
[System.Windows.Forms.SendKeys]::SendWait("^v")
Start-Sleep -Milliseconds 500
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
Start-Sleep -Seconds 4

# Confirm overwrite if needed
[System.Windows.Forms.SendKeys]::SendWait("{LEFT}")
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
Start-Sleep -Seconds 2

if (Test-Path $savePath) {
    $f = Get-Item $savePath
    Write-Host "SAVED_OK: $($f.FullName) ($($f.Length) bytes)"
    exit 0
}

Write-Host "SAVED_FAIL"
exit 1
