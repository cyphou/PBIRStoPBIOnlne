# Find AS database files from PBI Desktop RS workspace
$workspaceDirs = @(
    "$env:LOCALAPPDATA\Microsoft\Power BI Desktop RS\AnalysisServicesWorkspaces",
    "$env:LOCALAPPDATA\Microsoft\Power BI Desktop\AnalysisServicesWorkspaces"  
)

foreach ($wsDir in $workspaceDirs) {
    if (Test-Path $wsDir) {
        Write-Host "=== $wsDir ===" -ForegroundColor Cyan
        Get-ChildItem $wsDir -Recurse -Depth 4 | ForEach-Object {
            $indent = "  " * ($_.FullName.Replace($wsDir, "").Split("\").Length - 1)
            $size = ""
            if (-not $_.PSIsContainer) {
                $size = " ($([math]::Round($_.Length/1KB))KB)"
            }
            Write-Host "$indent$($_.Name)$size"
        }
    }
}

# Also check for TempSaves
$tempSaves = "$env:LOCALAPPDATA\Microsoft\Power BI Desktop RS\TempSaves"
if (Test-Path $tempSaves) {
    Write-Host "`n=== TempSaves ===" -ForegroundColor Cyan
    Get-ChildItem $tempSaves -Recurse | ForEach-Object {
        Write-Host "  $($_.FullName) ($([math]::Round($_.Length/1KB))KB)"
    }
}
