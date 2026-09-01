# Check Version/Metadata of all local .pbix files
Add-Type -AssemblyName System.IO.Compression.FileSystem

$files = Get-ChildItem (Join-Path $HOME "Downloads") -Filter "*.pbix" -File |
    Select-Object -ExpandProperty FullName

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
