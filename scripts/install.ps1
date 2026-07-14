[CmdletBinding()]
param(
    [ValidateSet("codex", "agents", "both")]
    [string]$Target = "codex",

    [string[]]$Skill = @(),

    [switch]$Force,

    [switch]$SkipSubmoduleUpdate
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$ManifestPath = Join-Path $RepoRoot "manifest\skills.json"

if (-not (Test-Path $ManifestPath)) {
    throw "Missing manifest: $ManifestPath"
}

if (-not $SkipSubmoduleUpdate) {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "git is required unless -SkipSubmoduleUpdate is supplied."
    }

    git -C $RepoRoot submodule update --init --recursive
    if ($LASTEXITCODE -ne 0) {
        throw "git submodule update failed."
    }
}

$Manifest = Get-Content -Raw -Path $ManifestPath | ConvertFrom-Json

function Get-TargetRoots {
    param([string]$RequestedTarget)

    $UserProfile = [Environment]::GetFolderPath("UserProfile")
    $CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $UserProfile ".codex" }
    $AgentsHome = if ($env:AGENTS_HOME) { $env:AGENTS_HOME } else { Join-Path $UserProfile ".agents" }

    $Roots = @()
    if ($RequestedTarget -eq "codex" -or $RequestedTarget -eq "both") {
        $Roots += [pscustomobject]@{
            Name = "codex"
            Path = Join-Path $CodexHome "skills"
        }
    }
    if ($RequestedTarget -eq "agents" -or $RequestedTarget -eq "both") {
        $Roots += [pscustomobject]@{
            Name = "agents"
            Path = Join-Path $AgentsHome "skills"
        }
    }

    return $Roots
}

$EntriesByName = @{}
foreach ($Entry in @($Manifest.skills)) {
    if (-not $Entry.name) {
        throw "Every manifest skill requires a name."
    }
    if ($EntriesByName.ContainsKey($Entry.name)) {
        throw "Duplicate skill in manifest: $($Entry.name)"
    }
    $EntriesByName[$Entry.name] = $Entry
}

function Add-SkillWithDependencies {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][hashtable]$Visiting,
        [Parameter(Mandatory = $true)][hashtable]$Added,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][System.Collections.ArrayList]$Output
    )

    if (-not $EntriesByName.ContainsKey($Name)) {
        throw "Skill or dependency not found in manifest: $Name"
    }
    if ($Added.ContainsKey($Name)) {
        return
    }
    if ($Visiting.ContainsKey($Name)) {
        $Cycle = @($Visiting.Keys) + $Name
        throw "Skill dependency cycle detected: $($Cycle -join ' -> ')"
    }

    $Visiting[$Name] = $true
    $Entry = $EntriesByName[$Name]
    $Dependencies = if ($null -eq $Entry.dependencies) { @() } else { @($Entry.dependencies) }
    foreach ($Dependency in $Dependencies) {
        if (-not ($Dependency -is [string]) -or [string]::IsNullOrWhiteSpace($Dependency)) {
            throw "Skill $Name has an invalid dependency entry."
        }
        Add-SkillWithDependencies -Name $Dependency -Visiting $Visiting -Added $Added -Output $Output
    }
    [void]$Visiting.Remove($Name)
    $Added[$Name] = $true
    [void]$Output.Add($Entry)
}

$RequestedNames = if ($Skill.Count -gt 0) { @($Skill) } else { @($Manifest.skills | ForEach-Object { $_.name }) }
$ResolvedEntries = New-Object System.Collections.ArrayList
$AddedSkills = @{}
foreach ($Name in $RequestedNames) {
    Add-SkillWithDependencies -Name $Name -Visiting @{} -Added $AddedSkills -Output $ResolvedEntries
}
$Entries = @($ResolvedEntries)

$TargetRoots = Get-TargetRoots -RequestedTarget $Target

foreach ($Entry in $Entries) {
    $SourcePath = Join-Path $RepoRoot $Entry.source_path
    if (-not (Test-Path (Join-Path $SourcePath "SKILL.md"))) {
        throw "Missing SKILL.md for $($Entry.name): $SourcePath"
    }

    foreach ($TargetRoot in $TargetRoots) {
        New-Item -ItemType Directory -Force -Path $TargetRoot.Path | Out-Null

        $Destination = Join-Path $TargetRoot.Path $Entry.name
        if (Test-Path $Destination) {
            if (-not $Force) {
                Write-Host "skip $($Entry.name) -> $($TargetRoot.Name), already exists: $Destination"
                continue
            }
            Remove-Item -LiteralPath $Destination -Recurse -Force
        }

        Copy-Item -LiteralPath $SourcePath -Destination $Destination -Recurse -Force
        Write-Host "installed $($Entry.name) -> $Destination"
    }
}
