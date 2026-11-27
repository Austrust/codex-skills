# Changelog

Notable changes to this personal skill collection. Releases use date-based tags
`vYYYY.MM.DD`; `v2026.11.03` is the newest release, mirrored by the moving tag
`latest`. `manifest/skills.json` also records `latest_release`.

## Unreleased

- Added `mechanical-drawing`: 3D 模型（STEP / build123d）→ 规范机械加工工程图
  （draftwright ISO 128/129 视图与尺寸、ISO 7200 标题栏；PyMuPDF 中文标题、技术要求与标注叠加），
  含标准基线、中文叠加要点、自动标注人工修正表与成图检查清单。Collection now has 19 installable skills.
- Added `homebox-cli`: a dependency-free Python CLI for a HomeBox v0.27.x
  inventory over its REST API — search/list/show, create items and locations,
  merge-safe updates, move, delete with confirmation, tags, photo/attachment
  upload, maintenance entries, CSV export, collection statistics, QR images and
  API-key listing. Includes `references/api.md` for the entity model and
  full-replacement update semantics, and a gitignored `references/local-context.md`
  for per-deployment connection facts.
- `scripts/validate.py`: personal skills without historical import provenance are
  accepted (provenance remains optional and historical only); a present
  provenance commit must still be a 40-character hash.
- Refreshed original upstreams: `anti-defensive-writing` to `f516147`
  (Chinese technical-writing and SOP guidance) and mattpocock/skills to
  `4ae2317` (`grilling`, `grill-me`, and `to-tickets`).
- Removed the orphan `to-issue` manifest entry: no source package or tracked
  package history exists. The collection contains 18 installable skills.

- Added `to-tickets` from mattpocock/skills (existing `repos/grill-me`
  submodule, pin refreshed to `49dd158`): splits a plan, spec or conversation
  into tracer-bullet tickets with blocking edges and publishes them to the
  configured tracker (GitHub, GitLab or local markdown). `grilling` and
  `grill-me` pins were aligned to the same submodule HEAD.

## v2026.11.03 — 2026-11-03 (latest)

Updated skills:

- `maintain-knowledge-base`
  - One-page workflow with three modes: query (read-only), daily maintenance
    (notes, existing fact/status updates, new objects), structural operations
    (move/merge/schema/restore with preview and backup).
  - Retrieval protocol: `catalog` → entry front-matter `aliases`/`title` →
    body keywords → `relations.csv`; failures report nearest candidates.
  - Path priority (explicit > workspace declaration > machine default), audit
    timing, and explicit "not recommended" list.
  - New `references/paths.md` and `references/backup-restore.md`.
  - `aliases` spec: front matter only, never duplicated in CSV; IP addresses and
    hostnames are verified connection info, not permanent identity aliases.
  - `audit_kb.py`: duplicate note-ID and source-reference validity checks.

- `research-readme-index`
  - Role-aware navigation: explicit/known entry → `catalog` (knowledge-base
    auxiliary) → unknown; unknown pages still have their links checked but do not
    get navigation-page content/length rules.
  - Navigation pages route only; they do not maintain volatile facts owned by
    other records.
  - Tri-state link results: valid / stale / unchecked (with reasons).
  - Explicit scan scope: explicit paths or known changes → git; `mtime` only when
    explicitly requested; no scope means "cannot determine scope" (no implicit
    full scan).
  - Rewritten `audit_readme_index.py`: default prints only (no report file),
    `--check` exit codes, separate error/warning severity, container discovery,
    unknown-role parent handling, REPORT/PROJECT entry-link checks.
  - 10 unit tests under `tests/`.

Tooling:

- `scripts/validate.py`: `--skill` local validation (selected skills and
  dependencies) with `identical` / `newline_only` / `content_diff` comparison;
  full validation behavior unchanged.

Install this release (targeted, does not update submodules):

```powershell
.\scripts\install.ps1 -Target both -Skill maintain-knowledge-base,research-readme-index -SkipSubmoduleUpdate -Force
```

## Earlier history

Before `v2026.11.03`, changes are recorded in the repository history only; see
`git log`.
