param(
    [string]$FilePath = (Join-Path $PSScriptRoot "artifacts\pbix\sample.pbix")
)

if (-not (Test-Path $FilePath)) {
    Write-Host "MISSING $FilePath"
    exit 1
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($FilePath)

Write-Host "Entries (first 80):"
$zip.Entries | Select-Object -ExpandProperty FullName | Sort-Object | Select-Object -First 80

foreach ($name in @("Version", "Settings", "Metadata", "Connections")) {
    $entry = $zip.Entries | Where-Object FullName -eq $name
    if ($entry) {
        $reader = New-Object IO.StreamReader($entry.Open())
        $text = $reader.ReadToEnd()
        $reader.Close()
        Write-Host "`n--- $name ---"
        Write-Host $text
    }
}

$zip.Dispose()
