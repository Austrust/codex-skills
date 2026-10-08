# Project Context and Handoff

Updated: 2026-10-08

## Current governance

The user's 2026-10-08 decision replaces the former one-skill-one-repository model
with a hybrid collection. All 12 personal skills are ordinary tracked source
packages in `Austrust/codex-skills`. Four third-party skills use three submodules
of their original authors: Kiterlin, mattpocock, and Master-cai. Personal forks
are no longer part of the source or update chain.

`manifest/skills.json` schema 2 declares `storage`, source paths, and dependencies.
Personal `provenance` records original imports only. Third-party repository,
branch, `pinned_commit`, `.gitmodules`, and collection gitlinks describe the same
reproducible upstream source. `scripts/update-upstream.ps1` refreshes these pins
to the current original-upstream branch; installation also refreshes selected
upstreams unless `-SkipSubmoduleUpdate` is supplied.

The GitHub Actions upstream workflow runs daily at 10:00 Asia/Shanghai, with a
manual trigger as well. It validates and commits changed third-party pins.

Edit personal sources, validate, then commit and push this collection once.
Third-party refreshes commit gitlinks and the manifest together. Updating source
does not replace installed copies without an intentional `-Force` installation.
Original personal histories are retained in commit ancestry. Local recovery
mirrors preserve all old branches and tags. See
[the migration record](maintenance/2026-10-08-monorepo.md).

## Preserved workflow decisions

- Research workflow skills keep their tool-agnostic generated-output protection.
- `to-kanban` is the conversation-facing layer over `planka-kanban`; its full
  contract is in `repos/to-kanban/SKILL.md`. Preserve dependency-first installation,
  live discovery, preview, idempotence, and post-write verification.
- `grill-me` installs its `grilling` dependency first.
- Runtime state lives outside Git at `$CODEX_HOME/to-kanban/`, or `~/.codex/to-kanban/`.
- Planka accepts `PLANKA_BASE_URL` plus an API key or username/password.
  Keep credential values, Bark device keys, notification URLs, live board exports,
  and conversation transcripts out of repository source and logs.
- The user's historical Bark notification setup is account state. Verify before
  recreating it; material changes require authorization.
- Imported upstream licenses, attribution, and histories remain preserved.

## New-device bootstrap

### 1. Obtain and validate the sources

```powershell
git clone --recurse-submodules https://github.com/Austrust/codex-skills.git
cd codex-skills
python scripts/validate.py
```

A populated synchronized snapshot installs offline with `-SkipSubmoduleUpdate`.

### 2. Install the skills

```powershell
.\scripts\install.ps1 -Target agents
```

`-Target codex` remains supported for `.codex/skills`. `-Force` preserves existing
copies under the target home's `skill-backups/` before replacement. Individual
selection with `-Skill to-kanban` includes `planka-kanban` automatically.

### 3. Restore Planka access without committing secrets

Set the connection at Windows CurrentUser scope by a secure local method. Use
either:

- `PLANKA_BASE_URL` and `PLANKA_API_KEY`; or
- `PLANKA_BASE_URL`, `PLANKA_USERNAME`, and `PLANKA_PASSWORD`.

Do not paste values into this repository or a handoff document. Verify access
with the installed `planka-kanban` read-only flow before attempting any write.
If the old workstation's encrypted credential loader is deliberately migrated,
keep it under the user's private Codex secrets directory, never under this
repository.

### 4. Initialize `to-kanban` routing state

After the skills and Planka access are available:

```powershell
py "$env:CODEX_HOME\skills\to-kanban\scripts\kanban_context.py" init
py "$env:CODEX_HOME\skills\to-kanban\scripts\kanban_context.py" status
py "$env:CODEX_HOME\skills\to-kanban\scripts\kanban_context.py" refresh
```

If `CODEX_HOME` is unset, use
`$HOME\.codex\skills\to-kanban\scripts\kanban_context.py` instead.

The safest fresh-device default is to rebuild the sanitized offline snapshot
and allow the first ambiguous route to be confirmed once. To retain learned
routing, securely copy only the reviewed non-secret `memory.json` between the
private state directories. Do not put it in Git, and do not blindly migrate an
old `offline-board.json`.

### 5. Verify the checkout

```powershell
python scripts/validate.py
python scripts/validate.py --installed-root "$env:USERPROFILE/.agents/skills"
python -m unittest discover -s repos/to-kanban/scripts -p "test_*.py"
git status --short --branch
```

Use an available Python 3 executable. All personal sources must be ordinary files;
only declared original-upstream packages may be gitlinks. Installed file sets and SHA-256 hashes
must match when verifying a complete fresh installation.

## Maintenance boundaries

Compare installed copies before accepting changes, and normalize paths and private
values before publication. Use UTF-8 JSON files for Chinese or multiline Kanban
operations. Keep personal routing and account integrations outside Git.
Historical reports and the local pre-migration backup describe former states;
this document and `AGENTS.md` define current governance.

## Historical provenance

- [检查自建技能及集合治理](codex://threads/019f1d74-9a51-74c2-a080-ee3caa44cf8f)
- [创建并发布 to-kanban](codex://threads/019f5f3c-f448-7f81-bbb2-fb0a444cf0ed)
- [Collection PR #1](https://github.com/Austrust/codex-skills/pull/1)

The live checkout wins over historical thread text when they differ.
