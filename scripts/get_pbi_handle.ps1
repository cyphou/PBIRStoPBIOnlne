$p = Get-Process -Name PBIDesktop -ErrorAction Stop
Write-Host "PID: $($p.Id)"
Write-Host "Handle: $($p.MainWindowHandle)"
Write-Host "Title: $($p.MainWindowTitle)"
