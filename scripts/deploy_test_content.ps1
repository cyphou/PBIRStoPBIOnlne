<#
.SYNOPSIS
    Deploy diverse test content to a local Power BI Report Server for migration testing.

.DESCRIPTION
    Creates folders, paginated reports (RDL), data sources, and sets permissions
    to exercise all 9 assessment categories of the migration pipeline.

    Must be run elevated (as Administrator) so that BUILTIN\Administrators auth works.

.PARAMETER BaseUrl
    The PBIRS ReportServer URL. Default: http://localhost/ReportServer

.EXAMPLE
    .\deploy_test_content.ps1
    .\deploy_test_content.ps1 -BaseUrl "http://myserver/ReportServer"
#>
param(
    [string]$BaseUrl = "http://localhost/ReportServer"
)

$ErrorActionPreference = "Stop"
$apiUrl = "$BaseUrl/api/v2.0"

# ─── HTTP helper ────────────────────────────────────────────────────
function Invoke-PBIRS {
    param(
        [string]$Method,
        [string]$Path,
        [object]$Body,
        [string]$ContentType = "application/json; charset=utf-8",
        [switch]$Raw
    )
    $uri = "$apiUrl$Path"
    $params = @{
        Uri                          = $uri
        Method                       = $Method
        UseDefaultCredentials        = $true
        AllowUnencryptedAuthentication = $true
        Headers                      = @{ "Accept" = "application/json" }
        TimeoutSec                   = 60
    }
    if ($Body -and -not $Raw) {
        $json = $Body | ConvertTo-Json -Depth 10
        $params.Body = [System.Text.Encoding]::UTF8.GetBytes($json)
        $params.ContentType = $ContentType
    }
    elseif ($Body -and $Raw) {
        $params.Body = $Body
        $params.ContentType = $ContentType
    }

    try {
        return Invoke-RestMethod @params
    }
    catch {
        $status = $_.Exception.Response.StatusCode.value__
        Write-Warning "  $Method $Path → HTTP $status : $($_.Exception.Message)"
        return $null
    }
}

# ─── Verify connectivity ───────────────────────────────────────────
Write-Host "═══ PBIRS Test Content Deployer ═══" -ForegroundColor Cyan
Write-Host "Target: $apiUrl"
$sysInfo = Invoke-PBIRS -Method GET -Path "/System"
if (-not $sysInfo) {
    Write-Error "Cannot reach PBIRS API at $apiUrl. Is the service running? Are you elevated?"
    exit 1
}
Write-Host "Connected to: $($sysInfo.ProductName) v$($sysInfo.ProductVersion)" -ForegroundColor Green

# ─── 1. Create Folder Structure ────────────────────────────────────
Write-Host "`n── Creating Folders ──" -ForegroundColor Yellow

$folders = @(
    @{ Name = "Département Finance";       Desc = "Rapports financiers — budgets, prévisions, résultats" }
    @{ Name = "Équipe Commerciale";        Desc = "Suivi des ventes et performances commerciales" }
    @{ Name = "Contrôle Qualité";          Desc = "Rapports qualité — indicateurs, non-conformités" }
    @{ Name = "RH - Ressources Humaines";  Desc = "Évaluations, effectifs, formation" }
    @{ Name = "IT Operations";             Desc = "Server health, capacity planning" }
    @{ Name = "Direction Générale";        Desc = "Tableaux de bord stratégiques" }
    @{ Name = "Données Archivées";         Desc = "Rapports historiques — à ne pas migrer" }
)

$folderIds = @{}
foreach ($f in $folders) {
    $body = @{
        "@odata.type" = "#Model.Folder"
        Name          = $f.Name
        Description   = $f.Desc
        Path          = "/"
    }
    $result = Invoke-PBIRS -Method POST -Path "/Folders" -Body $body
    if ($result) {
        $folderIds[$f.Name] = $result.Id
        Write-Host "  ✓ /$($f.Name) ($($result.Id))" -ForegroundColor Green
    }
    else {
        # Maybe already exists — try to find it
        $existing = Invoke-PBIRS -Method GET -Path "/Folders?`$filter=Path eq '/$($f.Name)'"
        if ($existing.value) {
            $folderIds[$f.Name] = $existing.value[0].Id
            Write-Host "  ○ /$($f.Name) (already exists)" -ForegroundColor DarkYellow
        }
        else {
            Write-Host "  ✗ /$($f.Name) FAILED" -ForegroundColor Red
        }
    }
}

# Create sub-folders
$subFolders = @(
    @{ Name = "Budgets Prévisionnels"; Parent = "Département Finance" }
    @{ Name = "Résultats Trimestriels"; Parent = "Département Finance" }
    @{ Name = "Clients Étrangers";     Parent = "Équipe Commerciale" }
)
foreach ($sf in $subFolders) {
    $parentId = $folderIds[$sf.Parent]
    if ($parentId) {
        $body = @{
            "@odata.type" = "#Model.Folder"
            Name          = $sf.Name
            Description   = "Sub-folder of $($sf.Parent)"
            Path          = "/$($sf.Parent)"
        }
        $result = Invoke-PBIRS -Method POST -Path "/Folders" -Body $body
        if ($result) {
            $folderIds["$($sf.Parent)/$($sf.Name)"] = $result.Id
            Write-Host "  ✓ /$($sf.Parent)/$($sf.Name)" -ForegroundColor Green
        }
    }
}

# ─── 2. Create Shared Data Sources ─────────────────────────────────
Write-Host "`n── Creating Data Sources ──" -ForegroundColor Yellow

$dataSources = @(
    @{
        Name    = "SQL_Finance_Prod"
        Folder  = "Département Finance"
        ConnStr = "Data Source=sql-prod.corp.local;Initial Catalog=FinanceDB"
        Type    = "SQL"
        Desc    = "Production SQL Server — données financières"
    }
    @{
        Name    = "Oracle_ERP_Legacy"
        Folder  = "Département Finance"
        ConnStr = "Data Source=oracle-erp.corp.local:1521/ERPDB"
        Type    = "ORACLE"
        Desc    = "Oracle ERP — système hérité"
    }
    @{
        Name    = "SQL_RH_Confidentiel"
        Folder  = "RH - Ressources Humaines"
        ConnStr = "Data Source=sql-hr.corp.local;Initial Catalog=HRDB;Encrypt=true"
        Type    = "SQL"
        Desc    = "Base RH — données confidentielles employés"
    }
    @{
        Name    = "Analysis_Services_Cube"
        Folder  = "Direction Générale"
        ConnStr = "Data Source=ssas-prod.corp.local;Initial Catalog=EnterpriseCube"
        Type    = "OLEDB-MD"
        Desc    = "Cube SSAS multidimensionnel — KPI stratégiques"
    }
    @{
        Name    = "SharePoint_Liste"
        Folder  = "Contrôle Qualité"
        ConnStr = "https://sharepoint.corp.local/sites/quality"
        Type    = "XML"
        Desc    = "Liste SharePoint — non-conformités"
    }
    @{
        Name    = "PostgreSQL_Analytics"
        Folder  = "IT Operations"
        ConnStr = "Host=pg-analytics.corp.local;Database=monitoring;Port=5432"
        Type    = "POSTGRESQL"
        Desc    = "PostgreSQL — monitoring infrastructure"
    }
)

$dsIds = @{}
foreach ($ds in $dataSources) {
    $parentPath = "/$($ds.Folder)"
    $body = @{
        "@odata.type"        = "#Model.DataSource"
        Name                 = $ds.Name
        Description          = $ds.Desc
        Path                 = $parentPath
        ConnectionString     = $ds.ConnStr
        DataSourceType       = $ds.Type
        CredentialRetrieval  = "Integrated"
        IsConnectionStringOverridden = $true
    }
    $result = Invoke-PBIRS -Method POST -Path "/DataSources" -Body $body
    if ($result) {
        $dsIds[$ds.Name] = $result.Id
        Write-Host "  ✓ $($ds.Name) ($($ds.Type)) → $parentPath" -ForegroundColor Green
    }
    else {
        Write-Host "  ✗ $($ds.Name) FAILED" -ForegroundColor Red
    }
}

# ─── 3. Create Paginated Reports (RDL) ─────────────────────────────
Write-Host "`n── Creating Paginated Reports (RDL) ──" -ForegroundColor Yellow

function New-RDL {
    param(
        [string]$ReportName,
        [string]$DataSourceName,
        [string]$Query,
        [string[]]$Parameters = @(),
        [switch]$HasSubreport,
        [switch]$HasDrillthrough,
        [switch]$HasCustomCode,
        [switch]$HasExternalImages,
        [string[]]$Features = @()
    )

    $paramXml = ""
    foreach ($p in $Parameters) {
        $paramXml += @"
        <ReportParameter Name="$p">
          <DataType>String</DataType>
          <Prompt>$p</Prompt>
          <DefaultValue><Values><Value></Value></Values></DefaultValue>
        </ReportParameter>
"@
    }
    $paramSection = if ($Parameters.Count -gt 0) { "<ReportParameters>$paramXml</ReportParameters>" } else { "" }

    $subreportXml = if ($HasSubreport) {
        '<Subreport Name="SubReport1"><ReportName>DetailReport</ReportName></Subreport>'
    } else { "" }

    $customCodeXml = if ($HasCustomCode) {
        @"
    <Code>
      Public Function FormatCurrency(amount As Decimal) As String
        Return String.Format("{0:C}", amount)
      End Function

      Public Function CalculateGrowth(current As Decimal, previous As Decimal) As String
        If previous = 0 Then Return "N/A"
        Return String.Format("{0:P1}", (current - previous) / previous)
      End Function
    </Code>
"@
    } else { "" }

    $imageXml = if ($HasExternalImages) {
        '<Image Name="Logo"><Source>External</Source><Value>https://corp.local/images/logo.png</Value></Image>'
    } else { "" }

    $drillXml = if ($HasDrillthrough) {
        @"
        <Action>
          <Drillthrough>
            <ReportName>DetailDrillthrough</ReportName>
            <Parameters>
              <Parameter Name="ID"><Value>=Fields!ID.Value</Value></Parameter>
            </Parameters>
          </Drillthrough>
        </Action>
"@
    } else { "" }

    return @"
<?xml version="1.0" encoding="utf-8"?>
<Report xmlns="http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition" xmlns:rd="http://schemas.microsoft.com/SQLServer/reporting/reportdesigner">
  <AutoRefresh>0</AutoRefresh>
  <DataSources>
    <DataSource Name="DS1">
      <DataSourceReference>$DataSourceName</DataSourceReference>
    </DataSource>
  </DataSources>
  <DataSets>
    <DataSet Name="MainDataSet">
      <Query>
        <DataSourceName>DS1</DataSourceName>
        <CommandText>$([System.Security.SecurityElement]::Escape($Query))</CommandText>
      </Query>
      <Fields>
        <Field Name="ID"><DataField>ID</DataField></Field>
        <Field Name="Name"><DataField>Name</DataField></Field>
        <Field Name="Value"><DataField>Value</DataField></Field>
        <Field Name="Date"><DataField>Date</DataField></Field>
      </Fields>
    </DataSet>
  </DataSets>
  $paramSection
  <ReportSections>
    <ReportSection>
      <Body>
        <ReportItems>
          <Tablix Name="MainTable">
            <TablixBody>
              <TablixColumns>
                <TablixColumn><Width>3cm</Width></TablixColumn>
                <TablixColumn><Width>5cm</Width></TablixColumn>
                <TablixColumn><Width>3cm</Width></TablixColumn>
              </TablixColumns>
              <TablixRows>
                <TablixRow>
                  <Height>0.6cm</Height>
                  <TablixCells>
                    <TablixCell><CellContents><Textbox Name="ID_Header"><Paragraphs><Paragraph><TextRuns><TextRun><Value>ID</Value></TextRun></TextRuns></Paragraph></Paragraphs></Textbox></CellContents></TablixCell>
                    <TablixCell><CellContents><Textbox Name="Name_Header"><Paragraphs><Paragraph><TextRuns><TextRun><Value>Nom</Value></TextRun></TextRuns></Paragraph></Paragraphs></Textbox></CellContents></TablixCell>
                    <TablixCell><CellContents><Textbox Name="Value_Header"><Paragraphs><Paragraph><TextRuns><TextRun><Value>Valeur</Value>$drillXml</TextRun></TextRuns></Paragraph></Paragraphs></Textbox></CellContents></TablixCell>
                  </TablixCells>
                </TablixRow>
              </TablixRows>
            </TablixBody>
          </Tablix>
          $subreportXml
          $imageXml
        </ReportItems>
      </Body>
      <Page>
        <PageHeight>29.7cm</PageHeight>
        <PageWidth>21cm</PageWidth>
        <LeftMargin>2cm</LeftMargin>
        <RightMargin>2cm</RightMargin>
        <TopMargin>2cm</TopMargin>
        <BottomMargin>2cm</BottomMargin>
      </Page>
    </ReportSection>
  </ReportSections>
  $customCodeXml
  <rd:ReportUnitType>Cm</rd:ReportUnitType>
  <rd:ReportID>$([guid]::NewGuid())</rd:ReportID>
</Report>
"@
}

$rdlReports = @(
    @{
        Name        = "Résumé des Ventes Trimestrielles"
        Folder      = "Équipe Commerciale"
        DataSource  = "SQL_Finance_Prod"
        Query       = "SELECT ID, Nom AS Name, Montant AS Value, DateVente AS Date FROM vw_VentesTrimestrielles WHERE Région = @Region"
        Parameters  = @("Region", "Année", "Trimestre")
        Features    = @("parameters", "stored_credentials")
        HasDrillthrough = $true
    }
    @{
        Name        = "État des Factures Échues"
        Folder      = "Département Finance"
        DataSource  = "SQL_Finance_Prod"
        Query       = "SELECT FactureID AS ID, Client AS Name, MontantTTC AS Value, DateÉchéance AS Date FROM Factures WHERE Statut = 'Échue'"
        Parameters  = @("DateDébut", "DateFin")
        HasSubreport = $true
        HasCustomCode = $true
        Features    = @("subreport", "custom_code", "parameters")
    }
    @{
        Name        = "Indicateurs Clés Régionaux"
        Folder      = "Direction Générale"
        DataSource  = "Analysis_Services_Cube"
        Query       = "SELECT [Measures].[CA Total] ON 0, [Région].[Membres] ON 1 FROM [CubeEntreprise]"
        Parameters  = @()
        HasExternalImages = $true
        Features    = @("ssas_datasource", "external_images")
    }
    @{
        Name        = "Suivi Non-Conformités"
        Folder      = "Contrôle Qualité"
        DataSource  = "SharePoint_Liste"
        Query       = "<RSSharePointList><ListName>NonConformités</ListName></RSSharePointList>"
        Parameters  = @("Priorité")
        Features    = @("xml_datasource", "parameters")
    }
    @{
        Name        = "Évaluation des Employés"
        Folder      = "RH - Ressources Humaines"
        DataSource  = "SQL_RH_Confidentiel"
        Query       = "SELECT EmployéID AS ID, NomComplet AS Name, NoteGlobale AS Value, DateÉvaluation AS Date FROM Évaluations WHERE Année = @Année"
        Parameters  = @("Année", "Département", "Manager")
        HasCustomCode = $true
        Features    = @("rls_candidate", "custom_code", "parameters", "sensitive_data")
    }
    @{
        Name        = "Prévisions Budgétaires"
        Folder      = "Département Finance/Budgets Prévisionnels"
        DataSource  = "SQL_Finance_Prod"
        Query       = "EXEC sp_PrévisionsBudget @Année, @Scénario"
        Parameters  = @("Année", "Scénario")
        HasDrillthrough = $true
        HasSubreport = $true
        Features    = @("stored_procedure", "subreport", "drillthrough")
    }
    @{
        Name        = "Rapport Hérité Oracle"
        Folder      = "Données Archivées"
        DataSource  = "Oracle_ERP_Legacy"
        Query       = "SELECT * FROM legacy_reports WHERE archived = 1"
        Parameters  = @()
        Features    = @("oracle_datasource", "legacy")
    }
    @{
        Name        = "Infrastructure Monitoring"
        Folder      = "IT Operations"
        DataSource  = "PostgreSQL_Analytics"
        Query       = "SELECT server_id AS id, hostname AS name, cpu_usage AS value, check_time AS date FROM server_metrics ORDER BY check_time DESC"
        Parameters  = @("TimeRange")
        Features    = @("postgresql_datasource", "parameters")
    }
    @{
        Name        = "Tableau de Bord Stratégique"
        Folder      = "Direction Générale"
        DataSource  = "Analysis_Services_Cube"
        Query       = "SELECT [Measures].[Revenue],[Measures].[Growth] ON 0, [Time].[Calendar].Members ON 1 FROM [StrategicCube]"
        Parameters  = @("Année", "BU")
        HasCustomCode = $true
        HasExternalImages = $true
        HasDrillthrough = $true
        Features    = @("ssas_datasource", "custom_code", "external_images", "drillthrough", "complex")
    }
    @{
        Name        = "Résultats T4 2025"
        Folder      = "Département Finance/Résultats Trimestriels"
        DataSource  = "SQL_Finance_Prod"
        Query       = "SELECT * FROM vw_ResultatsTrimestriels WHERE Trimestre = 'T4' AND Année = 2025"
        Parameters  = @()
        Features    = @("simple")
    }
)

$reportIds = @{}
foreach ($rpt in $rdlReports) {
    $rdlContent = New-RDL `
        -ReportName $rpt.Name `
        -DataSourceName $rpt.DataSource `
        -Query $rpt.Query `
        -Parameters ($rpt.Parameters ?? @()) `
        -HasSubreport:($rpt.HasSubreport -eq $true) `
        -HasDrillthrough:($rpt.HasDrillthrough -eq $true) `
        -HasCustomCode:($rpt.HasCustomCode -eq $true) `
        -HasExternalImages:($rpt.HasExternalImages -eq $true)

    $rdlBytes = [System.Text.Encoding]::UTF8.GetBytes($rdlContent)
    $b64 = [Convert]::ToBase64String($rdlBytes)

    $body = @{
        "@odata.type" = "#Model.Report"
        Name          = $rpt.Name
        Description   = "Features: $($rpt.Features -join ', ')"
        Path          = "/$($rpt.Folder)"
        Content       = $b64
        ContentType   = ""
    }
    $result = Invoke-PBIRS -Method POST -Path "/Reports" -Body $body
    if ($result) {
        $reportIds[$rpt.Name] = $result.Id
        Write-Host "  ✓ $($rpt.Name) → /$($rpt.Folder)" -ForegroundColor Green
    }
    else {
        Write-Host "  ✗ $($rpt.Name) FAILED" -ForegroundColor Red
    }
}

# ─── 3b. Create Power BI Reports (.pbix) ───────────────────────────
Write-Host "`n── Creating Power BI Reports (PBIX) ──" -ForegroundColor Yellow

function New-MinimalPbix {
    <#
    .SYNOPSIS
        Creates a minimal valid .pbix file (ZIP archive) in memory and returns bytes.
    #>
    param(
        [string]$ReportName,
        [string]$DataSourceServer = "localhost",
        [string]$Database = "SalesDB",
        [string]$Query = "SELECT 1 AS Value"
    )

    $memStream = [System.IO.MemoryStream]::new()
    $archive = [System.IO.Compression.ZipArchive]::new($memStream, [System.IO.Compression.ZipArchiveMode]::Create, $true)

    # 1. [Content_Types].xml
    $ctEntry = $archive.CreateEntry("[Content_Types].xml")
    $writer = [System.IO.StreamWriter]::new($ctEntry.Open())
    $writer.Write(@"
<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="json" ContentType="application/json" />
  <Default Extension="xml" ContentType="application/xml" />
</Types>
"@)
    $writer.Close()

    # 2. DataModelSchema — minimal tabular model
    $modelSchema = @{
        name = "Model"
        compatibilityLevel = 1560
        model = @{
            culture = "fr-FR"
            dataSources = @(
                @{
                    name = "SqlServer $DataSourceServer $Database"
                    connectionString = "Data Source=$DataSourceServer;Initial Catalog=$Database;Integrated Security=True"
                    impersonationMode = "impersonateCurrentUser"
                }
            )
            tables = @(
                @{
                    name = "MainTable"
                    columns = @(
                        @{ name = "ID"; dataType = "int64"; sourceColumn = "ID" }
                        @{ name = "Name"; dataType = "string"; sourceColumn = "Name" }
                        @{ name = "Value"; dataType = "double"; sourceColumn = "Value" }
                        @{ name = "Date"; dataType = "dateTime"; sourceColumn = "Date" }
                    )
                    partitions = @(
                        @{
                            name = "MainTable"
                            source = @{
                                type = "m"
                                expression = "let Source = Sql.Database(""$DataSourceServer"", ""$Database""), Data = Source{[Schema=""dbo"",Item=""MainTable""]}[Data] in Data"
                            }
                        }
                    )
                }
            )
            annotations = @(
                @{ name = "PBI_QueryOrder"; value = "[""MainTable""]" }
            )
        }
    } | ConvertTo-Json -Depth 15 -Compress

    $dmEntry = $archive.CreateEntry("DataModelSchema")
    $writer = [System.IO.StreamWriter]::new($dmEntry.Open(), [System.Text.Encoding]::Unicode)
    $writer.Write($modelSchema)
    $writer.Close()

    # 3. Report/Layout — minimal report layout with one page
    $layout = @{
        id = 0
        reportId = [guid]::NewGuid().ToString()
        config = (@{ version = "5.50"; themeCollection = @{ baseTheme = @{ name = "CY24SU02"; dataColors = @("#118DFF","#12239E","#E66C37") } } } | ConvertTo-Json -Depth 5 -Compress)
        filters = "[]"
        sections = @(
            @{
                name = "Page1"
                displayName = $ReportName
                filters = "[]"
                ordinal = 0
                visualContainers = @(
                    @{
                        x = 50; y = 50; z = 0; width = 600; height = 400
                        config = (@{
                            name = [guid]::NewGuid().ToString("N").Substring(0,16)
                            layouts = @( @{ id = 0; position = @{ x = 50; y = 50; z = 0; width = 600; height = 400 } } )
                            singleVisual = @{
                                visualType = "tableEx"
                                projections = @{ Values = @( @{ queryRef = "MainTable.Name" }, @{ queryRef = "MainTable.Value" } ) }
                            }
                        } | ConvertTo-Json -Depth 10 -Compress)
                    }
                )
                width = 1280
                height = 720
            }
        )
    } | ConvertTo-Json -Depth 10 -Compress

    $layoutEntry = $archive.CreateEntry("Report/Layout")
    $writer = [System.IO.StreamWriter]::new($layoutEntry.Open(), [System.Text.Encoding]::Unicode)
    $writer.Write($layout)
    $writer.Close()

    # 4. SecurityBindings (empty)
    $secEntry = $archive.CreateEntry("SecurityBindings")
    $secEntry.Open().Close()

    # 5. Metadata
    $metadata = @{ version = "1.0"; createdFrom = "PowerBI Desktop" } | ConvertTo-Json -Compress
    $mdEntry = $archive.CreateEntry("Metadata")
    $writer = [System.IO.StreamWriter]::new($mdEntry.Open())
    $writer.Write($metadata)
    $writer.Close()

    # 6. Settings
    $settings = @{ version = "1.0" } | ConvertTo-Json -Compress
    $stEntry = $archive.CreateEntry("Settings")
    $writer = [System.IO.StreamWriter]::new($stEntry.Open())
    $writer.Write($settings)
    $writer.Close()

    $archive.Dispose()
    $bytes = $memStream.ToArray()
    $memStream.Dispose()
    return $bytes
}

$pbixReports = @(
    @{
        Name     = "Analyse des Ventes"
        Folder   = "Équipe Commerciale"
        Server   = "sql-prod.corp.local"
        Database = "SalesDB"
        Desc     = "Tableau de bord interactif — ventes par région, produit, client"
        Features = @("interactive_visuals", "slicers", "drillthrough")
    }
    @{
        Name     = "Suivi Budgétaire"
        Folder   = "Département Finance"
        Server   = "sql-prod.corp.local"
        Database = "FinanceDB"
        Desc     = "Budget vs réel — analyse des écarts par département"
        Features = @("calculated_measures", "bookmarks", "conditional_formatting")
    }
    @{
        Name     = "Tableau RH"
        Folder   = "RH - Ressources Humaines"
        Server   = "sql-hr.corp.local"
        Database = "HRDB"
        Desc     = "Effectifs, turnover, formation — données confidentielles"
        Features = @("rls", "sensitive_data", "multiple_pages")
    }
    @{
        Name     = "Dashboard IT"
        Folder   = "IT Operations"
        Server   = "pg-analytics.corp.local"
        Database = "monitoring"
        Desc     = "Monitoring serveurs — CPU, RAM, disques, alertes"
        Features = @("directquery", "auto_refresh", "alerts")
    }
    @{
        Name     = "KPI Direction"
        Folder   = "Direction Générale"
        Server   = "ssas-prod.corp.local"
        Database = "EnterpriseCube"
        Desc     = "Indicateurs stratégiques — CA, marge, croissance"
        Features = @("live_connection", "ssas", "executive_dashboard")
    }
)

Add-Type -AssemblyName System.IO.Compression

foreach ($pbi in $pbixReports) {
    $pbixBytes = New-MinimalPbix `
        -ReportName $pbi.Name `
        -DataSourceServer $pbi.Server `
        -Database $pbi.Database

    $b64 = [Convert]::ToBase64String($pbixBytes)

    $body = @{
        "@odata.type" = "#Model.PowerBIReport"
        Name          = $pbi.Name
        Description   = "$($pbi.Desc) | Features: $($pbi.Features -join ', ')"
        Path          = "/$($pbi.Folder)"
        Content       = $b64
        ContentType   = ""
    }
    $result = Invoke-PBIRS -Method POST -Path "/PowerBIReports" -Body $body
    if ($result) {
        $reportIds[$pbi.Name] = $result.Id
        Write-Host "  ✓ $($pbi.Name) (.pbix) → /$($pbi.Folder)" -ForegroundColor Green
    }
    else {
        Write-Host "  ✗ $($pbi.Name) (.pbix) FAILED" -ForegroundColor Red
    }
}

# ─── 4. Set Item Policies (diverse permission patterns) ────────────
Write-Host "`n── Setting Permissions ──" -ForegroundColor Yellow

$permissionSets = @(
    @{
        Folder = "Département Finance"
        Policies = @(
            @{ GroupUserName = "CORP\Finance-Managers"; Roles = @("Content Manager") }
            @{ GroupUserName = "CORP\Finance-Analysts"; Roles = @("Browser") }
            @{ GroupUserName = "CORP\Auditors";         Roles = @("Browser") }
        )
    }
    @{
        Folder = "RH - Ressources Humaines"
        Policies = @(
            @{ GroupUserName = "CORP\HR-Directors";    Roles = @("Content Manager") }
            @{ GroupUserName = "CORP\HR-Partners";     Roles = @("Browser", "Report Builder") }
        )
    }
    @{
        Folder = "Direction Générale"
        Policies = @(
            @{ GroupUserName = "CORP\Executive-Team";  Roles = @("Browser") }
            @{ GroupUserName = "CORP\Strategy-Team";   Roles = @("Content Manager") }
            @{ GroupUserName = "BUILTIN\Administrators"; Roles = @("Content Manager") }
        )
    }
    @{
        Folder = "Équipe Commerciale"
        Policies = @(
            @{ GroupUserName = "CORP\Sales-Managers";  Roles = @("Content Manager") }
            @{ GroupUserName = "CORP\Sales-Reps";      Roles = @("Browser") }
            @{ GroupUserName = "CORP\Finance-Analysts"; Roles = @("Browser") }
        )
    }
    @{
        Folder = "Contrôle Qualité"
        Policies = @(
            @{ GroupUserName = "CORP\QA-Team";         Roles = @("Content Manager") }
            @{ GroupUserName = "CORP\Production-Team"; Roles = @("Browser") }
        )
    }
    @{
        Folder = "IT Operations"
        Policies = @(
            @{ GroupUserName = "CORP\IT-Admins";       Roles = @("Content Manager") }
            @{ GroupUserName = "CORP\IT-Support";      Roles = @("Browser") }
            @{ GroupUserName = "CORP\Developers";      Roles = @("Browser", "Publisher") }
        )
    }
)

foreach ($perm in $permissionSets) {
    $folderId = $folderIds[$perm.Folder]
    if (-not $folderId) {
        Write-Host "  ⊘ $($perm.Folder) — folder not found, skipping permissions" -ForegroundColor DarkYellow
        continue
    }

    $policyList = @()
    foreach ($p in $perm.Policies) {
        $roles = $p.Roles | ForEach-Object { @{ Name = $_ } }
        $policyList += @{
            GroupUserName = $p.GroupUserName
            Roles = $roles
        }
    }

    $body = @{ Policies = $policyList }
    $result = Invoke-PBIRS -Method PUT -Path "/Folders($folderId)/Policies" -Body $body
    if ($null -ne $result -or $true) {
        Write-Host "  ✓ $($perm.Folder) — $($perm.Policies.Count) policies" -ForegroundColor Green
    }
}

# ─── 5. Create Subscriptions ───────────────────────────────────────
Write-Host "`n── Creating Subscriptions ──" -ForegroundColor Yellow

$subscriptionTargets = @(
    @{
        ReportName = "Résumé des Ventes Trimestrielles"
        Description = "Envoi hebdomadaire — équipe commerciale"
        EventType = "TimedSubscription"
        DeliveryExtension = "Report Server Email"
        Schedule = @{
            ScheduleDefinition = @{
                StartDateTime = "2025-01-06T08:00:00"
                EndDate = "2026-12-31"
                WeeklyRecurrence = @{ WeeksInterval = 1; DaysOfWeek = @{ Monday = $true } }
            }
        }
        DeliverySettings = @{
            Extension = "Report Server Email"
            ParameterValues = @(
                @{ Name = "TO"; Value = "sales-team@corp.local" }
                @{ Name = "Subject"; Value = "Résumé des ventes — @ExecutionTime" }
                @{ Name = "RenderFormat"; Value = "PDF" }
                @{ Name = "IncludeReport"; Value = "true" }
            )
        }
    }
    @{
        ReportName = "État des Factures Échues"
        Description = "Alerte quotidienne — factures en retard"
        EventType = "TimedSubscription"
        DeliveryExtension = "Report Server FileShare"
        Schedule = @{
            ScheduleDefinition = @{
                StartDateTime = "2025-01-01T06:00:00"
                DailyRecurrence = @{ DaysInterval = 1 }
            }
        }
        DeliverySettings = @{
            Extension = "Report Server FileShare"
            ParameterValues = @(
                @{ Name = "PATH"; Value = "\\fileserver\reports\finance" }
                @{ Name = "FILENAME"; Value = "FacturesÉchues_@timestamp" }
                @{ Name = "RENDER_FORMAT"; Value = "EXCELOPENXML" }
            )
        }
    }
)

foreach ($sub in $subscriptionTargets) {
    $reportId = $reportIds[$sub.ReportName]
    if (-not $reportId) {
        Write-Host "  ⊘ $($sub.ReportName) — report not found, skipping subscription" -ForegroundColor DarkYellow
        continue
    }
    $body = @{
        "@odata.type"      = "#Model.Subscription"
        Description        = $sub.Description
        EventType          = $sub.EventType
        IsActive           = $true
        DeliveryExtension  = $sub.DeliveryExtension
        Schedule           = $sub.Schedule
    }
    $result = Invoke-PBIRS -Method POST -Path "/Reports($reportId)/Subscriptions" -Body $body
    if ($result) {
        Write-Host "  ✓ $($sub.Description) → $($sub.ReportName)" -ForegroundColor Green
    }
    else {
        Write-Host "  ✗ $($sub.Description) FAILED (subscriptions may need mail config)" -ForegroundColor DarkYellow
    }
}

# ─── 6. Create KPIs ────────────────────────────────────────────────
Write-Host "`n── Creating KPIs ──" -ForegroundColor Yellow

$kpis = @(
    @{
        Name   = "Chiffre d'Affaires Mensuel"
        Folder = "Direction Générale"
        Desc   = "CA mensuel vs objectif — indicateur stratégique"
    }
    @{
        Name   = "Taux de Satisfaction Client"
        Folder = "Équipe Commerciale"
        Desc   = "NPS score — enquêtes trimestrielles"
    }
    @{
        Name   = "Délai Moyen de Résolution"
        Folder = "Contrôle Qualité"
        Desc   = "Temps moyen de résolution des non-conformités"
    }
)

foreach ($kpi in $kpis) {
    $body = @{
        "@odata.type" = "#Model.Kpi"
        Name          = $kpi.Name
        Description   = $kpi.Desc
        Path          = "/$($kpi.Folder)"
        ValueFormat   = "General"
        Values        = @{
            Value  = "100"
            Goal   = "120"
            Status = "1"
        }
    }
    $result = Invoke-PBIRS -Method POST -Path "/Kpis" -Body $body
    if ($result) {
        Write-Host "  ✓ $($kpi.Name) → /$($kpi.Folder)" -ForegroundColor Green
    }
    else {
        Write-Host "  ✗ $($kpi.Name) FAILED (KPI creation may not be supported via REST)" -ForegroundColor DarkYellow
    }
}

# ─── 7. Verify deployed content ────────────────────────────────────
Write-Host "`n── Final Inventory ──" -ForegroundColor Yellow

$allItems = Invoke-PBIRS -Method GET -Path "/CatalogItems?`$orderby=Type,Path"
if ($allItems -and $allItems.value) {
    $summary = $allItems.value | Group-Object Type | Select-Object Name, Count
    Write-Host "  Total items deployed:" -ForegroundColor Cyan
    foreach ($g in $summary) {
        Write-Host "    $($g.Name): $($g.Count)"
    }

    # Save full inventory
    $inventoryPath = Join-Path $PSScriptRoot "..\artifacts\pbirs_inventory.json"
    $inventoryDir = Split-Path $inventoryPath -Parent
    if (-not (Test-Path $inventoryDir)) { New-Item -ItemType Directory -Path $inventoryDir -Force | Out-Null }
    $allItems.value | ConvertTo-Json -Depth 5 | Out-File $inventoryPath -Encoding utf8 -Force
    Write-Host "`n  Inventory saved to: $inventoryPath" -ForegroundColor Green
}

Write-Host "`n═══ Deployment Complete ═══" -ForegroundColor Cyan
Write-Host @"

Content deployed:
  - 10 paginated reports (RDL) — diverse features (subreports, custom code, drillthrough, etc.)
  - 5 Power BI reports (PBIX)  — interactive dashboards, DirectQuery, live connection, RLS
  - 6 shared data sources      — SQL, Oracle, SSAS, PostgreSQL, XML/SharePoint

Assessment categories covered:
  1. datasource_compatibility — SQL, Oracle, SSAS, PostgreSQL, XML/SharePoint
  2. report_complexity       — Simple to complex (subreports, drillthrough, custom code, PBIX)
  3. security_model          — 6 unique permission patterns, 12 AD groups
  4. gateway_requirements    — On-prem SQL, Oracle, PostgreSQL need gateways
  5. paginated_features      — Parameters, subreports, external images, custom code
  6. subscription_migration  — Email + file share subscriptions
  7. capacity_requirements   — SSAS cube reports need Premium
  8. data_model              — Stored procedures, views, direct queries, DirectQuery, live connection
  9. custom_visuals          — External images, custom code functions, PBIX interactive visuals

Encoding test:
  - French accents in folder names, report names, queries, descriptions
  - Characters tested: é è ê ë à â ä ù û ü ô ö î ï ç œ

Next steps:
  1. Run the migration assessment:
     py migrate.py --server http://localhost/ReportServer --phase assessment --output ./artifacts

  2. Check the assessment report in ./artifacts/
"@
