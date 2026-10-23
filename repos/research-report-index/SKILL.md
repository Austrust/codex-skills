---
name: research-report-index
description: Maintain a lightweight report navigation index in research projects using their existing layout. Use when the user requests report discovery, indexing, or refreshing an existing generated report index.
---

# Research Report Index

Expose existing reports without reorganizing their source folders. Preserve task names, report locations, and established navigation formats.

## Workflow

1. Read project instructions and the existing index/configuration. Limit inspection to requested paths or the current changes; do not run a project-wide scan merely because a report changed.
2. For a small manual index, patch affected entries in place. Use the bundled generator when the project already uses its format or the user requests a generated index. It regenerates the complete configured index, not an incremental patch; do not overwrite a hand-maintained index without preserving its content or choosing a separate destination.
3. Infer task ownership from project context, not a T### prefix. Reports may live directly in a task or in named execution folders. Do not require numbered roots, dated runs, manifests, or a directory migration.
4. Include purpose/topic, concise summary, report link, and useful related links. Copy status only when explicitly recorded; do not infer scientific confidence or manuscript readiness.
5. Verify affected links and report coverage. Maintain an existing README route to a new index when needed, using research-readme-index. Do not create a Wiki, configuration, annotations, or per-turn log solely to satisfy this skill.

## Optional Generator

Resolve scripts/update_report_index.py relative to this installed skill directory and use the project's required Python interpreter:

    python <skill-directory>/scripts/update_report_index.py --project-root <project> --task-root analyses

--task-root is repeatable and names a parent containing task directories. With no root supplied, an existing configuration takes precedence; otherwise the script recognizes existing 10_tasks and tasks folders. If neither exists, it stops without writing and asks for an explicit root. It never creates task roots.

The generator supports <task>/<report-file> and <task>/<run-dir-name>/*/<report-file>. Task and run names are unrestricted. Use --run-dir-name experiments, --report-file findings.md, or --index-path docs/REPORT_INDEX.md as needed. For other layouts, maintain the existing index directly or supply a suitable configuration rather than moving reports.

The default output is REPORT_INDEX.md. The generator remains Chinese-dominant; maintain other-language indexes directly to preserve their language. A --update-summary explicitly requests an update-log entry; without it no PROJECT_UPDATES.md is created or appended. --changed-path records paths in that optional log and does not restrict scanning.

## Existing Configuration Compatibility

An existing 00_project/dashboard_config.json is still read automatically. Use --config <file> for another location; all configured project paths are relative to the project root. No configuration file is created automatically.

Supported settings include task_roots, task_pattern (default *), run_dir_name (default runs), report_file (default REPORT.md), index_path, annotations_path, updates_path, manifest_file, and related_files. Explicit legacy patterns and paths are preserved. Set annotations_path or updates_path to null to disable those optional files.

Existing annotations at 00_project/navigation_annotations.md remain supported, or set annotations_path to another location. Annotations are optional Markdown blocks keyed by project-relative task or report-folder path, with topic: and summary: fields. Use them only when extraction needs a durable override. Existing manifests and related files are linked when present; missing ones do not block indexing.
