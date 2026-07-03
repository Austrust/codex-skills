#!/usr/bin/env python3
"""Audit harness for Zotero literature-guide packages.

The harness is intentionally conservative. It does not generate guide prose and
does not write Zotero. It checks whether a package is structurally safe to keep
moving through the literature-guide workflow.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


CHINESE_LABELS = {
    "original": "**原文：**",
    "translation": "**翻译：**",
    "explanation": "**讲解：**",
    "caption_original": "**图注原文：**",
    "caption_translation": "**图注翻译：**",
    "caption_explanation": "**图注讲解：**",
}

FORBIDDEN_READING_BODY_PHRASES = {
    "needs_pdf": "需要对照PDF",
    "technical_paraphrase": "技术意译",
    "generation_note": "生成说明",
    "local_ollama": "本地 Ollama",
}

GENERIC_EXPLANATION_PHRASES = (
    "这一段承接所在小节",
    "这一节建立",
    "这一节把前面",
    "这一节固定",
    "引言通过两类实验",
    "阅读时要特别跟踪",
    "主要服务于",
    "不是背景细节",
    "该处同时服务于",
    "二维性在文中被分成",
)

DEFAULT_SKILL_ROOT = Path(__file__).resolve().parents[1]
IMAGE_LINK_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
DISPLAY_MATH_RE = re.compile(r"^\s*\$\$", flags=re.MULTILINE)
RAW_TEX_ENV_RE = re.compile(r"\\begin\{[^}]+\}|\\end\{[^}]+\}")
FORMULA_OCR_TEX_HINT_RE = re.compile(
    r"(\$\$|\\begin\{|\\end\{|\\frac|\\hat|\\bar|\\mathrm|\\mathbf|\\int|\\sum|[_^]\s*\{)"
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def normalize_markdown_image_target(target: str) -> str:
    return target.split()[0].strip("<>\"'").replace("\\", "/")


def looks_like_formula_ocr(text: object) -> bool:
    if not isinstance(text, str):
        return False
    stripped = text.strip()
    if len(stripped) < 8:
        return False
    return bool(FORMULA_OCR_TEX_HINT_RE.search(stripped))


def compact_formula_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def formula_latex_in_guide(guide: str, latex: object) -> bool:
    if not isinstance(latex, str):
        return False
    stripped = latex.strip()
    if not stripped:
        return False
    return stripped in guide or compact_formula_text(stripped) in compact_formula_text(guide)


def formula_latex_candidates(item: dict[str, Any], report_by_key: dict[str, dict[str, Any]]) -> list[str]:
    candidates: list[str] = []
    keys = [
        item.get("asset_id"),
        item.get("path"),
        Path(str(item.get("path") or "").replace("\\", "/")).name,
    ]
    for key in keys:
        if isinstance(key, str) and key.strip() and key.strip() in report_by_key:
            record = report_by_key[key.strip()]
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


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    path: str | None = None
    detail: Any = None


@dataclass
class Harness:
    package: Path
    workspace: Path
    skill_root: Path | None
    stage: str
    run_validator: bool
    findings: list[Finding] = field(default_factory=list)
    encodings: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)

    def add(self, severity: str, code: str, message: str, path: Path | None = None, detail: Any = None) -> None:
        rel = str(path) if path is not None else None
        self.findings.append(Finding(severity, code, message, rel, detail))

    def require_file(self, rel: str, severity: str = "error") -> Path | None:
        path = self.package / rel
        if not path.exists():
            self.add(severity, "missing_file", f"Missing required file: {rel}", path)
            return None
        if path.is_file() and path.stat().st_size == 0:
            self.add(severity, "empty_file", f"Required file is empty: {rel}", path)
        return path

    def read_text_auto(self, path: Path) -> tuple[str, str]:
        data = path.read_bytes()
        if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
            encoding = "utf-16"
            return data.decode(encoding), encoding
        if data.startswith(b"\xef\xbb\xbf"):
            return data.decode("utf-8-sig"), "utf-8-sig"
        try:
            return data.decode("utf-8"), "utf-8"
        except UnicodeDecodeError:
            for encoding in ("utf-16", "utf-16-le", "utf-16-be"):
                try:
                    return data.decode(encoding), encoding
                except UnicodeDecodeError:
                    continue
            return data.decode("utf-8", errors="replace"), "replace"

    def read_json_auto(self, rel: str, *, required: bool = True) -> tuple[Any | None, str | None]:
        path = self.package / rel
        if not path.exists():
            if required:
                self.add("error", "missing_json", f"Missing JSON file: {rel}", path)
            return None, None
        text, encoding = self.read_text_auto(path)
        self.encodings[rel] = encoding
        if encoding not in ("utf-8", "utf-8-sig"):
            self.add("error", "non_utf8_json", f"JSON must be UTF-8, found {encoding}: {rel}", path)
        try:
            return json.loads(text), encoding
        except json.JSONDecodeError as exc:
            self.add("error", "invalid_json", f"Invalid JSON in {rel}: {exc}", path)
            return None, encoding

    def read_markdown(self) -> str:
        path = self.require_file("literature_guide.md")
        if path is None:
            return ""
        text, encoding = self.read_text_auto(path)
        self.encodings["literature_guide.md"] = encoding
        if encoding not in ("utf-8", "utf-8-sig"):
            self.add("error", "non_utf8_markdown", f"Markdown must be UTF-8, found {encoding}", path)
        return text

    def extract_label_blocks(self, guide: str, label: str) -> list[str]:
        label_re = re.compile(rf"^{re.escape(label)}\s*(.*)$")
        stop_re = re.compile(
            r"^(?:"
            r"\*\*(?:P\d{3,}|原文|翻译|讲解|图注原文|图注翻译|图注讲解)：?\*\*"
            r"|<a id="
            r"|#{1,6}\s+"
            r"|!\["
            r")"
        )
        blocks: list[str] = []
        current: list[str] | None = None
        for line in guide.splitlines():
            match = label_re.match(line)
            if match:
                if current is not None:
                    blocks.append(" ".join(" ".join(current).split()))
                current = [match.group(1).strip()]
                continue
            if current is None:
                continue
            if not line.strip():
                blocks.append(" ".join(" ".join(current).split()))
                current = None
                continue
            if stop_re.match(line):
                blocks.append(" ".join(" ".join(current).split()))
                current = None
                continue
            current.append(line.strip())
        if current is not None:
            blocks.append(" ".join(" ".join(current).split()))
        return blocks

    def check_explanation_quality(self, guide: str, expected_count: int) -> None:
        explanations = self.extract_label_blocks(guide, CHINESE_LABELS["explanation"])
        counts = Counter(explanations)
        repeated = [
            {"count": count, "text": text[:160]}
            for text, count in counts.most_common()
            if text and count > 1
        ]
        empty_count = counts.get("", 0)
        generic_count = sum(
            1
            for text in explanations
            if any(phrase in text for phrase in GENERIC_EXPLANATION_PHRASES)
        )
        total = len(explanations)
        unique_nonempty = len([text for text in counts if text])
        unique_ratio = unique_nonempty / total if total else 1.0
        generic_ratio = generic_count / total if total else 0.0
        max_repeat = repeated[0]["count"] if repeated else 1
        self.metrics["explanation_quality"] = {
            "paragraph_explanation_blocks": total,
            "expected_paragraph_explanations": expected_count,
            "empty_count": empty_count,
            "unique_nonempty_count": unique_nonempty,
            "unique_ratio": round(unique_ratio, 3),
            "generic_phrase_count": generic_count,
            "generic_phrase_ratio": round(generic_ratio, 3),
            "max_repeat": max_repeat,
            "top_repeated": repeated[:5],
        }
        if total != expected_count:
            self.add(
                "warning",
                "explanation_block_count_mismatch",
                "Extracted paragraph explanation block count differs from guided paragraph count.",
                self.package / "literature_guide.md",
                {"explanations": total, "guided": expected_count},
            )
        if empty_count:
            self.add(
                "error",
                "empty_explanation_blocks",
                "Some paragraph explanation blocks are empty.",
                self.package / "literature_guide.md",
                {"empty_count": empty_count},
            )
        if total and (unique_ratio < 0.8 or max_repeat >= 3 or generic_ratio > 0.35):
            self.add(
                "error",
                "low_information_explanations",
                "Paragraph explanations look repetitive or template-like; review content depth before marking the package ready.",
                self.package / "literature_guide.md",
                {
                    "unique_ratio": round(unique_ratio, 3),
                    "max_repeat": max_repeat,
                    "generic_phrase_ratio": round(generic_ratio, 3),
                    "top_repeated": repeated[:3],
                },
            )

    def run(self) -> dict[str, Any]:
        self.check_location()
        self.check_required_layout()

        index, _ = self.read_json_auto("extraction/paragraph_index.json")
        assets, _ = self.read_json_auto("asset_manifest.json")
        status, _ = self.read_json_auto("status.json", required=False)
        validation, _ = self.read_json_auto("guide_validation.json", required=False)
        cache, _ = self.read_json_auto("batches/ollama_translation_cache.json", required=False)
        formula_report, _ = self.read_json_auto("formula_latex_validation.json", required=False)
        guide = self.read_markdown()

        self.check_paragraphs(index, status, cache, guide)
        self.check_assets(assets, guide, status, formula_report)
        self.check_status(status, validation, guide)
        if self.run_validator:
            self.check_with_skill_validator()
        self.check_stage_files(status)

        return self.report()

    def check_location(self) -> None:
        try:
            rel = self.package.resolve().relative_to((self.workspace / "outputs").resolve())
        except ValueError:
            self.add(
                "warning",
                "non_production_package_location",
                "Package is not under outputs/<item_key>; keep test packages out of the production index.",
                self.package,
            )
            return
        if len(rel.parts) != 1:
            self.add("warning", "nested_package_location", "Production package should be outputs/<item_key>.", self.package)

    def check_required_layout(self) -> None:
        for rel in (
            "source/zotero_lookup.json",
            "source/zotero_item.json",
            "source/zotero_children.json",
            "source/source.pdf",
            "extraction/mineru_result.json",
            "extraction/extracted.md",
            "extraction/content_list.json",
            "extraction/paragraph_index.json",
            "asset_manifest.json",
            "literature_guide.md",
            "status.json",
        ):
            self.require_file(rel)
        for rel in ("README.md", "build_log.md"):
            self.require_file(rel, severity="warning")

    def check_paragraphs(self, index: Any, status: Any, cache: Any, guide: str) -> None:
        if not isinstance(index, dict) or not isinstance(index.get("paragraphs"), list):
            self.add("error", "bad_paragraph_index", "paragraph_index.json must contain a paragraphs list.")
            return
        paragraphs = index["paragraphs"]
        guided = [
            p
            for p in paragraphs
            if isinstance(p, dict) and p.get("guide") is not False and p.get("kind") != "metadata"
        ]
        guided_ids = {str(p.get("id")) for p in guided}
        anchors = re.findall(r'<a id="(P\d{3,})"></a>', guide)
        bold_ids = re.findall(r"^\*\*(P\d{3,})\*\*", guide, flags=re.M)
        markdown_ids = set(anchors) | set(bold_ids)
        label_counts = {name: guide.count(label) for name, label in CHINESE_LABELS.items()}

        self.metrics.update(
            {
                "paragraph_index_total": len(paragraphs),
                "guided_count_by_index": len(guided),
                "markdown_anchor_count": len(anchors),
                "markdown_bold_pid_count": len(bold_ids),
                "label_counts": label_counts,
                "excluded_paragraphs": [
                    {
                        "id": p.get("id"),
                        "kind": p.get("kind"),
                        "guide": p.get("guide"),
                        "text": p.get("text"),
                        "boundary_note": p.get("boundary_note"),
                    }
                    for p in paragraphs
                    if isinstance(p, dict)
                    and (p.get("guide") is False or p.get("kind") in {"metadata", "parser_fragment"})
                ],
            }
        )

        for label_name in ("original", "translation", "explanation"):
            if label_counts[label_name] != len(guided):
                self.add(
                    "error",
                    "paragraph_label_count_mismatch",
                    f"{label_name} count {label_counts[label_name]} != guided paragraph count {len(guided)}.",
                    self.package / "literature_guide.md",
                )
        if len(anchors) != len(guided) or len(bold_ids) != len(guided):
            self.add(
                "error",
                "paragraph_id_count_mismatch",
                "Markdown paragraph anchors/bold IDs must match guided paragraph count.",
                self.package / "literature_guide.md",
                {"anchors": len(anchors), "bold_ids": len(bold_ids), "guided": len(guided)},
            )

        missing_in_md = sorted(guided_ids - markdown_ids)
        extra_in_md = sorted(markdown_ids - guided_ids)
        if missing_in_md:
            self.add("error", "guided_ids_missing_in_markdown", "Guided paragraphs missing from Markdown.", detail=missing_in_md)
        if extra_in_md:
            self.add("error", "markdown_ids_not_guided", "Markdown contains paragraph IDs not marked for guide.", detail=extra_in_md)

        self.check_explanation_quality(guide, len(guided))

        if isinstance(status, dict):
            self.metrics["status_paragraphs_guided"] = status.get("paragraphs_guided")
            if status.get("paragraphs_guided") != len(guided):
                self.add(
                    "error",
                    "status_count_mismatch",
                    "status.json paragraphs_guided does not match paragraph_index guided count.",
                    self.package / "status.json",
                    {"status": status.get("paragraphs_guided"), "guided": len(guided)},
                )

        if isinstance(cache, dict):
            cache_ids = set(cache)
            self.metrics["translation_cache_entries"] = len(cache)
            missing_cache = sorted(guided_ids - cache_ids)
            orphan_cache = sorted(cache_ids - guided_ids)
            if missing_cache:
                self.add("error", "translation_cache_missing_guided_ids", "Cache misses guided paragraphs.", detail=missing_cache)
            if orphan_cache:
                self.add(
                    "warning",
                    "translation_cache_orphans",
                    "Cache contains IDs no longer guided; this is acceptable only if parser fragments were excluded after generation.",
                    detail=orphan_cache,
                )

        short_excluded = [
            p.get("id")
            for p in paragraphs
            if isinstance(p, dict)
            and p.get("guide") is not False
            and len(str(p.get("text") or "").strip()) < 20
        ]
        if short_excluded:
            self.add("error", "short_guided_paragraphs", "Very short parser fragments are still marked for guide.", detail=short_excluded)

    def check_assets(self, assets: Any, guide: str, status: Any, formula_report: Any) -> None:
        if not isinstance(assets, list):
            self.add("error", "bad_asset_manifest", "asset_manifest.json must be a list.")
            return
        counts: dict[str, int] = {}
        formula_assets: list[dict[str, Any]] = []
        for item in assets:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("type") or "unknown").lower()
            counts[kind] = counts.get(kind, 0) + 1
            if kind in {"formula", "equation"}:
                formula_assets.append(item)
        self.metrics["asset_counts"] = counts
        image_count = counts.get("image", 0) + counts.get("figure", 0) + counts.get("table", 0)
        for label_name in ("caption_original", "caption_translation", "caption_explanation"):
            found = guide.count(CHINESE_LABELS[label_name])
            if image_count and found < image_count:
                self.add(
                    "error",
                    "caption_count_mismatch",
                    f"{label_name} count {found} < image/table asset count {image_count}.",
                    self.package / "literature_guide.md",
                )

        image_links: dict[Path, list[str]] = {}
        for match in IMAGE_LINK_RE.finditer(guide):
            alt = match.group(1)
            target = normalize_markdown_image_target(match.group(2))
            if target.startswith(("http://", "https://", "data:")):
                continue
            image_links.setdefault((self.package / target).resolve(), []).append(alt)

        formula_status_by_key: dict[str, str] = {}
        formula_record_by_key: dict[str, dict[str, Any]] = {}
        formula_report_present = isinstance(formula_report, dict) and isinstance(formula_report.get("formulas"), list)
        if formula_report_present:
            for record in formula_report.get("formulas", []):
                if not isinstance(record, dict):
                    continue
                rec_status = str(record.get("status") or "").strip().lower()
                for key in (record.get("asset_id"), record.get("path")):
                    if isinstance(key, str) and key.strip():
                        formula_status_by_key[key.strip()] = rec_status
                        formula_status_by_key[Path(key.replace("\\", "/")).name] = rec_status
                        formula_record_by_key[key.strip()] = record
                        formula_record_by_key[Path(key.replace("\\", "/")).name] = record

        formula_image_embedded = 0
        formula_latex_embedded = 0
        formula_image_fallback_count = 0
        for item in formula_assets:
            rel = item.get("path")
            if not isinstance(rel, str) or not rel.strip():
                self.add(
                    "error",
                    "formula_asset_missing_path",
                    "Formula asset must have a source-derived image path.",
                    self.package / "asset_manifest.json",
                    item.get("asset_id"),
                )
                continue
            asset_path = (self.package / rel).resolve()
            if not asset_path.exists():
                self.add(
                    "error",
                    "formula_asset_file_missing",
                    "Formula asset image file is missing.",
                    asset_path,
                    item.get("asset_id"),
                )
                continue
            alts = image_links.get(asset_path, [])
            caption = item.get("caption_or_label")
            latex_candidates = formula_latex_candidates(item, formula_record_by_key)
            latex_embedded = any(formula_latex_in_guide(guide, candidate) for candidate in latex_candidates)
            latex_status = None
            for key in (item.get("asset_id"), rel, Path(rel.replace("\\", "/")).name):
                if isinstance(key, str) and key.strip() and key.strip() in formula_status_by_key:
                    latex_status = formula_status_by_key[key.strip()]
                    break
            if latex_embedded:
                formula_latex_embedded += 1
            if alts:
                formula_image_embedded += 1
                if any(alt.strip() for alt in alts):
                    self.add(
                        "error",
                        "formula_image_alt_not_empty",
                        "Formula image links must use empty alt text so Pandoc does not create fake figure captions.",
                        self.package / "literature_guide.md",
                        item.get("asset_id") or rel,
                    )
            if looks_like_formula_ocr(caption) and not latex_embedded and latex_status == "pass":
                self.add(
                    "error",
                    "validated_formula_latex_not_used",
                    "MinerU formula LaTeX passed validation but the guide used a formula image or omitted it.",
                    self.package / "literature_guide.md",
                    item.get("asset_id") or rel,
                )
            elif looks_like_formula_ocr(caption) and not latex_embedded and latex_status not in {"fail", "error"}:
                self.add(
                    "error",
                    "formula_recognition_not_used",
                    "MinerU recognized formula LaTeX is available, but the guide did not embed it and no failed formula validation record justifies image fallback.",
                    self.package / "literature_guide.md",
                    item.get("asset_id") or rel,
                )
            elif not latex_embedded and latex_status in {"fail", "error"}:
                formula_image_fallback_count += 1
                if not alts:
                    self.add(
                        "error",
                        "failed_formula_missing_image_fallback",
                        "Formula LaTeX failed validation; a source-derived formula image fallback must be embedded.",
                        self.package / "literature_guide.md",
                        item.get("asset_id") or rel,
                    )

        display_math_count = len(DISPLAY_MATH_RE.findall(guide))
        raw_tex_env_count = len(RAW_TEX_ENV_RE.findall(guide))
        math_enabled_evidence = self.render_math_parsing_enabled(status)
        self.metrics["formula_asset_count"] = len(formula_assets)
        self.metrics["formula_image_embedded_count"] = formula_image_embedded
        self.metrics["formula_latex_embedded_count"] = formula_latex_embedded
        self.metrics["formula_image_fallback_count"] = formula_image_fallback_count
        self.metrics["formula_latex_validation_status"] = formula_report.get("status") if isinstance(formula_report, dict) else None
        self.metrics["tex_like_markdown_counts"] = {
            "display_math_lines": display_math_count,
            "raw_tex_environments": raw_tex_env_count,
            "math_parsing_enabled_evidence": math_enabled_evidence,
        }
        if formula_assets and not formula_report_present:
            self.add(
                "warning",
                "formula_latex_validation_missing",
                "Run validate_formula_latex.py and store formula_latex_validation.json before production render/attach.",
                self.package / "formula_latex_validation.json",
            )
        if formula_latex_embedded and not math_enabled_evidence:
            self.add(
                "warning",
                "math_parsing_enabled_not_recorded",
                "Formula LaTeX is embedded; record that rendering used markdown math parsing enabled.",
                self.package / "build_log.md",
            )

    def render_math_parsing_enabled(self, status: Any) -> bool:
        if isinstance(status, dict):
            value = str(status.get("render_math_parsing") or status.get("markdown_math_parsing") or "").strip().lower()
            if value in {"enabled", "on", "true", "yes"}:
                return True
        build_log = self.package / "build_log.md"
        if not build_log.exists():
            return False
        text, _ = self.read_text_auto(build_log)
        evidence = (
            "Markdown math parsing enabled",
            "markdown+tex_math_dollars+tex_math_single_backslash",
            "formula rendering uses MinerU-recognized LaTeX",
        )
        return any(item in text for item in evidence)

    def check_status(self, status: Any, validation: Any, guide: str) -> None:
        forbidden_counts = {name: guide.count(text) for name, text in FORBIDDEN_READING_BODY_PHRASES.items()}
        self.metrics["forbidden_phrase_counts"] = forbidden_counts
        for name, count in forbidden_counts.items():
            if count:
                severity = "error" if name in {"needs_pdf", "technical_paraphrase"} else "warning"
                self.add(
                    severity,
                    "forbidden_or_review_phrase_in_guide",
                    f"Guide body contains {count} occurrence(s) of review/provenance phrase: {FORBIDDEN_READING_BODY_PHRASES[name]}",
                    self.package / "literature_guide.md",
                )

        if isinstance(status, dict):
            model = str(status.get("translation_model") or "")
            self.metrics["translation_model"] = model
            reviewed = self.content_review_passed(status) if model else False
            self.metrics["content_review_passed"] = reviewed
            if model and not reviewed:
                self.add(
                    "warning",
                    "external_translation_model",
                    "Paragraph translation/explanation came from an external/local model cache; keep package needs-review until Codex or human review evidence is recorded.",
                    self.package / "status.json",
                    {"translation_model": model},
                )
                if status.get("status") != "needs-review":
                    self.add(
                        "error",
                        "external_model_without_needs_review",
                        "Unreviewed external/local model output must keep status.json status as needs-review.",
                        self.package / "status.json",
                    )

        if isinstance(validation, dict):
            self.metrics["recorded_validation_status"] = validation.get("status")
            if validation.get("status") == "fail":
                self.add(
                    "error",
                    "recorded_validation_failed",
                    "Recorded guide_validation.json is fail; rerun validator after fixes and store UTF-8 JSON.",
                    self.package / "guide_validation.json",
                    validation.get("errors"),
                )

    def check_with_skill_validator(self) -> None:
        if self.skill_root is None:
            self.add("warning", "validator_skipped", "No skill root supplied; strict validator was not run.")
            return
        validator = self.skill_root / "scripts" / "validate_guide.py"
        if not validator.exists():
            self.add("warning", "validator_missing", "Skill validate_guide.py not found.", validator)
            return
        args = [
            sys.executable,
            str(validator),
            "--guide",
            str(self.package / "literature_guide.md"),
            "--index",
            str(self.package / "extraction" / "paragraph_index.json"),
            "--assets-dir",
            str(self.package),
            "--asset-manifest",
            str(self.package / "asset_manifest.json"),
            "--require-embedded-assets",
            "--require-compact-blocks",
            "--require-inline-assets",
            "--require-image-captions",
            "--strict-translation-fidelity",
            "--allow-latex-formula-assets",
            "--json",
        ]
        report_path = self.package / "formula_latex_validation.json"
        if report_path.exists():
            args.extend(["--formula-latex-report", str(report_path)])
        proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.metrics["live_validator_returncode"] = proc.returncode
        if proc.stderr.strip():
            self.metrics["live_validator_stderr"] = proc.stderr.strip()
        try:
            live = json.loads(proc.stdout)
        except json.JSONDecodeError:
            self.add("error", "live_validator_bad_json", "Live validator did not emit valid JSON.", detail=proc.stdout[:2000])
            return
        self.metrics["live_validation"] = live
        if live.get("status") == "fail":
            self.add("error", "live_validation_failed", "Live strict validator failed.", detail=live.get("errors"))
        elif live.get("status") == "warn":
            self.add("warning", "live_validation_warn", "Live strict validator returned warnings.", detail=live.get("warnings"))

    def content_review_passed(self, status: dict[str, Any]) -> bool:
        nested = status.get("content_review")
        if not isinstance(nested, dict):
            return False
        nested_status = str(nested.get("status") or "").strip().lower()
        accepted = {"passed", "codex-reviewed", "human-reviewed", "reviewed", "approved"}
        if nested_status not in accepted:
            return False
        has_identity = bool(str(nested.get("reviewer") or "").strip())
        has_time = bool(str(nested.get("reviewed_at") or "").strip())
        has_scope = bool(str(nested.get("scope") or "").strip())
        has_ranges = bool(nested.get("paragraph_ranges_reviewed"))
        has_report = bool(str(nested.get("report_path") or "").strip())
        return has_identity and has_time and (has_scope or has_ranges or has_report)

    def translation_fidelity_review_passed(self, status: dict[str, Any]) -> bool:
        explicit = str(
            status.get("translation_fidelity_status")
            or status.get("translation_fidelity_review_status")
            or ""
        ).strip().lower()
        if explicit in {"pass", "passed", "reviewed", "codex-reviewed", "subagent-reviewed", "human-reviewed"}:
            return True
        nested = status.get("content_review")
        if not isinstance(nested, dict) or not self.content_review_passed(status):
            return False
        review_text = " ".join(
            str(nested.get(key) or "")
            for key in ("scope", "method", "notes", "report_path", "reviewer")
        ).lower()
        fidelity_terms = (
            "translation fidelity",
            "source fidelity",
            "faithful",
            "faithfulness",
            "忠实",
            "忠于原文",
            "原文忠实",
            "逐段重译",
            "逐句",
            "subagent",
        )
        return any(term.lower() in review_text for term in fidelity_terms)

    def check_stage_files(self, status: Any) -> None:
        if self.stage in {"rendered", "pre-attach"}:
            self.require_file("literature_guide.pdf")
            self.check_render_freshness()
        if self.stage == "pre-attach":
            manifest, _ = self.read_json_auto("attachment_manifest.json")
            if isinstance(manifest, dict) and manifest.get("status") != "ready_to_attach":
                self.add(
                    "error",
                    "attachment_manifest_not_ready",
                    "attachment_manifest.json must be ready_to_attach before Zotero write.",
                    self.package / "attachment_manifest.json",
                    manifest.get("status"),
                )
            if isinstance(status, dict):
                state = str(status.get("state") or "")
                simple_status = str(status.get("status") or "")
                if state != "ready_to_attach" or simple_status not in {"ready-to-attach", "ready_to_attach"}:
                    self.add(
                        "error",
                        "package_status_not_ready_to_attach",
                        "pre-attach gate requires status.json state/status to be ready_to_attach / ready-to-attach.",
                        self.package / "status.json",
                        {"state": state, "status": simple_status},
                    )
                if status.get("translation_model") and not self.content_review_passed(status):
                    self.add(
                        "error",
                        "external_model_pre_attach_blocked",
                        "External/local model draft output cannot pass pre-attach until Codex or human content review evidence is recorded.",
                        self.package / "status.json",
                        {"translation_model": status.get("translation_model")},
                    )
                fidelity_reviewed = self.translation_fidelity_review_passed(status)
                self.metrics["translation_fidelity_review_passed"] = fidelity_reviewed
                if not fidelity_reviewed:
                    self.add(
                        "error",
                        "translation_fidelity_review_missing",
                        "Pre-attach requires explicit source-faithfulness review evidence for paragraph translations.",
                        self.package / "status.json",
                        {
                            "required_evidence": "content_review scope/report mentions translation fidelity, source fidelity, faithful translation, 忠实, 忠于原文, 逐句, or subagent; or translation_fidelity_status=pass"
                        },
                    )

    def check_render_freshness(self) -> None:
        guide_path = self.package / "literature_guide.md"
        pdf_path = self.package / "literature_guide.pdf"
        if not guide_path.exists() or not pdf_path.exists():
            return
        guide_mtime = guide_path.stat().st_mtime
        pdf_mtime = pdf_path.stat().st_mtime
        self.metrics["render_freshness"] = {
            "markdown_updated_at": datetime.fromtimestamp(guide_mtime).isoformat(timespec="seconds"),
            "pdf_updated_at": datetime.fromtimestamp(pdf_mtime).isoformat(timespec="seconds"),
            "pdf_is_current": pdf_mtime + 1 >= guide_mtime,
        }
        if pdf_mtime + 1 < guide_mtime:
            self.add(
                "error",
                "stale_rendered_pdf",
                "literature_guide.pdf is older than literature_guide.md; rerender the PDF before marking rendered/pre-attach pass.",
                pdf_path,
                self.metrics["render_freshness"],
            )

    def report(self) -> dict[str, Any]:
        severity_order = {"error": 3, "warning": 2, "info": 1}
        max_sev = max((severity_order.get(f.severity, 0) for f in self.findings), default=0)
        status = "fail" if max_sev >= 3 else "warn" if max_sev == 2 else "pass"
        return {
            "schema_version": "0.1",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "package": str(self.package),
            "workspace": str(self.workspace),
            "stage": self.stage,
            "status": status,
            "metrics": self.metrics,
            "encodings": self.encodings,
            "findings": [f.__dict__ for f in self.findings],
        }


def write_markdown_report(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Literature Guide Harness Report",
        "",
        f"- Package: `{report['package']}`",
        f"- Stage: `{report['stage']}`",
        f"- Status: `{report['status']}`",
        f"- Generated at: `{report['generated_at']}`",
        "",
        "## Findings",
        "",
    ]
    findings = report.get("findings") or []
    if not findings:
        lines.append("No findings.")
    else:
        for item in findings:
            lines.append(f"- **{item['severity']} / {item['code']}**: {item['message']}")
            if item.get("path"):
                lines.append(f"  - Path: `{item['path']}`")
            if item.get("detail") is not None:
                detail = json.dumps(item["detail"], ensure_ascii=False)
                if len(detail) > 600:
                    detail = detail[:600] + "..."
                lines.append(f"  - Detail: `{detail}`")
    lines.extend(
        [
            "",
            "## Metrics",
            "",
            "```json",
            json.dumps(report.get("metrics", {}), ensure_ascii=False, indent=2),
            "```",
            "",
            "## Encodings",
            "",
            "```json",
            json.dumps(report.get("encodings", {}), ensure_ascii=False, indent=2),
            "```",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a Zotero literature-guide package.")
    parser.add_argument("--package", required=True, type=Path, help="Package directory, usually outputs/<item_key>.")
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="Literature-guide workspace root.")
    parser.add_argument("--skill-root", type=Path, default=DEFAULT_SKILL_ROOT)
    parser.add_argument("--stage", choices=["draft", "rendered", "pre-attach"], default="draft")
    parser.add_argument("--run-validator", action="store_true", help="Run the skill's strict validate_guide.py live.")
    parser.add_argument("--json-output", type=Path, help="Write JSON report.")
    parser.add_argument("--md-output", type=Path, help="Write Markdown report.")
    args = parser.parse_args()

    harness = Harness(
        package=args.package.resolve(),
        workspace=args.workspace.resolve(),
        skill_root=args.skill_root.resolve() if args.skill_root else None,
        stage=args.stage,
        run_validator=args.run_validator,
    )
    report = harness.run()
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.md_output:
        args.md_output.parent.mkdir(parents=True, exist_ok=True)
        write_markdown_report(report, args.md_output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
