Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$filePath = Join-Path $PSScriptRoot "artifacts\pbix\sample.pbix"
$z = [System.IO.Compression.ZipFile]::OpenRead($filePath)
foreach ($e in $z.Entries) {
    Write-Host "$($e.FullName) ($($e.Length) bytes)"
}
$z.Dispose()
