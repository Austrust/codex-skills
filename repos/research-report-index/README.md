# research-report-index

Maintain report navigation in the existing project layout. Use local edits for small or hand-maintained indexes; the optional generator groups reports by task without requiring numbered task names or dated runs.

## Files

- [SKILL.md](SKILL.md): workflow, supported layouts, optional configuration, and legacy compatibility.
- [scripts/update_report_index.py](scripts/update_report_index.py): full regeneration of a configured report index.

## Usage

With the project's Python, resolve the script from this installed skill directory:

    python <skill-directory>/scripts/update_report_index.py --project-root <project> --task-root analyses

Inputs are existing task reports, optional annotations, and optional manifests. Output defaults to REPORT_INDEX.md. Direct task reports and reports under a configurable run container are supported.

Existing 00_project/dashboard_config.json settings remain valid. Without configuration, existing 10_tasks and tasks roots are recognized; other roots are supplied explicitly. No setup files or directories are required. Update logging occurs only with --update-summary. See SKILL.md for configuration and naming overrides.
