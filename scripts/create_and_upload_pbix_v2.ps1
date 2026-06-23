<#
.SYNOPSIS
    Create 5 sample .pbix reports and upload to PBIRS.
    
.DESCRIPTION
    Uses AMO to create tabular models in PBI Desktop RS's AS instance,
    backs them up to the AS BackupDir, then packages as .pbix and uploads.
#>

$ErrorActionPreference = "Stop"
$apiUrl = "http://ms-len-moa/Reports/api/v2.0"
$outputDir = Join-Path $PSScriptRoot "artifacts\pbix"

# The AS data/backup directory (from msmdsrv.ini)
$asDataDir = "C:\Users\pidoudet\AppData\Local\Microsoft\Power BI Desktop SSRS\AnalysisServicesWorkspaces\AnalysisServicesWorkspace_eed750da-0ceb-4809-9107-f860d6333e87\Data"

# ─── 1. Load AMO assemblies from SSMS ────────────────────────────
$amoDir = "C:\Program Files\Microsoft SQL Server Management Studio 22\Release\Common7\IDE"
foreach ($dll in @("Microsoft.AnalysisServices.Core.dll", "Microsoft.AnalysisServices.Tabular.dll", "Microsoft.AnalysisServices.dll")) {
    $p = Join-Path $amoDir $dll
    if (Test-Path $p) {
        [System.Reflection.Assembly]::LoadFrom($p) | Out-Null
        Write-Host "Loaded: $dll" -ForegroundColor Green
    }
}

# ─── 2. Find PBI Desktop RS AS port ──────────────────────────────
$asPort = $null
$allMsmdsrv = Get-Process -Name "msmdsrv" -ErrorAction SilentlyContinue
foreach ($proc in $allMsmdsrv) {
    try {
        if ($proc.Path -and $proc.Path -like "*Power BI Desktop RS*") {
            $netstatLines = netstat -ano | Select-String "LISTENING" | Select-String "$($proc.Id)"
            foreach ($line in $netstatLines) {
                if ($line -match ':(\d+)\s') { $asPort = $Matches[1]; break }
            }
            break
        }
    } catch {}
}

if (-not $asPort) {
    Write-Error "PBI Desktop RS not running. Start PBIDesktop.exe first."
    exit 1
}
Write-Host "AS port: $asPort" -ForegroundColor Cyan

# ─── 3. Connect to AS ────────────────────────────────────────────
$server = New-Object Microsoft.AnalysisServices.Tabular.Server
$server.Connect("localhost:$asPort")
Write-Host "Connected: $($server.Name)" -ForegroundColor Green

# ─── 4. Define reports ───────────────────────────────────────────
$reports = @(
    @{
        Name = "Analyse des Ventes"; Folder = "/Équipe Commerciale"; Table = "Ventes"
        Columns = @(
            @{N="Produit"; V=@("Widget A","Widget B","Widget C","Gadget X","Gadget Y")},
            @{N="Region"; V=@("Nord","Sud","Est","Ouest","Centre")},
            @{N="Montant"; V=@(15000,22000,18000,31000,12000)},
            @{N="Quantite"; V=@(150,220,180,310,120)}
        )
    },
    @{
        Name = "Suivi Budgétaire"; Folder = "/Département Finance"; Table = "Budget"
        Columns = @(
            @{N="Categorie"; V=@("Personnel","Matériel","Logiciel","Formation","Voyage")},
            @{N="Budget_Prevu"; V=@(100000,50000,75000,25000,30000)},
            @{N="Depense_Reelle"; V=@(95000,62000,70000,18000,35000)},
            @{N="Ecart"; V=@(5000,-12000,5000,7000,-5000)}
        )
    },
    @{
        Name = "Tableau RH"; Folder = "/RH - Ressources Humaines"; Table = "Employes"
        Columns = @(
            @{N="Departement"; V=@("IT","RH","Finance","Marketing","Ventes")},
            @{N="Effectif"; V=@(45,12,18,22,35)},
            @{N="Turnover_Pct"; V=@(8.5,3.2,5.1,12.0,15.3)},
            @{N="Satisfaction"; V=@(4.2,4.8,4.1,3.9,3.5)}
        )
    },
    @{
        Name = "Dashboard IT"; Folder = "/IT Operations"; Table = "Incidents"
        Columns = @(
            @{N="Categorie"; V=@("Réseau","Serveur","Application","Sécurité","Base de données")},
            @{N="Nombre"; V=@(45,23,67,12,8)},
            @{N="Temps_h"; V=@(2.5,4.0,1.5,8.0,3.0)},
            @{N="Priorite"; V=@("Haute","Critique","Moyenne","Critique","Haute")}
        )
    },
    @{
        Name = "KPI Direction"; Folder = "/Direction Générale"; Table = "KPI"
        Columns = @(
            @{N="Indicateur"; V=@("CA Total","Marge Brute","EBITDA","Cash Flow","ROI")},
            @{N="Valeur"; V=@(5200000,1560000,780000,620000,18.5)},
            @{N="Objectif"; V=@(5000000,1500000,750000,600000,15.0)},
            @{N="Atteinte_Pct"; V=@(104.0,104.0,104.0,103.3,123.3)}
        )
    }
)

# ─── 5. Create output dir ────────────────────────────────────────
if (-not (Test-Path $outputDir)) { New-Item -ItemType Directory -Path $outputDir -Force | Out-Null }

# ─── 6. Create models and backup ─────────────────────────────────
$createdFiles = @()

foreach ($report in $reports) {
    Write-Host "`n--- $($report.Name) ---" -ForegroundColor Cyan
    $dbName = "Model_$($report.Name -replace '[^a-zA-Z0-9]','_')"
    
    # Drop existing
    $existing = $server.Databases.FindByName($dbName)
    if ($existing) { $existing.Drop(); Write-Host "  Dropped old $dbName" }
    
    # Create database with model
    $db = New-Object Microsoft.AnalysisServices.Tabular.Database
    $db.Name = $dbName
    $db.ID = $dbName
    $db.CompatibilityLevel = 1400
    $db.Model = New-Object Microsoft.AnalysisServices.Tabular.Model
    $db.Model.Name = "Model"
    
    # Create table with columns (no M partition — just calculated table)
    $table = New-Object Microsoft.AnalysisServices.Tabular.Table
    $table.Name = $report.Table
    
    # Build inline data as a DAX DATATABLE expression for a calculated table partition
    # This avoids M expression issues
    $partition = New-Object Microsoft.AnalysisServices.Tabular.Partition
    $partition.Name = $report.Table
    $partition.Source = New-Object Microsoft.AnalysisServices.Tabular.CalculatedPartitionSource
    
    # Build DATATABLE expression
    $colDefs = @()
    $colTypes = @()
    foreach ($col in $report.Columns) {
        $v = $col.V[0]
        if ($v -is [int] -or $v -is [double] -or $v -is [float]) {
            $colDefs += """$($col.N)"", CURRENCY"
            $colTypes += "number"
        } else {
            $colDefs += """$($col.N)"", STRING"
            $colTypes += "string"
        }
    }
    
    $rows = @()
    for ($i = 0; $i -lt $report.Columns[0].V.Count; $i++) {
        $vals = @()
        for ($c = 0; $c -lt $report.Columns.Count; $c++) {
            $v = $report.Columns[$c].V[$i]
            if ($colTypes[$c] -eq "number") {
                $vals += "$v"
            } else {
                $vals += """$v"""
            }
        }
        $rows += "        {$($vals -join ', ')}"
    }
    
    $daxExpr = "DATATABLE(`n    $($colDefs -join ",`n    "),`n    {`n$($rows -join ",`n")`n    }`n)"
    $partition.Source.Expression = $daxExpr
    $table.Partitions.Add($partition)
    
    # Add columns
    foreach ($col in $report.Columns) {
        $column = New-Object Microsoft.AnalysisServices.Tabular.DataColumn
        $column.Name = $col.N
        $column.SourceColumn = $col.N
        $v = $col.V[0]
        if ($v -is [int] -or $v -is [double] -or $v -is [float]) {
            $column.DataType = [Microsoft.AnalysisServices.Tabular.DataType]::Double
        } else {
            $column.DataType = [Microsoft.AnalysisServices.Tabular.DataType]::String
        }
        $table.Columns.Add($column)
    }
    
    # Add measure
    $measure = New-Object Microsoft.AnalysisServices.Tabular.Measure
    $numCol = $report.Columns | Where-Object { $_.V[0] -is [int] -or $_.V[0] -is [double] -or $_.V[0] -is [float] } | Select-Object -First 1
    if ($numCol) {
        $measure.Name = "Total_$($numCol.N)"
        $measure.Expression = "SUM('$($report.Table)'[$($numCol.N)])"
    } else {
        $measure.Name = "RowCount"
        $measure.Expression = "COUNTROWS('$($report.Table)')"
    }
    $table.Measures.Add($measure)
    $db.Model.Tables.Add($table)
    
    $server.Databases.Add($db)
    try {
        $db.Update([Microsoft.AnalysisServices.UpdateOptions]::ExpandFull)
        Write-Host "  DB created: $dbName" -ForegroundColor Green
    } catch {
        Write-Host "  DB creation failed: $_" -ForegroundColor Red
        continue
    }
    
    # ─── BACKUP: use just filename so it goes to BackupDir ────────
    $abfFilename = "$dbName.abf"
    $abfFullPath = Join-Path $asDataDir $abfFilename
    
    # Remove old backup file if exists
    if (Test-Path $abfFullPath) { Remove-Item $abfFullPath -Force }
    
    Write-Host "  Backing up (XMLA) to BackupDir as $abfFilename..."
    $xmlaCmd = @"
<Backup xmlns="http://schemas.microsoft.com/analysisservices/2003/engine">
  <Object><DatabaseID>$dbName</DatabaseID></Object>
  <File>$abfFilename</File>
  <AllowOverwrite>true</AllowOverwrite>
</Backup>
"@
    
    try {
        $result = $server.Execute($xmlaCmd)
        $hasErrors = $false
        foreach ($msg in $result) {
            if ($msg -is [Microsoft.AnalysisServices.XmlaError]) {
                Write-Host "    XMLA Error: $($msg.Description)" -ForegroundColor Red
                $hasErrors = $true
            } else {
                Write-Host "    XMLA: $msg" -ForegroundColor Gray
            }
        }
    } catch {
        Write-Host "  XMLA backup failed: $_" -ForegroundColor Red
    }
    
    # Check if file was created
    Start-Sleep -Milliseconds 500
    if (Test-Path $abfFullPath) {
        $size = (Get-Item $abfFullPath).Length
        Write-Host "  ABF created: $abfFullPath ($([math]::Round($size/1KB))KB)" -ForegroundColor Green
    } else {
        # Search for any new .abf files in the data directory
        Write-Host "  ABF not found at expected path. Searching..." -ForegroundColor Yellow
        $abfFiles = Get-ChildItem $asDataDir -Filter "*.abf" -ErrorAction SilentlyContinue
        if ($abfFiles) {
            foreach ($f in $abfFiles) {
                Write-Host "    Found: $($f.FullName) ($([math]::Round($f.Length/1KB))KB)" -ForegroundColor Yellow
            }
            $abfFullPath = $abfFiles[0].FullName
        } else {
            Write-Host "  NO ABF file found anywhere in data dir!" -ForegroundColor Red
            Write-Host "  Files in data dir:"
            Get-ChildItem $asDataDir -File | ForEach-Object {
                Write-Host "    $($_.Name) ($([math]::Round($_.Length/1KB))KB) Modified: $($_.LastWriteTime)"
            }
            
            # FALLBACK: Serialize model as JSON and use as thin report
            Write-Host "`n  FALLBACK: Using TMSL JSON as DataModel..." -ForegroundColor Yellow
            $modelJson = [Microsoft.AnalysisServices.Tabular.JsonSerializer]::SerializeDatabase($db)
            $modelBytes = [System.Text.Encoding]::UTF8.GetBytes($modelJson)
            
            # Create .pbix with JSON model
            $pbixPath = Join-Path $outputDir "$($report.Name).pbix"
            if (Test-Path $pbixPath) { Remove-Item $pbixPath -Force }
            
            Add-Type -AssemblyName System.IO.Compression
            $zipStream = [System.IO.File]::Create($pbixPath)
            $zip = New-Object System.IO.Compression.ZipArchive($zipStream, [System.IO.Compression.ZipArchiveMode]::Create)
            
            # [Content_Types].xml
            $e = $zip.CreateEntry("[Content_Types].xml")
            $w = New-Object System.IO.StreamWriter($e.Open())
            $w.Write('<?xml version="1.0" encoding="utf-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="json" ContentType="application/json" /></Types>')
            $w.Close()
            
            # DataModel (JSON)
            $e = $zip.CreateEntry("DataModel")
            $s = $e.Open()
            $s.Write($modelBytes, 0, $modelBytes.Length)
            $s.Close()
            
            # Version
            $e = $zip.CreateEntry("Version")
            $w = New-Object System.IO.StreamWriter($e.Open())
            $w.Write("2.0.0.0")
            $w.Close()
            
            # Settings
            $e = $zip.CreateEntry("Settings")
            $w = New-Object System.IO.StreamWriter($e.Open())
            $w.Write('{"IsReportServerNative":true}')
            $w.Close()
            
            # Report/Layout
            $layout = @{
                id = 0; reportId = [guid]::NewGuid().ToString()
                config = '{"version":"5.54","themeCollection":{"baseTheme":{"name":"CY24SU01","dataColors":["#118DFF","#12239E","#E66C37"]}}}'
                filters = "[]"; sections = @(@{name="Section1";displayName="Page 1";filters="[]";ordinal=0;visualContainers=@();width=1280;height=720})
            } | ConvertTo-Json -Depth 10
            $e = $zip.CreateEntry("Report/Layout")
            $w = New-Object System.IO.StreamWriter($e.Open(), [System.Text.Encoding]::Unicode)
            $w.Write($layout)
            $w.Close()
            
            $zip.Dispose()
            $zipStream.Close()
            
            $createdFiles += $pbixPath
            Write-Host "  Created (JSON model): $pbixPath ($([math]::Round((Get-Item $pbixPath).Length/1KB))KB)" -ForegroundColor Green
            
            # Clean up DB
            $db.Drop()
            continue
        }
    }
    
    # Package as .pbix with ABF
    $pbixPath = Join-Path $outputDir "$($report.Name).pbix"
    if (Test-Path $pbixPath) { Remove-Item $pbixPath -Force }
    
    Add-Type -AssemblyName System.IO.Compression
    $zipStream = [System.IO.File]::Create($pbixPath)
    $zip = New-Object System.IO.Compression.ZipArchive($zipStream, [System.IO.Compression.ZipArchiveMode]::Create)
    
    $e = $zip.CreateEntry("[Content_Types].xml")
    $w = New-Object System.IO.StreamWriter($e.Open())
    $w.Write('<?xml version="1.0" encoding="utf-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="json" ContentType="application/json" /></Types>')
    $w.Close()
    
    $e = $zip.CreateEntry("DataModel")
    $s = $e.Open()
    $abfBytes = [System.IO.File]::ReadAllBytes($abfFullPath)
    $s.Write($abfBytes, 0, $abfBytes.Length)
    $s.Close()
    
    $e = $zip.CreateEntry("Version")
    $w = New-Object System.IO.StreamWriter($e.Open())
    $w.Write("2.0.0.0")
    $w.Close()
    
    $e = $zip.CreateEntry("Settings")
    $w = New-Object System.IO.StreamWriter($e.Open())
    $w.Write('{"IsReportServerNative":true}')
    $w.Close()
    
    $layout = @{
        id = 0; reportId = [guid]::NewGuid().ToString()
        config = '{"version":"5.54","themeCollection":{"baseTheme":{"name":"CY24SU01","dataColors":["#118DFF","#12239E","#E66C37"]}}}'
        filters = "[]"; sections = @(@{name="Section1";displayName="Page 1";filters="[]";ordinal=0;visualContainers=@();width=1280;height=720})
    } | ConvertTo-Json -Depth 10
    $e = $zip.CreateEntry("Report/Layout")
    $w = New-Object System.IO.StreamWriter($e.Open(), [System.Text.Encoding]::Unicode)
    $w.Write($layout)
    $w.Close()
    
    $zip.Dispose()
    $zipStream.Close()
    
    # Clean up
    Remove-Item $abfFullPath -Force -ErrorAction SilentlyContinue
    $db.Drop()
    
    $createdFiles += $pbixPath
    Write-Host "  Created: $pbixPath ($([math]::Round((Get-Item $pbixPath).Length/1KB))KB)" -ForegroundColor Green
}

$server.Disconnect()

# ─── 7. Upload to PBIRS ──────────────────────────────────────────
Write-Host "`n=== Uploading to PBIRS ===" -ForegroundColor Cyan

foreach ($report in $reports) {
    $pbixPath = Join-Path $outputDir "$($report.Name).pbix"
    if (-not (Test-Path $pbixPath)) {
        Write-Host "  Skip: $($report.Name) (file not found)" -ForegroundColor Yellow
        continue
    }
    
    $bytes = [System.IO.File]::ReadAllBytes($pbixPath)
    $base64 = [Convert]::ToBase64String($bytes)
    
    $body = @{
        "@odata.type" = "#Model.PowerBIReport"
        "Content" = $base64
        "ContentType" = ""
        "Name" = $report.Name
        "Path" = "$($report.Folder)/$($report.Name)"
    } | ConvertTo-Json -Depth 5
    
    Write-Host "  Uploading '$($report.Name)' to '$($report.Folder)'..."
    try {
        $resp = Invoke-RestMethod -Uri "$apiUrl/PowerBIReports" `
            -Method Post `
            -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) `
            -ContentType "application/json; charset=utf-8" `
            -UseDefaultCredentials `
            -TimeoutSec 120
        
        Write-Host "  OK: $($report.Name) (Id: $($resp.Id))" -ForegroundColor Green
    } catch {
        $code = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { "?" }
        Write-Host "  FAILED ($code): $_" -ForegroundColor Red
        
        # Read error details
        if ($_.Exception.Response) {
            try {
                $errStream = $_.Exception.Response.GetResponseStream()
                $reader = New-Object System.IO.StreamReader($errStream)
                $errBody = $reader.ReadToEnd()
                Write-Host "  Error body: $errBody" -ForegroundColor Red
            } catch {}
        }
    }
}

Write-Host "`n=== Done ===" -ForegroundColor Green
Write-Host "Created files: $($createdFiles.Count)"
$createdFiles | ForEach-Object { Write-Host "  $_" }
