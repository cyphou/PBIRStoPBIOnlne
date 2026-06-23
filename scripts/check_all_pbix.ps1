# Check Version/Metadata of all local .pbix files
Add-Type -AssemblyName System.IO.Compression.FileSystem

$files = @(
    "C:\Users\pidoudet\Downloads\Dashboard.pbix",
    "C:\Users\pidoudet\Downloads\FCA_Core_Report.pbix",
    "C:\Users\pidoudet\Downloads\Maintenance predictive RK 1.5 - Fabric.pbix",
    "C:\Users\pidoudet\Downloads\SAP O2C Process.pbix",
    "C:\Users\pidoudet\Downloads\SAP_O2C_V2_Backup.pbix",
    "C:\Users\pidoudet\Downloads\SAP_O2C_V3 (1).pbix"
)

foreach ($f in $files) {
    if (!(Test-Path $f)) { continue }
    $size = [math]::Round((Get-Item $f).Length / 1MB, 1)
    Write-Host "`n=== $([System.IO.Path]::GetFileName($f)) (${size}MB) ===" -ForegroundColor Cyan
    try {
        $zip = [System.IO.Compression.ZipFile]::OpenRead($f)
        foreach ($entry in $zip.Entries) {
            if ($entry.FullName -in @("Version", "Settings", "Metadata", "Connections")) {
                $stream = $entry.Open()
                $reader = New-Object System.IO.StreamReader($stream)
                $content = $reader.ReadToEnd()
                $reader.Close()
                Write-Host "  $($entry.FullName): $content"
            }
        }
        $zip.Dispose()
    } catch {
        Write-Host "  ERROR: $_" -ForegroundColor Red
    }
}
