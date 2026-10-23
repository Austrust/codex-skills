# Full Research Project Restructuring

Use only for explicitly requested project-wide audits, initialization, or restructuring. The entrypoint's task aggregation, authorization, and preservation rules still apply.

## Survey and Design

Read project instructions, existing entrypoints, and Git status. Identify active tasks, shared inputs and methods, downstream manuscripts/reports, and confirmed historical material. Inspect contents and dependencies to validate classifications; filenames are only clues.

Choose a structure that fits the project. For a small project, existing task folders plus a root README may be enough. A larger project may benefit from tasks/, sources/, methods/, manuscript/, and archive/. Preserve an established numbering scheme if useful; do not create empty areas to satisfy a template.

Within each task, start with README.md and the actual working material. Add scripts/, outputs/, or runs/ only when they improve navigation. Use runs/ to separate repeated executions when needed; task identity should remain stable across runs. Record substantial input/dependency detail in a manifest only when it would overload the README.

## Optional Inventory

The bundled scripts/inventory.py scans recursively and writes reports without moving source material. Run it only when a full inventory is useful; it also traverses environment/data trees, so prefer targeted inspection for large stores. Its task README check recognizes only the legacy 10_tasks/T* layout and is not a universal completeness check.

Resolve the script relative to this skill directory. With the project's required Python interpreter:

    python <skill-directory>/scripts/inventory.py --root <project> --dry-run --format both

Use --out <directory> to select the report destination; otherwise it writes to <project>/_organizer/. It produces inventory.json, inventory_report.md, and proposed_batches.md. The proposed batches are generic review prompts, not an approved migration plan. Treat name-based lifecycle labels as candidates to verify.

## Migration and Verification

- Prepare a concrete old-path → new-path mapping with reasons and affected dependencies. Use the existing README as the main entrypoint; a second Wiki or registry is not required.
- For substantial migrations, retain the mapping and execution results in a compact record so moves can be traced or reversed. Reuse an existing record location; use _organizer/ only if needed.
- Execute cohesive groups within the user's authorization. Planning-only requests stop at recommendations. Resolve genuinely ambiguous or unauthorized actions together rather than requesting approval for every batch.
- Keep raw inputs in place where possible. Update known relative paths, configuration references, and README links alongside moves. Do not move unresolved dependencies.
- Archive only material confirmed superseded, following the project's current convention. Preserve original evidence and historical archives.
- Check destinations, changed links, relevant entrypoints, and pre/post Git status. Report unresolved references or checks that could not run. Stage or commit only when requested and exclude unrelated changes.
