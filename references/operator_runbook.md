# Operator Runbook

Use this runbook as the concrete step-by-step workflow for one paper. Batch processing is only a loop around this single-paper runbook.

For batch work, subagents may generate package files only. Do not let a generation subagent write Zotero. Judge package completion by local artifacts (`status.json`, `attachment_manifest.json`, harness reports, rendered PDF), not by subagent status or agent ID. If all active subagents are complete or blocked at a user decision gate, stop/close the agents and delete heartbeat files immediately.

## 0. Preconditions

Use PowerShell UTF-8 setup before any command that touches Chinese paths or text:

```powershell
$env:PYTHONIOENCODING='utf-8'
$OutputEncoding=[System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding=[System.Text.UTF8Encoding]::new($false)
```

Check local services:

```powershell
curl.exe -sS http://127.0.0.1:23119/connector/ping
curl.exe -sS http://localhost:18000/docs
```

If Zotero is not reachable, stop before any Zotero item workflow. If MinerU is not reachable, either stop or use the documented fallback route; do not silently generate a guide from a weak PDF read.

When the OpenAI Zotero plugin is installed, prefer its helper for Zotero readiness:

```powershell
$zoteroHelper = "<plugin-root>\skills\zotero\scripts\zotero.py"
py -3 $zoteroHelper status --json
```

Use the helper path from the active Zotero plugin cache. If the helper is not found or does not run, fall back to `curl.exe` and this skill's bundled scripts.

## 1. Resolve The Zotero Item

Default input is a Zotero item key.

If the user gives a title, resolve it to an item key first:

```powershell
py -3 $zoteroHelper search "<paper title>" --json --with-bibtex-keys
```

If the Zotero plugin helper is unavailable or returns ambiguous output, fall back to:

```powershell
python <skill-root>\scripts\zotero_title_search.py `
  --title "<paper title>" `
  --json `
  --output work\title_search_<slug>.json
```

Proceed only when exactly one high-confidence item is selected. If no item or multiple plausible items are returned, show candidates and ask for the Zotero item key.

## 2. Create The Package

Use a production package under:

```text
<workspace>/outputs/<item_key>/
```

Create directories:

```powershell
$pkg="outputs\<item_key>"
New-Item -ItemType Directory -Force -Path "$pkg\source","$pkg\extraction","$pkg\context","$pkg\batches","$pkg\assets" | Out-Null
```

Do not use a root-level `<item_key>/` folder for production output. Temporary experiments may live under `agent-tests/`.

## 3. Resolve Metadata And Source PDF

```powershell
python <skill-root>\scripts\zotero_local_lookup.py `
  --item-key <item_key> `
  --output-dir <package>\source `
  --zotero-data-dir "<ZOTERO_DATA_DIR>" `
  --json
```

The Zotero plugin helper can supplement this lookup:

```powershell
py -3 $zoteroHelper children <item_key> --json
py -3 $zoteroHelper file-url <attachment_key>
py -3 $zoteroHelper export-bibtex --item-key <item_key> --out <package>\source\zotero_item.bib
```

Still keep `source/zotero_item.json`, `source/zotero_children.json`, and `source/zotero_lookup.json` from the package lookup script because they are the workflow's provenance files.

Expected files:

```text
source/zotero_item.json
source/zotero_children.json
source/zotero_lookup.json
```

If the lookup reports no PDF, stop. If it reports multiple PDFs, require `attachment_key`. If one PDF is selected, copy it into:

```text
source/source.pdf
```

Record source PDF SHA256 in `build_log.md`.

## 4. MinerU Extraction

Run local MinerU with production options:

```powershell
powershell -ExecutionPolicy Bypass `
  -File <skill-root>\scripts\mineru_local_parse.ps1 `
  -PdfPath <package>\source\source.pdf `
  -OutputJson <package>\extraction\mineru_result.json
```

Normalize output:

```powershell
python <skill-root>\scripts\extract_mineru_result.py `
  --input <package>\extraction\mineru_result.json `
  --output-dir <package>\extraction `
  --assets-dir <package>\assets `
  --asset-manifest <package>\asset_manifest.json
```

Required outputs:

```text
extraction/mineru_result.json
extraction/extracted.md
extraction/content_list.json
asset_manifest.json
```

Stop if `content_list.json` is missing when the paper has figures/formulas/tables.

## 5. Build And Repair The Paragraph Index

```powershell
python <skill-root>\scripts\build_paragraph_index.py `
  --content-list <package>\extraction\content_list.json `
  --output <package>\extraction\paragraph_index.json `
  --report <package>\extraction\paragraph_boundary_report.md
```

Manual repair is expected. Treat natural paragraphs as semantic units:

- mark title, authors, affiliations, dates, headers, footers, and page numbers as `metadata` and `guide=false`;
- mark single-word parser fragments such as `and` or `where` as `parser_fragment` and `guide=false`;
- merge line-break fragments caused by PDF parsing;
- do not renumber paragraph IDs after exclusions;
- record every exclusion in `boundary_note`.

Run draft harness after index repair:

```powershell
python <skill-root>\scripts\literature_guide_harness.py `
  --package <package> `
  --workspace <workspace> `
  --stage draft `
  --json-output <package>\harness_index_report.json `
  --md-output <package>\harness_index_report.md
```

This may fail before Markdown exists; use it to catch layout/encoding problems early, then continue only after the paragraph index is defensible.

## 6. Draft The Guide Content

Default: Codex drafts the final paragraph translations and explanations in batches. Use batches by section and paragraph range.

Batch payload must include:

```text
global context
term glossary
section title
previous/next paragraph IDs
source paragraphs with IDs
nearby figure/formula/table references
```

For every guided paragraph, write:

```markdown
<a id="P001"></a>

**P001**

**原文：** ...

**翻译：** ...

**讲解：** ...
```

If the user explicitly chooses local-model draft mode, keep it as draft only:

```text
status.json translation_model = <model>
status.json status = needs-review
do not put "本地 Ollama" or "生成说明" in literature_guide.md
do not build a ready_to_attach manifest
```

## 7. Restore Figures, Tables, And Formulas

Use `content_list.json` as the source-order stream and `asset_manifest.json` as the asset inventory.

Rules:

- formulas: run `validate_formula_latex.py`, then embed MinerU-recognized LaTeX for formulas that pass; use source formula images only for formulas with missing/failed LaTeX validation;
- true figures/tables: embed source image/table at the nearest source-order paragraph;
- after each figure/table, include `图注原文`, `图注翻译`, and `图注讲解`;
- formula image fallback links should use empty alt text so Pandoc does not generate fake figure captions;
- do not leave recoverable visuals as “需要对照 PDF”.

Formula compile gate:

```powershell
python <skill-root>\scripts\validate_formula_latex.py `
  --asset-manifest <package>\asset_manifest.json `
  --formula-overrides <package>\context\formula_latex_overrides.json `
  --json-output <package>\formula_latex_validation.json `
  --json

Omit `--formula-overrides` when no audited manual formula transcription is needed.
```

If this report is `fail`, do not disable math parsing globally. Use the report to fall back only failed formulas to images.

## 8. Clean, Validate, And Harness Draft

Clean:

```powershell
python <skill-root>\scripts\clean_guide_markdown.py `
  --guide <package>\literature_guide.md `
  --asset-manifest <package>\asset_manifest.json `
  --in-place `
  --report <package>\guide_cleanup_report.json
```

Write validation JSON through Python, not PowerShell redirection:

```powershell
python <skill-root>\scripts\validate_guide.py `
  --guide <package>\literature_guide.md `
  --index <package>\extraction\paragraph_index.json `
  --assets-dir <package> `
  --asset-manifest <package>\asset_manifest.json `
  --require-embedded-assets `
  --require-compact-blocks `
  --require-inline-assets `
  --require-image-captions `
  --allow-latex-formula-assets `
  --formula-latex-report <package>\formula_latex_validation.json `
  --json
```

Capture that stdout in Python and write UTF-8 `guide_validation.json`.

Then run:

```powershell
python <skill-root>\scripts\literature_guide_harness.py `
  --package <package> `
  --workspace <workspace> `
  --stage draft `
  --run-validator `
  --json-output <package>\harness_report.json `
  --md-output <package>\harness_report.md
```

Do not render if draft harness is `fail`.

## 9. Render PDF And Harness Rendered State

Render with academic layout. Example:

```powershell
pandoc <package>\literature_guide.md `
  -o <package>\literature_guide.pdf `
  --from markdown+tex_math_dollars+tex_math_single_backslash `
  --pdf-engine=xelatex `
  --toc `
  --toc-depth=2 `
  --resource-path ".;<package>" `
  -V mainfont="Times New Roman" `
  -V CJKmainfont="Microsoft YaHei" `
  -V mathfont="Cambria Math" `
  -V geometry:a4paper `
  -V geometry:margin=2cm
```

Check that the PDF exists and is non-empty. Use `pdftotext` when available to confirm:

```text
P001/P002 paragraph IDs are not in the TOC
原文/翻译/讲解 labels appear
图注原文/图注翻译/图注讲解 counts match figure/table assets
no "需要对照PDF" when assets were recoverable
no internal asset IDs such as image_059
validated MinerU formula LaTeX is rendered; image fallback appears only for formulas recorded as failed/missing in `formula_latex_validation.json`
```

Run:

```powershell
python <skill-root>\scripts\literature_guide_harness.py `
  --package <package> `
  --workspace <workspace> `
  --stage rendered `
  --run-validator `
  --json-output <package>\harness_rendered_report.json `
  --md-output <package>\harness_rendered_report.md
```

## 10. Content Review Gate

Structure validation is not content-quality review.

If `translation_model` is present, Codex or a human must review the paragraph translations/explanations before attach. Record review only after actual review:

```json
{
  "content_review": {
    "status": "codex-reviewed",
    "reviewer": "Codex",
    "reviewed_at": "2026-06-08T15:00:00",
    "scope": "all guided paragraphs and figure/table captions",
    "report_path": "content_review_report.md"
  }
}
```

The review record must identify who/what reviewed it, when, and what scope/evidence was reviewed. A bare `content_review_status` field is not enough.

Do not mark a local-model draft as ready merely because validator and rendered harness pass.

## 11. Prepare Attachment Manifest

Only after rendered harness and content review pass:

```powershell
python <skill-root>\scripts\build_attachment_manifest.py `
  --zotero-item-key <item_key> `
  --package-dir <package> `
  --validation-status <pass|warn|fail> `
  --status-json <package>\status.json `
  --harness-report-json <package>\harness_pre_attach_report.json `
  --output <package>\attachment_manifest.json
```

Expected manifest status:

```text
ready_to_attach
```

If manifest status is `blocked`, do not attach.

## 12. Pre-Attach Harness

Before any Zotero write:

```powershell
python <skill-root>\scripts\literature_guide_harness.py `
  --package <package> `
  --workspace <workspace> `
  --stage pre-attach `
  --run-validator `
  --json-output <package>\harness_pre_attach_report.json `
  --md-output <package>\harness_pre_attach_report.md
```

`pre-attach` must fail when:

```text
status.json state/status is still needs-review
translation_model is present without evidence-bearing content_review
attachment_manifest.json is blocked or missing
PDF is missing
validation fails
```

Only `pre-attach status=pass` allows the workflow to proceed to a Zotero write. A command exit code of 0 from a draft/rendered harness is not sufficient evidence for attachment eligibility.

## 13. Attach To Zotero

Only after the user explicitly confirms and all gates pass.

Default attachment:

```text
file: literature_guide.pdf
Zotero title: 文献导读.pdf
mode: stored/imported file
tags: codex-literature-guide, guide-needs-review
```

Use `references/zotero_contract.md` for the confirmed attachment route. The default route is the Zotero Guide Helper plugin, not the debug bridge.

Check the plugin first:

```powershell
curl.exe -sS http://127.0.0.1:23119/guide-helper/health
```

If the endpoint is missing or does not report `plugin=zotero-guide-helper`, recommend installing the bundled XPI:

```text
<skill-root>/assets/zotero-guide-helper/zotero-guide-helper.xpi
```

After the plugin is available, run duplicate preflight:

```powershell
curl.exe -sS "http://127.0.0.1:23119/guide-helper/items/<item_key>/guide-attachments"
```

If duplicates exist, stop and ask for `replace / keep-both / cancel`. The MVP plugin supports duplicate rejection and explicit `keep-both`; replace/delete remains a manual or future route.

Attach with:

```powershell
python <skill-root>\scripts\zotero_guide_helper_attach.py `
  --manifest <package>\attachment_manifest.json `
  --report <package>\zotero_helper_attach_report.json
```

For batch attach, first produce a decision table with one row per item key:

```text
ready
warn
duplicate gate
PDF gate
blocked
```

Attach only rows the user explicitly approves. A duplicate gate must be resolved before writing that row.

Use the Better BibTeX/ztoolkit debug bridge only if the Zotero Guide Helper plugin cannot be installed or the user explicitly asks for fallback. Do not start with `/connector/saveAttachment`; it depends on an active Connector save session and is not reliable for arbitrary existing items.

Verify with Zotero local API and SHA256 before success:

```text
new child exists under parent item
linkMode is imported_file
contentType is application/pdf
title is 文献导读.pdf
tags include both defaults
Zotero storage PDF SHA256 equals package literature_guide.pdf SHA256
```

Only after these pass, update `zotero_attach_report.json`, `attachment_manifest.json`, and `status.json` to `attached`.

The final `status.json` and `attachment_manifest.json` must preserve both:

```text
zotero_source_attachment_key = original paper PDF attachment used as input
zotero_guide_attachment_key = newly imported 文献导读.pdf attachment
```

Do not confuse the source PDF child key with the guide PDF child key. In batch writes, create one `zotero_attach_report.json` or `zotero_helper_attach_report.json` per item and verify each row independently with local API, stored-file mode, tags, and SHA256.

## Successful Patterns To Preserve

- Keep raw Zotero API responses and MinerU raw JSON. They make failures diagnosable.
- Preserve item key as package identity. Human titles belong in README, not directory names.
- Exclude metadata and parser fragments in `paragraph_index.json`; do not renumber IDs after exclusion.
- Use harness stages. `draft warn` can be acceptable for model-draft packages; `pre-attach fail` is correct until review is recorded.
- Keep provenance in logs/status, not reader-facing `literature_guide.md`.
- Generate JSON with Python UTF-8 writes. Avoid PowerShell redirection for reports.
- Build manifest only after `status.json` and harness state agree.

## Known Failure Patterns

- PowerShell writes UTF-16 `guide_validation.json`; harness must fail.
- A generated `attachment_manifest.json` says `ready_to_attach` while `status.json` is still `needs-review`; manifest builder must block.
- Ollama/local-model cache is used and then treated as final content; harness and manifest must block pre-attach.
- Single-word parser fragments such as `and` or `where` remain guided paragraphs; validator/harness must fail.
- Reader-facing guide contains `本地 Ollama`, `生成说明`, `技术意译`, or `需要对照PDF`; fix content before rendering/attach.
