---
name: scientific-data-report
description: Use when processing scientific data or reporting scientific data-processing work, especially when the user needs an auditable report package with provenance, commands, parameters, input fingerprints, output lineage, QC checks, scientific assumptions, risks, reproducibility status, and claims boundaries.
---

# Scientific Data Report

Use this skill for any scientific data processing task where results may support figures, tables, reports, manuscripts, decisions, or later review. The output is a data-processing report package, not just prose.

## Core Rule

Deliver an auditable package that lets the user check what was done, why it was scientifically defensible, what evidence proves it was executed, and what remains uncertain.

Never blur missing provenance. If key information is unavailable, stop, ask, or downgrade the report status.

## Reader Orientation Rule

Default `REPORT.md` is a reader-first processing summary, not the full audit record. It must be self-contained for a reader who knows only the broad project topic, not the run-internal folder scan, script names, step IDs, abbreviations, or prior agent context.

Keep orientation small but explicit. At the top of `REPORT.md`, give only the few context facts needed to understand the processing flow:

- the project/problem in one sentence;
- the concrete dataset/input family in one sentence;
- the processing goal in one sentence;
- definitions for any IDs, abbreviations, variables, or labels reused in the report.

Do not flood the report with background, but never drop unexplained internal context into it. In `REPORT.md`, do not mention a file, variable, parameter, task slug, figure ID, step ID, abbreviation, method label, or prior result without either defining it in the orientation section or making its meaning obvious in the same row/sentence.

Avoid context cliffs: bare path lists, unexplained filenames, unexplained folder-derived facts, unexplained acronyms, and statements that assume the reader has read the source scripts, manuscript, or previous reports. Use plain-language labels next to technical IDs. Put detailed provenance, fingerprints, environment details, full QC surfaces, and expanded figure metadata in `AUDIT_MANIFEST.json`, `COMMAND_LOG.md`, `QC_CHECKLIST.md`, and `FIGURE_INDEX.md`; `REPORT.md` should summarize and link to those files.

## Project Configuration

Before creating or revising a report package, look for this file under the project root:

```text
00_project/scientific_data_report_config.json
```

If it exists, load it and follow it before applying generic defaults. Supported configuration keys include:

- `default_language`: `zh`, `en`, or `auto`. Use this for all user-facing report documents unless the user explicitly asks otherwise.
- `report_style.context_policy`: default `minimal_but_self_contained`; keep `REPORT.md` concise but never context-broken.
- `report_style.technical_id_policy`: require plain-language labels beside technical IDs, filenames, variables, step IDs, and output IDs.
- `report_style.figure_caption_detail`: use compact captions in `REPORT.md` and complete captions in `FIGURE_INDEX.md`.
- `workflow.formal_requires_plan_confirmation`: whether formal mode must stop after `PROCESSING_PLAN.md` unless preapproved.
- `workflow.prefer_task_package_runs`: whether task packages should be preferred for placement.

If `00_project/` exists but the config file is missing, generate it before creating new report packages. If `00_project/` is missing, run the config wizard to create `00_project/` and the config file. Use the helper script when possible:

```bash
python <skill_dir>/scripts/init_report_package.py --root . --init-config
```

Wizard defaults should be conservative: `default_language=zh` for Chinese-language research projects, `context_policy=minimal_but_self_contained`, `technical_id_policy=technical_ids_must_have_plain_language_labels`, `formal_requires_plan_confirmation=true`, and `prefer_task_package_runs=true`. Ask only when the answer is genuinely project-specific; otherwise write the default and let the user edit the JSON later.

## Required Package

Package placement:

1. If the project follows the `research-folder-organizer` task-package layout and this work belongs to one concrete task, place the report package under that task:

   ```text
   <project_root>/10_tasks/T###_short_slug/runs/YYYYMMDD_HHMMSS_<task_slug>/
   ```

2. If the output is a cross-task stage summary, reviewer-facing report, or project-level audit, place it under:

   ```text
   <project_root>/50_reports/YYYYMMDD_HHMMSS_<task_slug>/
   ```

3. If no project structure is known, use:

```text
<project_root>/data_processing_reports/YYYYMMDD_HHMMSS_<task_slug>/
```

If a project has any other established reports/runs structure, follow it. Always record the chosen path in `AUDIT_MANIFEST.json`.

Required files:

```text
PROCESSING_PLAN.md
REPORT.md
AUDIT_MANIFEST.json
COMMAND_LOG.md
QC_CHECKLIST.md
FIGURE_INDEX.md
outputs/
figures/
tables/
logs/
```

`AUDIT_MANIFEST.json` is the machine-readable source of truth. YAML is optional.

## Helper Scripts

Create or refresh the project-level config when needed:

```bash
python <skill_dir>/scripts/init_report_package.py --root . --init-config
```

Create a package with:

```bash
python <skill_dir>/scripts/init_report_package.py --root . --task "short task title" --mode exploratory
```

For a known task package:

```bash
python <skill_dir>/scripts/init_report_package.py --root . --task "short task title" --task-package 10_tasks/T012_some_task --mode formal
```

For a cross-task report:

```bash
python <skill_dir>/scripts/init_report_package.py --root . --task "short task title" --cross-task-report --mode formal
```

Use `--mode formal` for manuscript, final figure, final table, or conclusion-supporting work.

Validate before final delivery with:

```bash
python <skill_dir>/scripts/validate_report_package.py <package_dir>
```

For a freshly initialized empty template only:

```bash
python <skill_dir>/scripts/validate_report_package.py <package_dir> --allow-draft
```

If a script cannot run, create the same structure manually and record the failure in `COMMAND_LOG.md`.

## Processing Modes

- `formal`: final/report/manuscript/conclusion-supporting processing. Write `PROCESSING_PLAN.md` first and wait for user confirmation before executing, unless the user explicitly preapproved execution.
- `exploratory`: exploratory analysis may proceed without waiting, but `audit_status` must be `exploratory` and conclusions must stay provisional.
- `repair`: fix or patch an existing data-processing workflow. Record the defect, changed code, and verification.
- `reproduce`: rerun or verify an existing workflow. Record exact reproduction scope and deviations.

If the user says to directly process and report, still write `PROCESSING_PLAN.md` and set `plan.user_preapproved = true`.

## Hard Constraints

- Treat raw data as read-only. Do not modify, move, rename, delete, or overwrite original data unless the user explicitly authorizes it.
- Never silently overwrite outputs. Use a new timestamped run directory if output paths already exist.
- Separate executed evidence from inferred descriptions.
- Existing output files are `existing_file`, not `executed_this_session`.
- If a step is inferred from code or filenames, label it `inferred_from_code`.
- If provenance, metadata, units, scale, sampling, code version, parameters, or execution evidence are missing, block or downgrade.
- For non-scripted work such as GUI, Excel, Origin, MATLAB interactive work, COMSOL GUI, or notebooks, capture configuration, screenshots/exports when relevant, file fingerprints, and exact manual steps. Reproducibility is at most `partially_reproducible` unless the workflow can be rerun deterministically.

## Required Status Fields

Set these near the top of `REPORT.md` and in `AUDIT_MANIFEST.json`:

```text
Audit status: complete | partial | blocked | exploratory
Reproducibility: reproducible | partially_reproducible | not_reproducible | not_assessed
Scientific confidence: high | medium | low | not_assessed
```

`complete` requires reproducible outputs, complete provenance, complete input fingerprints or documented fallback fingerprints, no unresolved blockers, and no unknown critical fields.

## Plan Before Processing

`PROCESSING_PLAN.md` must state:

- Objective and whether the work is `formal`, `exploratory`, `repair`, or `reproduce`.
- Raw inputs to be used and expected metadata.
- Planned steps, algorithms, thresholds, filters, fitting/statistics, unit conversions, and visualization choices.
- Method basis for each key choice: user instruction, paper, instrument metadata, code default, domain convention, or exploratory judgment.
- Expected outputs and review checkpoints.
- What would block or downgrade the result.

For `formal` work, stop after writing the plan until the user confirms.

## What Counts As A Key Step

Any operation that can affect data values, sample membership, coordinates, units, time interpretation, statistics, visual interpretation, or claims is a key step.

Key steps include:

- Reading, conversion, channel/variable selection.
- Sample filtering, region/time cropping, bad-point or outlier removal.
- Unit conversion, coordinate transformation, calibration, normalization, nondimensionalization.
- Filtering, smoothing, interpolation, resampling, registration, denoising.
- Fitting, statistical testing, error estimation, uncertainty propagation.
- Parameter or threshold choice, including defaults.
- Aggregation or post-processing that affects figures, tables, or core values.
- Visualization choices that affect interpretation: color limits, axis truncation, log scales, normalized display.

Every key step must appear in `AUDIT_MANIFEST.json` with:

```text
method_basis
assumptions
risks
verification
```

Non-key operational steps may be summarized in `COMMAND_LOG.md`.

## Provenance Requirements

Each important input must record:

- Path and role.
- Whether it existed at runtime.
- Size and modified time when available.
- Full SHA256 for small/medium files.
- Fallback fingerprint for very large files or directory datasets: file count, total size, modified-time summary, key metadata hash, or sampled-block hash.
- Format, dimensions/shape, dtype, units, coordinates, sampling rate, or other scientific metadata where relevant.

For Zarr, HDF5, MAT, NetCDF, TIFF stacks, and similar structured data, record dataset/group names, shapes, dtypes, attrs, and units where available.

If even fallback fingerprinting is absent, the report cannot be `complete`.

## Output Lineage

Every figure, table, processed dataset, model, or statistic used in conclusions must trace back to:

- Input IDs.
- Step IDs.
- Script/function/command or evidence source.
- Parameters and method basis.

The report cannot just say "generated figure X." It must state how X was derived.

## Figures And Captions

Reports that produce, audit, or rely on figures must include figure references and captions, but keep `REPORT.md` captions compact.

Required behavior:

- Put generated or copied review figures under `figures/`, or reference existing figure paths if copying would duplicate large files.
- Add every review-relevant figure to `FIGURE_INDEX.md`.
- In `REPORT.md`, embed or link only the figures needed to follow the processing outcome.
- In `REPORT.md`, use one-sentence captions that state what is shown in plain language, define or avoid unfamiliar input/step IDs, give the key unit/scale/colorbar meaning, and add one caveat if needed.
- In `FIGURE_INDEX.md` and `AUDIT_MANIFEST.json`, keep the complete figure metadata: data source, processing step IDs, key parameters, units/scale/colorbar meaning, caption, caveats, `derived_from_steps`, and `derived_from_inputs`.
- If a figure is pre-existing, label it `existing_file` and record its source path/fingerprint when possible.
- If a figure is only illustrative or exploratory, label it as such; do not let it support a formal claim.

Minimal `REPORT.md` caption pattern:

```text
Figure N. What is shown; input/step IDs; key unit/scale; one caveat if needed.
```

## Execution Evidence

`COMMAND_LOG.md` records actual operations only:

- Commands run, working directories, timestamps, exit status, important output.
- Script paths, function entry points, notebook paths/cells, software versions.
- Failures and corrections.

Use these evidence labels in `AUDIT_MANIFEST.json`:

```text
executed_this_session | existing_file | inferred_from_code | user_provided | gui_manual | unknown
```

`unknown` requires downgrade or blockage.

## Environment And Code Version

Record:

- Working directory and OS.
- Python/MATLAB/R/COMSOL/Origin/Excel or other relevant runtime versions.
- Important package versions.
- Git repo, commit, and dirty status when applicable.
- Script/notebook/model file paths, Git status, and SHA256 when not fully tracked.
- Random seeds and nondeterministic settings.

If environment or code version cannot be confirmed, reproducibility is at most `partially_reproducible`.

## Scientific Review

`QC_CHECKLIST.md` is the complete scientific review surface. `REPORT.md` should contain only the highest-signal review outcome:

- 3-5 manual review targets, blockers, or downgrade reasons.
- One-line status for units/coordinates/scale/calibration, key filters/statistics/thresholds, and figure readability.
- Any sensitivity or plausibility result that changes confidence.

`QC_CHECKLIST.md` must still include:

- Unit and coordinate checks.
- Sampling rate, time step, spatial scale, and calibration checks.
- Filtering, smoothing, interpolation, fitting, statistics, and threshold justification.
- Outlier/missing-data policy.
- Sensitivity checks for important thresholds, or explicit `not_assessed`.
- Physical/statistical plausibility checks.
- What would invalidate the result.
- The 3-5 highest-priority manual review targets for formal outputs.
- Figure-level checks: axes, units, colorbars, legends, annotations, cropping, normalization, and caption accuracy.

Do not write "no issue found" unless the attack surfaces checked are listed.

## Claims Boundary

Separate data-processing conclusions from scientific interpretation. Keep `REPORT.md` claim boundaries short; store expanded claim lists in `AUDIT_MANIFEST.json` when needed.

- `Claims allowed by this processing`
- `Claims not supported by this processing`
- `Claims requiring external evidence`

Do not turn processed trends into final scientific mechanism claims unless the evidence chain actually supports that.

## Final Response

When finished, tell the user:

- Package path.
- Audit status, reproducibility, and scientific confidence.
- Whether validation passed.
- The most important blockers or manual review targets.

If validation was not run, state why.
