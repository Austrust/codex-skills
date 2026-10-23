---
name: research-folder-organizer
description: Organize research folders locally around concrete research tasks, preserving useful existing structure. Use for grouping scattered task materials, archiving superseded work, or requested project restructuring. For routine README-only upkeep, use research-readme-index.
---

# Research Folder Organizer

Make research materials easy to find and understand. Default to local organization within the requested scope; keep the files answering one research question together.

## Organizing Principles

- Preserve useful existing names and structure. Group scripts, tables, figures, notes, and reports by the research task they serve, not merely by file type.
- Introduce a task folder only when it clarifies ownership. Task IDs, numbered top-level areas, dates, and standard subfolders are optional; create folders only for material that exists or is immediately needed.
- Keep shared methods and references outside individual tasks only when they actually serve multiple tasks. Manuscripts and presentations consume analysis results; keep the analysis with its task.
- Reference shared raw inputs instead of copying them. Record source paths and relevant versions in the task README; use a separate input manifest only when the dependency detail warrants it.

## Default: Local Organization

1. Read applicable project instructions and the nearest README. Use user-specified paths; otherwise use the current change set or clearly identified task area. If no scope can be inferred, ask for the target. Start with one or two directory levels and inspect deeper only as needed. Do not run a project-wide inventory by default.
2. Identify the concrete problem and the smallest useful change. Inspect task context and path references before moving code, notebooks, or their inputs. An unclear filename or old modification date alone does not establish that material is obsolete.
3. Briefly describe meaningful moves as old path → new path, then carry out clear, reversible changes covered by the user's request. A request for advice or an audit authorizes recommendations, not moves. Existing authorization carries forward: do not ask again for every folder, README edit, or execution batch.
4. Maintain affected README navigation using research-readme-index. Preserve language and style; parents index direct children only. Explain purpose, status, main inputs, key outputs, and the next reading entry without duplicating reports.
5. Verify moved destinations, affected links, and known path dependencies. Use focused checks appropriate to the changes; report anything not verified. Summarize what changed and any unresolved decisions.

## Boundaries

- Do not delete or overwrite by default. Ask only when a consequential action remains unauthorized, ownership is ambiguous, or a dependency risk cannot be resolved by inspection. Group unresolved questions and continue independent authorized work.
- Protect raw data, scientific stores, environment directories, Git metadata, and unfamiliar generated-tool outputs. Leave data and notebooks with unresolved path dependencies in place; link to them instead.
- Preserve unrelated work. Check Git status before and after changes when in a repository; staging and committing are outside ordinary organization unless requested.
- Archive confirmed superseded material using the existing archive convention. Do not consolidate historical archives just for uniformity.
- README is the default navigation artifact. Do not automatically create a separate Wiki, task registry, input manifest, inventory report, or execution log. Add one only when requested or when the scale of the authorized work makes its distinct purpose necessary.
- Do not create READMEs for caches, temporary folders, generated image folders, outputs/intermediate/, or one-off script outputs.

## Optional: Full Restructuring

Read [references/full-restructure.md](references/full-restructure.md) only when the user requests project-wide auditing, initialization, or restructuring. Local messiness does not itself authorize a full migration. The inventory script is an optional reporting tool for that mode, not a prerequisite for ordinary organization.
