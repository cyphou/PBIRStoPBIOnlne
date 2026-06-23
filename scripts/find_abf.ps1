Get-ChildItem "$env:LOCALAPPDATA\Microsoft\Power BI Desktop RS" -Recurse -Filter "*.abf" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "$($_.FullName) | $($_.LastWriteTime) | $([math]::Round($_.Length/1KB))KB"
}
# Also check temp and common backup dirs
Get-ChildItem "$env:TEMP" -Filter "*.abf" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "$($_.FullName) | $($_.LastWriteTime) | $([math]::Round($_.Length/1KB))KB"
}
