# Workflow Contract

Use this contract when building a local literature guide package.

## Inputs

Primary input:

```text
zotero_item_key
```

Optional input:

```text
attachment_key
paper_title
guide_output_root
preferred_terms.yaml
metadata.yaml
```

Local PDF mode is only a fallback/debug route. If no Zotero item key is available, build the guide package but do not prepare automatic Zotero writes.

If only `paper_title` is supplied, resolve it first:

```powershell
python <skill-root>\scripts\zotero_title_search.py `
  --title "<paper title>" `
  --json `
  --output work\title_search_<slug>.json
```

Proceed only when one high-confidence item key is selected. Otherwise ask the user for the Zotero item key.

## PDF Resolution

Default lookup route:

```text
Zotero Desktop local API
http://127.0.0.1:23119/api/users/0
```

Do not read `zotero.sqlite` directly.

Health check:

```powershell
curl.exe -sS http://127.0.0.1:23119/connector/ping
```

Item lookup:

```powershell
curl.exe -sS "http://127.0.0.1:23119/api/users/0/items/<ITEM_KEY>?format=json"
curl.exe -sS "http://127.0.0.1:23119/api/users/0/items/<ITEM_KEY>/children?format=json"
```

Preferred script:

```powershell
python scripts/zotero_local_lookup.py `
  --item-key <ITEM_KEY> `
  --output-dir <package>/source `
  --zotero-data-dir "<ZOTERO_DATA_DIR>"
```

Save:

```text
source/zotero_item.json
source/zotero_children.json
source/zotero_lookup.json
```

For a Zotero item:

```text
0 PDF attachments -> stop and report missing PDF
1 PDF attachment  -> use it
2+ PDF attachments -> stop and require attachment_key
```

Do not guess among publisher version, accepted manuscript, supplementary PDF, notes PDF, or appendix PDF.

PDF attachment filter:

```text
data.itemType == attachment
and one of:
  data.contentType == application/pdf
  data.filename ends with .pdf
  links.enclosure.type == application/pdf
```

PDF path resolution:

```text
1. links.enclosure.href starts with file:/// -> decode as local path
2. data.path is absolute -> use it
3. zotero_data_dir + storage/<attachment_key>/<filename> -> use it if it exists
4. otherwise stop and ask for zotero_data_dir or a manual PDF path
```

If `attachment_key` is supplied, it must match one of the PDF attachments. If it does not match, stop.

## Package Layout

Use:

```text
<guide_output_root>/<zotero_item_key>/
```

Default `guide_output_root`:

```text
outputs/zotero-literature-guides/
```

Package contents:

```text
README.md
source/
  source.pdf
  zotero_metadata.json
extraction/
  extracted.md
  chunks/
  extraction_manifest.json
  extraction_report.md
context/
  global_context.md
  term_glossary.json
  preferred_terms.yaml
batches/
assets/
literature_guide.md
literature_guide.pdf
attachment_manifest.json
guide_validation.json
guide_cleanup_report.json
harness_report.json
harness_report.md
build_log.md
status.json
```

Keep generated source files and logs in the local package. Zotero should receive only the final PDF unless the user explicitly asks otherwise.

## Root README Index

Maintain:

```text
<guide_output_root>/README.md
```

Use this table:

```markdown
| Zotero Key | Year | First Author | Title | Status | Guide PDF | Updated |
|---|---:|---|---|---|---|---|
```

Use item keys for directory names. Keep human-readable metadata in README files, not in directory names.

## Package README

Each package `README.md` should include:

```markdown
# 文献导读包

- Zotero item key:
- Zotero source attachment key:
- Zotero guide attachment key:
- 标题:
- 作者:
- 年份:
- DOI:
- 源 PDF:
- 导读 PDF:
- 导读 Markdown:
- 解析报告:
- 构建日志:
- 当前状态:
- Zotero 挂回状态:
```

## State

Store detailed state in `status.json`. Use a simplified status in README indexes.

In batch processing, package state is authoritative. Do not infer completion from subagent IDs, subagent lookup status, or heartbeat files. A package is complete only according to local artifacts:

```text
status.json
attachment_manifest.json
harness reports
literature_guide.pdf
zotero_attach_report.json after attach
```

If every active package is complete or waiting at `duplicate gate`, `PDF gate`, or another user decision gate, stop agent monitors and remove heartbeat files immediately.

Simplified statuses:

```text
building
needs-review
ready-to-attach
attached
failed
```

Suggested detailed pipeline states:

```text
initialized
metadata_loaded
pdf_resolved
chunked
extracted
extraction_warn
extraction_failed
indexed
guide_drafting
guide_drafted
guide_warn
guide_failed
pdf_rendered
ready_to_attach
attached
attach_failed
```

If `translation_model` is present in `status.json`, the package is draft-model generated and must remain `needs-review` until Codex or a human has reviewed the paragraph translations/explanations. Do not promote such a package to `ready_to_attach` by structure validation alone.

Use separate Zotero attachment identity fields:

```json
{
  "zotero_item_key": "ABCD1234",
  "zotero_source_attachment_key": "SOURCEPDF1",
  "zotero_guide_attachment_key": null,
  "state": "ready_to_attach",
  "status": "ready-to-attach"
}
```

After successful attach, set `zotero_guide_attachment_key` to the new `文献导读.pdf` child key and keep `zotero_source_attachment_key` unchanged. Do not use a generic `zotero_attachment_key` field unless it is explicitly scoped.

## MinerU Local API Extraction

Default route:

```text
local MinerU precise parsing API
POST http://localhost:18000/file_parse
```

Default request fields:

```text
backend=pipeline
parse_method=auto
return_md=true
return_content_list=true
return_images=true
formula_enable=true
table_enable=true
image_analysis=false
```

Use `formula_enable=false` or `table_enable=false` only for fast smoke tests or when deliberately isolating text extraction. Production literature guides should keep formulas and tables enabled.

Use this production local parse shape:

```powershell
curl.exe -sS -X POST http://localhost:18000/file_parse `
  -F "files=@work\mineru_smoke_test.pdf" `
  -F "backend=pipeline" `
  -F "parse_method=auto" `
  -F "return_md=true" `
  -F "return_content_list=true" `
  -F "return_images=true" `
  -F "formula_enable=true" `
  -F "table_enable=true" `
  -F "image_analysis=false" `
  -o outputs\mineru_smoke_result.json
```

For a fast text-only smoke test, it is acceptable to set `parse_method=txt`, `formula_enable=false`, and `table_enable=false`, but do not use those settings for final literature-guide extraction.

Observed successful local response shape:

```json
{
  "task_id": "...",
  "status": "completed",
  "backend": "pipeline",
  "version": "3.2.3",
  "results": {
    "file_stem": {
      "md_content": "...",
      "content_list": "[{\"type\":\"text\",\"text\":\"...\",\"bbox\":[...],\"page_idx\":0}]"
    }
  }
}
```

Save:

```text
extraction/mineru_result.json
extraction/extracted.md
extraction/content_list.json
assets/
asset_manifest.json
```

If `content_list` is returned as a JSON string, parse it and save the decoded list to `content_list.json`.

Do not infer the full visual/formula asset set only from Markdown image links in `extracted.md`. MinerU may return displayed formulas as `content_list` entries with `img_path` and LaTeX text while `md_content` contains few or no image links. Use `asset_manifest.json` as the authoritative asset inventory for final guide embedding.

Record in `build_log.md`:

```text
service: local MinerU
endpoint: http://localhost:18000/file_parse
backend
parse_method
task_id
version
status_url
result_url
request fields
input PDF path
output files
```

## Asset Capture Requirement

Final reading PDFs must include paper-sourced visual assets that are needed to understand the guide:

```text
figures
tables rendered as images when Markdown table structure is degraded
displayed equations or formula images
important diagrams and captions
```

Preferred asset sources:

```text
1. MinerU returned images/assets
2. MinerU content_list bounding boxes plus source PDF page crops
3. full-width source PDF page crop for a figure/equation when region crop is unavailable
```

Save all source-derived assets under:

```text
assets/
asset_manifest.json
```

Each `asset_manifest.json` entry should include:

```json
{
  "asset_id": "fig_001",
  "type": "figure|table|formula|page_crop",
  "source": "mineru|pdf_crop",
  "source_pdf_page": 4,
  "bbox": [0, 0, 0, 0],
  "path": "assets/fig_001.png",
  "caption_or_label": "Figure 1"
}
```

If a guide-worthy figure/table/displayed formula cannot be extracted or cropped, validation should be `warn` or `fail`. Do not ship a clean `pass` guide that only tells the reader to check the source PDF for required figures or formulas.

## MinerU Fallback and Chunking

Use MinerU free Agent/lightweight API only when local MinerU is unavailable or the user explicitly requests cloud fallback.

Do not require `MINERU_API_TOKEN` for the fallback route. Do not auto-switch to paid/precise cloud APIs.

If the PDF exceeds the free API's practical limits, split by page range:

```text
page_chunk_size = 10
chunk_overlap = 0
retry = 3
rate_limit_sleep = 3-10 seconds
```

Save chunks:

```text
extraction/chunks/chunk_001.md
extraction/chunks/chunk_001_meta.json
```

Then merge into:

```text
extraction/extracted.md
extraction/extraction_manifest.json
extraction/extraction_report.md
```

Also use 10-page chunking for local MinerU only when full-file parsing repeatedly times out or fails. Prefer full-file local parsing first.

## Semantic Paragraph Reconstruction

Do not treat raw Markdown line breaks, PDF visual lines, page-column breaks, or MinerU content blocks as final natural paragraphs.

When `extraction/content_list.json` is available, start with:

```powershell
python scripts/build_paragraph_index.py `
  --content-list <package>/extraction/content_list.json `
  --output <package>/extraction/paragraph_index.json `
  --boundary-report <package>/extraction/paragraph_boundary_report.md
```

Then inspect and repair the generated index where the report or the paper structure indicates uncertain boundaries. The script is a conservative starting point, not a substitute for semantic reconstruction.

Build `paragraph_index.json` after a semantic reconstruction pass:

```text
merge:
  PDF visual line breaks inside one sentence
  hyphenated words split at line ends
  parser blocks that are fragments of the same natural paragraph
  paragraph fragments split only by page/column boundary

split:
  parser blocks that contain multiple complete semantic paragraphs
  heading + body accidentally merged into one block
  figure/table caption + body paragraph accidentally merged

preserve:
  original section order
  natural paragraph order
  complete formulas and citation markers
  figure/table captions as their own caption units when appropriate
```

Do not merge semantically distinct paragraphs just because they are short or adjacent. Do not split one semantic paragraph only because the PDF rendered it across lines, columns, or pages.

When the boundary is uncertain, keep the safest semantic unit and record it:

```text
paragraph_boundary_report.md
paragraph_index.json records[].boundary_confidence = high|medium|low
paragraph_index.json records[].boundary_note = "..."
```

If many paragraph boundaries are uncertain, set extraction QA to `warn` or `fail` depending on severity.

## Extraction QA

Before drafting, check:

```text
extracted.md exists and is non-empty
sections are detected
paragraph count is plausible
paragraph boundaries are semantic rather than raw PDF line breaks
page/chunk coverage is complete
chunk order is correct
headers/footers/page numbers are not dominant
figures or figure links are recorded when present
formulas and citation markers are preserved or flagged
guide-worthy figures/tables/displayed formulas have local assets or explicit warn/fail records
References is detected and excluded from paragraph-by-paragraph translation
```

QA status:

```text
pass -> continue
warn -> continue and record risk in build_log.md
fail -> stop
```

If extraction is degraded, do not invent missing text, formulas, tables, or figures. Record the risk and require checking the original PDF.

## Guide Validation Before Rendering

Run validation before `literature_guide.pdf` is rendered. A failing guide must not be rendered, indexed as ready, or attached to Zotero.

First clean generated Markdown:

```powershell
python scripts/clean_guide_markdown.py `
  --guide <package>/literature_guide.md `
  --asset-manifest <package>/asset_manifest.json `
  --in-place `
  --report <package>/guide_cleanup_report.json
```

If `guide_cleanup_report.json` reports removed HTML comments or cleared formula image alt text, record the count in `build_log.md`. Do not preserve commented-out mojibake headings, duplicate paragraph block labels, or renderer workarounds in the final Markdown source.

Formula/equation image assets must be embedded without non-empty Markdown alt text, otherwise Pandoc may render them as numbered figures such as `Figure 37: equation_158`. True paper figures may have meaningful captions; formula images should be visually centered source-derived equations, not figure-captioned objects.

Formula rendering defaults to MinerU-recognized LaTeX after compile validation. Run `scripts/validate_formula_latex.py` and save `formula_latex_validation.json` before inserting displayed formulas. Use a source-derived formula image only for formulas whose recognition is missing or whose LaTeX validation failed, and record the fallback reason in the build log/report.

Render production PDFs with Markdown math parsing enabled (`markdown+tex_math_dollars+tex_math_single_backslash`) so validated formula LaTeX is rendered. Do not solve a formula compile failure by disabling math parsing globally; identify the failing formula with `validate_formula_latex.py` and fall back only that formula to its source image.

Reader-facing guide text must not expose internal asset IDs such as `equation_030`, `image_059`, or `table_012`. Keep those IDs in `asset_manifest.json` and logs. Use `公式（源页 x）`, `图像（源页 x）`, or the paper's actual figure/table label in the guide.

Preferred production validation:

```powershell
python scripts/validate_guide.py `
  --guide <package>/literature_guide.md `
  --index <package>/extraction/paragraph_index.json `
  --assets-dir <package> `
  --asset-manifest <package>/asset_manifest.json `
  --require-embedded-assets `
  --require-compact-blocks `
  --require-inline-assets `
  --require-image-captions `
  --allow-latex-formula-assets `
  --formula-latex-report <package>/formula_latex_validation.json `
  --json
```

This validation is expected to fail when:

```text
the `原文` block is only a locator or summary
the guide says it does not repeat English originals
paragraph IDs are Markdown headings such as `### P001`
recoverable figures/tables/formulas are not embedded in Markdown
local image links point to missing files
```

Only render the PDF after the validator returns `pass`, or after a deliberate `warn` state is recorded in `build_log.md` with the exact unrecoverable extraction reason.

## Harness Gate

Run `scripts/literature_guide_harness.py` after paragraph-index repair, after Markdown assembly, after PDF rendering, and before any Zotero write. It is a package gate, not a prose generator.

Draft-stage example:

```powershell
python <skill-root>\scripts\literature_guide_harness.py `
  --package <package> `
  --workspace <guide_output_root_parent> `
  --stage draft `
  --run-validator `
  --json-output <package>/harness_report.json `
  --md-output <package>/harness_report.md
```

Stage meanings:

```text
draft      literature_guide.md exists; PDF and attachment manifest are not required
rendered   literature_guide.pdf must exist
pre-attach literature_guide.pdf and ready_to_attach manifest must exist
```

For `pre-attach`, `status.json` must also have:

```json
{
  "state": "ready_to_attach",
  "status": "ready-to-attach"
}
```

If `translation_model` is present, `pre-attach` must fail unless Codex or human content review is recorded, for example:

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

The review record must include reviewer identity, review time, and review scope or report evidence. A bare `content_review_status` field is not enough.

Build `attachment_manifest.json` only after the package status and harness state agree:

```powershell
python <skill-root>\scripts\build_attachment_manifest.py `
  --zotero-item-key <item_key> `
  --package-dir <package> `
  --validation-status <pass|warn|fail> `
  --status-json <package>/status.json `
  --harness-report-json <package>/harness_report.json `
  --output <package>/attachment_manifest.json
```

Do not pass `--allow-harness-warn` for external/local model draft warnings. Use it only for an explicitly accepted non-content extraction/rendering warning.

Harness status:

```text
fail -> stop; do not render, prepare manifest, or attach
warn -> continue only for engineering work; keep needs-review unless the warning is an explicit accepted extraction risk
pass -> current stage gate passed; still perform content-quality review where required
```

Only `pre-attach` with `status=pass` can be used as evidence for Zotero writing. Draft/rendered `pass` or command exit code 0 does not imply attachment eligibility.

For batch attach, produce a user-facing gate table before writing Zotero:

```text
ready          all local gates pass and no duplicate guide is detected
warn           local gate warning requires explicit acceptance
duplicate gate existing guide attachment detected; ask replace / keep-both / cancel
PDF gate       source or guide PDF missing/unverified
blocked        validation, harness, status, or manifest blocks attach
```

Only the rows explicitly approved by the user can advance to Zotero writing.

Harness must catch:

```text
PowerShell-created UTF-16 JSON reports
paragraph_index guided count, Markdown IDs, status.json, and label-count mismatches
parser fragments still marked for guide
missing README.md or build_log.md
caption triples missing after source figures/tables
guide_validation fail/stale state
external/local model draft output incorrectly promoted beyond needs-review
reader-facing provenance such as "生成说明" or "本地 Ollama"
```

## Batching

Draft paragraph guide content in batches by section and paragraph range.

Default split:

```text
8-12 natural paragraphs per batch
3000-5000 English words per batch
```

If a section is longer than the threshold, split into numbered parts. Keep individual natural paragraphs intact.

For each batch, provide:

```text
global context:
  metadata
  one-sentence summary
  section tree
  glossary
  writing rules

section context:
  current section title
  section purpose
  paragraph range

local paragraphs:
  P identifiers
  original text
  figure/table references
  formula status

continuity state:
  established terminology
  key variables and abbreviations
  3-5 bullets from the previous batch
  next section or paragraph preview when available
```

Save:

```text
batches/batch_003_input.json
batches/batch_003_output.md
batches/batch_003_validation.json
```

Update `context/term_glossary.json` after each batch. If `preferred_terms.yaml` exists, it overrides automatic terminology.
