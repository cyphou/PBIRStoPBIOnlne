Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$z = [System.IO.Compression.ZipFile]::OpenRead("C:\Users\pidoudet\OneDrive - Microsoft\Boulot\PBI SME\OracleToPostgre\PBIReporttoPBIOnline\scripts\artifacts\pbix\sample.pbix")
foreach ($e in $z.Entries) {
    Write-Host "$($e.FullName) ($($e.Length) bytes)"
}
$z.Dispose()
