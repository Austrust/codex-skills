[CmdletBinding()]
param([string[]]$SubmodulePath = @())
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ManifestPath = Join-Path $RepoRoot 'manifest/skills.json'
$Manifest = Get-Content -Raw -LiteralPath $ManifestPath | ConvertFrom-Json
if ($Manifest.schema_version -ne 2 -or $Manifest.repository_model -ne 'hybrid') {
    throw 'Expected a schema 2 hybrid manifest.'
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'git is required to update upstream skills.' }
if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot '.git'))) { throw 'Update upstream skills from a Git checkout, not a source-only snapshot.' }
function Invoke-CollectionGit {
    param([string]$Directory, [string[]]$GitArgs)
    $Result = & git -c http.lowSpeedLimit=1 -c http.lowSpeedTime=30 -C $Directory @GitArgs
    if ($LASTEXITCODE -ne 0) { throw "git failed in ${Directory}: $($GitArgs -join ' ')" }
    return $Result
}
$AllEntries = @($Manifest.skills | Where-Object { $_.storage -eq 'submodule' })
$Paths = @($AllEntries | ForEach-Object { $_.submodule_path } | Select-Object -Unique)
if ($SubmodulePath.Count -gt 0) {
    foreach ($Requested in $SubmodulePath) {
        if ($Requested -notin $Paths) { throw "Unknown upstream submodule: $Requested" }
    }
    $Paths = @($SubmodulePath | Select-Object -Unique)
}
# Refuse to overwrite local upstream work, including untracked files.
foreach ($Relative in $Paths) {
    $Directory = [IO.Path]::GetFullPath((Join-Path $RepoRoot $Relative))
    $Prefix = [IO.Path]::GetFullPath((Join-Path $RepoRoot 'repos')).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if (-not $Directory.StartsWith($Prefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Submodule outside repos/: $Relative" }
    if (Test-Path -LiteralPath (Join-Path $Directory '.git')) {
        $Dirty = @(Invoke-CollectionGit -Directory $Directory -GitArgs @('status', '--porcelain'))
        if ($Dirty.Count -gt 0) { throw "Upstream submodule has local changes; preserve them before updating: $Relative" }
    }
}
$GitArgs = @('submodule', 'update', '--init', '--recursive', '--') + $Paths
Invoke-CollectionGit -Directory $RepoRoot -GitArgs $GitArgs | Out-Null
$Updates = @()
foreach ($Relative in $Paths) {
    $Entries = @($AllEntries | Where-Object { $_.submodule_path -eq $Relative })
    $Entry = $Entries[0]
    $Directory = Join-Path $RepoRoot $Relative
    # The manifest always names the original upstream, never a personal fork.
    Invoke-CollectionGit -Directory $Directory -GitArgs @('remote', 'set-url', 'origin', $Entry.repository) | Out-Null
    Invoke-CollectionGit -Directory $Directory -GitArgs @('fetch', 'origin', $Entry.branch) | Out-Null
    $Commit = (Invoke-CollectionGit -Directory $Directory -GitArgs @('rev-parse', 'FETCH_HEAD')).Trim()
    foreach ($SkillEntry in $Entries) {
        $SkillRelative = $SkillEntry.source_path.Substring($Relative.Length).TrimStart('/')
        $SkillFile = if ($SkillRelative) { "$SkillRelative/SKILL.md" } else { 'SKILL.md' }
        Invoke-CollectionGit -Directory $Directory -GitArgs @('cat-file', '-e', "$($Commit):$SkillFile") | Out-Null
    }
    $Updates += [pscustomobject]@{ Path = $Relative; Directory = $Directory; Commit = $Commit; Entries = $Entries }
}
foreach ($Update in $Updates) {
    Invoke-CollectionGit -Directory $Update.Directory -GitArgs @('checkout', '--detach', $Update.Commit) | Out-Null
    foreach ($Entry in $Update.Entries) { $Entry.pinned_commit = $Update.Commit }
    Write-Host "updated $($Update.Path) -> $($Update.Commit)"
}
$Json = ($Manifest | ConvertTo-Json -Depth 30) + [Environment]::NewLine
[IO.File]::WriteAllText($ManifestPath, $Json, [Text.UTF8Encoding]::new($false))
Write-Host 'Upstream sources refreshed. Validate and commit changed gitlinks and manifest together.'
