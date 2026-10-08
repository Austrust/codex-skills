---
name: zotero-literature-guide
description: Generate Chinese literature guide packages for Zotero papers from Zotero item keys or local PDFs. Use when the user wants a Zotero-integrated paper reading workflow, PDF-to-Markdown extraction with MinerU, paragraph-by-paragraph original/translation/explanation guides, academic PDF rendering, attachment manifests, or confirmed Zotero attachment/tag updates.
---

# Zotero Literature Guide

Build one Chinese literature guide package for one paper at a time. Treat batch processing as an outer loop over the same single-paper workflow.

## Operating Principles

- Use the Zotero item key as the default input. Accept a local PDF plus `metadata.yaml` only for temporary or debugging runs.
- Do not modify Zotero during guide generation. Generate local files and an attachment manifest first; attach to Zotero only after explicit confirmation.
- Use local MinerU precise parsing API as the default extraction route when `http://localhost:18000/file_parse` is available. Use MinerU free Agent/lightweight API only as a fallback.
- Preserve paper structure. The paragraph guide must follow the original section and paragraph order.
- Treat natural paragraphs as semantic units, not raw PDF visual lines or parser blocks. Repair PDF-caused line breaks and false paragraph splits before drafting.
- Restore the paper's source order for figures, tables, and displayed formulas inside the paragraph guide. Do not move all visual/formula assets into a front-loaded gallery when `content_list.json` provides their order.
- Preserve the actual original paragraph text in the guide. Do not replace original text with a pointer to `paragraph_index.json` or the source PDF.
- The `翻译` block must be a faithful translation of the full `原文` paragraph, not a summary, technical paraphrase, or section-level interpretation. Put compression and explanation only in `讲解`.
- Treat translation fidelity as a hard production gate. For final guide packages, run an independent source-faithfulness pass after drafting or revision, preferably by a subagent when subagents are available, and record the evidence in `context/translation_fidelity_report.md` or `context/translation_revision_report.md`.
- Insert source figures, tables, and displayed formulas into the guide PDF when they are needed for reading. Displayed formulas default to MinerU-recognized LaTeX after a formula compile gate; use source-derived formula images only as per-formula fallback when recognition is missing or validation fails. Do not leave final guide content as "check the PDF" unless extraction truly failed and validation is `warn` or `fail`.
- Keep the PDF table of contents clean. Paragraph IDs such as `P001` must not appear as TOC entries.
- On Windows/PowerShell, protect UTF-8 Chinese text explicitly. Terminal mojibake is not proof of file corruption, but non-UTF-8 PowerShell stdin can corrupt Chinese text before Python receives it.
- Keep the guide focused on the paper itself. Do not add the user's research context unless it is present in the paper.
- Never guess missing formulas or silently repair degraded extraction. Mark extraction risks and require source PDF checks.
- Codex should draft the final paragraph translations/explanations by default. Do not route paragraph prose through Ollama or another external/local model unless the user explicitly asks for draft-mode generation; such output must remain `needs-review`.
- Treat `scripts/literature_guide_harness.py` as the package gate after indexing, after Markdown assembly, after rendering, and before any Zotero write.
- In batch runs, subagents may only generate local `outputs/<item_key>/` packages. Judge completion by `status.json`, `attachment_manifest.json`, and harness reports, not by subagent IDs or heartbeat status.
- For literature processing that drafts, revises, or audits paragraph translations, use a subagent as the default second pass when available. The subagent must compare `原文` against `翻译`, rewrite unfaithful translation blocks, and report paragraph IDs reviewed; do not let the main agent's first draft be the only fidelity check.
- Stop heartbeat/monitor agents as soon as all active package agents are complete or blocked at a user decision gate. Do not keep reminder loops alive after the work has reached `ready`, `duplicate`, `PDF gate`, or `needs user decision`.
- If the Zotero Guide Helper plugin is installed, use it as the default confirmed guide-PDF attachment writer. It must create a stored `literature_guide.pdf` child, set title `文献导读.pdf`, add the default tags, reject duplicates by default, and return enough data for SHA256 verification.
- Keep the OpenAI Zotero plugin helper for Zotero readiness, library search, children listing, attachment file URLs, indexed full text, BibTeX export, and connector record import; do not confuse it with the Zotero Guide Helper write-back plugin.

## Workflow

1. Resolve input.
   - If given a Zotero item key, read Zotero metadata and locate PDF attachments through Zotero's local API.
   - If the OpenAI Zotero plugin helper exists at `<plugin-root>/skills/zotero/scripts/zotero.py`, run its `status --json` first and prefer its `search`, `children`, `file-url`, `fulltext`, and `export-bibtex` commands for read-only discovery.
   - If given a paper title, use the Zotero plugin helper `search "<title>" --json --with-bibtex-keys` when available; otherwise use `scripts/zotero_title_search.py`. Resolve exactly one high-confidence Zotero item key before continuing; if ambiguous, ask for the item key.
   - Use `scripts/zotero_local_lookup.py` to save `source/zotero_item.json`, `source/zotero_children.json`, and `source/zotero_lookup.json`. The Zotero plugin helper may supplement this with `children` and `file-url`, but it does not replace the package-local raw JSON provenance files.
   - If there is one PDF, use it. If there are no PDFs, stop. If there are multiple PDFs, list candidates and require an `attachment_key`.
   - If given a local PDF, require or create `metadata.yaml`; do not prepare Zotero writes unless an item key is supplied.

2. Create the package.
   - Use `guide_output_root` from config when available.
   - Otherwise use `outputs/zotero-literature-guides/` in the current workspace.
   - Use `<guide_output_root>/<zotero_item_key>/` as the paper package directory.
   - Create or update both the package `README.md` and root `README.md` index.

3. Extract the PDF.
   - Prefer local MinerU API: `POST http://localhost:18000/file_parse` with `backend=pipeline`, `parse_method=auto`, `return_md=true`, `return_content_list=true`, `return_images=true`, `formula_enable=true`, and `table_enable=true`.
   - Save the raw response as `extraction/mineru_result.json`.
   - Extract `results.<file_name>.md_content` to `extraction/extracted.md`.
   - Extract `results.<file_name>.content_list` to `extraction/content_list.json` when present.
   - If local MinerU is unavailable, use MinerU free Agent/lightweight API fallback.
   - For fallback API limits or local timeout/retry failures, split into 10-page chunks and save chunk outputs under `extraction/chunks/`.
   - Save `extraction/extracted.md`, `extraction/extraction_manifest.json`, and `extraction/extraction_report.md`.
   - Run extraction QA before drafting. If extraction fails, stop.

4. Build the paragraph index.
   - Build `paragraph_index.json` from `extracted.md`.
   - Prefer `scripts/build_paragraph_index.py` when `extraction/content_list.json` exists, then manually inspect/repair uncertain boundaries recorded in `paragraph_boundary_report.md`.
   - Reconstruct natural paragraphs semantically: merge PDF line-break fragments and wrongly split parser blocks; split only when one parser block clearly contains multiple semantic paragraphs.
   - Preserve sections, paragraph order, figure/table references, formula status, page or chunk provenance when available.
   - Build an asset manifest for figures, tables, and displayed formulas that must appear in the guide PDF.
   - Treat `asset_manifest.json` as the authoritative visual/formula inventory; `extracted.md` may include only a subset of MinerU-returned assets.
   - Treat `extraction/content_list.json` as the authoritative source-order stream for interleaving paragraph text with figures, tables, and displayed formulas.
   - Exclude `References` from paragraph-by-paragraph translation; preserve it as source text or a brief note.

5. Draft the guide.
   - Read `references/guide_contract.md` before drafting.
   - Draft the overall guide first: metadata, one-sentence summary, problem, reading roadmap, methods, assumptions, findings, figures, formulas, glossary.
   - Draft paragraph-by-paragraph content in batches by section and paragraph range.
   - After each drafting or revision pass, run an independent translation-fidelity pass. When subagents are available, delegate this pass to a subagent with only the package path and fidelity criteria; require it to compare every guide-worthy `原文`/`翻译` pair, rewrite or list unfaithful blocks, and save `context/translation_fidelity_report.md` or `context/translation_revision_report.md`.
   - Default to Codex-authored translation/explanation batches. If a local model cache is used with explicit user approval, record `translation_model`, keep the package `needs-review`, and do not put model provenance in reader-facing `literature_guide.md`.
   - Use compact paragraph labels by default: `**原文：** ...`, `**翻译：** ...`, `**讲解：** ...`. Do not use separate mini-sections for these three labels unless the user explicitly asks for a spacious layout.
   - Before inserting displayed formulas, run `scripts/validate_formula_latex.py --asset-manifest <package>/asset_manifest.json --json-output <package>/formula_latex_validation.json`.
   - If one formula OCR is invalid but the source formula image is legible, record an audited `context/formula_latex_overrides.json` entry with asset/path, LaTeX, reason, source, and reviewed date, then rerun validation with `--formula-overrides`; never silently reconstruct missing formulas.
   - Place source figures, tables, and displayed formulas in the `原文：` stream at the same relative position indicated by MinerU `content_list.json`. Use MinerU-recognized formula LaTeX for formulas that pass `formula_latex_validation.json`; use the source formula image only for formulas with missing recognition or failed validation, and record the fallback in build logs.
   - For each inserted figure or table, place its source caption immediately after the image, followed by a faithful Chinese caption translation and a short caption explanation. Use compact labels: `**图注原文：**`, `**图注翻译：**`, and `**图注讲解：**`.
   - Save figure/table caption translations and explanations in `figure_caption_annotations.json` when using `scripts/build_compact_inline_guide.py`; do not rely on image links alone to carry figure meaning.
   - For each paragraph, translate the whole original paragraph faithfully before writing the explanation; do not generate template phrases such as "本段的技术意译" or "作者在这里围绕" in the translation block.
   - For each paragraph explanation, write paragraph-specific content. Do not reuse section-level templates such as "this section establishes..." or "the introduction contrasts two experiments" across multiple paragraphs. The explanation must name the paragraph's own claim, equation/figure/table role, variable/condition, local transition, or likely misunderstanding.
   - After drafting, inspect the harness `explanation_quality` metrics. If `low_information_explanations`, empty explanations, or repeated/template-like explanation warnings appear, rewrite the affected explanation batches and keep the package `needs-review` until the warning is cleared or explicitly accepted as a non-final draft.
   - Also inspect translation-fidelity warnings from `validate_guide.py --strict-translation-fidelity`. If long source paragraphs have compressed translations, meta-commentary appears in `翻译`, English source sentences are copied into `翻译`, or figure/table/equation anchors are missing from translations, rewrite the affected batches before rendering.
   - Default batch size: 8-12 natural paragraphs, or 3000-5000 English words. Very long paragraphs remain intact.
   - Pass each batch global context, section context, local paragraphs, and continuity state.
   - Maintain `context/term_glossary.json`; allow `preferred_terms.yaml` to override automatic terminology.

6. Validate and render.
   - Before validation, run `scripts/clean_guide_markdown.py --guide <package>/literature_guide.md --asset-manifest <package>/asset_manifest.json --in-place --report <package>/guide_cleanup_report.json` to remove hidden HTML comments and clear formula image captions created by renderer or encoding workarounds.
   - Run `scripts/validate_guide.py` on `literature_guide.md` and `paragraph_index.json`.
   - For production guides, include `--strict-translation-fidelity` and treat its errors as blockers. Warnings require either rewriting the affected translation blocks or recording a paragraph-level justification in the fidelity report.
   - In production, also pass `--asset-manifest <package>/asset_manifest.json --require-embedded-assets` so available source figures/tables/formulas must be embedded before rendering.
   - Run `scripts/literature_guide_harness.py` with `--run-validator` after Markdown assembly; use `--stage draft`, `--stage rendered`, or `--stage pre-attach` for the current gate.
   - Pre-attach harness now requires explicit translation-fidelity review evidence in `status.json`: set `translation_fidelity_status` to `pass`, or make `content_review.scope/report_path` clearly mention source fidelity, faithful translation, 忠于原文, 逐句, or subagent review.
   - Production output remains `literature_guide.md` and `literature_guide.pdf`; if a test variant such as `literature_guide_compact_inline.md` is generated, substitute that actual guide path in every cleanup, validation, render, and report command.
   - If validation or harness fails, do not render, prepare an attach manifest, or attach until fixed. If harness warns about low-information paragraph explanations, rewrite the prose before promoting the package. If harness warns only because an external/local model cache was used, keep `needs-review` and require evidence-bearing Codex/human `content_review` before final attach.
   - Read `references/windows_powershell_contract.md` before generating Chinese files or rendering PDFs from PowerShell.
   - Render TOC with a depth that excludes paragraph IDs, or use non-heading paragraph labels so P IDs do not enter the TOC.
   - Render `literature_guide.pdf` with plain academic styling. Keep `literature_guide.md` as the editable local source.
   - For compact/inline guides, validate with `--require-compact-blocks --require-inline-assets --require-image-captions --allow-latex-formula-assets --formula-latex-report <package>/formula_latex_validation.json` in addition to normal validation flags.

7. Prepare and execute Zotero attachment.
   - Read `references/zotero_contract.md` before any Zotero write.
   - Build `attachment_manifest.json` with `scripts/build_attachment_manifest.py`, passing `--status-json <package>/status.json` and the latest relevant `--harness-report-json`.
   - In batch mode, first produce a decision table of `ready`, `warn`, `duplicate gate`, and `PDF gate`; attach only the item keys the user explicitly approves.
   - Default Zotero attachment is only `literature_guide.pdf`, titled `文献导读.pdf`.
   - Default attachment mode is stored attachment. Linked attachment is optional.
   - After explicit user confirmation, execute the plugin-first attach route in `references/zotero_contract.md#confirmed-attachment-execution`.
   - First check `GET http://127.0.0.1:23119/guide-helper/health`. If it returns `plugin=zotero-guide-helper`, attach with `scripts/zotero_guide_helper_attach.py --manifest <package>/attachment_manifest.json` and verify the generated report.
   - If the Zotero Guide Helper plugin is missing, recommend installing the bundled `assets/zotero-guide-helper/zotero-guide-helper.xpi` and retrying the health check. Use the Better BibTeX/ztoolkit debug bridge only when plugin installation is blocked or the user explicitly asks for the fallback.
   - Do not start with `/connector/saveAttachment`; it depends on an active Connector save session and is only appropriate for just-saved items.
   - Do not treat the OpenAI Zotero plugin helper `import-bibtex` / `import-ris` commands as a guide attachment route. They import reference records into the selected Zotero target; they do not attach a local `literature_guide.pdf` to an existing parent item with title/tag/hash verification.
   - Use `curl.exe` or Python `urllib` for Zotero local API checks on Windows. Avoid PowerShell `Invoke-WebRequest`.
   - Before writing, run duplicate checks by title `文献导读.pdf`, filename `literature_guide.pdf`, tag `codex-literature-guide`, and any prior manifest key; the Zotero Guide Helper repeats duplicate detection inside Zotero before import.
   - If a duplicate guide exists, stop for `replace / keep-both / cancel`. `keep-both` requires explicit approval; `keep original` or `cancel` means do not attach the new guide.
   - After writing, report success only if Zotero local API shows the new child, it is an imported/stored PDF with both tags, and its storage-file SHA256 equals the package PDF.
   - Preserve `zotero_source_attachment_key` and `zotero_guide_attachment_key` as separate fields in `status.json` and `attachment_manifest.json`; never reuse the source PDF attachment key as the guide attachment key.
   - On confirmed attach, also add tags `codex-literature-guide` and `guide-needs-review`.
   - Do not add Zotero notes by default.

## References

- Read `references/operator_runbook.md` when executing a full paper workflow; it is the concrete command-level runbook.
- Read `references/workflow_contract.md` for package layout, state machine, extraction QA, batching, and root/package README rules.
- Read `references/guide_contract.md` before generating or revising guide content.
- Read `references/windows_powershell_contract.md` before writing Chinese Markdown/JSON/HTML/PDF files through PowerShell or debugging Chinese font/encoding output.
- Read `references/zotero_contract.md` before preparing or executing any Zotero attachment update.

## Scripts

- `scripts/validate_guide.py`: Check paragraph coverage, section structure, required blocks, forbidden content hints, and local image references.
- `scripts/validate_formula_latex.py`: Compile-check MinerU-recognized displayed formula LaTeX from `asset_manifest.json`; write `formula_latex_validation.json` before formula insertion or PDF rendering.
- `scripts/validate_guide.py --asset-manifest ... --require-embedded-assets`: Hard-fail guides that omit recoverable paper figures, tables, validated formula LaTeX, or justified formula image fallbacks from the Markdown/PDF path.
- `scripts/validate_guide.py --require-compact-blocks --require-inline-assets --allow-latex-formula-assets --formula-latex-report ...`: Hard-fail guides that do not use compact paragraph labels, leave recoverable assets outside the paragraph guide, omit formula LaTeX that passed validation, or embed formula LaTeX that failed validation.
- `scripts/validate_guide.py --require-image-captions`: Hard-fail inserted figure/table images that do not include `图注原文`, `图注翻译`, and `图注讲解` immediately after the image.
- `scripts/literature_guide_harness.py`: Audit package layout, UTF-8 JSON/Markdown, paragraph/cache/label counts, strict validator output, external-model draft status, rendered/pre-attach readiness, and forbidden reader-facing provenance.
- `scripts/build_compact_inline_guide.py`: Convert an existing guide plus `paragraph_index.json`, MinerU `content_list.json`, `asset_manifest.json`, and optional `figure_caption_annotations.json` into compact paragraph blocks with figures/tables/formulas restored in source order.
- `scripts/clean_guide_markdown.py`: Remove hidden HTML comments and formula-image caption alt text from generated guide Markdown before validation and PDF rendering.
- `scripts/build_attachment_manifest.py`: Create a safe manifest for attaching only `literature_guide.pdf`; blocks packages that are not `ready_to_attach`, fail/warn harness without explicit acceptance, or contain unreviewed `translation_model` draft output.
- `scripts/zotero_guide_helper_attach.py`: Preferred confirmed write-back client for the Zotero Guide Helper plugin; checks plugin health, posts `literature_guide.pdf`, verifies stored attachment metadata and SHA256, and writes `zotero_helper_attach_report.json`.
- `scripts/zotero_local_lookup.py`: Query Zotero's local API by item key, save item/children JSON, filter PDF attachments, and resolve a source PDF path when possible.
- `scripts/zotero_title_search.py`: Resolve a paper title to exactly one high-confidence Zotero item key through Zotero's local API before the item-key workflow.
- `scripts/mineru_local_parse.ps1`: Smoke test or run the local MinerU `/file_parse` API with the standard production parameters for this workflow.
- `scripts/extract_mineru_result.py`: Normalize a MinerU JSON response into `extracted.md`, `content_list.json`, and a small manifest.
- `scripts/build_paragraph_index.py`: Build an initial `paragraph_index.json` from MinerU `content_list.json`, skipping page furniture and recording conservative boundary repairs.
