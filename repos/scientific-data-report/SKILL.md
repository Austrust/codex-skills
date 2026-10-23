---
name: scientific-data-report
description: Write concise scientific processing reports with useful outputs, essential methods, checks, and rerun instructions. Add structured audit records when needed for handoff; answer bounded data questions inline.
---

# Scientific Data Report

Help readers understand the result, judge whether it is usable, and repeat important work. Each artifact should support a result, decision, rerun, or real review need.

## Delivery size

- **Inline:** bounded question, quick inspection, or explanation of existing results. Answer with decisive evidence; do not create a package solely because scientific data is involved.
- **Lean (default for saved work):** An existing report entrypoint (REPORT.md for new helper-created packages) plus actual useful data, figures, tables, or code. Keep essential provenance, commands, and QC in the report or link existing authoritative records. No mandatory sidecars or empty directories.
- **Audited:** add AUDIT_MANIFEST.json when requested, required by the project, or needed for complex lineage and handoff. Read [references/audited.md](references/audited.md). Manuscript use increases verification requirements; it does not automatically require extra documents.

Processing mode is independent of delivery size: exploratory for provisional analysis, formal for conclusion-supporting results, repair for a defect and its verification, reproduce for a rerun with deviations recorded.

## Workflow

1. Identify the question, intended use, inputs, and existing rerun entrypoints. Inspect only the needed scope.
2. Resolve consequential scientific choices. A plan in the conversation or report is usually enough. Create PROCESSING_PLAN.md only for a complex reviewable plan or explicit project requirement. Honor prior authorization; do not stop just because the mode is formal. Ask about unresolved consequential choices or an explicit approval gate not already satisfied.
3. Execute authorized processing, preserve raw data, and run relevant checks.
4. Write the result first. Reuse existing code, environments, logs, and data paths instead of copying them.
5. Check output links and reported numbers, inspect figures, and remove template text. Maintain owning README navigation for new stable runs according to research-readme-index; do not duplicate REPORT.md in a run README.

## Report content

Use the project's language and style. Routine reports should usually fit one or two screens before figures; expand when needed. These are content requirements, not mandatory headings or tables:

- Result and context: question, data family, key finding with units, and processing status. Explain unfamiliar terms where first used.
- Useful outputs: link deliverables readers will use and explain their purpose. Include decisive figures with readable axes, units, and concise captions. Link existing figures without copying them.
- Method and evidence: input paths/version, selections, transformations, consequential parameters and their basis; distinguish current execution, existing results, and inferred behavior. Explain lineage in plain language without mandatory artificial step IDs.
- Checks and limitations: actual checks and outcomes (sample counts, missingness, units, fit residuals, threshold sensitivity). State limitations affecting interpretation. No fixed quota of review targets or boilerplate lists of unsupported claims.
- Reproduction: working directory, command or manual procedure, code revision/hash, relevant environment or links to existing records, and missing rerun prerequisites.

Keep these concise fields near the top for navigation compatibility:

    Audit status: complete | partial | blocked | exploratory
    Reproducibility: reproducible | partially_reproducible | not_reproducible | not_assessed

Complete means the declared processing scope and essential checks are complete, with retraceable inputs and a usable rerun procedure; it does not certify scientific truth. Use partial for material evidence gaps and blocked when the intended result cannot be produced. Scientific confidence is optional; explain its basis if used.

## Essential evidence

- Keep raw data read-only unless explicitly authorized. Keep new results distinguishable from prior results using the existing project convention; create a new run only when it adds needed version separation. Edit existing reports in place when requested. Never silently overwrite results or delete old artifacts as part of simplification.
- Identify conclusion-bearing inputs by stable dataset version or hash. For large inputs use an inexpensive documented fallback (size/mtime plus metadata or sampled hashes), noting its weaker guarantees. Reuse trustworthy fingerprints. Quick inline inspections need not hash entire datasets.
- Record relevant metadata: units, shape, selected channels/groups, coordinates, calibration, sampling, missing-data policy. Missing critical metadata restricts affected claims; unrelated unknowns do not block all work.
- Distinguish executed_this_session, existing_file, inferred_from_code, user_provided, and gui_manual evidence. Never infer execution from file presence. Unknown evidence cannot support a verified claim.
- Preserve parameters and code/environment identity for reruns. Manual work needs sufficient actions/settings; assess whether it can actually be repeated.
- Check choices affecting values, sample membership, statistics, or visual interpretation. Formal claims need relevant assumptions, uncertainty, and sensitivity checks. Do not invent unrelated plots or tests.
- Separate measured results from mechanism or causal interpretation. Put necessary qualifications next to affected claims.

## Optional files, placement, and configuration

Create COMMAND_LOG.md only for useful execution history beyond a reproduction block; QC_CHECKLIST.md for substantial independent review; FIGURE_INDEX.md for a collection needing navigation. Store each detailed fact once and link to it. Create outputs/, figures/, tables/, and logs/ only when they contain useful artifacts. Preserve intermediates needed for interpretation or reruns; do not generate speculative extras.

Follow established report locations and filenames; no fixed task prefix, run container, or date naming is required. Use an existing task/report area before introducing a new directory. A short report can live directly in the task. The initializer's timestamped layout is an optional convenience, not a project requirement. No project-wide restructuring.

Use --config <path> for existing configuration elsewhere; otherwise load 00_project/scientific_data_report_config.json if present; never create it automatically. Respect language and explicit workflow gates. Legacy required_files/required_dirs generated by the old skill are layout hints, not reasons to recreate empty scaffolding; explicit project instructions still apply. New report_package.profile is lean or audited; explicit --profile overrides it. Configuration creation is opt-in via --init-config.

## Helpers

Use the initializer only for a new saved report:

    python <skill_dir>/scripts/init_report_package.py --root . --task "analysis title" --mode exploratory
    python <skill_dir>/scripts/init_report_package.py --root . --task "analysis title" --task-package analyses/flow --mode formal --profile audited
    python <skill_dir>/scripts/validate_report_package.py <package_dir>

Use --package-dir analyses/flow/baseline for an exact new destination without a timestamp, or --run-dir-name experiments with --task-package. Relative placement/config paths are resolved from --root. Exact destinations must not already exist; update existing reports directly instead. The helper creates only REPORT.md for lean or REPORT.md plus AUDIT_MANIFEST.json for audited. It does not mandate these names for existing projects.

The bundled validator targets helper-style packages. Check existing differently named reports in place against the content and evidence requirements; do not rename reports or create sidecars merely to satisfy this validator. Schema 1 checks describe the historical package contract, not mandatory files for new work; report legacy gaps without inventing missing records.

Use --allow-draft only for unfinished scaffolds. Validation checks structure and recorded consistency; manually verify numerical correctness, interpretation, and actual execution. Schema 1 manifests remain readable; do not bulk-migrate old reports.

Final response: link the report and useful outputs, state the result and material unresolved issues, and describe validation accurately. Avoid listing bookkeeping files.
