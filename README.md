# Codex Skill: Research Folder Organizer

This repository publishes the `research-folder-organizer` Codex skill.

The skill audits research project folders and proposes safe, reviewable organization plans around one-task-one-package research workflows. It is designed for scientific project folders where raw data, scripts, figures, reports, manuscript material, archives, and graph indexes need to remain traceable.

## What It Does

- Audits a research folder before changing anything.
- Classifies files by evidence lifecycle.
- Proposes batch plans for organization instead of silently moving files.
- Protects raw data, virtual environments, Git metadata, graphify outputs, scientific arrays, and media by default.
- Creates durable human and agent entrypoints such as organizer reports and task registries when approved.

## Install

Copy the skill folder into your Codex skills directory:

```powershell
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }
New-Item -ItemType Directory -Force -Path (Join-Path $codexHome "skills") | Out-Null
Copy-Item -Recurse -Force ".\research-folder-organizer" (Join-Path $codexHome "skills\research-folder-organizer")
```

Restart Codex after installation so the skill list is reloaded.

## Use

Ask Codex:

```text
Use $research-folder-organizer to audit this research folder and propose one-task-one-package organization.
```

The skill writes read-only dry-run outputs under the target project's `_organizer/` directory before any approved changes.

## Repository Layout

```text
research-folder-organizer/
├── SKILL.md
├── agents/
│   └── openai.yaml
└── scripts/
    └── inventory.py
```

## License

MIT
