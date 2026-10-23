# Audited delivery (schema 2)

Read this only for structured provenance or handoff. Deliver REPORT.md and AUDIT_MANIFEST.json plus useful results. Other files remain optional.

The manifest owns detailed lineage; the report explains the result and links to it. Do not duplicate figures into a separate figures array or copy captions into three places.

## Minimal records

- schema_version: "2.0"; profile: "audited"; generated_at: timestamp.
- task: title and mode; report_package_root: chosen package path.
- audit_status and reproducibility: agree with REPORT.md.
- inputs: entries with id, path, identity (hash, stable dataset version, or documented fallback). Include relevant metadata and provenance. Explain unavailable identity in limitations; it prevents complete status.
- steps: id, inputs (input IDs), method, parameters (object, empty only when none apply), method_basis, evidence_type. Include consequential assumptions, verification, and risks only where informative.
- outputs: id, path (absolute or package-relative), evidence_type, derived_from_inputs and derived_from_steps. Include captions/units for figures and purpose for other outputs.
- checks: objects with check and result; record actual observations, not unchecked boilerplate.
- reproduction: working_directory, procedure, code_identity, environment. Use concrete values or links to authoritative records; include seeds when relevant.
- limitations: material gaps or blockers, with affected outputs/claims. Empty list is valid.
- draft: true on initialization; set false after completing records.

A complete audit needs nonempty inputs, steps, outputs and checks, input identities, observed execution evidence, existing output paths, valid lineage IDs, and a usable rerun record. Complete does not imply high scientific confidence. Do not use unknown or inferred_from_code evidence to certify completion. Partial/exploratory records may explain missing information; never replace missing evidence with invented values.

For inherited results, record existing_file and its provenance. For manual work, record gui_manual and sufficient settings/actions; preserve relevant screenshots only when they add necessary evidence.

## Review

Validate schema and links, then verify substance: critical metadata, transformations, relevant QC, and claims supported by evidence. The validator cannot establish execution history or scientific correctness. Hash validation is not file integrity verification unless a hash is actually recomputed.

Schema 1 packages retain the existing validator and files. Do not rewrite historical records or remove their supporting files automatically.
