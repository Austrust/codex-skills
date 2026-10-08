#!/usr/bin/env python3
"""Smoke tests for literature_guide_harness.py and attachment manifest gates."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from build_attachment_manifest import build_manifest
from literature_guide_harness import Harness
from validate_guide import validate


def write_json(path: Path, data: object, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding=encoding)


def write_base_package(workspace: Path, item_key: str = "TESTKEY01") -> Path:
    pkg = workspace / "outputs" / item_key
    for rel in ("source", "extraction", "assets", "batches", "context"):
        (pkg / rel).mkdir(parents=True, exist_ok=True)
    (pkg / "source/source.pdf").write_bytes(b"%PDF-1.4\n% test\n")
    write_json(pkg / "source/zotero_item.json", {"data": {"key": item_key, "title": "Harness Test Paper"}})
    write_json(pkg / "source/zotero_children.json", [])
    write_json(pkg / "source/zotero_lookup.json", {"item_key": item_key, "selected_pdf": {"key": "PDFKEY"}})
    write_json(pkg / "extraction/mineru_result.json", {"status": "ok"})
    (pkg / "extraction/extracted.md").write_text("# Harness Test Paper\n\nThis is a source paragraph.\n", encoding="utf-8")
    write_json(pkg / "extraction/content_list.json", [])
    write_json(
        pkg / "extraction/paragraph_index.json",
        {
            "paragraphs": [
                {
                    "id": "P001",
                    "kind": "body",
                    "guide": True,
                    "section": "Abstract",
                    "text": "This is a source paragraph.",
                }
            ]
        },
    )
    write_json(pkg / "asset_manifest.json", [])
    (pkg / "literature_guide.md").write_text(
        "# 文献导读\n\n"
        "## 第二部分：逐段导读\n\n"
        '<a id="P001"></a>\n\n'
        "**P001**\n\n"
        "**原文：** This is a source paragraph.\n\n"
        "**翻译：** 这是一个源文本段落。\n\n"
        "**讲解：** 这一段用于测试导读块结构是否完整。\n",
        encoding="utf-8",
    )
    write_json(pkg / "guide_validation.json", {"status": "pass", "errors": [], "warnings": []})
    write_json(pkg / "batches/ollama_translation_cache.json", {"P001": {"translation": "这是一个源文本段落。", "explanation": "结构测试。"}})
    write_json(
        pkg / "status.json",
        {
            "schema_version": "0.1",
            "zotero_item_key": item_key,
            "state": "guide_drafted",
            "status": "needs-review",
            "paragraphs_guided": 1,
        },
    )
    (pkg / "README.md").write_text("# Harness Test Package\n", encoding="utf-8")
    (pkg / "build_log.md").write_text("# Build Log\n", encoding="utf-8")
    return pkg


def run_harness(pkg: Path, workspace: Path, stage: str) -> dict:
    report = Harness(
        package=pkg.resolve(),
        workspace=workspace.resolve(),
        skill_root=Path(__file__).resolve().parents[1],
        stage=stage,
        run_validator=False,
    ).run()
    return report


def assert_status(name: str, report: dict, expected: str) -> None:
    actual = report["status"]
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected}, got {actual}: {json.dumps(report, ensure_ascii=False)}")


def run_validator(pkg: Path, *, strict: bool = True) -> tuple[str, list[str], list[str]]:
    return validate(
        guide_path=pkg / "literature_guide.md",
        index_path=pkg / "extraction/paragraph_index.json",
        assets_dir=None,
        asset_manifest_path=pkg / "asset_manifest.json",
        require_embedded_assets=False,
        require_compact_blocks=True,
        require_inline_assets=False,
        allow_latex_formula_assets=False,
        require_image_captions=False,
        formula_latex_report_path=None,
        strict_translation_fidelity=strict,
    )


def add_formula_asset(pkg: Path, *, embed: str) -> None:
    formula_rel = "assets/equation_001.png"
    (pkg / formula_rel).write_bytes(b"\x89PNG\r\n\x1a\n")
    write_json(
        pkg / "asset_manifest.json",
        [
            {
                "asset_id": "equation_001",
                "type": "formula",
                "path": formula_rel,
                "caption_or_label": r"$$x = y + 1$$",
            }
        ],
    )
    guide = (pkg / "literature_guide.md").read_text(encoding="utf-8")
    guide = guide.replace(
        "**原文：** This is a source paragraph.",
        f"**原文：** This is a source paragraph.\n\n{embed}",
    )
    (pkg / "literature_guide.md").write_text(guide, encoding="utf-8")


def write_formula_report(pkg: Path, status: str) -> None:
    write_json(
        pkg / "formula_latex_validation.json",
        {
            "schema_version": "0.1",
            "status": "pass" if status == "pass" else "fail",
            "formula_count": 1,
            "passed_formula_count": 1 if status == "pass" else 0,
            "failed_formula_count": 0 if status == "pass" else 1,
            "formulas": [
                {
                    "asset_id": "equation_001",
                    "path": "assets/equation_001.png",
                    "status": status,
                    "mode": "latex" if status == "pass" else "image_fallback",
                }
            ],
        },
    )


def record_math_enabled(pkg: Path) -> None:
    status = json.loads((pkg / "status.json").read_text(encoding="utf-8"))
    status["render_math_parsing"] = "enabled"
    write_json(pkg / "status.json", status)


def make_repetitive_explanation_package(pkg: Path, paragraph_count: int = 6) -> None:
    paragraphs = []
    guide_lines = [
        "# 文献导读",
        "",
        "## 第二部分：逐段导读",
        "",
    ]
    repeated_explanation = (
        "引言通过两类实验的矛盾引出核心问题：为什么有些 MHD 实验显示强二维性，"
        "而均匀湍流理论和另一些实验仍显示三维耗散。"
    )
    for i in range(1, paragraph_count + 1):
        pid = f"P{i:03d}"
        source = f"This is source paragraph {i} with a specific claim."
        paragraphs.append(
            {
                "id": pid,
                "kind": "body",
                "guide": True,
                "section": "Introduction",
                "text": source,
            }
        )
        guide_lines.extend(
            [
                f'<a id="{pid}"></a>',
                "",
                f"**{pid}**",
                "",
                f"**原文：** {source}",
                "",
                f"**翻译：** 这是第 {i} 个源段落的忠实中文翻译。",
                "",
                f"**讲解：** {repeated_explanation}",
                "",
            ]
        )
    write_json(pkg / "extraction/paragraph_index.json", {"paragraphs": paragraphs})
    (pkg / "literature_guide.md").write_text("\n".join(guide_lines), encoding="utf-8")
    write_json(
        pkg / "batches/ollama_translation_cache.json",
        {
            f"P{i:03d}": {
                "translation": f"这是第 {i} 个源段落的忠实中文翻译。",
                "explanation": repeated_explanation,
            }
            for i in range(1, paragraph_count + 1)
        },
    )
    status = json.loads((pkg / "status.json").read_text(encoding="utf-8"))
    status["paragraphs_guided"] = paragraph_count
    write_json(pkg / "status.json", status)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="zlg_harness_test_") as tmp:
        workspace = Path(tmp)

        base = write_base_package(workspace, "PASSKEY1")
        assert_status("base draft", run_harness(base, workspace, "draft"), "pass")

        pseudo_translation = write_base_package(workspace, "PSEUDOTR")
        source = (
            "Steady incompressible rectilinear flow under transverse magnetic fields "
            "has received much attention and is now well understood."
        )
        write_json(
            pseudo_translation / "extraction/paragraph_index.json",
            {
                "paragraphs": [
                    {
                        "id": "P001",
                        "kind": "body",
                        "guide": True,
                        "section": "Background",
                        "text": source,
                    }
                ]
            },
        )
        (pseudo_translation / "literature_guide.md").write_text(
            "# 文献导读\n\n"
            "## 第二部分：逐段导读\n\n"
            '<a id="P001"></a>\n\n'
            "**P001**\n\n"
            f"**原文：** {source}\n\n"
            f"**翻译：** 这里说明：{source}\n\n"
            "**讲解：** 这一段只是测试伪翻译门禁。\n",
            encoding="utf-8",
        )
        pseudo_status, pseudo_errors, _ = run_validator(pseudo_translation, strict=True)
        if pseudo_status != "fail":
            raise AssertionError(f"pseudo translation validator should fail: {pseudo_errors}")
        if not any("meta-summary phrase" in err or "copied English" in err for err in pseudo_errors):
            raise AssertionError(f"pseudo translation failure reason was not specific: {pseudo_errors}")

        repetitive = write_base_package(workspace, "REPEAT01")
        make_repetitive_explanation_package(repetitive)
        repetitive_report = run_harness(repetitive, workspace, "draft")
        assert_status("repetitive explanations", repetitive_report, "fail")
        repetitive_codes = {finding["code"] for finding in repetitive_report["findings"]}
        if "low_information_explanations" not in repetitive_codes:
            raise AssertionError(f"repetitive explanations were not flagged: {repetitive_codes}")

        draft = write_base_package(workspace, "DRAFTKEY")
        status = json.loads((draft / "status.json").read_text(encoding="utf-8"))
        status["translation_model"] = "qwen3.5:9b"
        write_json(draft / "status.json", status)
        assert_status("external model draft", run_harness(draft, workspace, "draft"), "warn")

        stale = write_base_package(workspace, "STALEPDF")
        (stale / "literature_guide.pdf").write_bytes(b"%PDF-1.4\n% stale rendered\n")
        old_mtime = (stale / "literature_guide.md").stat().st_mtime - 60
        os.utime(stale / "literature_guide.pdf", (old_mtime, old_mtime))
        stale_report = run_harness(stale, workspace, "rendered")
        assert_status("stale rendered pdf", stale_report, "fail")
        stale_codes = {finding["code"] for finding in stale_report["findings"]}
        if "stale_rendered_pdf" not in stale_codes:
            raise AssertionError(f"stale PDF was not blocked: {stale_codes}")

        (draft / "literature_guide.pdf").write_bytes(b"%PDF-1.4\n% rendered\n")
        write_json(draft / "attachment_manifest.json", {"status": "ready_to_attach"})
        pre_attach = run_harness(draft, workspace, "pre-attach")
        assert_status("external model pre-attach", pre_attach, "fail")
        codes = {finding["code"] for finding in pre_attach["findings"]}
        if "external_model_pre_attach_blocked" not in codes:
            raise AssertionError(f"pre-attach did not block external model draft: {codes}")
        if "translation_fidelity_review_missing" not in codes:
            raise AssertionError(f"pre-attach did not require translation fidelity review: {codes}")

        utf16 = write_base_package(workspace, "UTF16KEY")
        write_json(utf16 / "guide_validation.json", {"status": "pass", "errors": [], "warnings": []}, encoding="utf-16")
        assert_status("utf16 validation json", run_harness(utf16, workspace, "draft"), "fail")

        formula_image = write_base_package(workspace, "FORMIMG")
        add_formula_asset(formula_image, embed="![](assets/equation_001.png)")
        formula_image_report = run_harness(formula_image, workspace, "draft")
        assert_status("formula image draft", formula_image_report, "fail")
        formula_image_codes = {finding["code"] for finding in formula_image_report["findings"]}
        if "formula_recognition_not_used" not in formula_image_codes:
            raise AssertionError(f"formula image without failed validation was not blocked: {formula_image_codes}")

        formula_latex = write_base_package(workspace, "FORMLATX")
        add_formula_asset(formula_latex, embed=r"$$x = y + 1$$")
        write_formula_report(formula_latex, "pass")
        record_math_enabled(formula_latex)
        formula_latex_report = run_harness(formula_latex, workspace, "draft")
        assert_status("formula latex draft", formula_latex_report, "pass")

        formula_fallback = write_base_package(workspace, "FORMFBK")
        add_formula_asset(formula_fallback, embed="![](assets/equation_001.png)")
        write_formula_report(formula_fallback, "fail")
        assert_status("formula failed-latex image fallback draft", run_harness(formula_fallback, workspace, "draft"), "pass")

        formula_alt = write_base_package(workspace, "FORMALT")
        add_formula_asset(formula_alt, embed="![equation_001](assets/equation_001.png)")
        write_formula_report(formula_alt, "fail")
        formula_alt_report = run_harness(formula_alt, workspace, "draft")
        assert_status("formula non-empty alt draft", formula_alt_report, "fail")
        formula_alt_codes = {finding["code"] for finding in formula_alt_report["findings"]}
        if "formula_image_alt_not_empty" not in formula_alt_codes:
            raise AssertionError(f"formula image alt text was not blocked: {formula_alt_codes}")

        blocked_manifest = build_manifest(
            zotero_item_key="DRAFTKEY",
            package_dir=draft,
            attachment_mode="stored",
            validation_status="pass",
            existing_guide_attachments=[],
            package_status=json.loads((draft / "status.json").read_text(encoding="utf-8")),
            harness_report=pre_attach,
        )
        if blocked_manifest["status"] != "blocked":
            raise AssertionError(f"manifest should be blocked, got {blocked_manifest['status']}")

        reviewed = write_base_package(workspace, "REVIEWED")
        (reviewed / "literature_guide.pdf").write_bytes(b"%PDF-1.4\n% rendered\n")
        reviewed_status = json.loads((reviewed / "status.json").read_text(encoding="utf-8"))
        reviewed_status.update(
            {
                "state": "ready_to_attach",
                "status": "ready-to-attach",
                "translation_model": "qwen3.5:9b",
                "zotero_source_attachment_key": "SRCATT1",
                "zotero_guide_attachment_key": None,
                "content_review": {
                    "status": "codex-reviewed",
                    "reviewer": "Codex",
                    "reviewed_at": "2026-06-08T15:00:00",
                    "scope": "all guided paragraphs and figure/table captions; source-fidelity review confirmed faithful translation and 忠于原文 coverage",
                    "report_path": "content_review_report.md",
                },
            }
        )
        write_json(reviewed / "status.json", reviewed_status)
        write_json(reviewed / "attachment_manifest.json", {"status": "ready_to_attach"})
        reviewed_pre_attach = run_harness(reviewed, workspace, "pre-attach")
        assert_status("reviewed external model pre-attach", reviewed_pre_attach, "pass")
        ready_manifest = build_manifest(
            zotero_item_key="REVIEWED",
            package_dir=reviewed,
            attachment_mode="stored",
            validation_status="pass",
            existing_guide_attachments=[],
            package_status=reviewed_status,
            harness_report=reviewed_pre_attach,
        )
        if ready_manifest["status"] != "ready_to_attach":
            raise AssertionError(f"reviewed manifest should be ready_to_attach, got {ready_manifest['status']}")
        if ready_manifest.get("zotero_source_attachment_key") != "SRCATT1":
            raise AssertionError("manifest lost zotero_source_attachment_key")
        if ready_manifest.get("zotero_guide_attachment_key") is not None:
            raise AssertionError("manifest should not invent zotero_guide_attachment_key before attach")

    print("literature guide harness smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
