# Codex Skills Collection

This repository collects personal skill repositories as pinned git submodules.
Each skill keeps its own source repository, while this repo provides one
bootstrap point for new machines.

## Included Skills

| Skill | Repository | Source path |
|---|---|---|
| `research-folder-organizer` | `Austrust/codex-skill-research-folder-organizer` | `repos/research-folder-organizer/research-folder-organizer` |
| `planka-kanban` | `Austrust/planka-kanban` | `repos/planka-kanban` |
| `scientific-data-report` | `Austrust/scientific-data-report` | `repos/scientific-data-report` |
| `research-report-index` | `Austrust/research-report-index` | `repos/research-report-index` |
| `zotero-literature-guide` | `Austrust/codex-skill-zotero-literature-guide` | `repos/zotero-literature-guide` |

The exact pinned commits are recorded in `manifest/skills.json` and in the
submodule gitlinks.

## Install On A New Machine

```powershell
git clone --recurse-submodules https://github.com/Austrust/codex-skills.git
cd codex-skills
.\scripts\install.ps1 -Target codex
```

Install into a generic `.agents\skills` directory instead:

```powershell
.\scripts\install.ps1 -Target agents
```

Install into both locations:

```powershell
.\scripts\install.ps1 -Target both
```

By default, the installer skips skills that already exist. Use `-Force` only
when you intentionally want to replace an installed skill folder:

```powershell
.\scripts\install.ps1 -Target codex -Force
```

## Update Submodules

To refresh the pinned version of a skill:

```powershell
git submodule update --remote repos/planka-kanban
git add .gitmodules repos/planka-kanban manifest/skills.json
git commit -m "Update planka-kanban"
```

After changing a submodule pin, update `manifest/skills.json` so the human
manifest and gitlinks agree.

## Repository Model

- Individual skill repos remain the source of truth.
- This collection repo is the install and inventory layer.
- `LOCAL_SKILL_INVENTORY.md` records installed local skills that were not added
  as submodules because no separate GitHub source repo was confirmed.
