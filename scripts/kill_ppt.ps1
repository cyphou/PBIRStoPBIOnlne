# Kill PowerPoint if it's running (was stealing focus)
$ppt = Get-Process -Name POWERPNT -ErrorAction SilentlyContinue
if ($ppt) {
    Write-Host "PowerPoint is running (PID $($ppt.Id)). Killing..."
    Stop-Process -Id $ppt.Id -Force
    Start-Sleep -Seconds 2
    Write-Host "PowerPoint killed"
} else {
    Write-Host "PowerPoint not running - good"
}
