$dataDir = "C:\Users\pidoudet\AppData\Local\Microsoft\Power BI Desktop SSRS\AnalysisServicesWorkspaces\AnalysisServicesWorkspace_eed750da-0ceb-4809-9107-f860d6333e87\Data"
Write-Host "=== AS Data Directory ===" -ForegroundColor Cyan
if (Test-Path $dataDir) {
    Get-ChildItem $dataDir -Recurse -Depth 3 | ForEach-Object {
        $size = ""
        if (-not $_.PSIsContainer) {
            $size = " ($([math]::Round($_.Length/1KB))KB)"
        }
        Write-Host "  $($_.FullName.Replace($dataDir, ''))$size"
    }
} else {
    Write-Host "  NOT FOUND"
}

# Also check port file
$portFile = Join-Path $dataDir "msmdsrv.port.txt"
if (Test-Path $portFile) {
    Write-Host "`nPort file content: $(Get-Content $portFile -Raw)"
}
