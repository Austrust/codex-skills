# research-report-index

Codex skill for generating a lightweight `REPORT_INDEX.md` in task-based research projects.

The first version scans `10_tasks/*/runs/*/REPORT.md`, groups reports by `T###` task package, and exposes each run with:

- topic
- short summary
- audit/reproducibility/confidence status when available
- `REPORT.md` link
- related links such as `AUDIT_MANIFEST.json`, `FIGURE_INDEX.md`, and `COMMAND_LOG.md`

## Files

- `SKILL.md` - Codex skill instructions.
- `scripts/update_report_index.py` - deterministic report-index generator.

## Typical Project Setup

```text
00_project/dashboard_config.json
00_project/navigation_annotations.md
REPORT_INDEX.md
PROJECT_UPDATES.md
```

Run from a project root:

```powershell
.\.venv\Scripts\python.exe 00_project\skills\research-report-index\scripts\update_report_index.py `
  --project-root . `
  --update-summary "刷新报告导航索引。"
```

