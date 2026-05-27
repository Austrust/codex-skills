---
name: research-folder-organizer
description: Audit and safely organize research project folders around task packages so they are readable for humans and navigable for agents. Use when the user asks to整理科研项目文件夹, make one concrete research task one folder, archive old research materials, create README/Wiki/index files, plan safe cleanup batches, or sync graphify after project-material changes.
---

# Research Folder Organizer

## Purpose

Use this skill for research project folders, not generic Downloads cleanup. The goal is to make project material easier to find, cite, maintain, and hand off while preserving evidence history.

Default organizing principle: one concrete research task gets one task package. Avoid using broad material buckets such as "figures", "scripts", "current mining", or "paper materials" as the main long-term structure when the work is really a data-processing or evidence-building task.

Default stance: audit first, propose batches second, mutate only after explicit user approval. Never delete by default.

## Workflow

1. **Ground in the project**
   - Read local instructions first: `AGENTS.md`, `README*`, `项目Wiki.md`, `ProjectWiki.md`, `.gitignore`, `.graphifyignore`.
   - Check whether the folder is a Git repo with `git status --short`.
   - If `graphify-out/` exists or local instructions mention graphify, treat graphify refresh as required after approved content/index changes.

2. **Run a read-only inventory**
   - Use `scripts/inventory.py --root <project> --dry-run --format both`.
   - Respect project Python rules. If `AGENTS.md` requires `.venv`, use that interpreter.
   - Write dry-run output to `<project>/_organizer/` unless the user asked for another location.

3. **Classify by evidence lifecycle**
   - `current_mainline`: current manuscript, active analysis, current project entrypoints.
   - `supporting_evidence`: validation packages, figures, tables, source reports, reproducibility notes.
   - `reproducible_output`: build output, generated figures, exported reports that can be regenerated.
   - `archive_candidate`: superseded drafts, old exploratory runs, stale copies, replaced exports.
   - `protected_data`: raw data, large scientific stores, venvs, Git metadata, graph outputs, media captures.
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
     graphify-out/        # graphify outputs when used by the project
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
   - `outputs/intermediate/` is for useful-but-not-final reproducible artifacts; cache-only material stays out of task outputs.
   - A task package may link to another task package output, but must record that dependency in `inputs/manifest.md`.

6. **Propose batches, do not silently execute**
   - Batch proposals should separate: entrypoint/index updates, archive moves, duplicate reports, cache cleanup, graphify refresh, Git staging/commit.
   - Ask for approval by batch before moving, editing, installing dependencies, rebuilding graphify, staging, or committing.
   - New archive moves go to `_archive/YYYY-MM-DD_description/`.
   - Existing archives such as `99_旧版归档_*` are not migrated automatically; suggest consolidation only in the report.

7. **Make human and agent entrypoints**
   - Keep existing project README/Wiki intact unless the user approves edits.
   - Create a separate organizer wiki when approved: `整理Wiki.md` for Chinese-dominant projects, `OrganizationWiki.md` for English-dominant projects.
   - Maintain a task registry when using task packages. It should map task id, task slug, purpose, owner/status if known, source inputs, key outputs, and downstream consumers.
   - Prefer relative links in generated project documentation.
   - Keep `_organizer/` as the home for inventories, dry-run reports, proposed batches, and execution records.

## Safety Rules

- Default to no deletion. Duplicate files are report-only unless the user explicitly approves removal in a later task.
- Protect paths from project config first. If config is missing, conservatively protect `.git/`, `.venv/`, `venv/`, `env/`, `dataset*/`, `graphify-out/`, Zarr stores, scientific arrays, HDF5/NetCDF/MAT files, raw media, and build caches.
- Do not move raw data or notebooks with unknown relative paths during the first pass.
- Do not split a coherent task package by file type. If a script, table, figure, and report exist to answer the same research question, keep them together under that task.
- Do not mix unrelated dirty worktree changes into organizer commits.
- If a dependency is missing, report it and ask before installing into the project environment.

## Git And Graphify

- Always record pre/post `git status --short` when inside a Git repo.
- If committing is approved, stage only organizer-created or organizer-moved files for that batch.
- If graphify is required by project instructions, rebuild it only after approved file/content changes, using the project Python environment.
- Keep `graphify-out/graph.json`, `graphify-out/graph.html`, and `graphify-out/GRAPH_REPORT.md` in sync when rebuilding.

## Script

Run the bundled inventory script:

```powershell
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }
$inventory = Join-Path $codexHome "skills\research-folder-organizer\scripts\inventory.py"
python $inventory --root . --dry-run --format both
```

For projects that require a local venv:

```powershell
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }
$inventory = Join-Path $codexHome "skills\research-folder-organizer\scripts\inventory.py"
.\.venv\Scripts\python.exe $inventory --root . --dry-run --format both
```

The script writes:

- `_organizer/inventory.json`
- `_organizer/inventory_report.md`
- `_organizer/proposed_batches.md`
