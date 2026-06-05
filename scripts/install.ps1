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

$RequestedSkills = @{}
foreach ($Name in $Skill) {
    $RequestedSkills[$Name] = $true
}

$Entries = @($Manifest.skills)
if ($Skill.Count -gt 0) {
    $Entries = @($Manifest.skills | Where-Object { $RequestedSkills.ContainsKey($_.name) })
}

if ($Entries.Count -eq 0) {
    throw "No matching skills found in manifest."
}

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
