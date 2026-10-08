# Agent Operating Guide

## Bootstrap context

Read `README.md`, `PROJECT_CONTEXT.md`, and `manifest/skills.json` before maintenance.
Read the complete `SKILL.md` of a skill before changing its behavior. The live
checkout and these documents are the durable project context.

## Repository model

- `Austrust/codex-skills` directly maintains personal skill sources as ordinary tracked packages under `repos/`.
- Third-party skills remain submodules of original authors. Never route upstream updates through personal forks.
- `manifest/skills.json` schema 2 declares storage, source paths, targets, and dependencies.
- Personal `provenance` records historical imports only. Do not restore separate personal repositories or personal gitlinks.
- Third-party repository/branch/pin fields, `.gitmodules`, and gitlinks must agree.
- `LOCAL_SKILL_INVENTORY.md` is historical, not an authority for current versions.
- Use repository-relative or environment-based paths; never publish developer-machine paths.

## Change and publish workflow

1. Inspect `git status` and preserve existing changes.
2. Edit personal source directly. For third-party refreshes, run `scripts/update-upstream.ps1`; preserve dirty upstream work before updating.
3. Validate affected behavior, metadata, dependencies, and installation as applicable.
4. Scan publishable changes for credentials, tokens, private keys, personal identifiers, and machine-local paths.
5. Stage named personal paths or updated upstream gitlinks together with the manifest, then commit and push the collection once.

Review upstream refreshes and retain licenses and attribution. Third-party changes
should follow their original authors; preserve deliberate local customization in a
separate personal skill or explicitly reviewed patch, rather than silently changing
a submodule worktree. Personal provenance stays historical.

## Project invariants

- Preserve the generic protection for unknown generated-tool output in the research workflow skills; do not reintroduce Graphify-specific defaults.
- `to-kanban` depends on `planka-kanban`; `grill-me` depends on `grilling`. Dependency-first installation must work.
- Kanban writes retain their live discovery, preview, authorization, and post-write verification requirements.
- Never commit Planka or Bark secrets, personal routing state, live board exports, or conversation transcripts.
- Preserve upstream history, license, and attribution for imported packages.
- Installed copies may be intentionally synchronized after comparison, normalization, and redaction; repository source remains authoritative.

## Validation baseline

```powershell
python scripts/validate.py
python -m unittest discover -s repos/to-kanban/scripts -p "test_*.py"
.\scripts\install.ps1 -Target agents -Skill to-kanban
```

Use a temporary `AGENTS_HOME` for installer tests. For all-skill installation,
compare installed file sets and SHA-256 hashes with `scripts/validate.py --installed-root`.
Confirm the only Git mode `160000` entries and nested Git metadata belong to the
three declared original-upstream submodules. Verify checked-out upstream HEADs
match manifest pins. Tests should be proportional to the changed behavior.

## Machine-local boundary

Follow `PROJECT_CONTEXT.md#new-device-bootstrap` for Planka environment variables
and `to-kanban` state. Keep local maintenance archives and recovery mirrors outside
published source. Historical maintenance reports do not override current governance.
