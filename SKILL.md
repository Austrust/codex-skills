---
name: research-report-index
description: Build and refresh a lightweight Markdown index of scientific report packages in task-based research projects. Use when a project has task folders with runs and REPORT.md files, or when the user asks to expose, index, navigate, or refresh generated scientific-data-report outputs.
---

# Research Report Index

## Quick Start

From the project root, run the bundled script with the project's Python:

```powershell
.\.venv\Scripts\python.exe 00_project\skills\research-report-index\scripts\update_report_index.py `
  --project-root . `
  --update-summary "本轮刷新报告导航索引。"
```

The default project files are:

- `00_project/dashboard_config.json` for machine-readable settings.
- `00_project/navigation_annotations.md` for optional human overrides.
- `REPORT_INDEX.md` as the generated report navigation page.
- `PROJECT_UPDATES.md` as the per-agent-turn update log.

## Workflow

1. Read the project instructions first, especially Python environment and post-change maintenance rules.
2. Make the requested project changes.
3. Add or adjust entries in `00_project/navigation_annotations.md` only when automatic extraction produces a weak topic or summary.
4. Run `scripts/update_report_index.py` with a concise `--update-summary`.
5. Verify `REPORT_INDEX.md` exposes the new or changed reports.
6. Run any project-required graph or index maintenance after the report index refresh.

## Scope

This skill intentionally keeps the generated page simple:

- Group by task folder.
- Under each task, list runs that contain `REPORT.md`.
- For each run, show topic, short summary, optional status, report link, and related links.
- Do not infer scientific evidence roles, claim boundaries, or manuscript readiness unless the user explicitly adds that language to annotations.

## Configuration

Minimal `00_project/dashboard_config.json`:

```json
{
  "language": "zh-CN",
  "index_path": "REPORT_INDEX.md",
  "updates_path": "PROJECT_UPDATES.md",
  "annotations_path": "00_project/navigation_annotations.md",
  "task_roots": ["10_tasks"],
  "task_pattern": "T[0-9][0-9][0-9]_*",
  "run_dir_name": "runs"
}
```

## Annotation Format

Use structured Markdown blocks keyed by a relative task or run path:

```markdown
## 10_tasks/T002_uiv_processing/runs/20260530_104646_flowrate0p1-full-source-refresh

topic: flowrate=0.1 完整数据源刷新
summary: 替换为完整 12000-frame OpenPIV 数据源，重新生成 UIV 主指标和图件。
```

Supported keys:

- `topic`
- `summary`

