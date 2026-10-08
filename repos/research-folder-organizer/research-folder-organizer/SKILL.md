---
name: research-folder-organizer
description: Audit and safely organize research project folders around task packages so they are readable for humans and navigable for agents. Use when the user asks to整理科研项目文件夹, make one concrete research task one folder, archive old research materials, create initial README/Wiki/index files during organization, or plan safe cleanup batches. For routine README index maintenance, use research-readme-index instead.
---

# Research Folder Organizer

## Purpose

Use this skill for research project folders, not generic Downloads cleanup. The goal is to make project material easier to find, cite, maintain, and hand off while preserving evidence history.

Default organizing principle: one concrete research task gets one task package. Avoid using broad material buckets such as "figures", "scripts", "current mining", or "paper materials" as the main long-term structure when the work is really a data-processing or evidence-building task.

Default stance: audit first, propose batches second, mutate only after explicit user approval. Never delete by default.

## Workflow

1. **Ground in the project**
   - Read local instructions first: `AGENTS.md`, `README*`, `项目Wiki.md`, `ProjectWiki.md`, and `.gitignore`.
   - Check whether the folder is a Git repo with `git status --short`.

2. **Run a read-only inventory**
   - Use `scripts/inventory.py --root <project> --dry-run --format both`.
   - Respect project Python rules. If `AGENTS.md` requires `.venv`, use that interpreter.
   - Write dry-run output to `<project>/_organizer/` unless the user asked for another location.

3. **Classify by evidence lifecycle**
   - `current_mainline`: current manuscript, active analysis, current project entrypoints.
   - `supporting_evidence`: validation packages, figures, tables, source reports, reproducibility notes.
   - `reproducible_output`: build output, generated figures, exported reports that can be regenerated.
   - `archive_candidate`: superseded drafts, old exploratory runs, stale copies, replaced exports.
   - `protected_data`: raw data, large scientific stores, virtual environments, Git metadata, unknown generated-tool outputs, and media captures.
   - `cache_or_temp`: caches, temporary folders, build artifacts, editor state.

4. **Plan task packages before moves**
   - Prefer a project layout like:

     ```text
     00_project/          # project-level indexes, task registry, governance
     01_sources/          # raw data/models and immutable inputs, indexed not copied
     10_tasks/            # one concrete task per package
     20_methods/          # reusable methods, shared workflows, common scripts
     30_literature/       # papers, literature audits, novelty-gap material
     40_reference/        # external specs, manuals, standards, symbol tables
     50_reports/          # internal reports and stage summaries
     70_manuscript/       # manuscript-facing final text, tables, and figures
     80_presentations/    # PPT, web/video presentations, talk scripts
     90_archive/          # retired task packages and historical archives
     _organizer/          # organizer reports and execution records
     ```

   - Use stable task names: `T001_uiv_processing`, `T002_comsol_uiv_comparison`, `T003_deep_exchange_reachability`.
   - Put dates in run folders or report filenames, not in the task identity unless the date is the scientific object.
   - Do not copy raw data into every task package. Put source paths, versions, filters, and fields in `inputs/manifest.md`.
   - Keep manuscript and presentation folders as consumers of task outputs, not as the home of the analysis process.
   - Use `20_methods/`, `30_literature/`, `40_reference/`, and `50_reports/` only for cross-task material. If a file exists mainly to answer one concrete research question, keep it in that task package instead.

5. **Use a standard task package shape**
   - Each task package should be independently understandable and reproducible:

     ```text
     T###_short_slug/
     ├── README.md
     ├── inputs/
     │   └── manifest.md
     ├── scripts/
     ├── outputs/
     │   ├── tables/
     │   ├── figures/
     │   ├── reports/
     │   └── intermediate/
     ├── runs/
     │   └── YYYYMMDD_label/
     ├── notes/
     └── _archive/
     ```

   - `README.md` must answer: why this task exists, what inputs it uses, how to run it, what it outputs, and what downstream manuscript/report consumes it.
   - `README.md` is the canonical task-level human index. It must explain the task and each `runs/*` folder in low-context prose: assume the reader knows only the broad project topic, not the local abbreviations, past decisions, or evidence chain.
   - `outputs/intermediate/` is for useful-but-not-final reproducible artifacts; cache-only material stays out of task outputs.
   - A task package may link to another task package output, but must record that dependency in `inputs/manifest.md`.

6. **Create initial task README run indexes**
   - Every `T###_short_slug/README.md` should include:
     - Task purpose in plain language.
     - Minimal background needed to understand why the task exists.
     - Main inputs and where they come from.
     - Main scripts or commands, if the task is reproducible.
     - Main outputs and how downstream manuscript/report work uses them.
     - A run index covering every `runs/YYYYMMDD_label/` folder.
   - Each run entry should give a short, self-contained explanation: what was done, why it was done, what evidence or artifact came out, current status/confidence if known, and the report path.
   - Do not write run summaries as private shorthand such as "rerun official data" unless the README also explains what "official data" means in that task context.
   - Prefer concise paragraphs or tables over long duplicated report text. The README routes readers to reports; it does not replace them.
   - For routine maintenance of existing README indexes after ordinary work, use `research-readme-index`.

7. **Propose batches, do not silently execute**
   - Batch proposals should separate: task README/run-index updates, other entrypoint/index updates, archive moves, duplicate reports, cache cleanup, and Git staging/commit.
   - Ask for approval by batch before moving, editing, installing dependencies, staging, or committing.
   - New archive moves go to `_archive/YYYY-MM-DD_description/`.
   - Existing archives such as `99_旧版归档_*` are not migrated automatically; suggest consolidation only in the report.

8. **Make human and agent entrypoints**
   - Keep existing project README/Wiki intact unless the user approves edits.
   - Create a separate organizer wiki when approved: `整理Wiki.md` for Chinese-dominant projects, `OrganizationWiki.md` for English-dominant projects.
   - Maintain a task registry when using task packages. It should map task id, task slug, purpose, owner/status if known, source inputs, key outputs, and downstream consumers.
   - Treat task package README files as the first detailed landing pages for humans and agents after the project-level registry.
   - Prefer relative links in generated project documentation.
   - Keep `_organizer/` as the home for inventories, dry-run reports, proposed batches, and execution records.

## Safety Rules

- Default to no deletion. Duplicate files are report-only unless the user explicitly approves removal in a later task.
- Protect paths from project config first. If config is missing, conservatively protect `.git/`, `.venv/`, `venv/`, `env/`, `dataset*/`, unknown generated-tool output directories, Zarr stores, scientific arrays, HDF5/NetCDF/MAT files, raw media, and build caches.
- Do not move raw data or notebooks with unknown relative paths during the first pass.
- Do not split a coherent task package by file type. If a script, table, figure, and report exist to answer the same research question, keep them together under that task.
- Do not mix unrelated dirty worktree changes into organizer commits.
- If a dependency is missing, report it and ask before installing into the project environment.

## Git

- Always record pre/post `git status --short` when inside a Git repo.
- If committing is approved, stage only organizer-created or organizer-moved files for that batch.
- Do not update, regenerate, or stage unknown generated-tool outputs as part of this skill.

## Script

Run the bundled inventory script:

```powershell
python $env:USERPROFILE\.codex\skills\research-folder-organizer\scripts\inventory.py --root . --dry-run --format both
```

For projects that require a local venv:

```powershell
.\.venv\Scripts\python.exe $env:USERPROFILE\.codex\skills\research-folder-organizer\scripts\inventory.py --root . --dry-run --format both
```

The script writes:

- `_organizer/inventory.json`
- `_organizer/inventory_report.md`
- `_organizer/proposed_batches.md`
