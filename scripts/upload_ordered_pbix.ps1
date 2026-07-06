param(
    [string]$BaseUrl = "http://localhost/reports",
    [string]$ArtifactsDir = "C:\GitHub Project\PBIReporttoPBIOnline\scripts\artifacts\pbix"
)

$ErrorActionPreference = "Stop"
$api = "$BaseUrl/api/v2.0"
$isHttp = $BaseUrl -match '^http://'

Add-Type -AssemblyName System.IO.Compression.FileSystem

function Test-PbixForPbirsUpload {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath
    )

    $result = [ordered]@{
        IsCompatible = $true
        Reason       = ""
    }

    try {
        $zip = [System.IO.Compression.ZipFile]::OpenRead($FilePath)
        $connEntry = $zip.Entries | Where-Object FullName -eq "Connections" | Select-Object -First 1
        if ($connEntry) {
            $reader = New-Object IO.StreamReader($connEntry.Open())
            $connText = $reader.ReadToEnd()
            $reader.Close()

            if ($connText) {
                try {
                    $connJson = $connText | ConvertFrom-Json -ErrorAction Stop
                    if ($connJson.Connections) {
                        $liveConn = $connJson.Connections | Where-Object { $_.ConnectionType -eq "pbiServiceLive" } | Select-Object -First 1
                        if ($liveConn) {
                            $result.IsCompatible = $false
                            $result.Reason = "PBIX uses ConnectionType=pbiServiceLive (Power BI Service live connection), which PBIRS import rejects."
                        }
                    }
                }
                catch {
                    # Keep going; invalid JSON here should not hard-fail the uploader.
                }
            }
        }
        $zip.Dispose()
    }
    catch {
        $result.IsCompatible = $false
        $result.Reason = "Failed to inspect PBIX package: $($_.Exception.Message)"
    }

    return [PSCustomObject]$result
}

if (-not (Test-Path $ArtifactsDir)) {
    throw "Artifacts directory not found: $ArtifactsDir"
}

$reports = @(
    @{ Name = "01-Analyse-des-Ventes"; Folder = "/Migration PBI"; File = "Analyse des Ventes.pbix" },
    @{ Name = "02-Suivi-Budgetaire"; Folder = "/Migration PBI"; File = "Suivi Budg*.pbix" },
    @{ Name = "03-Tableau-RH"; Folder = "/Migration PBI"; File = "Tableau RH.pbix" },
    @{ Name = "04-Dashboard-IT"; Folder = "/Migration PBI"; File = "Dashboard IT.pbix" },
    @{ Name = "05-KPI-Direction"; Folder = "/Migration PBI"; File = "KPI Direction.pbix" }
)

$commonInvokeParams = @{
    UseDefaultCredentials = $true
    TimeoutSec            = 60
}
if ($isHttp) {
    $commonInvokeParams.AllowUnencryptedAuthentication = $true
}

$sys = Invoke-RestMethod -Uri "$api/System" -Method Get @commonInvokeParams
Write-Host "Connected to $($sys.ProductName) $($sys.ProductVersion)"

$neededFolders = $reports.Folder | Sort-Object -Unique
$allFolders = (Invoke-RestMethod -Uri "$api/Folders" -Method Get @commonInvokeParams).value
foreach ($folderPath in $neededFolders) {
    if (-not ($allFolders | Where-Object { $_.Path -eq $folderPath })) {
        $name = ($folderPath -replace '^/', '')
        $body = @{
            '@odata.type' = '#Model.Folder'
            Name          = $name
            Description   = 'Auto-created for PBIX upload'
            Path          = '/'
        } | ConvertTo-Json -Depth 5

        Invoke-RestMethod -Uri "$api/Folders" -Method Post -Body ([Text.Encoding]::UTF8.GetBytes($body)) -ContentType "application/json; charset=utf-8" @commonInvokeParams | Out-Null
        Write-Host "Created folder $folderPath"
    }
}

    $existing = (Invoke-RestMethod -Uri "$api/PowerBIReports" -Method Get @commonInvokeParams).value

$index = 1
foreach ($r in $reports) {
    $sourceFile = Get-ChildItem -Path $ArtifactsDir -Filter $r.File | Select-Object -First 1
    if (-not $sourceFile) {
        Write-Host "[$index/$($reports.Count)] SKIP missing source pattern: $($r.File)" -ForegroundColor Yellow
        $index++
        continue
    }

    $pbixCheck = Test-PbixForPbirsUpload -FilePath $sourceFile.FullName
    if (-not $pbixCheck.IsCompatible) {
        Write-Host "[$index/$($reports.Count)] SKIP incompatible PBIX [$($sourceFile.Name)]" -ForegroundColor Yellow
        Write-Host "    -> $($pbixCheck.Reason)" -ForegroundColor Yellow
        $index++
        continue
    }

    $bytes = [IO.File]::ReadAllBytes($sourceFile.FullName)
    $b64 = [Convert]::ToBase64String($bytes)

    $targetPath = "$($r.Folder)/$($r.Name)"
    $match = $existing | Where-Object { $_.Path -eq $targetPath } | Select-Object -First 1

    if ($match) {
        Invoke-RestMethod -Uri "$api/CatalogItems($($match.Id))" -Method Delete @commonInvokeParams | Out-Null
        Write-Host "[$index/$($reports.Count)] Replacing existing $targetPath"
    }
    else {
        Write-Host "[$index/$($reports.Count)] Creating $targetPath"
    }

    $body = @{
        '@odata.type' = '#Model.PowerBIReport'
        Content       = $b64
        ContentType   = ''
        Name          = $r.Name
        Path          = $targetPath
    } | ConvertTo-Json -Depth 6

    try {
        $postParams = @{}
        $postParams += $commonInvokeParams
        $postParams.TimeoutSec = 180
        $resp = Invoke-RestMethod -Uri "$api/PowerBIReports" -Method Post -Body ([Text.Encoding]::UTF8.GetBytes($body)) -ContentType "application/json; charset=utf-8" @postParams
        if ($resp -and $resp.Id) {
            Write-Host "    -> OK Id=$($resp.Id) [source=$($sourceFile.Name)]"
        }
        else {
            Write-Host "    -> Uploaded [source=$($sourceFile.Name)]"
        }
    }
    catch {
        if ($_.Exception.Response) {
            Write-Host "    -> FAILED HTTP $([int]$_.Exception.Response.StatusCode) [source=$($sourceFile.Name)]" -ForegroundColor Red
        }
        else {
            Write-Host "    -> FAILED $($_.Exception.Message) [source=$($sourceFile.Name)]" -ForegroundColor Red
        }
    }
    $index++
}

$verify = (Invoke-RestMethod -Uri "$api/PowerBIReports" -Method Get @commonInvokeParams).value
Write-Host ""
Write-Host "Uploaded set (in requested order):"
foreach ($r in $reports) {
    $tp = "$($r.Folder)/$($r.Name)"
    $hit = $verify | Where-Object { $_.Path -eq $tp } | Select-Object -First 1
    if ($hit) {
        Write-Host "  - $($hit.Name) @ $($hit.Path)"
    }
    else {
        Write-Host "  - MISSING $tp"
    }
}
