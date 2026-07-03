#!/usr/bin/env python3
"""Build a compact paragraph guide with source-order inline assets."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path


SKIP_TYPES = {"header", "footer", "page_number", "aside_text"}
NON_BODY_KINDS = {"reference", "references", "acknowledgement", "funding", "metadata"}
SECTION_RE = re.compile(r"^(\d+\.|abstract\b|references\b|appendix\b|conclusions?\b)", re.I)
ANCHOR_RE = re.compile(r'(?=^<a id="P\d{3,}"></a>\s*$)', re.M)
PID_RE = re.compile(r'^<a id="(P\d{3,})"></a>\s*\n+\*\*\1\*\*', re.M)


def clean_text(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = text.replace("△", r"$\Delta$")
    text = text.replace(
        r"$( \delta _ { H } = 3 0 $ μm in mercury for $B = 1 \mathrm { T } )$",
        r"($\delta _ { H } = 30\,\mu\mathrm { m }$ in mercury for $B = 1 \mathrm { T }$)",
    )
    text = text.replace(r"\mathbf { \delta E }", r"\delta E")
    text = text.replace("unit vectorβ", r"unit vector $\boldsymbol{\beta}$")
    text = re.sub(r"-\s+([a-z])", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_caption_text(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = text.replace("△", r"$\Delta$")
    text = text.replace(r"\mathbf { \delta E }", r"\delta E")
    text = text.replace("unit vectorβ", r"unit vector $\boldsymbol{\beta}$")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", clean_text(text)).strip().lower()


def visible_text(markdown: str) -> str:
    text = re.sub(r"`[^`]*`", "", markdown)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"[>#*_~\\-]", " ", text)
    return " ".join(text.split())


def compact_label_text(markdown: str) -> str:
    text = re.sub(r"<!--.*?-->", "", markdown, flags=re.DOTALL)
    text = re.split(r"(?m)^\s*#{1,6}\s+", text, maxsplit=1)[0]
    text = text.strip()
    text = re.sub(r"[ \t]*\n[ \t]*", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def load_paragraphs(index_path: Path) -> list[dict]:
    data = json.loads(index_path.read_text(encoding="utf-8-sig"))
    records = data.get("paragraphs", data) if isinstance(data, dict) else data
    paragraphs: list[dict] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("guide") is False:
            continue
        kind = str(record.get("kind", "body")).strip().lower()
        section = str(record.get("section", "")).strip().lower()
        if kind in NON_BODY_KINDS or section.startswith("references"):
            continue
        pid = record.get("id") or record.get("paragraph_id") or record.get("pid")
        text = record.get("text")
        if not pid or not isinstance(text, str) or not text.strip():
            continue
        paragraphs.append({**record, "id": str(pid), "text": clean_text(text)})
    return paragraphs


def extract_pid_blocks(markdown: str) -> dict[str, str]:
    parts = ANCHOR_RE.split(markdown)
    blocks: dict[str, str] = {}
    for part in parts:
        match = PID_RE.search(part)
        if match:
            blocks[match.group(1)] = part
    return blocks


def extract_label(body: str, label: str, next_labels: tuple[str, ...]) -> str:
    compact = re.search(
        rf"\*\*{re.escape(label)}[：:]\*\*\s*(.*?)(?=" + "|".join(rf"\*\*{re.escape(x)}[：:]\*\*" for x in next_labels) + r"|\Z)",
        body,
        flags=re.S,
    )
    if compact:
        return compact.group(1).strip()

    start_marker = f"**{label}**"
    start = body.find(start_marker)
    if start == -1:
        return ""
    start += len(start_marker)
    end_positions = [body.find(f"**{x}**", start) for x in next_labels]
    end_positions.extend(body.find(f"**{x}：**", start) for x in next_labels)
    end_positions.extend(body.find(f"**{x}:**", start) for x in next_labels)
    end_positions = [x for x in end_positions if x != -1]
    end = min(end_positions) if end_positions else len(body)
    return body[start:end].strip()


def extract_translation_and_explanation(source_guide: str) -> dict[str, dict[str, str]]:
    blocks = extract_pid_blocks(source_guide)
    result: dict[str, dict[str, str]] = {}
    for pid, body in blocks.items():
        translation = extract_label(body, "翻译", ("讲解",))
        explanation = extract_label(body, "讲解", ())
        result[pid] = {
            "translation": compact_label_text(translation),
            "explanation": compact_label_text(explanation),
        }
    return result


def load_assets(asset_manifest_path: Path) -> dict[str, dict]:
    assets = json.loads(asset_manifest_path.read_text(encoding="utf-8-sig"))
    by_source: dict[str, dict] = {}
    for item in assets:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source_img_path") or "").replace("\\", "/")
        if source:
            by_source[source] = item
            by_source[Path(source).name] = item
    return by_source


def caption_key(text: str) -> str:
    return re.sub(r"\s+", " ", clean_caption_text(text)).strip().lower()


def load_caption_annotations(path: Path | None) -> dict[str, dict]:
    if not path:
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict) and isinstance(data.get("captions"), list):
        records = data["captions"]
    elif isinstance(data, list):
        records = data
    else:
        raise ValueError("caption annotations must be a list or an object with a captions list")
    annotations: dict[str, dict] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        keys = [
            record.get("asset_id"),
            record.get("path"),
            record.get("source_img_path"),
            record.get("caption_or_label"),
            record.get("caption_original"),
            record.get("original"),
        ]
        for key in keys:
            if isinstance(key, str) and key.strip():
                annotations[key.strip()] = record
                annotations[Path(key.replace("\\", "/")).name] = record
                annotations[caption_key(key)] = record
    return annotations


def load_formula_validation(path: Path | None) -> dict[str, dict]:
    if not path:
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    records = data.get("formulas", []) if isinstance(data, dict) else data
    if not isinstance(records, list):
        raise ValueError("formula validation report must contain a formulas list")
    result: dict[str, dict] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        for key in (record.get("asset_id"), record.get("path")):
            if isinstance(key, str) and key.strip():
                result[key.strip()] = record
                result[Path(key.replace("\\", "/")).name] = record
    return result


def formula_latex_allowed(asset: dict, validation: dict[str, dict]) -> bool:
    if not validation:
        return True
    keys = [
        asset.get("asset_id"),
        asset.get("path"),
        Path(str(asset.get("path") or "").replace("\\", "/")).name,
    ]
    for key in keys:
        if isinstance(key, str) and key.strip() and key.strip() in validation:
            return str(validation[key.strip()].get("status") or "").lower() == "pass"
    return False


def formula_latex_for_asset(asset: dict, validation: dict[str, dict]) -> str:
    caption = str(asset.get("caption_or_label") or "").strip()
    keys = [
        asset.get("asset_id"),
        asset.get("path"),
        Path(str(asset.get("path") or "").replace("\\", "/")).name,
    ]
    for key in keys:
        if isinstance(key, str) and key.strip() and key.strip() in validation:
            record = validation[key.strip()]
            latex = str(record.get("latex") or record.get("normalized_latex") or "").strip()
            if latex:
                return latex
    return caption


def find_caption_annotation(asset: dict, caption: str, annotations: dict[str, dict]) -> dict | None:
    keys = [
        asset.get("asset_id"),
        asset.get("path"),
        asset.get("source_img_path"),
        caption,
        Path(str(asset.get("path") or "").replace("\\", "/")).name,
        Path(str(asset.get("source_img_path") or "").replace("\\", "/")).name,
        caption_key(caption),
    ]
    for key in keys:
        if isinstance(key, str) and key.strip() and key.strip() in annotations:
            return annotations[key.strip()]
    return None


def caption_note(asset: dict, caption: str, annotation: dict | None) -> str:
    if not caption.strip() and not annotation:
        return ""
    original = ""
    translation = ""
    explanation = ""
    if annotation:
        original = str(annotation.get("caption_original") or annotation.get("original") or "").strip()
        translation = str(annotation.get("translation") or annotation.get("caption_translation") or "").strip()
        explanation = str(annotation.get("explanation") or annotation.get("caption_explanation") or "").strip()
    if not original:
        original = caption.strip()
    parts = [f"**图注原文：** {clean_caption_text(original)}"]
    if translation:
        parts.append(f"**图注翻译：** {compact_label_text(translation)}")
    if explanation:
        parts.append(f"**图注讲解：** {compact_label_text(explanation)}")
    return "\n\n".join(parts)


def is_heading_item(item: dict, text: str) -> bool:
    if isinstance(item.get("text_level"), int) and item.get("text_level") > 0:
        return True
    return bool(SECTION_RE.match(text))


def find_paragraph(paragraphs: list[dict], text: str, start: int) -> int | None:
    text_norm = norm(text)
    if not text_norm:
        return None
    for idx in range(start, min(len(paragraphs), start + 8)):
        para_norm = norm(str(paragraphs[idx].get("text", "")))
        if text_norm == para_norm or text_norm in para_norm:
            return idx
    for idx in range(0, len(paragraphs)):
        para_norm = norm(str(paragraphs[idx].get("text", "")))
        if text_norm == para_norm or text_norm in para_norm:
            return idx
    return None


def paragraph_for_content_index(paragraphs: list[dict], content_index: int) -> int | None:
    best: int | None = None
    for idx, para in enumerate(paragraphs):
        indices = para.get("content_indices")
        if isinstance(indices, list) and indices:
            numeric = [int(x) for x in indices if isinstance(x, int)]
            start = min(numeric) if numeric else None
            end = max(numeric) if numeric else start
        else:
            raw_start = para.get("content_index")
            raw_end = para.get("end_content_index", raw_start)
            start = int(raw_start) if isinstance(raw_start, int) else None
            end = int(raw_end) if isinstance(raw_end, int) else start
        if start is None:
            continue
        if start <= content_index and (best is None or start >= int(paragraphs[best].get("content_index") or -1)):
            best = idx
        if start <= content_index <= (end if end is not None else start):
            return idx
    return best


def build_events(
    content_list: list[dict],
    paragraphs: list[dict],
    assets_by_source: dict[str, dict],
    package_dir: Path,
    asset_mode: str,
    caption_annotations: dict[str, dict],
    formula_validation: dict[str, dict],
) -> tuple[dict[str, list[dict]], list[dict], list[str]]:
    events = {str(p["id"]): [] for p in paragraphs}
    order_index = 0
    current_idx = 0
    last_pid: str | None = None
    accumulated: dict[str, str] = {}
    assignments: list[dict] = []
    warnings: list[str] = []

    for content_index, item in enumerate(content_list):
        if not isinstance(item, dict):
            continue
        typ = str(item.get("type", "text"))
        if typ in SKIP_TYPES:
            continue
        if typ == "text":
            text = clean_text(str(item.get("text") or ""))
            if not text or is_heading_item(item, text):
                continue
            idx = find_paragraph(paragraphs, text, current_idx)
            if idx is None:
                continue
            pid = str(paragraphs[idx]["id"])
            events[pid].append({"kind": "text", "text": text, "order": order_index, "page_idx": item.get("page_idx")})
            order_index += 1
            last_pid = pid
            accumulated[pid] = clean_text((accumulated.get(pid, "") + " " + text).strip())
            if norm(paragraphs[idx]["text"]) in norm(accumulated[pid]) or norm(accumulated[pid]) in norm(paragraphs[idx]["text"]):
                current_idx = max(current_idx, idx + 1)
            else:
                current_idx = max(current_idx, idx)
            continue
        if typ not in {"equation", "image", "table"}:
            continue
        source_img = str(item.get("img_path") or "").replace("\\", "/")
        asset = assets_by_source.get(source_img) or assets_by_source.get(Path(source_img).name)
        if not asset:
            warnings.append(f"asset missing from manifest: {source_img}")
            continue
        anchor_idx = paragraph_for_content_index(paragraphs, content_index)
        anchor_pid = str(paragraphs[anchor_idx]["id"]) if anchor_idx is not None else last_pid
        if not anchor_pid:
            warnings.append(f"asset has no preceding paragraph: {asset.get('asset_id') or source_img}")
            continue
        rel = str(asset.get("path") or "")
        caption = str(asset.get("caption_or_label") or "")
        rendered = ""
        asset_type = str(asset.get("type") or "").lower()
        note = ""
        caption_annotation = None
        if (
            asset_type == "formula"
            and asset_mode == "latex"
            and caption.strip().startswith("$$")
            and formula_latex_allowed(asset, formula_validation)
        ):
            rendered = formula_latex_for_asset(asset, formula_validation)
        else:
            rendered = f"![]({rel})"
            if asset_type == "formula" and asset_mode == "latex" and caption.strip().startswith("$$"):
                warnings.append(f"formula LaTeX failed validation and used image fallback: {asset.get('asset_id') or rel}")
            if asset_type in {"image", "figure", "table"}:
                caption_annotation = find_caption_annotation(asset, caption, caption_annotations)
                note = caption_note(asset, caption, caption_annotation)
                if caption.strip() and not caption_annotation:
                    warnings.append(f"image/table caption has no translation annotation: {asset.get('asset_id') or rel}")
        events[anchor_pid].append(
            {
                "kind": "asset",
                "asset_type": asset_type,
                "asset_id": asset.get("asset_id"),
                "path": rel,
                "rendered": rendered,
                "caption": caption,
                "caption_note": note,
                "has_caption_translation": bool(caption_annotation and str(caption_annotation.get("translation") or caption_annotation.get("caption_translation") or "").strip()),
                "has_caption_explanation": bool(caption_annotation and str(caption_annotation.get("explanation") or caption_annotation.get("caption_explanation") or "").strip()),
                "order": order_index,
                "content_index": content_index,
                "page_idx": item.get("page_idx"),
            }
        )
        assignments.append(
            {
                "asset_id": asset.get("asset_id"),
                "asset_type": asset_type,
                "path": rel,
                "paragraph_id": anchor_pid,
                "source_pdf_page": item.get("page_idx"),
                "mode": "latex" if rendered.startswith("$$") else "image",
                "caption": caption if asset_type in {"image", "figure", "table"} else "",
                "caption_note": bool(note),
                "caption_translation": bool(caption_annotation and str(caption_annotation.get("translation") or caption_annotation.get("caption_translation") or "").strip()),
                "caption_explanation": bool(caption_annotation and str(caption_annotation.get("explanation") or caption_annotation.get("caption_explanation") or "").strip()),
            }
        )
        order_index += 1
    return events, assignments, warnings


def trim_asset_overview(first_part: str) -> str:
    replacement = (
        "### 8. 图表与公式导读\n\n"
        "图表与公式按照原文出现顺序嵌入在第二部分逐段导读中；本节只给出总体阅读提示，避免在正文前重复堆叠公式和图片。\n\n"
    )
    pattern = re.compile(r"^### 8\. 图表与公式(?:资产)?导读\s*\n.*?(?=^### \d+\.|\Z)", flags=re.S | re.M)
    if pattern.search(first_part):
        return pattern.sub(replacement, first_part)
    return first_part


def build_original(events: list[dict], fallback_text: str) -> str:
    parts: list[str] = [fallback_text]
    for event in sorted(events, key=lambda x: x.get("order", 0)):
        if event["kind"] == "asset":
            parts.append(event["rendered"])
            if event.get("caption_note"):
                parts.append(str(event["caption_note"]))
    return "\n\n".join(part for part in parts if part.strip())


INLINE_MATH_RE = re.compile(r"\$[^$\n]*\$")


def safe_explanation_excerpt(text: str, limit: int = 90) -> str:
    """Return a short prose excerpt without cutting through inline math."""
    text = INLINE_MATH_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[:limit].rstrip(" ,.;:，。；：") + "..."
    return text or "this paragraph's local claim"


def concise_explanation(para: dict, translation: str) -> str:
    section = str(para.get("section") or "").strip()
    source = str(para.get("text") or "")
    first_sentence = re.split(r"[。！？；;]", translation.strip(), maxsplit=1)[0].strip()
    first_sentence = safe_explanation_excerpt(first_sentence)
    anchors = []
    for pattern in (
        r"\b(?:Hartmann|MHD|Kulikovskii|Shercliff|Hunt|Lehnert|Murgatroyd)\b",
        r"\b(?:Equation|Figure)\s*[0-9][0-9A-Za-z.]*",
        r"\b[MBQIN]\b",
    ):
        for match in re.findall(pattern, source):
            value = match if isinstance(match, str) else " ".join(match)
            if value and value not in anchors:
                anchors.append(value)
            if len(anchors) >= 4:
                break
        if len(anchors) >= 4:
            break
    anchor_text = "、".join(anchors[:4]) if anchors else "该段中的变量、边界条件和引用"
    if section:
        return f"在“{section}”部分，这段推进的要点是：{first_sentence}。阅读时重点核对 {anchor_text}，因为它们限定了该段结论适用的物理区域或数学条件。"
    return f"这段推进的要点是：{first_sentence}。阅读时重点核对 {anchor_text}，因为它们限定了该段结论适用的物理区域或数学条件。"


def build_guide(
    source_guide: str,
    paragraphs: list[dict],
    events: dict[str, list[dict]],
    translations: dict[str, dict[str, str]],
) -> str:
    second_marker = "## 第二部分：逐段导读"
    if second_marker in source_guide:
        first_part = source_guide[: source_guide.find(second_marker)].rstrip()
    else:
        first_part = source_guide.rstrip()
    first_part = trim_asset_overview(first_part)

    lines = [first_part.rstrip(), "", second_marker, ""]
    current_section: str | None = None
    for para in paragraphs:
        section = str(para.get("section") or "").strip()
        if section and section != current_section:
            lines.extend([f"## {section}", ""])
            current_section = section
        pid = str(para["id"])
        original = build_original(events.get(pid, []), str(para["text"]))
        translation = translations.get(pid, {}).get("translation", "").strip()
        explanation = translations.get(pid, {}).get("explanation", "").strip()
        if not explanation:
            explanation = concise_explanation(para, translation)
        lines.extend([f'<a id="{pid}"></a>', "", f"**{pid}**", ""])
        lines.append(f"**原文：** {original}")
        lines.append("")
        lines.append(f"**翻译：** {translation}")
        lines.append("")
        lines.append(f"**讲解：** {explanation}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert a guide to compact inline paragraph format")
    parser.add_argument("--source-guide", required=True, type=Path)
    parser.add_argument("--paragraph-index", required=True, type=Path)
    parser.add_argument("--content-list", required=True, type=Path)
    parser.add_argument("--asset-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--asset-mode", choices=("latex", "image"), default="latex")
    parser.add_argument("--caption-annotations", type=Path, help="JSON records keyed by asset_id/path/caption with caption translation and explanation")
    parser.add_argument("--formula-validation-report", type=Path, help="JSON report from validate_formula_latex.py; failed formulas fall back to images")
    args = parser.parse_args()

    source_guide = args.source_guide.read_text(encoding="utf-8")
    paragraphs = load_paragraphs(args.paragraph_index)
    content_list = json.loads(args.content_list.read_text(encoding="utf-8-sig"))
    if not isinstance(content_list, list):
        raise ValueError("content_list must be a JSON list")
    assets_by_source = load_assets(args.asset_manifest)
    caption_annotations = load_caption_annotations(args.caption_annotations)
    formula_validation = load_formula_validation(args.formula_validation_report)
    translations = extract_translation_and_explanation(source_guide)
    events, assignments, warnings = build_events(
        content_list,
        paragraphs,
        assets_by_source,
        args.asset_manifest.parent,
        args.asset_mode,
        caption_annotations,
        formula_validation,
    )
    if args.asset_mode == "latex" and not args.formula_validation_report:
        warnings.append("asset-mode=latex used without --formula-validation-report; run validate_formula_latex.py before production rendering")
    output = build_guide(source_guide, paragraphs, events, translations)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")

    report = {
        "source_guide": str(args.source_guide.resolve()),
        "output": str(args.output.resolve()),
        "paragraphs": len(paragraphs),
        "paragraphs_with_assets": len({x["paragraph_id"] for x in assignments}),
        "asset_assignments": assignments,
        "asset_assignment_count": len(assignments),
        "formula_latex_count": sum(1 for x in assignments if x["asset_type"] == "formula" and x["mode"] == "latex"),
        "image_asset_count": sum(1 for x in assignments if x["mode"] == "image"),
        "image_caption_count": sum(1 for x in assignments if x.get("caption")),
        "image_caption_translation_count": sum(1 for x in assignments if x.get("caption_translation")),
        "image_caption_explanation_count": sum(1 for x in assignments if x.get("caption_explanation")),
        "warnings": warnings,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
