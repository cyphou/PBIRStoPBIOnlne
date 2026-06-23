Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$z = [System.IO.Compression.ZipFile]::OpenRead("<USER_HOME>\OneDrive - Organization\Boulot\Analytics Team\MigrationWorkspace\PBIReporttoPBIOnline\scripts\artifacts\pbix\sample.pbix")
foreach ($e in $z.Entries) {
    Write-Host "$($e.FullName) ($($e.Length) bytes)"
}
$z.Dispose()
