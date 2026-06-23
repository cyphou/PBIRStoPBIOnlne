<#
.SYNOPSIS
    Creates 5 sample Power BI reports (.pbix) and uploads them to PBIRS.
.DESCRIPTION
    Uses the local msmdsrv.exe from PBI Desktop RS to create valid .pbix files
    with embedded tabular models, then uploads them to the PBIRS server.
#>
param(
    [string]$PbirsUrl = "http://ms-len-moa/Reports/api/v2.0",
    [string]$DesktopRsPath = "C:\Program Files\Microsoft Power BI Desktop RS\bin"
)

$ErrorActionPreference = "Stop"

# ── AMO DLLs from NuGet ─────────────────────────────────────────────
$amoPkg = (Get-ChildItem "$env:USERPROFILE\.nuget\packages\microsoft.analysisservices.retail.amd64" -Directory |
           Sort-Object Name -Descending | Select-Object -First 1).FullName
$amoLib = Join-Path $amoPkg "lib\net45"

Add-Type -Path (Join-Path $amoLib "Microsoft.AnalysisServices.Core.dll")
Add-Type -Path (Join-Path $amoLib "Microsoft.AnalysisServices.Tabular.dll")
Add-Type -Path (Join-Path $amoLib "Microsoft.AnalysisServices.Tabular.Json.dll")

Write-Host "AMO loaded from $amoLib" -ForegroundColor Green

# ── Report definitions ───────────────────────────────────────────────
$reports = @(
    @{
        Name       = "Analyse des Ventes"
        Folder     = "/Équipe Commerciale"
        TableName  = "Ventes"
        Columns    = @(
            @{ Name = "Produit";  Type = "String" },
            @{ Name = "Region";   Type = "String" },
            @{ Name = "Montant";  Type = "Double" },
            @{ Name = "Quantite"; Type = "Int64" },
            @{ Name = "Date";     Type = "DateTime" }
        )
        MQuery     = '
let
    Source = Table.FromRows({
        {"Laptop","Nord",1250.00,5,"2024-01-15"},
        {"Laptop","Sud",980.50,3,"2024-01-20"},
        {"Tablet","Est",450.00,10,"2024-02-01"},
        {"Tablet","Ouest",675.25,7,"2024-02-10"},
        {"Phone","Nord",320.00,15,"2024-03-05"},
        {"Phone","Sud",280.00,12,"2024-03-12"},
        {"Monitor","Est",890.00,4,"2024-04-01"},
        {"Monitor","Ouest",1120.00,6,"2024-04-15"},
        {"Keyboard","Nord",45.00,25,"2024-05-01"},
        {"Keyboard","Sud",52.50,20,"2024-05-10"}
    }, {"Produit","Region","Montant","Quantite","Date"}),
    Types = Table.TransformColumnTypes(Source, {
        {"Montant", type number}, {"Quantite", Int64.Type}, {"Date", type date}
    })
in Types'
    },
    @{
        Name       = "Suivi Budgétaire"
        Folder     = "/Département Finance"
        TableName  = "Budget"
        Columns    = @(
            @{ Name = "Departement"; Type = "String" },
            @{ Name = "Categorie";   Type = "String" },
            @{ Name = "Budget";      Type = "Double" },
            @{ Name = "Depenses";    Type = "Double" },
            @{ Name = "Trimestre";   Type = "String" }
        )
        MQuery     = '
let
    Source = Table.FromRows({
        {"Marketing","Publicité",50000,42000,"Q1"},
        {"Marketing","Événements",30000,28500,"Q1"},
        {"IT","Infrastructure",80000,75000,"Q1"},
        {"IT","Licences",25000,24000,"Q1"},
        {"RH","Formation",15000,12000,"Q2"},
        {"RH","Recrutement",20000,18500,"Q2"},
        {"Finance","Audit",10000,9500,"Q2"},
        {"Finance","Outils",5000,4800,"Q3"},
        {"Marketing","Publicité",55000,51000,"Q3"},
        {"IT","Infrastructure",82000,79000,"Q4"}
    }, {"Departement","Categorie","Budget","Depenses","Trimestre"}),
    Types = Table.TransformColumnTypes(Source, {
        {"Budget", type number}, {"Depenses", type number}
    })
in Types'
    },
    @{
        Name       = "Tableau RH"
        Folder     = "/RH - Ressources Humaines"
        TableName  = "Employes"
        Columns    = @(
            @{ Name = "Nom";         Type = "String" },
            @{ Name = "Service";     Type = "String" },
            @{ Name = "Poste";       Type = "String" },
            @{ Name = "Anciennete";  Type = "Int64" },
            @{ Name = "Satisfaction"; Type = "Double" }
        )
        MQuery     = '
let
    Source = Table.FromRows({
        {"Dupont","IT","Développeur",5,4.2},
        {"Martin","IT","Chef de projet",8,3.8},
        {"Bernard","RH","Recruteur",3,4.5},
        {"Petit","Finance","Comptable",6,3.9},
        {"Robert","Marketing","Designer",2,4.7},
        {"Richard","IT","Analyste",4,4.0},
        {"Moreau","RH","Gestionnaire",7,3.6},
        {"Simon","Finance","Contrôleur",10,4.1},
        {"Laurent","Marketing","Manager",9,3.5},
        {"Michel","Direction","Directeur",12,4.3}
    }, {"Nom","Service","Poste","Anciennete","Satisfaction"}),
    Types = Table.TransformColumnTypes(Source, {
        {"Anciennete", Int64.Type}, {"Satisfaction", type number}
    })
in Types'
    },
    @{
        Name       = "Dashboard IT"
        Folder     = "/IT Operations"
        TableName  = "Incidents"
        Columns    = @(
            @{ Name = "Ticket";    Type = "String" },
            @{ Name = "Priorite";  Type = "String" },
            @{ Name = "Statut";    Type = "String" },
            @{ Name = "Systeme";   Type = "String" },
            @{ Name = "Duree_h";   Type = "Double" }
        )
        MQuery     = '
let
    Source = Table.FromRows({
        {"INC001","Haute","Résolu","ERP",2.5},
        {"INC002","Moyenne","En cours","CRM",0},
        {"INC003","Basse","Résolu","Email",1.0},
        {"INC004","Haute","Résolu","Réseau",4.0},
        {"INC005","Critique","En cours","Base de données",0},
        {"INC006","Moyenne","Résolu","Serveur Web",3.5},
        {"INC007","Basse","Résolu","Imprimante",0.5},
        {"INC008","Haute","Résolu","VPN",1.5},
        {"INC009","Moyenne","Nouveau","Stockage",0},
        {"INC010","Critique","Résolu","Firewall",6.0}
    }, {"Ticket","Priorite","Statut","Systeme","Duree_h"}),
    Types = Table.TransformColumnTypes(Source, {
        {"Duree_h", type number}
    })
in Types'
    },
    @{
        Name       = "KPI Direction"
        Folder     = "/Direction Générale"
        TableName  = "KPIs"
        Columns    = @(
            @{ Name = "Indicateur"; Type = "String" },
            @{ Name = "Valeur";     Type = "Double" },
            @{ Name = "Objectif";   Type = "Double" },
            @{ Name = "Unite";      Type = "String" },
            @{ Name = "Periode";    Type = "String" }
        )
        MQuery     = '
let
    Source = Table.FromRows({
        {"Chiffre Affaires",1250000,1500000,"EUR","2024-Q1"},
        {"Marge Brute",42.5,45.0,"%","2024-Q1"},
        {"Satisfaction Client",4.2,4.5,"/ 5","2024-Q1"},
        {"Taux Rétention",92.0,95.0,"%","2024-Q1"},
        {"NPS",45,50,"score","2024-Q1"},
        {"Chiffre Affaires",1380000,1500000,"EUR","2024-Q2"},
        {"Marge Brute",43.8,45.0,"%","2024-Q2"},
        {"Satisfaction Client",4.3,4.5,"/ 5","2024-Q2"},
        {"Taux Rétention",93.5,95.0,"%","2024-Q2"},
        {"NPS",48,50,"score","2024-Q2"}
    }, {"Indicateur","Valeur","Objectif","Unite","Periode"}),
    Types = Table.TransformColumnTypes(Source, {
        {"Valeur", type number}, {"Objectif", type number}
    })
in Types'
    }
)

# ── Helper: Create minimal .pbix ─────────────────────────────────────
function New-Pbix {
    param([string]$AbfPath, [string]$OutputPath, [string]$ReportName)

    $contentTypes = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Override PartName="/DataModel" ContentType="application/zip"/>
  <Override PartName="/Report/Layout" ContentType="application/json"/>
  <Override PartName="/SecurityBindings" ContentType="application/xml"/>
  <Override PartName="/Metadata" ContentType="application/json"/>
  <Override PartName="/Settings" ContentType="application/json"/>
  <Override PartName="/Version" ContentType="text/plain"/>
  <Override PartName="/DiagramState" ContentType="application/json"/>
</Types>
'@

    $rels = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.microsoft.com/packaging/2010/relationships/reportserver/powerbi-report" Target="/Report/Layout"/>
  <Relationship Id="rId2" Type="http://schemas.microsoft.com/packaging/2010/relationships/reportserver/powerbi-datamodel" Target="/DataModel"/>
</Relationships>
'@

    $layout = @"
{
  "id": 0,
  "reportId": "$([guid]::NewGuid().ToString())",
  "config": "{\"version\":\"5.53\",\"themeCollection\":{\"baseTheme\":{\"name\":\"CY24SU06\",\"version\":\"5.53\",\"type\":2}},\"activeSectionIndex\":0}",
  "displayOption": 0,
  "sections": [
    {
      "id": 0,
      "name": "Section1",
      "displayName": "$ReportName",
      "config": "{\"layouts\":[{\"id\":0,\"position\":{\"x\":0,\"y\":0,\"z\":0,\"width\":1280,\"height\":720,\"tabOrder\":0}}]}",
      "filters": "[]",
      "ordinal": 0,
      "visualContainers": [],
      "displayOption": 1,
      "width": 1280,
      "height": 720
    }
  ],
  "pods": []
}
"@

    $metadata = '{"version":"1.0","createdFrom":"RS"}'
    $settings = '{"version":"1.0"}'
    $version = "2.0"
    $diagramState = '{"version":"1.0","pages":[]}'

    # Build ZIP
    if (Test-Path $OutputPath) { Remove-Item $OutputPath -Force }

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem

    $zip = [System.IO.Compression.ZipFile]::Open($OutputPath, [System.IO.Compression.ZipArchiveMode]::Create)

    # Add [Content_Types].xml
    $entry = $zip.CreateEntry("[Content_Types].xml", [System.IO.Compression.CompressionLevel]::Optimal)
    $sw = New-Object System.IO.StreamWriter($entry.Open())
    $sw.Write($contentTypes); $sw.Close()

    # Add _rels/.rels
    $entry = $zip.CreateEntry("_rels/.rels", [System.IO.Compression.CompressionLevel]::Optimal)
    $sw = New-Object System.IO.StreamWriter($entry.Open())
    $sw.Write($rels); $sw.Close()

    # Add DataModel (the ABF backup)
    $entry = $zip.CreateEntry("DataModel", [System.IO.Compression.CompressionLevel]::NoCompression)
    $stream = $entry.Open()
    $abfBytes = [System.IO.File]::ReadAllBytes($AbfPath)
    $stream.Write($abfBytes, 0, $abfBytes.Length)
    $stream.Close()

    # Add Report/Layout
    $entry = $zip.CreateEntry("Report/Layout", [System.IO.Compression.CompressionLevel]::Optimal)
    $sw = New-Object System.IO.StreamWriter($entry.Open(), [System.Text.Encoding]::Unicode)
    $sw.Write($layout); $sw.Close()

    # Add SecurityBindings
    $entry = $zip.CreateEntry("SecurityBindings", [System.IO.Compression.CompressionLevel]::Optimal)
    $stream = $entry.Open(); $stream.Close()

    # Add Metadata
    $entry = $zip.CreateEntry("Metadata", [System.IO.Compression.CompressionLevel]::Optimal)
    $sw = New-Object System.IO.StreamWriter($entry.Open())
    $sw.Write($metadata); $sw.Close()

    # Add Settings
    $entry = $zip.CreateEntry("Settings", [System.IO.Compression.CompressionLevel]::Optimal)
    $sw = New-Object System.IO.StreamWriter($entry.Open())
    $sw.Write($settings); $sw.Close()

    # Add Version
    $entry = $zip.CreateEntry("Version", [System.IO.Compression.CompressionLevel]::Optimal)
    $sw = New-Object System.IO.StreamWriter($entry.Open())
    $sw.Write($version); $sw.Close()

    # Add DiagramState
    $entry = $zip.CreateEntry("DiagramState", [System.IO.Compression.CompressionLevel]::Optimal)
    $sw = New-Object System.IO.StreamWriter($entry.Open())
    $sw.Write($diagramState); $sw.Close()

    $zip.Dispose()
    Write-Host "  Created .pbix: $OutputPath ($([math]::Round((Get-Item $OutputPath).Length / 1KB)) KB)" -ForegroundColor Cyan
}

# ── Main ──────────────────────────────────────────────────────────────
$workDir   = Join-Path $env:TEMP "pbix_as_workspace"
$outputDir = Join-Path $PSScriptRoot "..\artifacts\pbix"

# Prepare directories
if (-not (Test-Path $workDir))   { New-Item $workDir -ItemType Directory -Force | Out-Null }
if (-not (Test-Path "$workDir\backup")) { New-Item "$workDir\backup" -ItemType Directory -Force | Out-Null }
if (-not (Test-Path $outputDir)) { New-Item $outputDir -ItemType Directory -Force | Out-Null }

# ── Find PBI Desktop RS AS instance ──────────────────────────────────
# PBI Desktop RS must be running — it starts its own msmdsrv.exe on a random port.
# The port is written to msmdsrv.port.txt in the workspace directory.
$asWorkspacesDir = Join-Path $env:LOCALAPPDATA "Microsoft\Power BI Desktop SSRS\AnalysisServicesWorkspaces"
$portFiles = Get-ChildItem $asWorkspacesDir -Recurse -Filter "msmdsrv.port.txt" -ErrorAction SilentlyContinue

if (-not $portFiles -or $portFiles.Count -eq 0) {
    Write-Host "No PBI Desktop RS AS instance found. Starting PBI Desktop RS..." -ForegroundColor Yellow
    Start-Process -FilePath (Join-Path $DesktopRsPath "PBIDesktop.exe")
    Start-Sleep -Seconds 20
    $portFiles = Get-ChildItem $asWorkspacesDir -Recurse -Filter "msmdsrv.port.txt" -ErrorAction SilentlyContinue
    if (-not $portFiles) {
        throw "PBI Desktop RS did not start its AS instance. Please start PBI Desktop RS manually first."
    }
}

$port = (Get-Content $portFiles[0].FullName).Trim()
Write-Host "Found PBI Desktop RS AS instance on port $port" -ForegroundColor Green

$connStr = "localhost:$port"
Write-Host "Connection string: '$connStr'" -ForegroundColor Gray

try {
    $server = New-Object Microsoft.AnalysisServices.Tabular.Server
    $server.Connect($connStr)
    Write-Host "Connected to PBI Desktop RS AS (v$($server.Version))" -ForegroundColor Green

    # Get CompatibilityLevel from the server version
    $compatLevel = 1400
    Write-Host "Using CompatibilityLevel: $compatLevel" -ForegroundColor Gray

    foreach ($rpt in $reports) {
        Write-Host "`nCreating model: $($rpt.Name)..." -ForegroundColor Yellow

        # Create database
        $dbId = [guid]::NewGuid().ToString()
        $db = New-Object Microsoft.AnalysisServices.Tabular.Database
        $db.Name = $rpt.Name
        $db.ID = $dbId
        $db.CompatibilityLevel = $compatLevel
        $db.Model = New-Object Microsoft.AnalysisServices.Tabular.Model
        $db.Model.Name = "Model"

        # Create table
        $table = New-Object Microsoft.AnalysisServices.Tabular.Table
        $table.Name = $rpt.TableName

        # Add columns
        foreach ($col in $rpt.Columns) {
            $column = New-Object Microsoft.AnalysisServices.Tabular.DataColumn
            $column.Name = $col.Name
            $column.SourceColumn = $col.Name
            switch ($col.Type) {
                "String"   { $column.DataType = [Microsoft.AnalysisServices.Tabular.DataType]::String }
                "Double"   { $column.DataType = [Microsoft.AnalysisServices.Tabular.DataType]::Double }
                "Int64"    { $column.DataType = [Microsoft.AnalysisServices.Tabular.DataType]::Int64 }
                "DateTime" { $column.DataType = [Microsoft.AnalysisServices.Tabular.DataType]::DateTime }
            }
            $table.Columns.Add($column)
        }

        # Add partition with M query
        $partition = New-Object Microsoft.AnalysisServices.Tabular.Partition
        $partition.Name = $rpt.TableName
        $partition.Source = New-Object Microsoft.AnalysisServices.Tabular.MPartitionSource
        $partition.Source.Expression = $rpt.MQuery
        $table.Partitions.Add($partition)

        $db.Model.Tables.Add($table)

        # Add to server and process
        $server.Databases.Add($db)
        $db.Update([Microsoft.AnalysisServices.UpdateOptions]::ExpandFull)
        Write-Host "  Model created, processing..." -ForegroundColor Gray

        $db.Model.RequestRefresh([Microsoft.AnalysisServices.Tabular.RefreshType]::Full)
        $db.Model.SaveChanges()
        Write-Host "  Model processed successfully" -ForegroundColor Green

        # Backup to ABF
        $abfPath = Join-Path $workDir "backup\$($rpt.Name).abf"
        $server.Backup($dbId, $abfPath, $true)
        Write-Host "  Backed up to ABF ($([math]::Round((Get-Item $abfPath).Length / 1KB)) KB)" -ForegroundColor Green

        # Package into .pbix
        $pbixPath = Join-Path $outputDir "$($rpt.Name).pbix"
        New-Pbix -AbfPath $abfPath -OutputPath $pbixPath -ReportName $rpt.Name

        # Drop the database (clean up)
        $server.Databases.RemoveAt($server.Databases.IndexOf($db))
    }
}
finally {
    if ($server -and $server.Connected) { $server.Disconnect() }
    Write-Host "`nDisconnected from PBI Desktop RS AS." -ForegroundColor Yellow
}

# ── Upload to PBIRS ──────────────────────────────────────────────────
Write-Host "`n=== Uploading reports to PBIRS ===" -ForegroundColor Cyan

foreach ($rpt in $reports) {
    $pbixPath = Join-Path $outputDir "$($rpt.Name).pbix"
    if (-not (Test-Path $pbixPath)) {
        Write-Host "  SKIP: $pbixPath not found" -ForegroundColor Red
        continue
    }

    $bytes = [System.IO.File]::ReadAllBytes($pbixPath)
    $b64 = [Convert]::ToBase64String($bytes)

    $body = @{
        "@odata.type" = "#Model.PowerBIReport"
        Name          = $rpt.Name
        Path          = "$($rpt.Folder)/$($rpt.Name)"
        Content       = $b64
        ContentType   = "application/octet-stream"
    } | ConvertTo-Json -Depth 5

    $jsonBytes = [System.Text.Encoding]::UTF8.GetBytes($body)

    Write-Host "  Uploading '$($rpt.Name)' to $($rpt.Folder)..." -ForegroundColor Yellow
    try {
        $resp = Invoke-RestMethod -Uri "$PbirsUrl/PowerBIReports" `
            -Method POST `
            -Body $jsonBytes `
            -ContentType "application/json; charset=utf-8" `
            -UseDefaultCredentials `
            -AllowUnencryptedAuthentication `
            -TimeoutSec 120

        Write-Host "  OK: $($resp.Name) → $($resp.Path)" -ForegroundColor Green
    }
    catch {
        $status = $_.Exception.Response.StatusCode.value__
        Write-Host "  FAIL ($status): $_" -ForegroundColor Red
    }
}

Write-Host "`n=== Done ===" -ForegroundColor Cyan
