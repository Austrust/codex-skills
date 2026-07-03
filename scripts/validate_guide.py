#!/usr/bin/env python3
"""Validate a Zotero literature guide against a paragraph index."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


REQUIRED_BLOCK_LABELS = ("原文", "翻译", "讲解")
FORBIDDEN_PLACEHOLDERS = (
    "原文定位 + 中文释义 + 讲解",
    "逐段导读不重复整段英文原文",
    "不重复整段英文原文",
    "不重复英文原文",
    "原文定位",
    "公式和图像若在 MinerU 中仅以占位形式出现",
    "见 `extraction/paragraph_index.json`",
    "见 extraction/paragraph_index.json",
    "需要对照 PDF",
    "需要对照PDF",
    "请对照 PDF",
    "请对照PDF",
    "请参见 source/source.pdf",
    "对照 `source/source.pdf`",
    "对照 source/source.pdf",
    "导读草案",
    "引用精确表述前",
    "英文原文复核",
    "原文复核",
    "应在引用",
    "source PDF only",
    "see paragraph_index.json",
    "see source PDF",
)
FORBIDDEN_HINTS = (
    "与我的课题关系",
    "对我的实验",
    "对我的论文投稿",
    "SM82",
    "COMSOL",
    "UIV",
    "EPV",
)
FORBIDDEN_TRANSLATION_META_PHRASES = (
    "这里说明",
    "这里给出推论",
    "这里用方程或变量关系说明",
    "技术锚点保留为",
    "局部锚点",
    "本处原文线索",
    "本段的技术意译",
    "技术意译",
    "作者在这里围绕",
    "本段是一个短的过渡",
    "本段说明",
    "这一段的作用",
    "本段的作用",
    "中文释义",
)
STRICT_TRANSLATION_META_PHRASES = (
    "\u672c\u6bb5",
    "\u8be5\u6bb5",
    "\u8fd9\u4e00\u6bb5",
    "\u672c\u6587\u6bb5",
    "\u672c\u6bb5\u8bf4\u660e",
    "\u672c\u6bb5\u7684\u4f5c\u7528",
    "\u6280\u672f\u610f\u8bd1",
    "\u610f\u8bd1",
    "\u6982\u62ec\u5982\u4e0b",
    "\u53ef\u6982\u62ec\u4e3a",
    "\u603b\u7ed3\u5982\u4e0b",
    "\u672c\u6bb5\u603b\u7ed3",
    "\u9605\u8bfb\u63d0\u793a",
    "\u53ef\u7406\u89e3\u4e3a",
    "\u4f5c\u8005\u5728\u8fd9\u91cc",
)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", flags=re.DOTALL)
IMAGE_LINK_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
ASSET_ID_RE = re.compile(r"\b(?:equation|image|table)_\d{3,}\b")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
REFERENCE_ANCHOR_RE = re.compile(
    r"\b(?:Fig(?:ure)?s?|Table|Eq(?:uation)?s?)\.?\s*\(?[0-9]+[A-Za-z]?\)?|\([0-9]{1,3}[a-z]?\)"
)
SYMBOL_ANCHOR_RE = re.compile(r"\b(?:Re|Ha|Gr|Pr|Ra|Ro|Rm|St|Nu|Pe|MHD|DNS|LES|PIV|UIV)\b")
FORMULA_OCR_TEX_HINT_RE = re.compile(
    r"(\$\$|\\begin\{|\\end\{|\\frac|\\hat|\\bar|\\mathrm|\\mathbf|\\int|\\sum|[_^]\s*\{)"
)
LATIN_SENTENCE_SPLIT_RE = re.compile(r"[\u4e00-\u9fff。！？；，、]+")


SOURCE_TEXT_KEYS = ("text", "original", "original_text", "source_text", "paragraph", "content")
LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'’-]*")
COMMON_WORDS = {
    "the",
    "and",
    "for",
    "that",
    "with",
    "from",
    "this",
    "are",
    "was",
    "were",
    "has",
    "have",
    "not",
    "but",
    "its",
    "into",
    "their",
    "which",
}


def load_expected_records(index_path: Path) -> dict[str, dict]:
    data = json.loads(index_path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict):
        records = data.get("paragraphs", [])
    elif isinstance(data, list):
        records = data
    else:
        raise ValueError("paragraph index must be a JSON object or list")

    expected: dict[str, dict] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("guide") is False:
            continue
        section = str(record.get("section", "")).strip().lower()
        kind = str(record.get("kind", "body")).strip().lower()
        if section in {"references", "参考文献"}:
            continue
        if kind in {"reference", "references", "acknowledgement", "funding", "metadata"}:
            continue
        pid = record.get("id") or record.get("paragraph_id") or record.get("pid")
        if pid:
            expected[str(pid)] = record
    return expected


def get_source_text(record: dict) -> str:
    for key in SOURCE_TEXT_KEYS:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def extract_sections(markdown: str) -> dict[str, str]:
    pattern = r"^(?:\*\*(P\d{3,})\*\*|<a\s+id=\"(P\d{3,})\"></a>|###\s+(P\d{3,})\s*)$"
    matches = list(re.finditer(pattern, markdown, flags=re.MULTILINE))
    sections: dict[str, str] = {}
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(markdown)
        pid = next(group for group in match.groups() if group)
        if pid in sections:
            sections[pid] += "\n" + markdown[start:end]
        else:
            sections[pid] = markdown[start:end]
    return sections


def block_between(body: str, start_marker: str, end_marker: str) -> str:
    start = body.find(start_marker)
    if start == -1:
        return ""
    start += len(start_marker)
    end = body.find(end_marker, start)
    if end == -1:
        return body[start:]
    return body[start:end]


def has_label(body: str, label: str) -> bool:
    return f"**{label}**" in body or f"**{label}：**" in body or f"**{label}:**" in body


def has_compact_label(body: str, label: str) -> bool:
    return f"**{label}：**" in body or f"**{label}:**" in body


def label_block(body: str, label: str, next_label: str | None) -> str:
    next_pattern = r"\Z"
    if next_label:
        next_pattern = rf"(?=\*\*{re.escape(next_label)}(?:[：:]|\*\*))"
    compact = re.search(rf"\*\*{re.escape(label)}[：:]\*\*\s*(.*?){next_pattern}", body, flags=re.DOTALL)
    if compact:
        return compact.group(1).strip()
    if not next_label:
        marker = f"**{label}**"
        start = body.find(marker)
        return body[start + len(marker) :].strip() if start != -1 else ""
    return block_between(body, f"**{label}**", f"**{next_label}**")


def label_block_any(body: str, label: str, next_labels: tuple[str, ...]) -> str:
    next_pattern = r"\Z"
    if next_labels:
        next_pattern = "(?=" + "|".join(rf"\*\*{re.escape(item)}[：:]\*\*" for item in next_labels) + r"|\Z)"
    match = re.search(rf"\*\*{re.escape(label)}[：:]\*\*\s*(.*?){next_pattern}", body, flags=re.DOTALL)
    return match.group(1).strip() if match else ""



TRUNCATED_INLINE_MATH_RE = re.compile(r"\$[^$\n]*(?:\.\.\.|\\[A-Za-z]{1,16}\.\.\.)")


def math_render_safety_issues(text: str) -> list[str]:
    issues: list[str] = []
    if text.count("$") % 2:
        issues.append("unbalanced inline math dollar delimiters")
    if TRUNCATED_INLINE_MATH_RE.search(text):
        issues.append("truncated inline math fragment")
    return issues

def visible_text(markdown: str) -> str:
    text = re.sub(r"`[^`]*`", "", markdown)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"[>#*_~\\-]", " ", text)
    return " ".join(text.split())


def strip_math_for_language_checks(text: str) -> str:
    text = re.sub(r"\$\$.*?\$\$", " ", text, flags=re.DOTALL)
    text = re.sub(r"\$.*?\$", " ", text, flags=re.DOTALL)
    text = re.sub(r"\\begin\{(?:array|aligned|matrix|cases|equation)\}.*?\\end\{(?:array|aligned|matrix|cases|equation)\}", " ", text, flags=re.DOTALL)
    return " ".join(text.split())


def significant_latin_words(text: str) -> list[str]:
    seen: set[str] = set()
    words: list[str] = []
    for word in LATIN_WORD_RE.findall(text.lower()):
        word = word.strip("'’-")
        if len(word) < 3 or word in COMMON_WORDS or word in seen:
            continue
        seen.add(word)
        words.append(word)
    return words


def cjk_char_count(text: str) -> int:
    return len(CJK_RE.findall(text))


def sentence_like_count(text: str) -> int:
    return len(re.findall(r"[。！？!?；;]", text))


def latin_word_count(text: str) -> int:
    return len(LATIN_WORD_RE.findall(strip_math_for_language_checks(text)))


def long_latin_runs(text: str, min_words: int = 8) -> list[str]:
    runs: list[str] = []
    for segment in LATIN_SENTENCE_SPLIT_RE.split(strip_math_for_language_checks(text)):
        words = LATIN_WORD_RE.findall(segment)
        if len(words) >= min_words:
            cleaned = " ".join(segment.split())
            if cleaned:
                runs.append(cleaned[:180])
    return runs


def source_reference_anchors(text: str) -> list[str]:
    seen: set[str] = set()
    anchors: list[str] = []
    for match in REFERENCE_ANCHOR_RE.findall(text):
        value = " ".join(match.split())
        if value and value not in seen:
            seen.add(value)
            anchors.append(value)
    return anchors


def source_symbol_anchors(text: str) -> list[str]:
    seen: set[str] = set()
    anchors: list[str] = []
    for match in SYMBOL_ANCHOR_RE.findall(text):
        if match and match not in seen:
            seen.add(match)
            anchors.append(match)
    return anchors


def anchor_present_in_translation(anchor: str, translation: str) -> bool:
    if anchor in translation:
        return True
    number_match = re.search(r"[0-9]+[A-Za-z]?", anchor)
    if not number_match:
        return True
    raw_number = number_match.group(0)
    candidate_numbers = {raw_number, raw_number.replace("O", "0").replace("o", "0")}
    number = "|".join(re.escape(item) for item in sorted(candidate_numbers, key=len, reverse=True))
    if re.search(r"\bfig", anchor, flags=re.IGNORECASE):
        return re.search(rf"图\s*[\(（]?\s*{number}\s*[\)）]?", translation) is not None
    if re.search(r"\btable", anchor, flags=re.IGNORECASE):
        return re.search(rf"表\s*[\(（]?\s*{number}\s*[\)）]?", translation) is not None
    if re.search(r"\beq", anchor, flags=re.IGNORECASE):
        return re.search(rf"(?:式|方程|公式)\s*[\(（]?\s*{number}\s*[\)）]?|[\(（]\s*{number}\s*[\)）]", translation) is not None
    return False


def source_overlap_ok(source: str, original: str) -> bool:
    expected_words = significant_latin_words(source)[:80]
    if len(expected_words) < 8:
        return True
    original_words = set(significant_latin_words(original))
    overlap = sum(1 for word in expected_words if word in original_words)
    required = min(10, max(5, int(len(expected_words) * 0.25)))
    return overlap >= required


def resolve_local_image(link: str, guide_path: Path, assets_dir: Path | None) -> Path:
    candidate = Path(link)
    if candidate.is_absolute():
        return candidate.resolve()
    candidates = [(guide_path.parent / link).resolve()]
    if assets_dir:
        candidates.append((assets_dir / link).resolve())
        if link.startswith("assets/"):
            candidates.append((assets_dir.parent / link).resolve())
        else:
            candidates.append((assets_dir / Path(link).name).resolve())
    for item in candidates:
        if item.exists():
            return item
    return candidates[0]


def load_asset_manifest(asset_manifest_path: Path | None) -> list[dict]:
    if not asset_manifest_path:
        return []
    if not asset_manifest_path.exists():
        raise FileNotFoundError(f"asset manifest not found: {asset_manifest_path}")
    data = json.loads(asset_manifest_path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError("asset manifest must be a JSON list")
    return [item for item in data if isinstance(item, dict)]


def load_formula_latex_report(path: Path | None) -> dict[str, dict]:
    if not path:
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    records = data.get("formulas", []) if isinstance(data, dict) else data
    if not isinstance(records, list):
        raise ValueError("formula latex report must contain a formulas list")
    result: dict[str, dict] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        for key in (record.get("asset_id"), record.get("path")):
            if isinstance(key, str) and key.strip():
                result[key.strip()] = record
                result[Path(key.replace("\\", "/")).name] = record
    return result


def formula_latex_status(item: dict, report: dict[str, dict]) -> str | None:
    keys = [
        item.get("asset_id"),
        item.get("path"),
        Path(str(item.get("path") or "").replace("\\", "/")).name,
    ]
    for key in keys:
        if isinstance(key, str) and key.strip() and key.strip() in report:
            return str(report[key.strip()].get("status") or "").lower()
    return None


def formula_latex_candidates(item: dict, report: dict[str, dict]) -> list[str]:
    candidates: list[str] = []
    keys = [
        item.get("asset_id"),
        item.get("path"),
        Path(str(item.get("path") or "").replace("\\", "/")).name,
    ]
    for key in keys:
        if isinstance(key, str) and key.strip() and key.strip() in report:
            record = report[key.strip()]
            for field in ("latex", "normalized_latex", "source_latex"):
                value = record.get(field)
                if isinstance(value, str) and value.strip():
                    candidates.append(value.strip())
    caption = item.get("caption_or_label")
    if isinstance(caption, str) and caption.strip():
        candidates.append(caption.strip())
    result: list[str] = []
    seen: set[str] = set()
    for value in candidates:
        compact = compact_formula_text(value)
        if compact and compact not in seen:
            seen.add(compact)
            result.append(value)
    return result


def looks_like_formula_ocr(text: object) -> bool:
    if not isinstance(text, str):
        return False
    stripped = text.strip()
    if len(stripped) < 8:
        return False
    return bool(FORMULA_OCR_TEX_HINT_RE.search(stripped))


def compact_formula_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def formula_latex_in_text(text: str, latex: object) -> bool:
    if not isinstance(latex, str):
        return False
    stripped = latex.strip()
    if not stripped:
        return False
    return stripped in text or compact_formula_text(stripped) in compact_formula_text(text)


def asset_path(package_dir: Path, rel: str) -> Path:
    return (package_dir / rel).resolve()


def caption_snippet_after_image(guide: str, image_end: int) -> str:
    boundary_positions = []
    for pattern in (r"\n\*\*翻译[：:]\*\*", r"\n<a\s+id=\"P\d{3,}\"></a>", r"\n\*\*P\d{3,}\*\*"):
        match = re.search(pattern, guide[image_end:], flags=re.MULTILINE)
        if match:
            boundary_positions.append(image_end + match.start())
    end = min(boundary_positions) if boundary_positions else len(guide)
    return guide[image_end:end]


def caption_blocks_ok(caption: str, snippet: str, asset_label: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    original = label_block_any(snippet, "图注原文", ("图注翻译", "图注讲解"))
    translation = label_block_any(snippet, "图注翻译", ("图注讲解",))
    explanation = label_block_any(snippet, "图注讲解", ())
    if not original:
        errors.append(f"{asset_label} missing 图注原文 after image")
    if not translation:
        errors.append(f"{asset_label} missing 图注翻译 after image")
    if not explanation:
        errors.append(f"{asset_label} missing 图注讲解 after image")
    if caption and original and not source_overlap_ok(caption, visible_text(original)):
        errors.append(f"{asset_label} 图注原文 does not sufficiently match manifest caption")
    translation_visible = visible_text(translation)
    explanation_visible = visible_text(explanation)
    if translation and (len(translation_visible) < 12 or not CJK_RE.search(translation_visible)):
        errors.append(f"{asset_label} 图注翻译 is too short or not Chinese")
    if explanation and (len(explanation_visible) < 12 or not CJK_RE.search(explanation_visible)):
        errors.append(f"{asset_label} 图注讲解 is too short or not Chinese")
    for phrase in FORBIDDEN_TRANSLATION_META_PHRASES:
        if phrase in translation:
            errors.append(f"{asset_label} 图注翻译 contains meta-summary phrase instead of a caption translation: {phrase}")
    return errors, warnings


def validate(
    guide_path: Path,
    index_path: Path,
    assets_dir: Path | None,
    asset_manifest_path: Path | None,
    require_embedded_assets: bool,
    require_compact_blocks: bool,
    require_inline_assets: bool,
    allow_latex_formula_assets: bool,
    require_image_captions: bool,
    formula_latex_report_path: Path | None = None,
    strict_translation_fidelity: bool = False,
) -> tuple[str, list[str], list[str]]:
    guide = guide_path.read_text(encoding="utf-8")
    expected_records = load_expected_records(index_path)
    expected = list(expected_records)
    sections = extract_sections(guide)
    asset_manifest = load_asset_manifest(asset_manifest_path)
    formula_latex_report = load_formula_latex_report(formula_latex_report_path)

    errors: list[str] = []
    warnings: list[str] = []
    if require_embedded_assets and not asset_manifest_path:
        errors.append("--require-embedded-assets requires --asset-manifest")
    if require_inline_assets and not asset_manifest_path:
        errors.append("--require-inline-assets requires --asset-manifest")
    if require_image_captions and not asset_manifest_path:
        errors.append("--require-image-captions requires --asset-manifest")
    if formula_latex_report_path and not allow_latex_formula_assets:
        errors.append("--formula-latex-report requires --allow-latex-formula-assets")

    if "## 第一部分：论文整体导读" not in guide:
        errors.append("missing overall guide heading")
    if "## 第二部分：逐段导读" not in guide:
        errors.append("missing paragraph guide heading")
    if re.search(r"^###\s+P\d{3,}\s*$", guide, flags=re.MULTILINE):
        errors.append("paragraph ids are Markdown headings; use non-heading P labels so they do not enter the PDF TOC")
    comments = HTML_COMMENT_RE.findall(guide)
    if comments:
        errors.append(f"HTML comments found in guide Markdown: {len(comments)}; do not hide corrupted headings or block labels in comments")
    guide_without_image_links = IMAGE_LINK_RE.sub("", guide)
    internal_asset_ids = sorted(set(ASSET_ID_RE.findall(guide_without_image_links)))
    if internal_asset_ids:
        errors.append("internal asset ids found in reader-facing guide text: " + ", ".join(internal_asset_ids[:20]))
    for phrase in FORBIDDEN_PLACEHOLDERS:
        if phrase in guide:
            errors.append(f"forbidden guide placeholder found: {phrase}")

    for pid in expected:
        body = sections.get(pid)
        if body is None:
            errors.append(f"missing paragraph section: {pid}")
            continue
        for label in REQUIRED_BLOCK_LABELS:
            if not has_label(body, label):
                errors.append(f"{pid} missing block label {label}")
            if require_compact_blocks and not has_compact_label(body, label):
                errors.append(f"{pid} must use compact inline label **{label}：**")
        source_text = get_source_text(expected_records[pid])
        original = label_block(body, "原文", "翻译")
        translation = label_block(body, "翻译", "讲解")
        explanation = label_block(body, "讲解", None)
        for block_name, block_text in (("translation", translation), ("explanation", explanation)):
            for issue in math_render_safety_issues(block_text):
                errors.append(f"{pid} {block_name} block has render-unsafe math text: {issue}")
        translation_visible = visible_text(translation)
        for phrase in FORBIDDEN_TRANSLATION_META_PHRASES:
            if phrase in translation:
                errors.append(f"{pid} translation block contains meta-summary phrase instead of faithful translation: {phrase}")
        if len(visible_text(source_text)) >= 400 and len(translation_visible) < 80:
            warnings.append(f"{pid} translation block is very short for a long source paragraph; check that it is not a summary")
        source_visible = visible_text(source_text)
        source_word_count = len(LATIN_WORD_RE.findall(source_visible))
        translation_cjk_count = cjk_char_count(translation_visible)
        translation_latin_count = latin_word_count(translation_visible)
        if strict_translation_fidelity:
            for phrase in STRICT_TRANSLATION_META_PHRASES:
                if phrase in translation_visible:
                    errors.append(f"{pid} strict translation fidelity: translation block contains review/meta wording, not only translation: {phrase}")
            copied_runs = long_latin_runs(translation_visible)
            if copied_runs:
                errors.append(
                    f"{pid} strict translation fidelity: translation block appears to contain copied English source sentence(s): "
                    + " | ".join(copied_runs[:3])
                )
            if (
                source_word_count >= 25
                and translation_latin_count > max(24, int(max(translation_cjk_count, 1) * 0.35))
            ):
                errors.append(
                    f"{pid} strict translation fidelity: translation contains too much source-language English "
                    f"(latin_words={translation_latin_count}, cjk_chars={translation_cjk_count}); likely bilingual commentary or copied source"
                )
            if source_word_count >= 80 and translation_cjk_count < max(60, int(source_word_count * 0.45)):
                errors.append(
                    f"{pid} strict translation fidelity: translation is too short for the source paragraph "
                    f"(source_words={source_word_count}, cjk_chars={translation_cjk_count}); likely summary/compression"
                )
            elif source_word_count >= 80 and translation_cjk_count < int(source_word_count * 0.65):
                warnings.append(
                    f"{pid} strict translation fidelity: translation may be compressed "
                    f"(source_words={source_word_count}, cjk_chars={translation_cjk_count})"
                )
            if source_word_count >= 60 and sentence_like_count(translation_visible) <= 1:
                warnings.append(f"{pid} strict translation fidelity: long source has one-sentence translation; check for summary")
            missing_refs = [
                anchor
                for anchor in source_reference_anchors(source_visible)
                if not anchor_present_in_translation(anchor, translation_visible)
            ]
            if missing_refs:
                warnings.append(f"{pid} strict translation fidelity: source figure/table/equation/reference anchors missing from translation: {missing_refs[:8]}")
            missing_symbols = [anchor for anchor in source_symbol_anchors(source_visible) if anchor not in translation_visible]
            if missing_symbols:
                warnings.append(f"{pid} strict translation fidelity: source technical symbols/acronyms missing from translation: {missing_symbols[:12]}")
        original_visible = visible_text(original)
        if len(original_visible) < 30:
            errors.append(f"{pid} original block is too short or missing actual source text")
        if "原文定位" in original or "paragraph_index.json" in original:
            errors.append(f"{pid} original block is a locator instead of actual source text")
        if source_text and not source_overlap_ok(source_text, original_visible):
            errors.append(f"{pid} original block does not sufficiently match paragraph_index source text")

    unexpected = sorted(set(sections) - set(expected))
    if unexpected:
        warnings.append("guide contains paragraph ids not in index: " + ", ".join(unexpected[:20]))

    for hint in FORBIDDEN_HINTS:
        if hint in guide:
            warnings.append(f"possible user-project context leaked into guide: {hint}")

    second_part_start = guide.find("## 第二部分")
    if second_part_start == -1:
        second_part_start = 0
    second_part = guide[second_part_start:]

    referenced_images: dict[Path, list[str]] = {}
    referenced_images_in_second_part: dict[Path, list[str]] = {}
    referenced_image_spans: dict[Path, list[int]] = {}
    for match in IMAGE_LINK_RE.finditer(guide):
        alt_text = match.group(1)
        image_path = match.group(2)
        if ASSET_ID_RE.search(alt_text):
            errors.append(f"image alt text exposes internal asset id: {alt_text}")
        if image_path.startswith(("http://", "https://", "data:")):
            continue
        candidate = resolve_local_image(image_path.split()[0].strip("<>\"'"), guide_path, assets_dir)
        referenced_images.setdefault(candidate, []).append(alt_text)
        if match.start() >= second_part_start:
            referenced_images_in_second_part.setdefault(candidate, []).append(alt_text)
            referenced_image_spans.setdefault(candidate, []).append(match.end())
        if not candidate.exists():
            warnings.append(f"missing local image: {image_path}")

    if (require_embedded_assets or require_inline_assets) and asset_manifest:
        for item in asset_manifest:
            typ = str(item.get("type", "")).lower()
            if typ not in {"image", "figure", "table", "formula", "equation"}:
                continue
            rel = item.get("path")
            if not isinstance(rel, str) or not rel.strip():
                errors.append(f"asset manifest entry has no path: {item.get('asset_id')}")
                continue
            package_dir = asset_manifest_path.parent if asset_manifest_path else guide_path.parent
            manifest_asset_path = asset_path(package_dir, rel)
            if not manifest_asset_path.exists():
                errors.append(f"asset file missing from manifest: {rel}")
                continue
            caption = item.get("caption_or_label")
            formula_candidates = formula_latex_candidates(item, formula_latex_report)
            latex_formula_text_present = (
                typ in {"formula", "equation"}
                and looks_like_formula_ocr(caption)
                and any(formula_latex_in_text(guide, candidate) for candidate in formula_candidates)
            )
            latex_formula_embedded = (
                allow_latex_formula_assets
                and typ in {"formula", "equation"}
                and bool(formula_candidates)
                and any(formula_latex_in_text(guide, candidate) for candidate in formula_candidates)
            )
            latex_formula_inline = latex_formula_embedded and any(
                formula_latex_in_text(second_part, candidate) for candidate in formula_candidates
            )
            image_embedded = manifest_asset_path in referenced_images
            image_inline = manifest_asset_path in referenced_images_in_second_part
            latex_status = formula_latex_status(item, formula_latex_report)
            if latex_formula_text_present and not allow_latex_formula_assets:
                errors.append(
                    f"formula asset appears as MinerU OCR/LaTeX but --allow-latex-formula-assets was not passed: {item.get('asset_id') or rel}"
                )
            if typ in {"formula", "equation"} and formula_latex_report:
                if latex_status == "pass" and not latex_formula_inline:
                    errors.append(f"formula LaTeX passed validation but is not embedded inline: {item.get('asset_id') or rel}")
                if latex_status and latex_status != "pass" and latex_formula_embedded:
                    errors.append(f"formula LaTeX failed validation but is embedded as LaTeX: {item.get('asset_id') or rel}")
            if require_embedded_assets and not (image_embedded or latex_formula_embedded):
                errors.append(f"asset not embedded in guide Markdown: {item.get('asset_id') or rel}")
                continue
            if require_inline_assets and not (image_inline or latex_formula_inline):
                errors.append(f"asset not embedded inside paragraph guide: {item.get('asset_id') or rel}")
                continue
            if typ in {"formula", "equation"} and image_embedded and any(alt.strip() for alt in referenced_images[manifest_asset_path]):
                errors.append(f"formula asset has non-empty image alt text that will render as a figure caption: {item.get('asset_id') or rel}")
            if require_image_captions and typ in {"image", "figure", "table"}:
                caption = item.get("caption_or_label")
                if not isinstance(caption, str) or not caption.strip():
                    errors.append(f"image/table asset has no manifest caption to translate: {item.get('asset_id') or rel}")
                    continue
                spans = referenced_image_spans.get(manifest_asset_path, [])
                if not spans:
                    errors.append(f"image/table asset has no inline image span for caption check: {item.get('asset_id') or rel}")
                    continue
                asset_label = str(item.get("asset_id") or rel)
                best_errors: list[str] | None = None
                best_warnings: list[str] = []
                for span in spans:
                    snippet = caption_snippet_after_image(guide, span)
                    caption_errors, caption_warnings = caption_blocks_ok(caption, snippet, asset_label)
                    if not caption_errors:
                        best_errors = []
                        best_warnings = caption_warnings
                        break
                    if best_errors is None or len(caption_errors) < len(best_errors):
                        best_errors = caption_errors
                        best_warnings = caption_warnings
                if best_errors:
                    errors.extend(best_errors)
                warnings.extend(best_warnings)

    status = "fail" if errors else ("warn" if warnings else "pass")
    return status, errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate literature_guide.md against paragraph_index.json")
    parser.add_argument("--guide", required=True, type=Path)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--asset-manifest", type=Path)
    parser.add_argument("--require-embedded-assets", action="store_true")
    parser.add_argument("--require-compact-blocks", action="store_true")
    parser.add_argument("--require-inline-assets", action="store_true")
    parser.add_argument(
        "--allow-latex-formula-assets",
        action="store_true",
        help="Count MinerU-recognized LaTeX formula text as embedded formula assets.",
    )
    parser.add_argument("--formula-latex-report", type=Path, help="JSON report from validate_formula_latex.py; passing formulas must be embedded as LaTeX and failed formulas must not")
    parser.add_argument("--require-image-captions", action="store_true", help="require image/table assets to have source caption, Chinese caption translation, and caption explanation after the image")
    parser.add_argument("--strict-translation-fidelity", action="store_true", help="warn/error on translation blocks that look compressed, meta-explanatory, or missing source anchors")
    parser.add_argument("--json", action="store_true", help="print JSON report")
    args = parser.parse_args()

    status, errors, warnings = validate(
        args.guide,
        args.index,
        args.assets_dir,
        args.asset_manifest,
        args.require_embedded_assets,
        args.require_compact_blocks,
        args.require_inline_assets,
        args.allow_latex_formula_assets,
        args.require_image_captions,
        args.formula_latex_report,
        args.strict_translation_fidelity,
    )
    report = {"status": status, "errors": errors, "warnings": warnings}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"status: {status}")
        for item in errors:
            print(f"ERROR: {item}")
        for item in warnings:
            print(f"WARN: {item}")
    return 1 if status == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
