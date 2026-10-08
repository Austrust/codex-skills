#!/usr/bin/env python3
"""Validate MinerU-recognized displayed formulas before guide rendering."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_FROM = "markdown+tex_math_dollars+tex_math_single_backslash"
OCR_OPERATOR_WORDS = {"grad", "div", "curl", "rot"}
OCR_ROMAN_WORDS = {
    "and",
    "or",
    "with",
    "where",
    "const",
    "constant",
    "unit",
    "vector",
}
SPACED_WORD_COMMAND_RE = re.compile(
    r"\\(?P<command>mathbf|mathrm|mathit|text|operatorname)\s*\{\s*(?P<word>(?:[A-Za-z]\s+){1,}[A-Za-z])\s*\}"
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def load_manifest(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError("asset_manifest.json must be a JSON list")
    return [item for item in data if isinstance(item, dict)]


def load_formula_overrides(path: Path | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    records = data.get("overrides", data) if isinstance(data, dict) else data
    if not isinstance(records, list):
        raise ValueError("formula override file must be a list or an object with an overrides list")
    overrides: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        latex = str(record.get("latex") or "").strip()
        if not latex:
            continue
        for key in (record.get("asset_id"), record.get("path"), record.get("source_image")):
            if isinstance(key, str) and key.strip():
                overrides[key.strip()] = record
                overrides[Path(key.replace("\\", "/")).name] = record
    return overrides


def normalize_spaced_word_command(match: re.Match[str]) -> str:
    command = match.group("command")
    word = re.sub(r"\s+", "", match.group("word"))
    lower = word.lower()
    if lower in OCR_OPERATOR_WORDS:
        return f"\\operatorname{{{lower}}}"
    if lower in OCR_ROMAN_WORDS:
        return f"\\mathrm{{{lower}}}"
    return f"\\{command}{{{word}}}"


def normalize_formula_latex(latex: str) -> str:
    """Clean common MinerU OCR spacing artifacts while preserving the formula."""
    text = latex.replace("\ufeff", "").replace("\u00a0", " ").strip()
    text = re.sub(r"\\(mathbf|mathrm|mathit|text|operatorname)\s+\{", r"\\\1{", text)
    text = SPACED_WORD_COMMAND_RE.sub(normalize_spaced_word_command, text)
    text = re.sub(r"\\big\s+([{}()[\]])", r"\\big\1", text)
    text = re.sub(r"\\tag\s*\{\s*([^{}]+?)\s*\}", lambda m: "\\tag{" + re.sub(r"\s+", "", m.group(1)) + "}", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def formula_records(manifest: list[dict[str, Any]], overrides: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, str]] = []
    for item in manifest:
        typ = str(item.get("type") or "").lower()
        if typ not in {"formula", "equation"}:
            continue
        latex = str(item.get("caption_or_label") or "").strip()
        if not latex:
            continue
        if "$" not in latex and "\\" not in latex:
            continue
        override = None
        for key in (
            item.get("asset_id"),
            item.get("path"),
            item.get("source_img_path"),
            Path(str(item.get("path") or "").replace("\\", "/")).name,
            Path(str(item.get("source_img_path") or "").replace("\\", "/")).name,
        ):
            if isinstance(key, str) and key.strip() and key.strip() in overrides:
                override = overrides[key.strip()]
                break
        override_latex = str(override.get("latex") or "").strip() if override else ""
        normalized = normalize_formula_latex(latex)
        if override_latex:
            normalized = normalize_formula_latex(override_latex)
        record: dict[str, Any] = {
            "asset_id": str(item.get("asset_id") or item.get("path") or f"formula_{len(records) + 1:03d}"),
            "path": str(item.get("path") or ""),
            "latex": normalized,
            "source_latex": latex,
        }
        if override:
            record["override"] = True
            for field in ("reason", "source", "source_image", "reviewed_at"):
                if override.get(field):
                    record[f"override_{field}"] = override[field]
        records.append(record)
    return records


def probe_markdown(records: list[dict[str, str]], title: str) -> str:
    lines = [
        f"# {title}",
        "",
        "This probe compiles MinerU-recognized displayed formulas before they are inserted into the guide.",
        "",
    ]
    for index, item in enumerate(records, 1):
        lines.extend([f"## F{index:03d} {item['asset_id']}", "", item["latex"], ""])
    return "\n".join(lines)


def run_pandoc(markdown: str, work_dir: Path, output_name: str, args: argparse.Namespace) -> subprocess.CompletedProcess[str]:
    md_path = work_dir / f"{output_name}.md"
    pdf_path = work_dir / f"{output_name}.pdf"
    md_path.write_text(markdown, encoding="utf-8")
    cmd = [
        args.pandoc,
        str(md_path),
        "-o",
        str(pdf_path),
        "--from",
        args.markdown_from,
        "--pdf-engine",
        args.pdf_engine,
        "-V",
        f"mainfont={args.mainfont}",
        "-V",
        f"CJKmainfont={args.cjk_font}",
        "-V",
        f"mathfont={args.mathfont}",
        "-V",
        "geometry:a4paper",
        "-V",
        "geometry:margin=2cm",
        "--pdf-engine-opt=-interaction=nonstopmode",
        "--pdf-engine-opt=-halt-on-error",
        "--pdf-engine-opt=-file-line-error",
    ]
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=args.active_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        stderr = (stderr + f"\nPandoc formula probe timed out after {args.active_timeout} seconds.").strip()
        return subprocess.CompletedProcess(cmd, 124, stdout=stdout, stderr=stderr)


def validate_records(records: list[dict[str, str]], args: argparse.Namespace) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="zlg_formula_latex_") as tmp:
        tmp_path = Path(tmp)
        probe_count = 0
        root_proc: subprocess.CompletedProcess[str] | None = None

        def pass_result(item: dict[str, str]) -> dict[str, Any]:
            result = {
                "asset_id": item["asset_id"],
                "path": item["path"],
                "status": "pass",
                "mode": "latex",
                "latex": item["latex"],
                "source_latex": item["source_latex"],
                "normalized": item["latex"] != item["source_latex"],
            }
            for field in ("override", "override_reason", "override_source", "override_source_image", "override_reviewed_at"):
                if item.get(field):
                    result[field] = item[field]
            return result

        def fail_result(item: dict[str, str], proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
            result: dict[str, Any] = {
                "asset_id": item["asset_id"],
                "path": item["path"],
                "status": "fail",
                "mode": "image_fallback",
                "latex": item["latex"],
                "source_latex": item["source_latex"],
                "normalized": item["latex"] != item["source_latex"],
                "pandoc_returncode": proc.returncode,
                "stderr": proc.stderr[-2000:],
            }
            for field in ("override", "override_reason", "override_source", "override_source_image", "override_reviewed_at"):
                if item.get(field):
                    result[field] = item[field]
            if proc.returncode == 124:
                result["error_type"] = "timeout"
            return result

        def validate_group(group: list[dict[str, str]], label: str, depth: int = 0) -> list[dict[str, Any]]:
            nonlocal probe_count, root_proc
            probe_count += 1
            args.active_timeout = args.per_formula_timeout if len(group) == 1 else args.compile_timeout
            proc = run_pandoc(probe_markdown(group, f"MinerU Formula Probe {label}"), tmp_path, f"formula_group_{label}", args)
            if depth == 0:
                root_proc = proc
            if proc.returncode == 0:
                return [pass_result(item) for item in group]
            if len(group) == 1:
                return [fail_result(group[0], proc)]
            midpoint = len(group) // 2
            return validate_group(group[:midpoint], f"{label}_a", depth + 1) + validate_group(
                group[midpoint:], f"{label}_b", depth + 1
            )

        results = validate_group(records, "all")
        all_proc = root_proc or subprocess.CompletedProcess([], 1, stdout="", stderr="root formula probe did not run")
        failed = [item for item in results if item["status"] != "pass"]
        return {
            "schema_version": "0.1",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "status": "pass" if not failed else "fail",
            "formula_count": len(records),
            "passed_formula_count": len(records) - len(failed),
            "failed_formula_count": len(failed),
            "markdown_from": args.markdown_from,
            "pdf_engine": args.pdf_engine,
            "pandoc_returncode_all": all_proc.returncode,
            "pandoc_stderr_all": all_proc.stderr[-4000:] if all_proc.returncode != 0 else "",
            "compile_timeout_seconds": args.compile_timeout,
            "per_formula_timeout_seconds": args.per_formula_timeout,
            "normalized_formula_count": sum(1 for item in results if item.get("normalized")),
            "override_formula_count": sum(1 for item in results if item.get("override")),
            "probe_count": probe_count,
            "validation_strategy": "recursive_group_compile",
            "formulas": results,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile-check MinerU formula LaTeX from asset_manifest.json")
    parser.add_argument("--asset-manifest", required=True, type=Path)
    parser.add_argument("--formula-overrides", type=Path, help="audited manual LaTeX transcriptions keyed by asset_id/path for OCR failures")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--pandoc", default="pandoc")
    parser.add_argument("--pdf-engine", default="xelatex")
    parser.add_argument("--markdown-from", default=DEFAULT_FROM)
    parser.add_argument("--mainfont", default="Times New Roman")
    parser.add_argument("--cjk-font", default="Microsoft YaHei")
    parser.add_argument("--mathfont", default="Cambria Math")
    parser.add_argument("--compile-timeout", type=int, default=120, help="seconds allowed for the aggregate Pandoc compile probe")
    parser.add_argument("--per-formula-timeout", type=int, default=20, help="seconds allowed for each per-formula fallback probe")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    records = formula_records(load_manifest(args.asset_manifest), load_formula_overrides(args.formula_overrides))
    report = validate_records(records, args) if records else {
        "schema_version": "0.1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "warn",
        "formula_count": 0,
        "passed_formula_count": 0,
        "failed_formula_count": 0,
        "formulas": [],
        "warnings": ["no MinerU formula LaTeX found in asset manifest"],
    }
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json or not args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report.get("status") == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
