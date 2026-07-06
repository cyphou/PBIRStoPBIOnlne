$ErrorActionPreference = 'Stop'
$amoPkg = (Get-ChildItem "$env:USERPROFILE\.nuget\packages\microsoft.analysisservices.retail.amd64" -Directory |
    Sort-Object Name -Descending | Select-Object -First 1).FullName
$amoLib = Join-Path $amoPkg 'lib\net45'

Add-Type -Path (Join-Path $amoLib 'Microsoft.AnalysisServices.Core.dll')
Add-Type -Path (Join-Path $amoLib 'Microsoft.AnalysisServices.Tabular.dll')

$tests = @(
    'localhost:54903',
    'Data Source=localhost:54903;',
    'Provider=MSOLAP;Data Source=localhost:54903;'
)

foreach ($t in $tests) {
    $s = New-Object Microsoft.AnalysisServices.Tabular.Server
    try {
        $s.Connect($t)
        Write-Host "OK -> $t" -ForegroundColor Green
        $s.Disconnect()
    }
    catch {
        Write-Host "FAIL -> $t :: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}
