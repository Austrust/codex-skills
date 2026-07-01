---
name: research-readme-index
description: Lightly maintain README-based navigation indexes in research projects. Use when the user asks to update README navigation, maintain folder indexes, add a task/run/report folder to navigation, refresh run indexes, or audit missing README links. Defaults to the task-package structure produced by research-folder-organizer.
---

# Research README Index

## Purpose

Use this skill for lightweight README navigation maintenance in research projects. It is for routine index upkeep after stable folder or run changes, not for full folder reorganization.

Default structure is compatible with `research-folder-organizer`:

```text
00_project/
01_sources/
10_tasks/T###_short_slug/runs/YYYYMMDD_label/
20_methods/
30_literature/
40_reference/
50_reports/
70_manuscript/
80_presentations/
90_archive/
```

## Core Rules

- Use `README.md` as the navigation file. Do not introduce `data_structure.md`.
- Default to the current change set. Use `git status --short` or user-provided paths; scan the whole project only when the user explicitly asks for a full audit.
- Prefer local patches over full rewrites. Preserve existing README tone, language, table shape, and section order.
- Do not update graphify.
- Do not create README files for cache folders, temporary folders, generated figure directories, `outputs/intermediate/`, or one-off script output directories.

## Reader Orientation

README text is for a low-context reader: assume they know only the broad project topic, not local abbreviations, previous agent decisions, source substitutions, or run history.

A README entry should tell the reader:

- what this folder or run is for;
- whether it is active, complete, partial, exploratory, archived, deprecated, or blocked;
- which input family or upstream result it uses;
- what output, evidence, report, or downstream consumer matters;
- what to read next.

Do not turn README files into full reports, complete file trees, raw command logs, or private shorthand such as "rerun official data" without explaining what the shorthand means.

## Layered README Navigation

Each README answers only the routing question for its level:

- Project root `README.md`: project purpose, main navigation routes, and what each top-level area owns.
- Top-level area README, such as `10_tasks/README.md` or `50_reports/README.md`: what belongs there, what does not, and a compact list of direct child packages.
- Task package README, such as `10_tasks/T###_short_slug/README.md`: task purpose, minimal background, main inputs, key scripts, main outputs, downstream consumers, and a run index.
- Run-level `README.md` or `REPORT.md`: what this run did, why it was needed, inputs, workflow or commands, outputs, confidence, limitations, and next-step implications.
- Archive README: why the material was archived, what replaced it, and whether it is forbidden as active evidence.

Parent README files list direct children only. Do not make the root README carry a full project tree.

## Workflow

1. Read local instructions first, especially Python environment and documentation language rules.
2. Determine scope:
   - If the user gave paths, use those paths.
   - Else use the current Git change set.
   - Use full-project scanning only when the user explicitly asks.
3. Run the audit script when useful:

   ```powershell
   .\.venv\Scripts\python.exe C:\Users\A_Tas\.codex\skills\research-readme-index\scripts\audit_readme_index.py --project-root .
   ```

   With explicit paths:

   ```powershell
   .\.venv\Scripts\python.exe C:\Users\A_Tas\.codex\skills\research-readme-index\scripts\audit_readme_index.py --project-root . --paths 10_tasks\T016_example\runs\20260605_new_run
   ```

   Full audit:

   ```powershell
   .\.venv\Scripts\python.exe C:\Users\A_Tas\.codex\skills\research-readme-index\scripts\audit_readme_index.py --project-root . --full
   ```

4. Patch README files minimally:
   - Existing README: add or update only the relevant row, bullet, or short section.
   - Missing README for a stable folder: create a concise README.
   - Missing run entry: update the owning task package README.
   - Parent README: add only the direct child entry needed for navigation.
5. Verify the changed README links resolve where practical.

The script writes:

- `_organizer/readme_index_audit.json`
- `_organizer/readme_index_audit.md`

## Run Index Format

Recommended format, not mandatory:

```markdown
## Runs

| Run | Purpose | Status | Report |
| --- | --- | --- | --- |
| `YYYYMMDD_label` | Low-context explanation of what this run did and why it matters. | complete | [REPORT.md](runs/YYYYMMDD_label/REPORT.md) |
```

Use an existing list or table format when one is already established. Do not rewrite old entries only for formatting consistency.

## Status Words

Prefer these status meanings for new entries:

- `active`: current usable entrypoint or evidence.
- `complete`: run is complete and outputs/reports are present.
- `partial`: useful, but provenance, coverage, or reproducibility is incomplete.
- `exploratory`: exploration only, not a main conclusion.
- `archived`: retained for history, not current evidence.
- `deprecated`: replaced; avoid using it.
- `blocked`: stopped by missing data, dependency, access, or unresolved scientific premise.

Chinese equivalents are fine in Chinese-dominant projects. Existing README wording can remain if its meaning is clear.

## Boundaries

- Use `research-folder-organizer` instead when the project is messy, being reorganized from scratch, or needs archive/move batches.
- Use `research-report-index` when the requested artifact is the generated root `REPORT_INDEX.md`.
- Use `scientific-data-report` when creating a new auditable processing report package.
