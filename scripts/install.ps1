[CmdletBinding()]
param(
    [ValidateSet("codex", "agents", "both")]
    [string]$Target = "codex",

    [string[]]$Skill = @(),

    [switch]$Force,

    # Skip network refresh for an already-populated checkout or offline snapshot.
    [switch]$SkipSubmoduleUpdate
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$ManifestPath = Join-Path $RepoRoot "manifest\skills.json"

if (-not (Test-Path $ManifestPath)) {
    throw "Missing manifest: $ManifestPath"
}

$Manifest = Get-Content -Raw -Path $ManifestPath | ConvertFrom-Json
if ($Manifest.schema_version -ne 2 -or $Manifest.repository_model -ne "hybrid") {
    throw "Expected a schema 2 hybrid manifest."
}

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

# Third-party sources follow their original upstreams; personal sources are bundled.
$UpstreamPaths = @($Entries | Where-Object { $_.storage -eq 'submodule' } | ForEach-Object { $_.submodule_path } | Select-Object -Unique)
if (-not $SkipSubmoduleUpdate -and $UpstreamPaths.Count -gt 0) {
    & (Join-Path $ScriptDir 'update-upstream.ps1') -SubmodulePath $UpstreamPaths
}

# Validate all selected sources before creating any installed folders.
foreach ($Entry in $Entries) {
    if ($Entry.name -notmatch '^[a-z0-9]+(-[a-z0-9]+)*$') {
        throw "Invalid skill directory name: $($Entry.name)"
    }
    $CheckedSource = [IO.Path]::GetFullPath((Join-Path $RepoRoot $Entry.source_path))
    $SourcePrefix = [IO.Path]::GetFullPath($RepoRoot).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if (-not $CheckedSource.StartsWith($SourcePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Skill source must remain inside the collection: $($Entry.name)"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $CheckedSource 'SKILL.md') -PathType Leaf)) {
        throw "Missing SKILL.md for $($Entry.name)"
    }
}

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
            $ResolvedRoot = [IO.Path]::GetFullPath($TargetRoot.Path).TrimEnd('\', '/')
            $ResolvedDestination = [IO.Path]::GetFullPath($Destination)
            if ([IO.Path]::GetDirectoryName($ResolvedDestination) -ne $ResolvedRoot) {
                throw "Destination is outside the intended skills directory."
            }
            # Keep an existing installation recoverable, outside skill discovery.
            $BackupRoot = Join-Path (Split-Path -Parent $ResolvedRoot) 'skill-backups'
            New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
            $Backup = Join-Path $BackupRoot ($Entry.name + '-' + [guid]::NewGuid().ToString('N'))
            Move-Item -LiteralPath $ResolvedDestination -Destination $Backup
            Write-Host "backup $($Entry.name) -> $Backup"
        }

        New-Item -ItemType Directory -Force -Path $Destination | Out-Null
        $SourceAbsolute = (Resolve-Path -LiteralPath $SourcePath).Path.TrimEnd('\', '/')
        foreach ($File in Get-ChildItem -LiteralPath $SourcePath -Recurse -File -Force) {
            $Relative = $File.FullName.Substring($SourceAbsolute.Length + 1)
            if ($Relative -match '(^|[\\/])(\.git|__pycache__|\.pytest_cache|\.test-state)([\\/]|$)' -or $Relative -match '\.py[co]$') {
                continue
            }
            $OutputPath = Join-Path $Destination $Relative
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputPath) | Out-Null
            Copy-Item -LiteralPath $File.FullName -Destination $OutputPath
        }
        Write-Host "installed $($Entry.name) -> $Destination"
    }
}
