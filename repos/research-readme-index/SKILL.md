---
name: research-readme-index
description: Lightly maintain README-based navigation indexes in research projects. Use when the user asks to update README navigation, maintain folder indexes, add a task/run/report folder to navigation, refresh run indexes, or audit missing README links. Preserves existing project layouts and naming.
---

# Research README Index

## Purpose

Use this skill for lightweight README navigation maintenance in research projects. It is for routine index upkeep after stable folder or run changes, not for full folder reorganization.

Use the project's existing structure. Task folders need no fixed parent, numbering, or naming pattern; runs need no date prefix. Do not migrate folders to satisfy an index convention.

## Core Rules

- Use `README.md` as the navigation file. Do not introduce `data_structure.md`.
- Default to the current change set. Use `git status --short` or user-provided paths; scan the whole project only when the user explicitly asks for a full audit.
- Prefer local patches over full rewrites. Preserve existing README tone, language, table shape, and section order.
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
- Existing area README, such as `tasks/README.md` or `reports/README.md`: what belongs there, what does not, and a compact list of direct child packages.
- Task package README, such as `analyses/flow/README.md`: task purpose, minimal background, main inputs, key scripts, main outputs, downstream consumers, and a run index.
- Run-level `README.md` or `REPORT.md`: what this run did, why it was needed, inputs, workflow or commands, outputs, confidence, limitations, and next-step implications.
- Archive README: why the material was archived, what replaced it, and whether it is forbidden as active evidence.

Parent README files list direct children only. Do not make the root README carry a full project tree.

## Workflow

1. Read local instructions first, especially Python environment and documentation language rules.
2. Determine scope:
   - If the user gave paths, use those paths.
   - Else use the current Git change set.
   - Use full-project scanning only when the user explicitly asks.
3. Small changes can be checked directly without generating audit artifacts. Optionally run the bundled script, resolved relative to this skill directory, with the project's Python:

   ```powershell
   .\.venv\Scripts\python.exe <skill-directory>/scripts/audit_readme_index.py --project-root .
   ```

   With explicit paths:

   ```powershell
   .\.venv\Scripts\python.exe <skill-directory>/scripts/audit_readme_index.py --project-root . --paths tasks\flow_analysis\runs\baseline
   ```

   Full audit:

   ```powershell
   .\.venv\Scripts\python.exe <skill-directory>/scripts/audit_readme_index.py --project-root . --full
   ```

4. Patch README files minimally:
   - Existing README: add or update only the relevant row, bullet, or short section.
   - Missing README for a confirmed stable folder: create a concise README when it adds navigation value; an existing run REPORT.md can already serve as its landing page.
   - Missing run entry: update the owning task package README.
   - Parent README: add only the direct child entry needed for navigation.
5. Verify the changed README links resolve where practical.

The script recognizes tasks by a run-container child (default runs), existing README/REPORT entrypoints, or explicitly supplied folder paths. Use --run-dir-name experiments for another run-container name. Full scans identify candidates from these signals, not every folder; review ambiguous ownership manually. A run REPORT.md is a valid landing page and does not require a duplicate README.

The optional script writes:

- `_organizer/readme_index_audit.json`
- `_organizer/readme_index_audit.md`

## Run Index Format

Recommended format, not mandatory:

```markdown
## Runs

| Run | Purpose | Status | Report |
| --- | --- | --- | --- |
| `baseline` | Low-context explanation of what this run did and why it matters. | complete | [REPORT.md](runs/baseline/REPORT.md) |
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
