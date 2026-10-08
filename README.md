# Codex Skills

Personal skills are maintained directly in this repository. Third-party skills
remain Git submodules of their original authors, so updates do not depend on
personal forks. `manifest/skills.json` schema 2 declares sources and dependencies.

## Start here

- Humans: use this README for installation and source navigation.
- Agents: read [AGENTS.md](AGENTS.md) and [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).
- `storage: vendored` means ordinary tracked personal source; its `provenance` is historical import attribution.
- `storage: submodule` means an original-upstream checkout; its `pinned_commit` and gitlink record a reproducible version.
- [LOCAL_SKILL_INVENTORY.md](LOCAL_SKILL_INVENTORY.md) is a historical local snapshot.

## Included skills

| Skill | Maintained source | Model |
|---|---|---|
| `overleaf` | [repos/overleaf/overleaf](repos/overleaf/overleaf/SKILL.md) | Personal source |
| `reader-first-communication` | [repos/reader-first-communication](repos/reader-first-communication/SKILL.md) | Personal source |
| `anti-defensive-writing` | [repos/anti-defensive-writing/skill/anti-defensive-writing](https://github.com/Kiterlin/anti-defensive-writing/tree/c7edf8fc91ae9c4f7e58345bd12934bb4cf41c46/skill/anti-defensive-writing) | Original-upstream submodule |
| `grilling` | [repos/grill-me/skills/productivity/grilling](https://github.com/mattpocock/skills/tree/b0618bc436ad893b3c5e84e55fba86586d34a404/skills/productivity/grilling) | Original-upstream submodule |
| `grill-me` | [repos/grill-me/skills/productivity/grill-me](https://github.com/mattpocock/skills/tree/b0618bc436ad893b3c5e84e55fba86586d34a404/skills/productivity/grill-me) | Original-upstream submodule |
| `research-folder-organizer` | [repos/research-folder-organizer/research-folder-organizer](repos/research-folder-organizer/research-folder-organizer/SKILL.md) | Personal source |
| `neat-freak` | [repos/neat-freak](repos/neat-freak/SKILL.md) | Personal source |
| `planka-kanban` | [repos/planka-kanban](repos/planka-kanban/SKILL.md) | Personal source |
| `to-kanban` | [repos/to-kanban](repos/to-kanban/SKILL.md) | Personal source |
| `research-paper-writing` | [repos/research-paper-writing/research-paper-writing](https://github.com/Master-cai/Research-Paper-Writing-Skills/tree/77e7c2c1ba06f7d71844873147665437a03aac1b/research-paper-writing) | Original-upstream submodule |
| `scientific-data-report` | [repos/scientific-data-report](repos/scientific-data-report/SKILL.md) | Personal source |
| `research-report-index` | [repos/research-report-index](repos/research-report-index/SKILL.md) | Personal source |
| `research-readme-index` | [repos/research-readme-index](repos/research-readme-index/SKILL.md) | Personal source |
| `zotero-literature-guide` | [repos/zotero-literature-guide](repos/zotero-literature-guide/SKILL.md) | Personal source |
| `maintain-knowledge-base` | [repos/maintain-knowledge-base](repos/maintain-knowledge-base/SKILL.md) | Personal source |
| `research-illustrated-guide` | [repos/research-illustrated-guide](repos/research-illustrated-guide/SKILL.md) | Personal source |

## Install on a new machine

```powershell
git clone --recurse-submodules https://github.com/Austrust/codex-skills.git
cd codex-skills
.\scripts\install.ps1 -Target agents
python scripts/validate.py
```

The installer initializes selected third-party submodules and fetches the latest
upstream branch before installation. A normal clone without `--recurse-submodules`
also works: the installer initializes the needed sources. It never fetches from a
personal fork. Upstream refreshes leave changed gitlinks and matching manifest pins
for review and commit.

The `agents` target uses `$AGENTS_HOME/skills`, or `~/.agents/skills` by default.
The `codex` target uses `$CODEX_HOME/skills`, or `~/.codex/skills`; `both` installs
into both homes. Usually choose one target to avoid duplicate discovery.

Select individual skills with dependencies first:

```powershell
.\scripts\install.ps1 -Target agents -Skill to-kanban
.\scripts\install.ps1 -Target agents -Skill grill-me
```

`to-kanban` includes `planka-kanban`; `grill-me` includes `grilling`.
Existing installed folders are skipped unless `-Force` is supplied. Forced
replacement preserves the old folder in the target home's `skill-backups/`.
For an intentional installation update, use:

```powershell
.\scripts\install.ps1 -Target agents -Force
```

For offline installation from a populated checkout or synchronized snapshot:

```powershell
.\scripts\install.ps1 -Target agents -SkipSubmoduleUpdate
python scripts/validate.py --installed-root "$env:USERPROFILE/.agents/skills"
```

This verifies installed file sets and SHA-256 hashes. Use an available Python 3
command in place of `python` when needed.

## Keep third-party skills current

[The update workflow](.github/workflows/update-upstream.yml) runs daily at 10:00
Asia/Shanghai and can also be triggered manually from GitHub Actions. It refreshes
original upstream branches, validates sources, and commits only changed pins.
It does not replace installed copies on individual machines.


Refresh all third-party sources directly from their original authors:

```powershell
.\scripts\update-upstream.ps1
python scripts/validate.py
git add .gitmodules manifest/skills.json repos/anti-defensive-writing repos/grill-me repos/research-paper-writing
git commit -m "Update third-party skills"
git push
```

The updater refuses to overwrite dirty upstream worktrees and verifies that all
manifest skill entrypoints still exist at the fetched commit before checkout.
Pins provide reproducibility; upstream refresh explicitly moves them to the latest
branch commits. Updating repository sources does not replace already-installed
copies unless installation is run with `-Force`.

## Maintain personal skills

Edit the personal source path above, validate the affected behavior, then commit
and push this repository once. Do not create separate personal skill repositories.
For upstream additions, add an original-author submodule and manifest entries.
Preserve dependencies, licenses, attribution, and the runtime boundaries in
[PROJECT_CONTEXT.md](PROJECT_CONTEXT.md#new-device-bootstrap).

## Upstream attribution

- `anti-defensive-writing`: [Kiterlin/anti-defensive-writing](https://github.com/Kiterlin/anti-defensive-writing).
- `grilling` and `grill-me`: [mattpocock/skills](https://github.com/mattpocock/skills).
- `research-paper-writing`: [Master-cai/Research-Paper-Writing-Skills](https://github.com/Master-cai/Research-Paper-Writing-Skills).

Their licenses, attribution, and histories remain with the original submodules.
Personal source histories are retained in the collection's commit ancestry.
See [the migration record](maintenance/2026-10-08-monorepo.md).
