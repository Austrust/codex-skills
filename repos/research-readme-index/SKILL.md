---
name: research-readme-index
description: Lightly maintain README-based navigation indexes in research projects and knowledge bases. Use when the user asks to update README navigation, maintain folder indexes, add a task/run/report folder to navigation, refresh run indexes, audit missing or stale README links, or keep a knowledge-base landing page navigable. Preserves existing layouts and naming; reports navigation gaps without changing content records.
---

# Research README Index

## Purpose and Scope

Use this skill for lightweight README navigation upkeep in two kinds of trees:

- research projects: project root, area folders, task packages, run folders;
- knowledge bases and document directories: the root landing page and category
  directories whose children are already stable.

This skill only decides *where a reader should click next*. It does not store
knowledge, record status, dates, owners, counts, progress, or todos, and it does
not reorganize folders. Use `maintain-knowledge-base` for knowledge content,
`research-report-index` for a generated `REPORT_INDEX.md`,
`research-folder-organizer` for restructuring, and `scientific-data-report` for
new report packages.

Prefer local patches over full rewrites. Preserve the existing README language,
tone, table shape, and section order. Do not migrate folders to satisfy an index
convention.

## README Role

Determine what a page is before judging it, using this priority:

1. **Explicit declaration** — the local `AGENTS.md`, README or user instruction
   says what the page is for.
2. **Known entry file** — `README.md` is a navigation page; `REPORT.md` and
   `PROJECT.md` are object entry pages (a run report or a project record).
3. **Knowledge-base `catalog/`** — auxiliary factual record, not a navigation
   page; it is linked once from the root page and does not own navigation links.
4. **Unknown** — no role can be established. Still check its links, but do not
   apply navigation-page content or length rules and do not infer status.

When an object's `canonical_path` points at a directory, only that object's
entry file (`README.md` in that directory) is its landing page. Other files in
that directory are content, not additional navigation entries.

A navigation page does not independently maintain volatile facts that another
record owns. Link the authoritative record instead of copying counts, status,
dates, or evidence text.

## Route-Only Rule

A route entry contains exactly three things: an ID or name, one sentence saying
what the target is for, and one resolved relative link to the entry.

Never write into a README:

- status snapshots (`active`/`complete`/`partial`/... and Chinese equivalents);
- dates, owners, counts, versions, progress, or confidence labels;
- todo items, "待确认", "下一步" checklists, or meeting notes.

Those belong in `PROJECT.md`, `REPORT.md`, `catalog/` tables, or the linked
entity record. This skill has no status-word table; status vocabulary belongs to
the record that owns the fact.

If an existing README already has a status column or dated notes, leave old rows
alone (local patch over rewrite) and do not add status to new rows.

Optional recent-changes section: off by default. Build it only when the user or
the project explicitly asks for one; keep it to at most 5 lines, newest first,
rolling (oldest dropped), each line = date + ID + one-line change event +
authority link. It is maintained by this skill during a navigation-maintenance
round; the knowledge-base skill never writes README files.

## Entry Format and Budget

- Directory entry: `- 名称 — 一句话用途：[入口](child/)`
- No directory page? Link the real entry file:
  `[REPORT.md](runs/x/REPORT.md)` or `[PROJECT.md](projects/PRJ-xxx/PROJECT.md)`.
- Links must resolve to an existing target; directory links end with `/`.
  Targets are URL-decoded and matched case-insensitively on Windows; spaces and
  Chinese characters are valid.
- Every link has one of three states: **valid**, **stale**, or **unchecked**.
  Readable cross-tree links (for example a link to a sibling project or a
  knowledge-base record) must be checked. Remote URLs and material that cannot
  be read are recorded as unchecked with a reason, never guessed.
- Budget is a hint, not an error: project root ≤12 child links, folder README
  ≤20 entry lines, knowledge-base root ≤35 lines and ≤12 links. Prefer IDs over
  prose.
- List only direct children; one child appears exactly once, in its own parent's
  README. Never list caches, temporary folders, `_organizer/`,
  `intermediate/`, generated figures, or one-off script output.

## Layered Navigation

Each README answers only the routing question for its level:

- project root: purpose, main routes, what each top-level area owns;
- area README: what belongs there, what does not, compact direct-child list;
- task package: purpose, minimal inputs, key outputs, run index when applicable;
- run `REPORT.md` or `PROJECT.md`: the object's own landing page;
- archive README: why archived, what replaced it, whether usable as evidence;
- knowledge-base root: four sections — 定位 / 入口 / 最近变更 (optional) / 维护
  (a one-line pointer to `AGENTS.md`, not a rules section); knowledge-base
  category README: direct children only, one line of purpose each, no copied
  catalog state, ID convention links the global registry once.

## Run Index

Create a `## Runs` table only when the run container has two or more run
children or the user explicitly asks for a run index. With a single run, the
parent entry links `runs/<name>/REPORT.md` directly. A run `REPORT.md` is a valid
landing page: do not add a duplicate README, and do not omit the run from the
parent index.

## Workflow

1. Read local instructions first, especially documentation language rules.
2. Determine scope explicitly: user paths, or the current change set when the
   tree is inside a Git work tree; otherwise require `--mtime-hours` or `--full`
   from the user. Never start a full scan on your own.
3. Audit when useful (the script is read-only and writes nothing by default):

   ```powershell
   python <skill-dir>/scripts/audit_readme_index.py --project-root . --paths tasks\flow\README.md --check
   python <skill-dir>/scripts/audit_readme_index.py --project-root . --full --check
   python <skill-dir>/scripts/audit_readme_index.py --project-root . --full --check --json
   python <skill-dir>/scripts/audit_readme_index.py --project-root <kb> --kb-root . --full --check
   ```

4. Patch minimally: existing README — one row/bullet/short section; missing
   stable child entry — create a concise README when it adds navigation value;
   missing run entry — update the owning task package README.
5. Verify changed links resolve; record stale and unchecked states honestly.
6. Report only what changed; do not leave audit artifacts unless the user asked
   for them (`--out` writes the JSON/Markdown report).

## Script Semantics

`scripts/audit_readme_index.py` is standard-library only.

- Default: print a summary, write nothing.
- `--check`: 0 = no error, 1 = error-level findings, 2 = usage/environment
  error (missing root, undetermined scope, unwritable `--out`).
- `--strict` with `--check`: warnings also fail.
- Severity: `error` = `missing_entry`, `missing_parent_link`, internal
  `stale_link`; `warning` = `stale_external_link`, `unchecked` cross-tree link,
  `budget_exceeded`, `duplicate_entry`, `cross_level_entry` (with
  `--strict-index`).
- Entry files default to `README.md`, `REPORT.md`, `PROJECT.md`; links inside
  `REPORT.md`/`PROJECT.md` are checked as well.
- `--entry-file` adds/replaces entry names; `--require-entry` marks a directory
  as requiring an entry; `--run-dir-name` changes the run-container name;
  `--mtime-hours` is the explicit non-Git fallback; `--kb-root` enables the
  knowledge-base roles (`catalog/` auxiliary, section roots require entries,
  `inbox/` skipped); `--max-entry-links` is the optional budget hint;
  `--strict-index` also warns about links below the direct-child level.
- `--out DIR` writes `readme_index_audit.json` and `.md`; `--json` prints JSON.

## Non-Git Usage

Git is optional. Without a repository, pass explicit paths or an explicit mtime
window; the script reports "Cannot determine scan scope" instead of guessing:

```powershell
python <skill-dir>/scripts/audit_readme_index.py --project-root . --paths <changed-path> --check
python <skill-dir>/scripts/audit_readme_index.py --project-root . --mtime-hours 168 --check
python <skill-dir>/scripts/audit_readme_index.py --project-root . --full --check --out $env:TEMP\readme-audit
```

## Boundaries

- Use `research-folder-organizer` when the project is messy, being reorganized
  from scratch, or needs archive/move batches.
- Use `research-report-index` when the requested artifact is the generated root
  `REPORT_INDEX.md`.
- Use `maintain-knowledge-base` for knowledge content, records, and facts; this
  skill only keeps the navigation to them usable.
- Use `scientific-data-report` when creating a new auditable processing report
  package.
