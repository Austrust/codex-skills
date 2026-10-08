# Guide Contract

Read this before generating or revising `literature_guide.md`.

## Output Language

- Overall guide: Chinese.
- Translation: Chinese academic prose.
- Explanation: Chinese.
- Original block: keep the paper's original language.
- Keep important English terms on first occurrence when useful.

Use stable local filenames:

```text
literature_guide.md
literature_guide.pdf
```

Use Chinese display title only for the Zotero PDF attachment:

```text
文献导读.pdf
```

## Structure

Use two major parts:

```markdown
# 文献导读

## 第一部分：论文整体导读

## 第二部分：逐段导读
```

The overall guide may include:

```text
1. 文献信息
2. 一句话概括
3. 论文解决的问题
4. 阅读路线图
5. 方法与思路
6. 关键假设
7. 主要结论
8. 图表导读
9. 公式与符号说明
10. 术语表
```

## Paragraph Guide Format

Preserve the original section order. Each natural paragraph is the basic unit.

Use this compact paragraph block format by default. The paragraph label must not be a Markdown heading, because paragraph IDs must not enter the PDF table of contents:

```markdown
<a id="P001"></a>

**P001**

**原文：** Original paragraph in the paper's original language. Include the actual paragraph text here.

**翻译：** 中文忠实翻译。

**讲解：** 这一段的意思、作用、关键概念、与上下文的关系、阅读难点。
```

Every paragraph that appears in `paragraph_index.json` as guide-worthy body text must have exactly these three labels.

The `原文：` label must contain the actual source paragraph text and any source-order figures, tables, or displayed formulas that occur with that paragraph. It must not be a locator, a summary, a paraphrase, a hash, a filename, or a note that the English source is available elsewhere. A source locator may appear only after the original paragraph, never in place of it.

Forbidden original-block placeholders:

```text
原文定位 + 中文释义 + 讲解
逐段导读不重复整段英文原文
不重复英文原文
原文定位
见 `extraction/paragraph_index.json`
见 extraction/paragraph_index.json
请参见 source/source.pdf
请对照 source/source.pdf
导读草案
引用精确表述前对照英文原文复核
英文原文复核
see paragraph_index.json
source PDF only
```

The guide may include a short source locator after the original paragraph, but never instead of the original paragraph.

Pre-render hard gate:

```text
If any guide-worthy paragraph has no actual original text in `原文`, stop.
If the guide tells the reader that paragraph originals are not repeated, stop.
If any `翻译` block is a summary, technical paraphrase, section-level note, copied English source sentence, or contains meta phrases such as `这里说明`, `这里给出推论`, `这里用方程或变量关系说明`, `技术锚点保留为`, `本段的技术意译`, `作者在这里围绕`, `本段说明`, or `这一段的作用`, stop and rewrite it as a true translation.
If a paragraph uses separate mini-sections `**原文**`, `**翻译**`, and `**讲解**` instead of compact labels `**原文：**`, `**翻译：**`, and `**讲解：**`, stop unless the user explicitly requested a spacious layout.
If a paragraph ID is written as `### P001`, stop.
If required source figures/tables/formulas are available as assets but not embedded in `literature_guide.md`, stop.
If recoverable figures/tables/formulas are only embedded in an overall asset gallery and not in the second-part paragraph guide, stop.
If the final guide solves missing formulas or figures by saying only "对照 PDF", stop unless extraction/cropping truly failed and validation is warn/fail.
If Markdown contains hidden HTML comments used to preserve corrupted headings, duplicate block labels, or renderer workarounds, stop and clean the source.
```

## Must Preserve

- Natural paragraph boundaries.
- Original paragraph order.
- Section hierarchy.
- Important formulas, variables, citation markers, and symbols.
- Figure/table references.
- Actual original paragraph text in the `原文：` label.
- Relative source order of paragraph text, figures, tables, and displayed formulas when MinerU `content_list.json` provides it.

Allowed cleanup:

```text
PDF line-break repair
hyphenation repair
obvious page header/footer removal
page number removal
```

Do not alter the original meaning.

## Natural Paragraph Boundary Rules

Natural paragraphs are semantic units. Do not mechanically use raw PDF visual lines, Markdown hard line breaks, page breaks, column breaks, or MinerU content blocks as paragraph boundaries.

Before drafting, use the `paragraph_index.json` produced after semantic reconstruction:

```text
merge false splits:
  one sentence broken across PDF lines
  one paragraph broken across page or column boundaries
  hyphenated line-end word fragments
  parser blocks that continue the same idea without a real paragraph break

split false merges:
  heading merged with body text
  two complete semantic paragraphs inside one parser block
  figure/table caption merged with a body paragraph
```

Preserve the author's paragraph structure when it can be inferred. If a boundary cannot be inferred confidently, do not pretend certainty; keep the safest unit and mark the boundary risk in `paragraph_boundary_report.md`.

The paragraph guide should follow `P001`, `P002`, etc. from the semantic paragraph index, not raw extracted Markdown line breaks.

## Source-Order Figures, Tables, and Formulas

Use `extraction/content_list.json` as the source-order stream for interleaving guide-worthy paragraphs with figures, tables, and displayed formulas.

Default placement:

```markdown
<a id="P017"></a>

**P017**

**原文：** The following conditions are assumed to be valid...

$$
... validated source formula LaTeX ...
$$

**翻译：** 下列条件被假定为成立……

**讲解：** 这一段引出控制参数条件……
```

For displayed formulas:

- Run `scripts/validate_formula_latex.py` before formula insertion and save `formula_latex_validation.json`.
- If a formula's OCR LaTeX is structurally damaged but its source image is legible, use an audited `context/formula_latex_overrides.json` record and pass it via `--formula-overrides`. The override must include the formula asset/path, replacement LaTeX, reason, source image/provenance, and review date.
- If MinerU provides LaTeX in `caption_or_label` or `content_list.text` and that formula passes `formula_latex_validation.json`, place that LaTeX in the `原文：` stream.
- If a specific formula has no recognized LaTeX or fails validation, embed the original formula image from `asset_manifest.json` at the same source-order position and record the reason.
- Keep the original formula image in `assets/` even when the reading guide uses LaTeX, so the formula can be audited.

For figures and tables:

- Embed the source image/table crop at the source-order position in the second-part paragraph guide.
- Use empty image alt text (`![](...)`) unless a real caption is intentionally supplied outside the image link; do not let Pandoc generate duplicate figure captions such as `Figure 1: Figure 1`.
- Immediately after each figure/table image, include the source caption, a faithful Chinese caption translation, and a short caption explanation using compact labels: `**图注原文：**`, `**图注翻译：**`, and `**图注讲解：**`.
- Keep figure/table caption notes outside the paragraph `翻译：` label. The paragraph translation translates the paragraph; the caption translation translates the caption.
- If using `scripts/build_compact_inline_guide.py`, store the caption translation/explanation records in `figure_caption_annotations.json` and pass it with `--caption-annotations`.

The overall guide may summarize key figures/formulas, but it must not be the only place where recoverable assets appear. Avoid a front-loaded asset gallery that forces the reader to jump away from the paragraph being read.

## Translation Rules

The `翻译` block is a true translation of the full `原文` block. It is not a summary, not a technical paraphrase, not a section-level interpretation, and not a bilingual commentary. Keep English only for necessary terms, symbols, acronyms, equation/figure/table labels, names, and citation markers; never copy a full English source sentence into `翻译`.

### Source-Fidelity Review Gate

Before a guide can be considered final, rendered-ready, or Zotero-attach-ready, run a dedicated source-fidelity review of paragraph translations.

- Use a subagent for this review when subagents are available. Give it the package path and require direct comparison of every guide-worthy `原文`/`翻译` pair.
- The reviewer must verify that the translation preserves every source sentence or clause-level claim, condition, caveat, contrast word, variable, formula reference, figure/table reference, citation marker, and equation number.
- The reviewer must rewrite unfaithful translation blocks or list them as blockers. Do not defer a known mismatch to `讲解`.
- Save review evidence as `context/translation_fidelity_report.md` or `context/translation_revision_report.md`, listing paragraph ranges/IDs reviewed, high-risk paragraphs corrected, and any remaining source/OCR uncertainty.
- Record the gate in `status.json` with `translation_fidelity_status: "pass"` or a `content_review` object whose `scope` or `report_path` clearly mentions source fidelity, faithful translation, 忠于原文, 逐句, or subagent review.
- Do not prepare an attachment manifest or attach to Zotero if this evidence is absent.

By default, Codex should author the final paragraph translations and explanations batch by batch. A local/external model such as Ollama may be used only when the user explicitly chooses draft-mode generation. Draft-mode model output must:

- be recorded in `status.json` as `translation_model`;
- keep package status as `needs-review`;
- keep model provenance in `status.json`, `build_log.md`, or batch logs, not in reader-facing `literature_guide.md`;
- pass the structural validator and harness before rendering, but still require Codex/human content review before final Zotero attachment.

- Translate every source sentence or clause-level claim faithfully; do not omit conditions, examples, citations, variables, caveats, or contrast words merely to make the Chinese shorter.
- Use academic Chinese, but keep the paragraph's information density close to the original.
- Keep formulas, variables, citations, equation numbers, figure/table references, and symbols consistent.
- Split long English sentences into natural Chinese when needed, but preserve the logical relations and qualifiers.
- Do not add conclusions absent from the source paragraph.
- Do not put explanation phrases in `翻译`, such as `这里说明`, `这里给出推论`, `这里用方程或变量关系说明`, `技术锚点保留为`, `本段的技术意译是`, `本段说明`, `作者在这里围绕`, `这一段的作用`, or `本段是一个短的过渡`.
- Do not leave source-language sentence fragments in `翻译`. A valid translation may retain terms such as `Hartmann number`, `MHD`, `Kulikovskii`, `Fig. 1`, `Eq. (2)`, `M`, or `B`; it must not contain a six-word-or-longer English sentence run copied from the source.
- If a paragraph is long, the translation should also be long enough to cover it; do not compress it into a reading note.
- Put summaries, implications, reading advice, and conceptual simplification only in `讲解`.
- Follow `preferred_terms.yaml` when provided.
- Otherwise follow `context/term_glossary.json`.

## Explanation Rules

Explain the paragraph itself:

```text
what the paragraph says
its role in the section
how it connects to nearby paragraphs
key terms
formula/table/figure function
easy misunderstandings
why it matters for understanding the paper
```

Each explanation must be specific to its own paragraph. It should usually mention at least one local anchor from the paragraph: a concrete claim, contrast, condition, variable, equation, figure/table reference, experimental fact, inference step, or caveat. It must not be only a section summary or reading instruction.

Do not mass-produce explanations by joining a section-level sentence with keyword snippets. Repeated explanations such as "the introduction contrasts two kinds of experiments" or "this section establishes the governing equations" are acceptable once as a section orientation, but not as paragraph-by-paragraph explanations.

The harness records `explanation_quality` metrics. A `low_information_explanations` warning means the paragraph guide is not final-quality prose. Keep the package `needs-review` and rewrite the affected batches before treating it as ready for attachment.

Do not turn the guide into the user's project analysis.

Forbidden unless the paper itself discusses it:

```text
与我的课题关系
对我的实验的启发
对我的论文投稿的帮助
对我的 SM82 / COMSOL / UIV / EPV 研究的意义
```

## Abstract, References, and Non-Body Sections

- Include Abstract in paragraph-by-paragraph guide.
- Do not translate or explain References item by item.
- Preserve References as source text or summarize that it is retained for citation checking.
- Do not usually paragraph-guide Acknowledgements, Funding, Author contributions, Competing interests, Data availability, or Ethics statements unless the user explicitly asks.

## Formulas

Formula handling:

```text
formula parsed as image plus MinerU LaTeX text -> compile-check the LaTeX, then use LaTeX if it passes
formula parsed as image without reliable LaTeX -> embed the image in the guide near the paragraph
formula degraded/missing but visible in source PDF -> crop from source PDF and embed, then mark extraction risk
formula truly unrecoverable -> mark extraction risk and set validation warn/fail
```

Never reconstruct a missing formula from memory or inference.

Do not use "check the PDF" as the final reader-facing solution when a source-derived formula asset can be embedded. Use a risk note only after embedding the best available source-derived asset, or when embedding failed and validation is not `pass`.

For displayed formulas returned by MinerU, insert the validated recognized LaTeX or a justified source formula image fallback in `literature_guide.md` at the formula's source-order position in the second-part paragraph guide. Do not leave formulas only in `asset_manifest.json` or only in the overall guide.

When using an image fallback, formula/equation image links must not carry non-empty alt text such as `equation_030`, because Pandoc renders those as numbered figures. Use an empty-alt image link for formula image fallbacks:

```markdown
![](assets/images/equation_asset.jpg)
```

Do not render formula images as `Figure N: equation_xxx`.

Render production PDFs with Markdown math parsing enabled, because validated MinerU formula LaTeX is the default displayed-formula path. If a formula fails validation, fall back only that formula to its source image rather than disabling formula recognition for the whole guide.

Do not expose internal asset IDs such as `equation_030`, `image_059`, or `table_012` in reader-facing Markdown or PDF text. Those IDs belong in `asset_manifest.json`, validation reports, or build logs only. In the guide, use reader-facing labels such as:

```text
公式（源页 11）
图像（源页 4）
Figure 1（源页 4）
```

Use risk note only when needed:

```markdown
> 解析风险：此处公式在 PDF 解析中不完整，需要对照原 PDF 核查。
```

## Figures and Tables

Use both:

```text
overall figure/table guide
inline figure/table placement near relevant paragraph
```

If an extracted image exists:

```markdown
![](assets/figure_001.png)

**图注原文：** FIGURE 1. Plausible evolution of an eddy...

**图注翻译：** 图 1。一个初始尺度为 L 的涡在翻转时间内可能发生的演化……

**图注讲解：** 这张图用线型区分无磁场和强磁场下涡结构的最终形态，帮助读者把正文中的电磁扩散和各向异性拉长联系起来。
```

If an image is missing:

```markdown
> 图表提取风险：Figure 1 暂未能从 MinerU 输出中直接取得，已使用 PDF 页面/区域裁剪 `assets/figure_001.png`。
```

If both MinerU extraction and PDF cropping fail, validation must be `warn` or `fail`. Do not silently omit the figure from the reading PDF.

Do not generate, redraw, or hallucinate paper figures.

Figures, tables, and formula images must be embedded with local Markdown image links before PDF rendering. The guide PDF is the reading artifact; it must not require the reader to open the source PDF merely to see normal figures or formulas that were recoverable from MinerU or PDF crops.

## PDF Table of Contents

The PDF table of contents should include only meaningful navigation levels:

```text
文献导读
第一部分：论文整体导读
第二部分：逐段导读
paper sections such as Abstract, Introduction, Methods, Results, Discussion, Conclusion
```

Do not include paragraph IDs in the TOC:

```text
P001
P002
P003
...
```

Use non-heading paragraph labels, or render with a TOC depth that excludes paragraph labels.

When using Pandoc, prefer `--toc --toc-depth=2` unless the section hierarchy requires one more level. Never use a render setting that allows `P001`, `P002`, etc. into the PDF table of contents.

Do not hide alternate headings or paragraph block labels in HTML comments. Comments can still leak into source review, confuse validators, and preserve mojibake. Fix the visible Markdown instead.

## External Sources

Default: do not search external sources.

Use external sources only when needed to explain a term or method that the paper does not define. Mark it explicitly:

```markdown
> 外部补充：...
```

Keep the guide centered on the paper, not a literature review.

## PDF Style

Render `literature_guide.pdf` as plain academic reading notes:

```text
A4
printable
clear section hierarchy
readable Chinese and English fonts
body 10.5-11 pt
line-height 1.4-1.6
original blocks visually distinct
images constrained to page width
table of contents for long guides
page numbers
```
