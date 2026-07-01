# Research README Index

Lightweight Codex skill for maintaining README-based navigation indexes in research projects.

The skill keeps routing documentation readable after stable task, run, or report folders change. It is intentionally scoped to README navigation maintenance, not full folder reorganization.

## Contents

- `SKILL.md` - skill instructions and workflow.
- `agents/openai.yaml` - Codex skill display metadata.
- `scripts/audit_readme_index.py` - read-only audit helper for README navigation coverage and broken links.

## Typical Use

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
