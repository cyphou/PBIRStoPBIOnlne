<#
.SYNOPSIS
    Set permissions on PBIRS folders and verify full inventory.
    Run elevated (as Administrator).
#>
param([string]$BaseUrl = "http://localhost/ReportServer")

$ErrorActionPreference = "Continue"
$apiUrl = "$BaseUrl/api/v2.0"

function Invoke-PBIRS {
    param([string]$Method, [string]$Path, [object]$Body)
    $uri = "$apiUrl$Path"
    $params = @{
        Uri = $uri; Method = $Method
        UseDefaultCredentials = $true; AllowUnencryptedAuthentication = $true
        Headers = @{ "Accept" = "application/json" }; TimeoutSec = 60
    }
    if ($Body) {
        $params.Body = [System.Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json -Depth 10))
        $params.ContentType = "application/json; charset=utf-8"
    }
    try { Invoke-RestMethod @params } catch {
        Write-Warning "  $Method $Path → $($_.Exception.Response.StatusCode.value__)"
        $null
    }
}

Write-Host "═══ PBIRS Permissions & Verification ═══" -ForegroundColor Cyan

# ─── 1. Get all catalog items ──────────────────────────────────────
Write-Host "`n── Fetching Inventory ──" -ForegroundColor Yellow
$allItems = Invoke-PBIRS -Method GET -Path "/CatalogItems"
$items = if ($allItems.value) { $allItems.value } else { @() }

# Also try Folders, Reports, DataSources endpoints directly
$folders = (Invoke-PBIRS -Method GET -Path "/Folders").value
$reports = (Invoke-PBIRS -Method GET -Path "/Reports").value
$dataSources = (Invoke-PBIRS -Method GET -Path "/DataSources").value

Write-Host "  CatalogItems: $($items.Count)"
Write-Host "  Folders:      $($folders.Count)"
Write-Host "  Reports:      $($reports.Count)"
Write-Host "  DataSources:  $($dataSources.Count)"

# Build ID lookup
$folderLookup = @{}
foreach ($f in $folders) { $folderLookup[$f.Name] = $f.Id; $folderLookup[$f.Path] = $f.Id }
$reportLookup = @{}
foreach ($r in $reports) { $reportLookup[$r.Name] = $r.Id }

# Print everything
Write-Host "`n── All Folders ──" -ForegroundColor Yellow
foreach ($f in $folders) {
    Write-Host "  $($f.Path) [Id: $($f.Id)]"
}

Write-Host "`n── All Reports ──" -ForegroundColor Yellow
foreach ($r in $reports) {
    Write-Host "  $($r.Path)/$($r.Name) [Id: $($r.Id)]"
}

Write-Host "`n── All Data Sources ──" -ForegroundColor Yellow
foreach ($ds in $dataSources) {
    Write-Host "  $($ds.Path)/$($ds.Name) [Type: $($ds.DataSourceType)]"
}

# ─── 2. Set Folder Policies ───────────────────────────────────────
Write-Host "`n── Setting Folder Policies ──" -ForegroundColor Yellow

$permissionSets = @(
    @{
        FolderName = "Département Finance"
        Policies = @(
            @{ GroupUserName = "CORP\Finance-Managers"; Roles = @(@{ Name = "Content Manager" }) }
            @{ GroupUserName = "CORP\Finance-Analysts"; Roles = @(@{ Name = "Browser" }) }
            @{ GroupUserName = "CORP\Auditors";         Roles = @(@{ Name = "Browser" }) }
            @{ GroupUserName = "BUILTIN\Administrators"; Roles = @(@{ Name = "Content Manager" }) }
        )
    }
    @{
        FolderName = "RH - Ressources Humaines"
        Policies = @(
            @{ GroupUserName = "CORP\HR-Directors";    Roles = @(@{ Name = "Content Manager" }) }
            @{ GroupUserName = "CORP\HR-Partners";     Roles = @(@{ Name = "Browser" }, @{ Name = "Report Builder" }) }
            @{ GroupUserName = "BUILTIN\Administrators"; Roles = @(@{ Name = "Content Manager" }) }
        )
    }
    @{
        FolderName = "Direction Générale"
        Policies = @(
            @{ GroupUserName = "CORP\Executive-Team";  Roles = @(@{ Name = "Browser" }) }
            @{ GroupUserName = "CORP\Strategy-Team";   Roles = @(@{ Name = "Content Manager" }) }
            @{ GroupUserName = "BUILTIN\Administrators"; Roles = @(@{ Name = "Content Manager" }) }
        )
    }
    @{
        FolderName = "Équipe Commerciale"
        Policies = @(
            @{ GroupUserName = "CORP\Sales-Managers";  Roles = @(@{ Name = "Content Manager" }) }
            @{ GroupUserName = "CORP\Sales-Reps";      Roles = @(@{ Name = "Browser" }) }
            @{ GroupUserName = "CORP\Finance-Analysts"; Roles = @(@{ Name = "Browser" }) }
            @{ GroupUserName = "BUILTIN\Administrators"; Roles = @(@{ Name = "Content Manager" }) }
        )
    }
    @{
        FolderName = "Contrôle Qualité"
        Policies = @(
            @{ GroupUserName = "CORP\QA-Team";         Roles = @(@{ Name = "Content Manager" }) }
            @{ GroupUserName = "CORP\Production-Team"; Roles = @(@{ Name = "Browser" }) }
            @{ GroupUserName = "BUILTIN\Administrators"; Roles = @(@{ Name = "Content Manager" }) }
        )
    }
    @{
        FolderName = "IT Operations"
        Policies = @(
            @{ GroupUserName = "CORP\IT-Admins";       Roles = @(@{ Name = "Content Manager" }) }
            @{ GroupUserName = "CORP\IT-Support";      Roles = @(@{ Name = "Browser" }) }
            @{ GroupUserName = "CORP\Developers";      Roles = @(@{ Name = "Browser" }, @{ Name = "Publisher" }) }
            @{ GroupUserName = "BUILTIN\Administrators"; Roles = @(@{ Name = "Content Manager" }) }
        )
    }
)

foreach ($perm in $permissionSets) {
    $folderId = $folderLookup[$perm.FolderName]
    if (-not $folderId) {
        # Try path lookup
        $folderId = $folderLookup["/$($perm.FolderName)"]
    }
    if (-not $folderId) {
        Write-Host "  ⊘ $($perm.FolderName) — not found" -ForegroundColor Red
        continue
    }

    $body = @{ Policies = $perm.Policies }
    Invoke-PBIRS -Method PUT -Path "/Folders($folderId)/Policies" -Body $body | Out-Null
    Write-Host "  ✓ $($perm.FolderName) [$folderId] — $($perm.Policies.Count) policies" -ForegroundColor Green

    # Verify
    $readBack = Invoke-PBIRS -Method GET -Path "/Folders($folderId)/Policies"
    if ($readBack.Policies) {
        Write-Host "    → Verified: $($readBack.Policies.Count) policies active"
    }
}

# ─── 3. Save complete inventory to JSON ───────────────────────────
Write-Host "`n── Saving Inventory ──" -ForegroundColor Yellow

$inventory = @{
    timestamp    = (Get-Date -Format "o")
    server       = $BaseUrl
    folders      = $folders
    reports      = $reports
    dataSources  = $dataSources
    catalogItems = $items
}
$outDir = Join-Path (Split-Path $PSScriptRoot) "artifacts"
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
$outFile = Join-Path $outDir "pbirs_test_inventory.json"
$inventory | ConvertTo-Json -Depth 10 | Out-File $outFile -Encoding utf8 -Force
Write-Host "  Saved to: $outFile" -ForegroundColor Green

# ─── 4. Summary ────────────────────────────────────────────────────
Write-Host "`n═══ Summary ═══" -ForegroundColor Cyan
Write-Host "  Folders:      $($folders.Count)"
Write-Host "  Reports:      $($reports.Count)"
Write-Host "  Data Sources: $($dataSources.Count)"
Write-Host "  Total items:  $($items.Count)"
