# Try uploading the smallest local .pbix to test PBIRS compatibility
$apiUrl = "http://ms-len-moa/Reports/api/v2.0"

# Check sizes first
$localPbix = @(
    "C:\Users\pidoudet\Downloads\Dashboard.pbix",
    "C:\Users\pidoudet\Downloads\FCA_Core_Report.pbix"
)

foreach ($path in $localPbix) {
    if (Test-Path $path) {
        $size = (Get-Item $path).Length
        Write-Host "$([System.IO.Path]::GetFileName($path)): $([math]::Round($size/1MB, 1))MB"
    }
}

# Try the smallest
$testFile = $localPbix | Where-Object { Test-Path $_ } | Sort-Object { (Get-Item $_).Length } | Select-Object -First 1
Write-Host "`nUsing: $testFile ($([math]::Round((Get-Item $testFile).Length/1MB,1))MB)" -ForegroundColor Cyan

$bytes = [System.IO.File]::ReadAllBytes($testFile)
$base64 = [Convert]::ToBase64String($bytes)

$body = @{
    "@odata.type" = "#Model.PowerBIReport"
    "Content" = $base64
    "ContentType" = ""
    "Name" = "Test Upload"
    "Path" = "/IT Operations/Test Upload"
} | ConvertTo-Json -Depth 5

Write-Host "Uploading to PBIRS..."
try {
    $resp = Invoke-RestMethod -Uri "$apiUrl/PowerBIReports" `
        -Method Post `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) `
        -ContentType "application/json; charset=utf-8" `
        -UseDefaultCredentials `
        -TimeoutSec 120
    
    Write-Host "SUCCESS: $($resp.Name) (Id: $($resp.Id))" -ForegroundColor Green
} catch {
    $code = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { "?" }
    Write-Host "FAILED ($code)" -ForegroundColor Red
    if ($_.Exception.Response) {
        try {
            $errStream = $_.Exception.Response.GetResponseStream()
            $reader = New-Object System.IO.StreamReader($errStream)
            Write-Host $reader.ReadToEnd()
        } catch {}
    }
    
    # Try without Path
    Write-Host "`nRetrying without Path..."
    $body2 = @{
        "@odata.type" = "#Model.PowerBIReport"
        "Content" = $base64
        "ContentType" = ""
        "Name" = "Test Upload"
    } | ConvertTo-Json -Depth 5
    
    try {
        $resp2 = Invoke-RestMethod -Uri "$apiUrl/PowerBIReports" `
            -Method Post `
            -Body ([System.Text.Encoding]::UTF8.GetBytes($body2)) `
            -ContentType "application/json; charset=utf-8" `
            -UseDefaultCredentials `
            -TimeoutSec 120
        
        Write-Host "SUCCESS (no path): $($resp2.Name) (Id: $($resp2.Id))" -ForegroundColor Green
    } catch {
        $code2 = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { "?" }
        Write-Host "FAILED ($code2)" -ForegroundColor Red
        if ($_.Exception.Response) {
            try {
                $errStream2 = $_.Exception.Response.GetResponseStream()
                $reader2 = New-Object System.IO.StreamReader($errStream2)
                Write-Host $reader2.ReadToEnd()
            } catch {}
        }
    }
}
