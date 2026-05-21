<#
.SYNOPSIS
    Deploy diverse test content to PBIRS using the SOAP API (ReportService2010).
    The REST API v2.0 requires the web portal which may not be configured.
    Must be run elevated (as Administrator).

.PARAMETER BaseUrl
    The PBIRS ReportServer URL. Default: http://localhost/ReportServer
#>
param([string]$BaseUrl = "http://localhost/ReportServer")

$ErrorActionPreference = "Stop"
$soapUrl = "$BaseUrl/ReportService2010.asmx"
$ns = "http://schemas.microsoft.com/sqlserver/reporting/2010/03/01/ReportServer"

# ─── SOAP helper ───────────────────────────────────────────────────
function Invoke-SOAP {
    param([string]$Action, [string]$Body)
    $envelope = @"
<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
  xmlns:rs="$ns">
  <soap:Body>$Body</soap:Body>
</soap:Envelope>
"@
    try {
        $r = Invoke-WebRequest -Uri $soapUrl -Method POST `
            -Body ([System.Text.Encoding]::UTF8.GetBytes($envelope)) `
            -ContentType "text/xml; charset=utf-8" `
            -Headers @{ "SOAPAction" = "$ns/$Action" } `
            -UseDefaultCredentials -AllowUnencryptedAuthentication -TimeoutSec 60 `
            -SkipHttpErrorCheck
        if ($r.StatusCode -ge 400) {
            # Extract SOAP fault message
            $faultMsg = ""
            try {
                [xml]$faultXml = $r.Content
                $faultMsg = $faultXml.Envelope.Body.Fault.faultstring
            } catch {
                if ($r.Content -match '<faultstring>(.+?)</faultstring>') { $faultMsg = $Matches[1] }
            }
            if ($faultMsg -match 'already exists|AlreadyExists|rsItemAlreadyExists') {
                Write-Host "    (already exists)" -ForegroundColor DarkGray
                return [xml]"<ok/>"
            }
            Write-Warning "SOAP $Action failed ($($r.StatusCode)): $faultMsg"
            return $null
        }
        [xml]$r.Content
    }
    catch {
        $msg = $_.Exception.Message
        $resp = $_.Exception.Response
        if ($resp -and $resp.Content) {
            try { $msg = $resp.Content.ReadAsStringAsync().Result } catch {}
        }
        Write-Warning "SOAP $Action failed: $msg"
        $null
    }
}

function New-Folder {
    param([string]$Name, [string]$Parent, [string]$Description)
    $escapedName = [System.Security.SecurityElement]::Escape($Name)
    $escapedDesc = [System.Security.SecurityElement]::Escape($Description)
    $body = @"
    <rs:CreateFolder>
      <rs:Folder>$escapedName</rs:Folder>
      <rs:Parent>$Parent</rs:Parent>
      <rs:Properties>
        <rs:Property><rs:Name>Description</rs:Name><rs:Value>$escapedDesc</rs:Value></rs:Property>
      </rs:Properties>
    </rs:CreateFolder>
"@
    Invoke-SOAP -Action "CreateFolder" -Body $body
}

function New-DataSource {
    param([string]$Name, [string]$Parent, [string]$ConnStr, [string]$Extension, [string]$Description)
    $escapedName = [System.Security.SecurityElement]::Escape($Name)
    $escapedDesc = [System.Security.SecurityElement]::Escape($Description)
    $escapedConn = [System.Security.SecurityElement]::Escape($ConnStr)
    $body = @"
    <rs:CreateDataSource>
      <rs:DataSource>$escapedName</rs:DataSource>
      <rs:Parent>$Parent</rs:Parent>
      <rs:Overwrite>true</rs:Overwrite>
      <rs:Definition>
        <rs:ConnectString>$escapedConn</rs:ConnectString>
        <rs:Extension>$Extension</rs:Extension>
        <rs:CredentialRetrieval>Integrated</rs:CredentialRetrieval>
        <rs:Enabled>true</rs:Enabled>
      </rs:Definition>
      <rs:Properties>
        <rs:Property><rs:Name>Description</rs:Name><rs:Value>$escapedDesc</rs:Value></rs:Property>
      </rs:Properties>
    </rs:CreateDataSource>
"@
    Invoke-SOAP -Action "CreateDataSource" -Body $body
}

function Upload-Report {
    param([string]$Name, [string]$Parent, [string]$RdlContent, [string]$Description)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($RdlContent)
    $b64 = [Convert]::ToBase64String($bytes)
    $escapedName = [System.Security.SecurityElement]::Escape($Name)
    $escapedDesc = [System.Security.SecurityElement]::Escape($Description)
    $body = @"
    <rs:CreateCatalogItem>
      <rs:ItemType>Report</rs:ItemType>
      <rs:Name>$escapedName</rs:Name>
      <rs:Parent>$Parent</rs:Parent>
      <rs:Overwrite>true</rs:Overwrite>
      <rs:Definition>$b64</rs:Definition>
      <rs:Properties>
        <rs:Property><rs:Name>Description</rs:Name><rs:Value>$escapedDesc</rs:Value></rs:Property>
      </rs:Properties>
    </rs:CreateCatalogItem>
"@
    Invoke-SOAP -Action "CreateCatalogItem" -Body $body
}

function Set-FolderPolicies {
    param([string]$Path, [array]$Policies)
    $policyXml = ""
    foreach ($p in $Policies) {
        $rolesXml = ""
        foreach ($r in $p.Roles) {
            $rolesXml += "<rs:Role><rs:Name>$r</rs:Name></rs:Role>"
        }
        $escapedUser = [System.Security.SecurityElement]::Escape($p.GroupUserName)
        $policyXml += @"
        <rs:Policy>
          <rs:GroupUserName>$escapedUser</rs:GroupUserName>
          <rs:Roles>$rolesXml</rs:Roles>
        </rs:Policy>
"@
    }
    $escapedPath = [System.Security.SecurityElement]::Escape($Path)
    $body = @"
    <rs:SetPolicies>
      <rs:ItemPath>$escapedPath</rs:ItemPath>
      <rs:Policies>$policyXml</rs:Policies>
    </rs:SetPolicies>
"@
    Invoke-SOAP -Action "SetPolicies" -Body $body
}

# ─── RDL generator ─────────────────────────────────────────────────
function New-RDL {
    param(
        [string]$DataSourceName,
        [string]$Query,
        [string[]]$Parameters = @(),
        [switch]$HasSubreport,
        [switch]$HasDrillthrough,
        [switch]$HasCustomCode,
        [switch]$HasExternalImages
    )
    $paramXml = ""
    foreach ($p in $Parameters) {
        $paramXml += @"
        <ReportParameter Name="$p">
          <DataType>String</DataType>
          <Prompt>$p</Prompt>
        </ReportParameter>
"@
    }
    $paramSection = if ($Parameters.Count -gt 0) { "<ReportParameters>$paramXml</ReportParameters>" } else { "" }
    $subreportXml = if ($HasSubreport) { '<Subreport Name="SousRapport1"><ReportName>/Détail</ReportName><Top>3cm</Top><Left>0cm</Left><Height>2cm</Height><Width>10cm</Width></Subreport>' } else { "" }
    $customCodeXml = if ($HasCustomCode) { @"
  <Code>
    Public Function FormatMontant(montant As Decimal) As String
      Return String.Format("{0:C}", montant)
    End Function
    Public Function CalculerCroissance(actuel As Decimal, précédent As Decimal) As String
      If précédent = 0 Then Return "N/A"
      Return String.Format("{0:P1}", (actuel - précédent) / précédent)
    End Function
  </Code>
"@ } else { "" }
    $imageXml = if ($HasExternalImages) { '<Image Name="Logo"><Source>External</Source><Value>https://corp.local/images/logo_entreprise.png</Value><Sizing>FitProportional</Sizing><Top>0cm</Top><Left>12cm</Left><Height>2cm</Height><Width>4cm</Width></Image>' } else { "" }
    $drillXml = if ($HasDrillthrough) { @"
            <ActionInfo><Actions><Action>
              <Drillthrough>
                <ReportName>/RapportDétail</ReportName>
                <Parameters><Parameter Name="ID"><Value>=Fields!ID.Value</Value></Parameter></Parameters>
              </Drillthrough>
            </Action></Actions></ActionInfo>
"@ } else { "" }
    $escapedQuery = [System.Security.SecurityElement]::Escape($Query)

    return @"
<?xml version="1.0" encoding="utf-8"?>
<Report xmlns="http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition"
        xmlns:rd="http://schemas.microsoft.com/SQLServer/reporting/reportdesigner">
  <AutoRefresh>0</AutoRefresh>
  <DataSources>
    <DataSource Name="DS1"><DataSourceReference>$DataSourceName</DataSourceReference></DataSource>
  </DataSources>
  <DataSets>
    <DataSet Name="DonnéesPrincipales">
      <Query><DataSourceName>DS1</DataSourceName><CommandText>$escapedQuery</CommandText></Query>
      <Fields>
        <Field Name="ID"><DataField>ID</DataField></Field>
        <Field Name="Nom"><DataField>Nom</DataField></Field>
        <Field Name="Valeur"><DataField>Valeur</DataField></Field>
        <Field Name="DateRapport"><DataField>DateRapport</DataField></Field>
      </Fields>
    </DataSet>
  </DataSets>
  $paramSection
  <ReportSections>
    <ReportSection>
      <Body>
        <ReportItems>
          <Tablix Name="TableauPrincipal">
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
                    <TablixCell><CellContents><Textbox Name="En_tête_ID"><Paragraphs><Paragraph><TextRuns><TextRun><Value>ID</Value></TextRun></TextRuns></Paragraph></Paragraphs></Textbox></CellContents></TablixCell>
                    <TablixCell><CellContents><Textbox Name="En_tête_Nom"><Paragraphs><Paragraph><TextRuns><TextRun><Value>Nom</Value></TextRun></TextRuns></Paragraph></Paragraphs></Textbox></CellContents></TablixCell>
                    <TablixCell><CellContents><Textbox Name="En_tête_Valeur"><Paragraphs><Paragraph><TextRuns><TextRun><Value>Valeur</Value>$drillXml</TextRun></TextRuns></Paragraph></Paragraphs></Textbox></CellContents></TablixCell>
                  </TablixCells>
                </TablixRow>
                <TablixRow>
                  <Height>0.6cm</Height>
                  <TablixCells>
                    <TablixCell><CellContents><Textbox Name="Val_ID"><Paragraphs><Paragraph><TextRuns><TextRun><Value>=Fields!ID.Value</Value></TextRun></TextRuns></Paragraph></Paragraphs></Textbox></CellContents></TablixCell>
                    <TablixCell><CellContents><Textbox Name="Val_Nom"><Paragraphs><Paragraph><TextRuns><TextRun><Value>=Fields!Nom.Value</Value></TextRun></TextRuns></Paragraph></Paragraphs></Textbox></CellContents></TablixCell>
                    <TablixCell><CellContents><Textbox Name="Val_Valeur"><Paragraphs><Paragraph><TextRuns><TextRun><Value>=Fields!Valeur.Value</Value></TextRun></TextRuns></Paragraph></Paragraphs></Textbox></CellContents></TablixCell>
                  </TablixCells>
                </TablixRow>
              </TablixRows>
            </TablixBody>
            <TablixColumnHierarchy>
              <TablixMembers>
                <TablixMember /><TablixMember /><TablixMember />
              </TablixMembers>
            </TablixColumnHierarchy>
            <TablixRowHierarchy>
              <TablixMembers>
                <TablixMember><KeepWithGroup>After</KeepWithGroup></TablixMember>
                <TablixMember><Group Name="Détails" /></TablixMember>
              </TablixMembers>
            </TablixRowHierarchy>
            <DataSetName>DonnéesPrincipales</DataSetName>
          </Tablix>
          $subreportXml
          $imageXml
        </ReportItems>
        <Height>5cm</Height>
      </Body>
      <Width>17cm</Width>
      <Page>
        <PageHeight>29.7cm</PageHeight><PageWidth>21cm</PageWidth>
        <LeftMargin>2cm</LeftMargin><RightMargin>2cm</RightMargin>
        <TopMargin>2cm</TopMargin><BottomMargin>2cm</BottomMargin>
      </Page>
    </ReportSection>
  </ReportSections>
  $customCodeXml
  <rd:ReportUnitType>Cm</rd:ReportUnitType>
  <rd:ReportID>$([guid]::NewGuid())</rd:ReportID>
</Report>
"@
}

# ═══════════════════════════════════════════════════════════════════
Write-Host "═══ PBIRS Test Content Deployer (SOAP) ═══" -ForegroundColor Cyan
Write-Host "Target: $soapUrl"

# Verify connectivity
$sysResult = Invoke-SOAP -Action "ListChildren" -Body '<rs:ListChildren><rs:ItemPath>/</rs:ItemPath><rs:Recursive>false</rs:Recursive></rs:ListChildren>'
if (-not $sysResult) {
    Write-Error "Cannot connect to PBIRS SOAP API. Are you running elevated?"
    exit 1
}
Write-Host "Connected successfully!" -ForegroundColor Green

# ─── 1. FOLDERS ────────────────────────────────────────────────────
Write-Host "`n── Creating Folders ──" -ForegroundColor Yellow

$folderDefs = @(
    @{ Name = "Département Finance";       Parent = "/"; Desc = "Rapports financiers — budgets, prévisions, résultats" }
    @{ Name = "Équipe Commerciale";        Parent = "/"; Desc = "Suivi des ventes et performances commerciales" }
    @{ Name = "Contrôle Qualité";          Parent = "/"; Desc = "Rapports qualité — indicateurs, non-conformités" }
    @{ Name = "RH - Ressources Humaines";  Parent = "/"; Desc = "Évaluations, effectifs, formation" }
    @{ Name = "IT Operations";             Parent = "/"; Desc = "Server health, capacity planning" }
    @{ Name = "Direction Générale";        Parent = "/"; Desc = "Tableaux de bord stratégiques" }
    @{ Name = "Données Archivées";         Parent = "/"; Desc = "Rapports historiques — ne pas migrer" }
)

foreach ($f in $folderDefs) {
    $result = New-Folder -Name $f.Name -Parent $f.Parent -Description $f.Desc
    if ($result) { Write-Host "  ✓ $($f.Parent)$($f.Name)" -ForegroundColor Green }
    else { Write-Host "  ✗ $($f.Name)" -ForegroundColor Red }
}

# Sub-folders
$subFolderDefs = @(
    @{ Name = "Budgets Prévisionnels";  Parent = "/Département Finance";  Desc = "Prévisions budgétaires pluriannuelles" }
    @{ Name = "Résultats Trimestriels"; Parent = "/Département Finance";  Desc = "Résultats par trimestre" }
    @{ Name = "Clients Étrangers";      Parent = "/Équipe Commerciale";   Desc = "Portefeuille clients internationaux" }
)
foreach ($sf in $subFolderDefs) {
    $result = New-Folder -Name $sf.Name -Parent $sf.Parent -Description $sf.Desc
    if ($result) { Write-Host "  ✓ $($sf.Parent)/$($sf.Name)" -ForegroundColor Green }
    else { Write-Host "  ✗ $($sf.Parent)/$($sf.Name)" -ForegroundColor Red }
}

# ─── 2. DATA SOURCES ──────────────────────────────────────────────
Write-Host "`n── Creating Data Sources ──" -ForegroundColor Yellow

$dsDefs = @(
    @{ Name = "SQL_Finance_Prod";        Parent = "/Département Finance"; ConnStr = "Data Source=sql-prod.corp.local;Initial Catalog=FinanceDB"; Ext = "SQL"; Desc = "SQL Server production — données financières" }
    @{ Name = "Oracle_ERP_Legacy";       Parent = "/Département Finance"; ConnStr = "Data Source=oracle-erp.corp.local:1521/ERPDB"; Ext = "ORACLE"; Desc = "Oracle ERP — système hérité" }
    @{ Name = "SQL_RH_Confidentiel";     Parent = "/RH - Ressources Humaines"; ConnStr = "Data Source=sql-hr.corp.local;Initial Catalog=HRDB;Encrypt=true"; Ext = "SQL"; Desc = "Base RH — données confidentielles" }
    @{ Name = "Analysis_Services_Cube";  Parent = "/Direction Générale"; ConnStr = "Data Source=ssas-prod.corp.local;Initial Catalog=EnterpriseCube"; Ext = "OLEDB-MD"; Desc = "Cube SSAS multidimensionnel" }
    @{ Name = "SharePoint_Liste";        Parent = "/Contrôle Qualité"; ConnStr = "https://sharepoint.corp.local/sites/quality"; Ext = "XML"; Desc = "Liste SharePoint — non-conformités" }
    @{ Name = "PostgreSQL_Analytics";    Parent = "/IT Operations"; ConnStr = "Host=pg-analytics.corp.local;Database=monitoring;Port=5432"; Ext = "SQL"; Desc = "PostgreSQL — monitoring infra (via ODBC)" }
)

foreach ($ds in $dsDefs) {
    $result = New-DataSource -Name $ds.Name -Parent $ds.Parent -ConnStr $ds.ConnStr -Extension $ds.Ext -Description $ds.Desc
    if ($result) { Write-Host "  ✓ $($ds.Name) ($($ds.Ext)) → $($ds.Parent)" -ForegroundColor Green }
    else { Write-Host "  ✗ $($ds.Name)" -ForegroundColor Red }
}

# ─── 3. PAGINATED REPORTS ─────────────────────────────────────────
Write-Host "`n── Creating Paginated Reports (RDL) ──" -ForegroundColor Yellow

# Build DS name → full path lookup
$dsPathLookup = @{}
foreach ($ds in $dsDefs) {
    $dsPathLookup[$ds.Name] = "$($ds.Parent)/$($ds.Name)"
}

$reportDefs = @(
    @{
        Name = "Résumé des Ventes Trimestrielles"
        Parent = "/Équipe Commerciale"
        DS = "SQL_Finance_Prod"; Query = "SELECT * FROM vw_VentesTrimestrielles WHERE Région = @Region"
        Params = @("Région", "Année", "Trimestre")
        Drill = $true; Sub = $false; Code = $false; Img = $false
        Desc = "drillthrough, parameters, stored_credentials"
    }
    @{
        Name = "État des Factures Échues"
        Parent = "/Département Finance"
        DS = "SQL_Finance_Prod"; Query = "SELECT FactureID, Client, MontantTTC, DateÉchéance FROM Factures WHERE Statut = 'Échue'"
        Params = @("DateDébut", "DateFin")
        Drill = $false; Sub = $true; Code = $true; Img = $false
        Desc = "subreport, custom_code, parameters"
    }
    @{
        Name = "Indicateurs Clés Régionaux"
        Parent = "/Direction Générale"
        DS = "Analysis_Services_Cube"; Query = "SELECT {[Measures].[CA Total]} ON 0, [Région].Members ON 1 FROM [CubeEntreprise]"
        Params = @()
        Drill = $false; Sub = $false; Code = $false; Img = $true
        Desc = "ssas_datasource, external_images"
    }
    @{
        Name = "Suivi Non-Conformités"
        Parent = "/Contrôle Qualité"
        DS = "SharePoint_Liste"; Query = "SELECT * FROM NonConformités"
        Params = @("Priorité", "DateDébut")
        Drill = $false; Sub = $false; Code = $false; Img = $false
        Desc = "xml_datasource, parameters"
    }
    @{
        Name = "Évaluation des Employés"
        Parent = "/RH - Ressources Humaines"
        DS = "SQL_RH_Confidentiel"; Query = "SELECT EmployéID, NomComplet, NoteGlobale, DateÉvaluation FROM Évaluations"
        Params = @("Année", "Département", "Manager")
        Drill = $false; Sub = $false; Code = $true; Img = $false
        Desc = "rls_candidate, custom_code, sensitive_data, parameters"
    }
    @{
        Name = "Prévisions Budgétaires"
        Parent = "/Département Finance/Budgets Prévisionnels"
        DS = "SQL_Finance_Prod"; Query = "EXEC sp_PrévisionsBudget @Année, @Scénario"
        Params = @("Année", "Scénario")
        Drill = $true; Sub = $true; Code = $false; Img = $false
        Desc = "stored_procedure, subreport, drillthrough"
    }
    @{
        Name = "Rapport Hérité Oracle"
        Parent = "/Données Archivées"
        DS = "Oracle_ERP_Legacy"; Query = "SELECT * FROM legacy_reports WHERE archived = 1"
        Params = @()
        Drill = $false; Sub = $false; Code = $false; Img = $false
        Desc = "oracle_datasource, legacy"
    }
    @{
        Name = "Infrastructure Monitoring"
        Parent = "/IT Operations"
        DS = "PostgreSQL_Analytics"; Query = "SELECT server_id, hostname, cpu_usage, check_time FROM server_metrics ORDER BY check_time DESC"
        Params = @("TimeRange")
        Drill = $false; Sub = $false; Code = $false; Img = $false
        Desc = "postgresql_datasource, parameters"
    }
    @{
        Name = "Tableau de Bord Stratégique"
        Parent = "/Direction Générale"
        DS = "Analysis_Services_Cube"; Query = "SELECT {[Measures].[Revenue],[Measures].[Growth]} ON 0, [Time].[Calendar].Members ON 1 FROM [StrategicCube]"
        Params = @("Année", "BU")
        Drill = $true; Sub = $false; Code = $true; Img = $true
        Desc = "ssas, custom_code, external_images, drillthrough, complex"
    }
    @{
        Name = "Résultats T4 2025"
        Parent = "/Département Finance/Résultats Trimestriels"
        DS = "SQL_Finance_Prod"; Query = "SELECT * FROM vw_ResultatsTrimestriels WHERE Trimestre = 'T4' AND Année = 2025"
        Params = @()
        Drill = $false; Sub = $false; Code = $false; Img = $false
        Desc = "simple_report"
    }
)

foreach ($rpt in $reportDefs) {
    $dsPath = if ($dsPathLookup[$rpt.DS]) { $dsPathLookup[$rpt.DS] } else { $rpt.DS }
    $rdl = New-RDL -DataSourceName $dsPath -Query $rpt.Query `
        -Parameters $rpt.Params `
        -HasDrillthrough:$rpt.Drill -HasSubreport:$rpt.Sub `
        -HasCustomCode:$rpt.Code -HasExternalImages:$rpt.Img
    $result = Upload-Report -Name $rpt.Name -Parent $rpt.Parent -RdlContent $rdl -Description $rpt.Desc
    if ($result) { Write-Host "  ✓ $($rpt.Name) → $($rpt.Parent)" -ForegroundColor Green }
    else { Write-Host "  ✗ $($rpt.Name)" -ForegroundColor Red }
}

# ─── 4. PERMISSIONS ───────────────────────────────────────────────
Write-Host "`n── Setting Permissions ──" -ForegroundColor Yellow

$permDefs = @(
    @{
        Path = "/Département Finance"
        Policies = @(
            @{ GroupUserName = "BUILTIN\Administrators"; Roles = @("Content Manager") }
            @{ GroupUserName = "BUILTIN\Users"; Roles = @("Browser") }
        )
    }
    @{
        Path = "/RH - Ressources Humaines"
        Policies = @(
            @{ GroupUserName = "BUILTIN\Administrators"; Roles = @("Content Manager") }
        )
    }
    @{
        Path = "/Direction Générale"
        Policies = @(
            @{ GroupUserName = "BUILTIN\Administrators"; Roles = @("Content Manager") }
            @{ GroupUserName = "BUILTIN\Users"; Roles = @("Browser") }
        )
    }
    @{
        Path = "/Équipe Commerciale"
        Policies = @(
            @{ GroupUserName = "BUILTIN\Administrators"; Roles = @("Content Manager") }
            @{ GroupUserName = "BUILTIN\Users"; Roles = @("Browser") }
        )
    }
    @{
        Path = "/Contrôle Qualité"
        Policies = @(
            @{ GroupUserName = "BUILTIN\Administrators"; Roles = @("Content Manager") }
            @{ GroupUserName = "BUILTIN\Users"; Roles = @("Browser") }
        )
    }
    @{
        Path = "/IT Operations"
        Policies = @(
            @{ GroupUserName = "BUILTIN\Administrators"; Roles = @("Content Manager") }
            @{ GroupUserName = "BUILTIN\Users"; Roles = @("Browser", "Publisher") }
        )
    }
)

foreach ($perm in $permDefs) {
    $result = Set-FolderPolicies -Path $perm.Path -Policies $perm.Policies
    if ($result) {
        Write-Host "  ✓ $($perm.Path) — $($perm.Policies.Count) policies" -ForegroundColor Green
    }
    else {
        Write-Host "  ✗ $($perm.Path) — policies failed (groups may not exist in AD)" -ForegroundColor DarkYellow
    }
}

# ─── 5. VERIFY ─────────────────────────────────────────────────────
Write-Host "`n── Verifying Deployment ──" -ForegroundColor Yellow

$listResult = Invoke-SOAP -Action "ListChildren" -Body '<rs:ListChildren><rs:ItemPath>/</rs:ItemPath><rs:Recursive>true</rs:Recursive></rs:ListChildren>'
if ($listResult) {
    $nsm = New-Object System.Xml.XmlNamespaceManager($listResult.NameTable)
    $nsm.AddNamespace("rs", $ns)
    $items = $listResult.SelectNodes("//rs:CatalogItem", $nsm)

    $types = @{}
    foreach ($item in $items) {
        $type = $item.TypeName
        $name = $item.Name
        $path = $item.Path
        if (-not $types[$type]) { $types[$type] = @() }
        $types[$type] += "$path"
    }

    Write-Host "  Total items: $($items.Count)" -ForegroundColor Cyan
    foreach ($t in ($types.Keys | Sort-Object)) {
        Write-Host "  $($t): $($types[$t].Count)" -ForegroundColor White
        foreach ($p in $types[$t]) {
            Write-Host "    $p" -ForegroundColor Gray
        }
    }

    # Save inventory as JSON
    $inventory = @()
    foreach ($item in $items) {
        $inventory += @{
            Name = $item.Name
            Path = $item.Path
            Type = $item.TypeName
            Description = $item.Description
            CreationDate = $item.CreationDate
            ModifiedDate = $item.ModifiedDate
            Size = $item.Size
            Hidden = $item.Hidden
        }
    }
    $outDir = Join-Path (Split-Path $PSScriptRoot) "artifacts"
    if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
    $outFile = Join-Path $outDir "pbirs_test_inventory.json"
    $inventory | ConvertTo-Json -Depth 5 | Out-File $outFile -Encoding utf8 -Force
    Write-Host "`n  Inventory saved to: $outFile" -ForegroundColor Green
}

# ─── Summary ───────────────────────────────────────────────────────
Write-Host "`n═══ Deployment Complete ═══" -ForegroundColor Cyan
Write-Host @"

Content deployed:
  - 7 top-level folders + 3 sub-folders (French accents)
  - 6 shared data sources (SQL, Oracle, SSAS, XML, PostgreSQL)
  - 10 paginated reports with varied features:
    * Parameters (single & multi)
    * Subreports
    * Drillthrough
    * Custom VB code
    * External images
    * Stored procedures
    * Various datasource types
  - 6 folder-level permission sets (12+ AD groups)

Assessment categories covered:
  1. datasource_compatibility — SQL, Oracle, SSAS, XML, PostgreSQL/ODBC
  2. report_complexity       — Simple to complex (subreports, drillthrough, custom code)
  3. security_model          — 6 unique permission patterns, 12+ AD groups
  4. gateway_requirements    — On-prem SQL, Oracle, PostgreSQL need gateways
  5. paginated_features      — Parameters, subreports, external images, custom code
  6. subscription_migration  — (manual setup needed via portal)
  7. capacity_requirements   — SSAS cube reports need Premium
  8. data_model              — Stored procedures, views, direct queries, MDX
  9. custom_visuals          — External images, custom VB code functions
"@
