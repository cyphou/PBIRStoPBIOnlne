<#
.SYNOPSIS
    Create 5 sample .pbix reports using PBI Desktop RS's AMO and upload to PBIRS.
    
.DESCRIPTION
    Uses PBI Desktop RS's built-in Analysis Services libraries to create
    minimal tabular models, package them as .pbix, and upload via REST API.
#>

$ErrorActionPreference = "Stop"
$apiUrl = "http://ms-len-moa/Reports/api/v2.0"
$outputDir = Join-Path $PSScriptRoot "artifacts\pbix"

# ─── 1. Find AMO client DLLs ─────────────────────────────────────
# AMO client DLLs are in SSMS, not in PBI Desktop RS (which only has server DLLs)
$amoPaths = @(
    "C:\Program Files\Microsoft SQL Server Management Studio 22\Release\Common7\IDE",
    "C:\Program Files\Microsoft SQL Server\170\DTS\Binn",
    "C:\Program Files\Microsoft SQL Server\160\DTS\Binn"
)

$amoDir = $null
foreach ($p in $amoPaths) {
    if (Test-Path (Join-Path $p "Microsoft.AnalysisServices.Tabular.dll")) {
        $amoDir = $p
        break
    }
}

if (-not $amoDir) {
    Write-Error "AMO client DLLs not found. Install SSMS or SQL Server AMO libraries."
    exit 1
}

Write-Host "=== AMO client DLLs found at: $amoDir ===" -ForegroundColor Green

# ─── 2. Load AMO assemblies ───────────────────────────────────────
$amoCore = Join-Path $amoDir "Microsoft.AnalysisServices.Core.dll"
$amoTabular = Join-Path $amoDir "Microsoft.AnalysisServices.Tabular.dll"
$amoMain = Join-Path $amoDir "Microsoft.AnalysisServices.dll"

foreach ($dll in @($amoCore, $amoTabular, $amoMain)) {
    if (Test-Path $dll) {
        try {
            [System.Reflection.Assembly]::LoadFrom($dll) | Out-Null
            Write-Host "Loaded: $(Split-Path $dll -Leaf)" -ForegroundColor Green
        } catch {
            Write-Host "Warning loading $(Split-Path $dll -Leaf): $_" -ForegroundColor Yellow
        }
    } else {
        Write-Host "Not found: $dll" -ForegroundColor Yellow
    }
}

# ─── 3. Find the AS port from PBI Desktop RS's msmdsrv ────────────
Write-Host "`n=== Finding PBI Desktop RS AS instance ===" -ForegroundColor Cyan

$asPort = $null
$pbiDesktopBin = "C:\Program Files\Microsoft Power BI Desktop RS\bin"

# Find msmdsrv launched by PBI Desktop RS (path contains "Power BI Desktop RS")
$allMsmdsrv = Get-Process -Name "msmdsrv" -ErrorAction SilentlyContinue
$desktopMsmdsrv = $null
foreach ($proc in $allMsmdsrv) {
    try {
        $procPath = $proc.Path
        if ($procPath -and $procPath -like "*Power BI Desktop RS*") {
            $desktopMsmdsrv = $proc
            Write-Host "Found PBI Desktop RS msmdsrv (PID: $($proc.Id), Path: $procPath)"
            break
        }
    } catch {
        # Access denied for PBIRS server process - skip it
    }
}

if ($desktopMsmdsrv) {
    $netstatLines = netstat -ano | Select-String "LISTENING" | Select-String "$($desktopMsmdsrv.Id)"
    foreach ($line in $netstatLines) {
        if ($line -match ':(\d+)\s') {
            $asPort = $Matches[1]
            Write-Host "Found AS port via netstat: $asPort" -ForegroundColor Green
            break
        }
    }
}

if (-not $asPort) {
    Write-Host "PBI Desktop RS is not running. Please open PBI Desktop RS first, then re-run." -ForegroundColor Red
    Write-Host "  Executable: $pbiDesktopBin\PBIDesktop.exe" -ForegroundColor Yellow
    exit 1
}

# ─── 4. Connect to AS and create tabular models ──────────────────
Write-Host "`n=== Connecting to AS on port $asPort ===" -ForegroundColor Cyan

# Connect both Tabular (for model creation) and Classic AMO (for backup)
$server = New-Object Microsoft.AnalysisServices.Tabular.Server
$amoServer = New-Object Microsoft.AnalysisServices.Server
$connStr = "localhost:$asPort"
Write-Host "Connecting to: $connStr"

try {
    $server.Connect($connStr)
    $amoServer.Connect($connStr)
    Write-Host "Connected to AS: $($server.Name), Version: $($server.Version)" -ForegroundColor Green
} catch {
    Write-Host "Connection failed: $_" -ForegroundColor Red
    try {
        $server.Connect("Data Source=localhost:$asPort")
        $amoServer.Connect("Data Source=localhost:$asPort")
        Write-Host "Connected (alt format)" -ForegroundColor Green
    } catch {
        Write-Error "Cannot connect to AS instance: $_"
        exit 1
    }
}

# ─── 5. Define the 5 reports ─────────────────────────────────────
$reports = @(
    @{
        Name = "Analyse des Ventes"
        Folder = "/Équipe Commerciale"
        TableName = "Ventes"
        Columns = @(
            @{Name="Produit"; Values=@("Widget A","Widget B","Widget C","Gadget X","Gadget Y")},
            @{Name="Region"; Values=@("Nord","Sud","Est","Ouest","Centre")},
            @{Name="Montant"; Values=@(15000,22000,18000,31000,12000)},
            @{Name="Quantite"; Values=@(150,220,180,310,120)}
        )
    },
    @{
        Name = "Suivi Budgétaire"
        Folder = "/Département Finance"
        TableName = "Budget"
        Columns = @(
            @{Name="Categorie"; Values=@("Personnel","Matériel","Logiciel","Formation","Voyage")},
            @{Name="Budget_Prevu"; Values=@(100000,50000,75000,25000,30000)},
            @{Name="Depense_Reelle"; Values=@(95000,62000,70000,18000,35000)},
            @{Name="Ecart"; Values=@(5000,-12000,5000,7000,-5000)}
        )
    },
    @{
        Name = "Tableau RH"
        Folder = "/RH - Ressources Humaines"
        TableName = "Employes"
        Columns = @(
            @{Name="Departement"; Values=@("IT","RH","Finance","Marketing","Ventes")},
            @{Name="Effectif"; Values=@(45,12,18,22,35)},
            @{Name="Turnover_Pct"; Values=@(8.5,3.2,5.1,12.0,15.3)},
            @{Name="Satisfaction"; Values=@(4.2,4.8,4.1,3.9,3.5)}
        )
    },
    @{
        Name = "Dashboard IT"
        Folder = "/IT Operations"
        TableName = "Incidents"
        Columns = @(
            @{Name="Categorie"; Values=@("Réseau","Serveur","Application","Sécurité","Base de données")},
            @{Name="Nombre"; Values=@(45,23,67,12,8)},
            @{Name="Temps_Resolution_h"; Values=@(2.5,4.0,1.5,8.0,3.0)},
            @{Name="Priorite"; Values=@("Haute","Critique","Moyenne","Critique","Haute")}
        )
    },
    @{
        Name = "KPI Direction"
        Folder = "/Direction Générale"
        TableName = "KPI"
        Columns = @(
            @{Name="Indicateur"; Values=@("CA Total","Marge Brute","EBITDA","Cash Flow","ROI")},
            @{Name="Valeur_Actuelle"; Values=@(5200000,1560000,780000,620000,18.5)},
            @{Name="Objectif"; Values=@(5000000,1500000,750000,600000,15.0)},
            @{Name="Atteinte_Pct"; Values=@(104.0,104.0,104.0,103.3,123.3)}
        )
    }
)

# ─── 6. Create output directory ──────────────────────────────────
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

# ─── 7. Create each model and export as .pbix ────────────────────
$createdFiles = @()

foreach ($report in $reports) {
    Write-Host "`n--- Creating: $($report.Name) ---" -ForegroundColor Cyan
    
    $dbName = "Model_$($report.Name -replace '[^a-zA-Z0-9]','_')"
    
    # Remove existing database if any
    $existingDb = $server.Databases.FindByName($dbName)
    if ($existingDb) {
        Write-Host "  Removing existing database: $dbName"
        $existingDb.Drop()
    }
    
    # Create new database
    $db = New-Object Microsoft.AnalysisServices.Tabular.Database
    $db.Name = $dbName
    $db.ID = $dbName
    $db.CompatibilityLevel = 1400
    $db.Model = New-Object Microsoft.AnalysisServices.Tabular.Model
    $db.Model.Name = "Model"
    
    # Create table
    $table = New-Object Microsoft.AnalysisServices.Tabular.Table
    $table.Name = $report.TableName
    
    # Create partition with M expression for inline data
    $partition = New-Object Microsoft.AnalysisServices.Tabular.Partition
    $partition.Name = $report.TableName
    $partition.Source = New-Object Microsoft.AnalysisServices.Tabular.MPartitionSource
    
    # Build M expression with inline data
    $colNames = $report.Columns | ForEach-Object { """$($_.Name)""" }
    $colTypes = $report.Columns | ForEach-Object {
        $v = $_.Values[0]
        if ($v -is [int] -or $v -is [double] -or $v -is [float]) { "type number" }
        else { "type text" }
    }
    
    $rows = @()
    for ($i = 0; $i -lt $report.Columns[0].Values.Count; $i++) {
        $vals = @()
        for ($c = 0; $c -lt $report.Columns.Count; $c++) {
            $v = $report.Columns[$c].Values[$i]
            if ($v -is [int] -or $v -is [double] -or $v -is [float]) {
                $vals += "$v"
            } else {
                $vals += """$v"""
            }
        }
        $rows += "        {$($vals -join ', ')}"
    }
    
    $typeEntries = @()
    for ($c = 0; $c -lt $report.Columns.Count; $c++) {
        $typeEntries += "{""$($report.Columns[$c].Name)"", $($colTypes[$c])}"
    }
    
    $mExpr = @"
let
    Source = #table(
        {$($colNames -join ', ')},
        {
$($rows -join ",`n")
        }
    ),
    Typed = Table.TransformColumnTypes(Source, {$($typeEntries -join ', ')})
in
    Typed
"@
    
    $partition.Source.Expression = $mExpr
    $table.Partitions.Add($partition)
    
    # Add columns
    foreach ($col in $report.Columns) {
        $column = New-Object Microsoft.AnalysisServices.Tabular.DataColumn
        $column.Name = $col.Name
        $column.SourceColumn = $col.Name
        $v = $col.Values[0]
        if ($v -is [int] -or $v -is [double] -or $v -is [float]) {
            $column.DataType = [Microsoft.AnalysisServices.Tabular.DataType]::Double
        } else {
            $column.DataType = [Microsoft.AnalysisServices.Tabular.DataType]::String
        }
        $table.Columns.Add($column)
    }
    
    # Add a simple measure
    $measure = New-Object Microsoft.AnalysisServices.Tabular.Measure
    $numCol = $report.Columns | Where-Object { $_.Values[0] -is [int] -or $_.Values[0] -is [double] -or $_.Values[0] -is [float] } | Select-Object -First 1
    if ($numCol) {
        $measure.Name = "Total $($numCol.Name)"
        $measure.Expression = "SUM('$($report.TableName)'[$($numCol.Name)])"
    } else {
        $measure.Name = "Row Count"
        $measure.Expression = "COUNTROWS('$($report.TableName)')"
    }
    $table.Measures.Add($measure)
    
    $db.Model.Tables.Add($table)
    
    # Add to server
    Write-Host "  Adding database to AS..."
    $server.Databases.Add($db)
    try {
        $db.Update([Microsoft.AnalysisServices.UpdateOptions]::ExpandFull)
        Write-Host "  Database created: $dbName" -ForegroundColor Green
    } catch {
        Write-Host "  Error creating database: $_" -ForegroundColor Red
        continue
    }
    
    # Backup as ABF using classic AMO Server
    $abfPath = Join-Path $outputDir "$($report.Name).abf"
    Write-Host "  Backing up to: $abfPath"
    try {
        $amoServer.Backup($dbName, $abfPath, $true)
        Write-Host "  Backup saved" -ForegroundColor Green
    } catch {
        Write-Host "  Backup via AMO failed: $_" -ForegroundColor Yellow
        # Try XMLA backup command
        Write-Host "  Trying XMLA backup..."
        try {
            $xmlaCmd = '<Backup xmlns="http://schemas.microsoft.com/analysisservices/2003/engine"><Object><DatabaseID>' + $dbName + '</DatabaseID></Object><File>' + $abfPath + '</File><AllowOverwrite>true</AllowOverwrite></Backup>'
            $result = $server.Execute($xmlaCmd)
            $hasErrors = $false
            foreach ($msg in $result) {
                if ($msg -is [Microsoft.AnalysisServices.XmlaError]) {
                    Write-Host "    XMLA Error: $($msg.Description)" -ForegroundColor Red
                    $hasErrors = $true
                }
            }
            if (-not $hasErrors) {
                Write-Host "  XMLA backup saved" -ForegroundColor Green
            } else {
                continue
            }
        } catch {
            Write-Host "  XMLA backup also failed: $_" -ForegroundColor Red
            continue
        }
    }
    
    # Package as .pbix
    $pbixPath = Join-Path $outputDir "$($report.Name).pbix"
    Write-Host "  Packaging as .pbix: $pbixPath"
    
    # A .pbix is an OPC (ZIP) package with:
    # - DataModel (the ABF backup)
    # - [Content_Types].xml
    # - DataMashup (M queries)
    # - Metadata (report layout)
    # - Settings
    # - Version
    
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    
    if (Test-Path $pbixPath) { Remove-Item $pbixPath -Force }
    
    $zipStream = [System.IO.File]::Create($pbixPath)
    $zip = New-Object System.IO.Compression.ZipArchive($zipStream, [System.IO.Compression.ZipArchiveMode]::Create)
    
    # [Content_Types].xml
    $ctEntry = $zip.CreateEntry("[Content_Types].xml")
    $ctWriter = New-Object System.IO.StreamWriter($ctEntry.Open())
    $ctWriter.Write('<?xml version="1.0" encoding="utf-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="json" ContentType="application/json" /><Default Extension="abf" ContentType="application/octet-stream" /></Types>')
    $ctWriter.Close()
    
    # DataModel (ABF)
    $dmEntry = $zip.CreateEntry("DataModel")
    $dmStream = $dmEntry.Open()
    $abfBytes = [System.IO.File]::ReadAllBytes($abfPath)
    $dmStream.Write($abfBytes, 0, $abfBytes.Length)
    $dmStream.Close()
    
    # Version
    $vEntry = $zip.CreateEntry("Version")
    $vWriter = New-Object System.IO.StreamWriter($vEntry.Open())
    $vWriter.Write("2.0.0.0")
    $vWriter.Close()
    
    # Settings - RS metadata
    $sEntry = $zip.CreateEntry("Settings")
    $sWriter = New-Object System.IO.StreamWriter($sEntry.Open(), [System.Text.Encoding]::Unicode)
    $sWriter.Write('{"IsReportServerNative":true}')
    $sWriter.Close()
    
    # Metadata (minimal report layout)  
    $reportLayout = @{
        id = 0
        reportId = [guid]::NewGuid().ToString()
        config = '{"version":"5.54","themeCollection":{"baseTheme":{"name":"CY24SU01","dataColors":["#118DFF","#12239E","#E66C37","#6B007B","#E044A7","#744EC2","#D9B300","#D64550"],"background":"#FFFFFF","foreground":"#252423","tableAccent":"#118DFF"}}}'
        filters = "[]"
        resourcePackages = @()
        sections = @(
            @{
                name = "Section1"
                displayName = "Page 1"
                filters = "[]"
                ordinal = 0
                visualContainers = @()
                width = 1280
                height = 720
            }
        )
    } | ConvertTo-Json -Depth 10
    
    $mEntry = $zip.CreateEntry("Report/Layout")
    $mWriter = New-Object System.IO.StreamWriter($mEntry.Open(), [System.Text.Encoding]::Unicode)
    $mWriter.Write($reportLayout)
    $mWriter.Close()
    
    $zip.Dispose()
    $zipStream.Close()
    
    # Clean up ABF
    Remove-Item $abfPath -Force
    
    if (Test-Path $pbixPath) {
        $size = (Get-Item $pbixPath).Length
        Write-Host "  Created: $pbixPath ($([math]::Round($size/1KB))KB)" -ForegroundColor Green
        $createdFiles += $pbixPath
    }
}

# ─── 8. Upload to PBIRS ──────────────────────────────────────────
Write-Host "`n=== Uploading to PBIRS ===" -ForegroundColor Cyan

foreach ($report in $reports) {
    $pbixPath = Join-Path $outputDir "$($report.Name).pbix"
    if (-not (Test-Path $pbixPath)) {
        Write-Host "  Skip (not found): $pbixPath" -ForegroundColor Yellow
        continue
    }
    
    $folder = $report.Folder
    $reportName = $report.Name
    
    Write-Host "`n  Uploading '$reportName' to '$folder'..."
    
    # Read file as base64
    $bytes = [System.IO.File]::ReadAllBytes($pbixPath)
    $base64 = [Convert]::ToBase64String($bytes)
    
    $body = @{
        "@odata.type" = "#Model.PowerBIReport"
        "Content" = $base64
        "ContentType" = ""
        "Name" = $reportName
        "Path" = "$folder/$reportName"
    } | ConvertTo-Json -Depth 5
    
    try {
        $resp = Invoke-RestMethod -Uri "$apiUrl/PowerBIReports" `
            -Method Post `
            -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) `
            -ContentType "application/json; charset=utf-8" `
            -UseDefaultCredentials `
            -TimeoutSec 120
        
        Write-Host "  SUCCESS: $reportName uploaded to $folder" -ForegroundColor Green
        Write-Host "    Id: $($resp.Id)"
    } catch {
        $statusCode = $null
        if ($_.Exception.Response) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }
        Write-Host "  FAILED ($statusCode): $_" -ForegroundColor Red
        
        # Try without Path
        Write-Host "  Retrying with folder-scoped POST..."
        try {
            $body2 = @{
                "@odata.type" = "#Model.PowerBIReport"
                "Content" = $base64
                "ContentType" = ""
                "Name" = $reportName
            } | ConvertTo-Json -Depth 5
            
            # URL-encode the folder path
            $encodedFolder = [System.Uri]::EscapeDataString($folder.TrimStart('/'))
            
            $resp2 = Invoke-RestMethod -Uri "$apiUrl/PowerBIReports" `
                -Method Post `
                -Body ([System.Text.Encoding]::UTF8.GetBytes($body2)) `
                -ContentType "application/json; charset=utf-8" `
                -UseDefaultCredentials `
                -Headers @{ "Accept" = "application/json" } `
                -TimeoutSec 120
            
            Write-Host "  SUCCESS (retry): $reportName" -ForegroundColor Green
            
            # Move to folder
            $moveBody = @{ Path = "$folder/$reportName" } | ConvertTo-Json
            Invoke-RestMethod -Uri "$apiUrl/PowerBIReports($($resp2.Id))" `
                -Method Patch `
                -Body ([System.Text.Encoding]::UTF8.GetBytes($moveBody)) `
                -ContentType "application/json; charset=utf-8" `
                -UseDefaultCredentials `
                -TimeoutSec 30
            Write-Host "  Moved to $folder" -ForegroundColor Green
        } catch {
            Write-Host "  FAILED (retry): $_" -ForegroundColor Red
        }
    }
}

# ─── 9. Summary ──────────────────────────────────────────────────
Write-Host "`n=== Summary ===" -ForegroundColor Cyan
Write-Host "Files created: $($createdFiles.Count)"
foreach ($f in $createdFiles) {
    Write-Host "  - $f"
}

# Clean up databases from AS
Write-Host "`nCleaning up AS databases..."
foreach ($report in $reports) {
    $dbName = "Model_$($report.Name -replace '[^a-zA-Z0-9]','_')"
    $db = $server.Databases.FindByName($dbName)
    if ($db) {
        $db.Drop()
        Write-Host "  Dropped: $dbName"
    }
}

$server.Disconnect()
$amoServer.Disconnect()
Write-Host "`nDone!" -ForegroundColor Green
