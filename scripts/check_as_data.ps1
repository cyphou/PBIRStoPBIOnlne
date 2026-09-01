$workspaceRoot = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "Microsoft\Power BI Desktop SSRS\AnalysisServicesWorkspaces"
$dataDir = Get-ChildItem $workspaceRoot -Directory -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    ForEach-Object { Join-Path $_.FullName "Data" } |
    Where-Object { Test-Path $_ } |
    Select-Object -First 1
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
