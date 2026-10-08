#!/usr/bin/env python3
"""Validate a scientific data-processing report package structure."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_FILES = [
    "PROCESSING_PLAN.md",
    "REPORT.md",
    "AUDIT_MANIFEST.json",
    "COMMAND_LOG.md",
    "QC_CHECKLIST.md",
    "FIGURE_INDEX.md",
]
REQUIRED_DIRS = ["outputs", "figures", "tables", "logs"]
AUDIT_STATUSES = {"complete", "partial", "blocked", "exploratory"}
REPRO_STATUSES = {"reproducible", "partially_reproducible", "not_reproducible", "not_assessed"}
CONFIDENCE_STATUSES = {"high", "medium", "low", "not_assessed"}
EVIDENCE_TYPES = {
    "executed_this_session",
    "existing_file",
    "inferred_from_code",
    "user_provided",
    "gui_manual",
    "unknown",
}
PLACEHOLDERS = {"todo", "tbd", "unset", "fill_me", "placeholder"}
UNKNOWN_VALUES = {"unknown", "missing", "not_assessed", "not assessed", "n/a", "na", "none"}
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class Validation:
    def __init__(self, allow_draft: bool = False) -> None:
        self.allow_draft = allow_draft
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def is_placeholder(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        lowered = value.strip().lower()
        return lowered in PLACEHOLDERS or "todo" in lowered
    return False


def is_unknown(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        lowered = value.strip().lower()
        return lowered == "" or lowered in UNKNOWN_VALUES
    return False


def iter_values(value: Any, path: str = "$"):
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from iter_values(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_values(child, f"{path}[{index}]")


def require_key(v: Validation, obj: dict, key: str, path: str, *, allow_unknown: bool = False) -> Any:
    if key not in obj:
        v.error(f"{path}.{key} is missing")
        return None
    value = obj[key]
    if is_placeholder(value):
        message = f"{path}.{key} still contains a placeholder"
        if v.allow_draft:
            v.warn(message)
        else:
            v.error(message)
    elif is_unknown(value) and not allow_unknown:
        v.error(f"{path}.{key} is unknown or empty")
    return value


def validate_files(v: Validation, package_dir: Path) -> None:
    for name in REQUIRED_FILES:
        if not (package_dir / name).is_file():
            v.error(f"required file missing: {name}")
    for name in REQUIRED_DIRS:
        if not (package_dir / name).is_dir():
            v.error(f"required directory missing: {name}")


def load_manifest(v: Validation, package_dir: Path) -> dict:
    path = package_dir / "AUDIT_MANIFEST.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        v.error(f"AUDIT_MANIFEST.json is invalid JSON: {exc}")
        return {}
    if not isinstance(data, dict):
        v.error("AUDIT_MANIFEST.json root must be an object")
        return {}
    return data


def validate_top_level(v: Validation, manifest: dict) -> tuple[str, str, str]:
    status = require_key(v, manifest, "audit_status", "$")
    repro = require_key(v, manifest, "reproducibility", "$", allow_unknown=True)
    confidence = require_key(v, manifest, "scientific_confidence", "$", allow_unknown=True)
    require_key(v, manifest, "report_package_root", "$")
    require_key(v, manifest, "schema_version", "$")
    require_key(v, manifest, "generated_at", "$")
    require_key(v, manifest, "task", "$")

    if status and status not in AUDIT_STATUSES:
        v.error(f"$.audit_status must be one of {sorted(AUDIT_STATUSES)}")
    if repro and repro not in REPRO_STATUSES:
        v.error(f"$.reproducibility must be one of {sorted(REPRO_STATUSES)}")
    if confidence and confidence not in CONFIDENCE_STATUSES:
        v.error(f"$.scientific_confidence must be one of {sorted(CONFIDENCE_STATUSES)}")
    return str(status or ""), str(repro or ""), str(confidence or "")


def validate_fingerprint(v: Validation, item: dict, path: str) -> None:
    sha = item.get("sha256")
    fallback = item.get("fingerprint_fallback")
    if sha:
        if sha == "not_computed_large_file":
            if not isinstance(fallback, dict) or not fallback:
                v.error(f"{path}.fingerprint_fallback is required when sha256 is not_computed_large_file")
        elif not SHA256_RE.match(str(sha)):
            v.error(f"{path}.sha256 is not a valid SHA256 hex digest")
    elif not fallback:
        v.error(f"{path} requires sha256 or fingerprint_fallback")


def validate_inputs(v: Validation, manifest: dict, status: str) -> None:
    inputs = manifest.get("inputs")
    if not isinstance(inputs, list):
        v.error("$.inputs must be a list")
        return
    if status != "blocked" and not inputs:
        if v.allow_draft:
            v.warn("$.inputs is empty in draft package")
        else:
            v.error("$.inputs must not be empty unless audit_status is blocked")
    for index, item in enumerate(inputs):
        path = f"$.inputs[{index}]"
        if not isinstance(item, dict):
            v.error(f"{path} must be an object")
            continue
        for key in ["id", "path", "role", "exists_at_runtime"]:
            require_key(v, item, key, path)
        if item.get("exists_at_runtime") is True:
            require_key(v, item, "size_bytes", path)
            require_key(v, item, "modified_time", path)
        validate_fingerprint(v, item, path)


def validate_steps(v: Validation, manifest: dict, status: str) -> None:
    steps = manifest.get("steps")
    if not isinstance(steps, list):
        v.error("$.steps must be a list")
        return
    if status != "blocked" and not steps:
        if v.allow_draft:
            v.warn("$.steps is empty in draft package")
        else:
            v.error("$.steps must not be empty unless audit_status is blocked")
    for index, item in enumerate(steps):
        path = f"$.steps[{index}]"
        if not isinstance(item, dict):
            v.error(f"{path} must be an object")
            continue
        for key in [
            "id",
            "purpose",
            "inputs",
            "outputs",
            "evidence_type",
            "method_basis",
            "assumptions",
            "risks",
            "verification",
        ]:
            require_key(v, item, key, path, allow_unknown=(key == "evidence_type"))
        if item.get("evidence_type") not in EVIDENCE_TYPES:
            v.error(f"{path}.evidence_type must be one of {sorted(EVIDENCE_TYPES)}")
        for key in ["inputs", "outputs"]:
            if key in item and not isinstance(item[key], list):
                v.error(f"{path}.{key} must be a list")


def validate_outputs(v: Validation, manifest: dict, status: str) -> None:
    outputs = manifest.get("outputs")
    if not isinstance(outputs, list):
        v.error("$.outputs must be a list")
        return
    if status not in {"blocked", "exploratory"} and not outputs:
        if v.allow_draft:
            v.warn("$.outputs is empty in draft package")
        else:
            v.error("$.outputs must not be empty unless blocked or purely exploratory")
    for index, item in enumerate(outputs):
        path = f"$.outputs[{index}]"
        if not isinstance(item, dict):
            v.error(f"{path} must be an object")
            continue
        for key in ["id", "path", "role", "status", "derived_from_steps", "derived_from_inputs", "evidence_type"]:
            require_key(v, item, key, path, allow_unknown=(key == "evidence_type"))
        if item.get("evidence_type") not in EVIDENCE_TYPES:
            v.error(f"{path}.evidence_type must be one of {sorted(EVIDENCE_TYPES)}")
        role = str(item.get("role", "")).lower()
        if "figure" in role:
            require_key(v, item, "caption", path)
            if not item.get("derived_from_steps"):
                v.error(f"{path}.derived_from_steps is required for figures")
            if not item.get("derived_from_inputs"):
                v.error(f"{path}.derived_from_inputs is required for figures")


def validate_figures(v: Validation, manifest: dict, status: str) -> None:
    figures = manifest.get("figures")
    if figures is None:
        return
    if not isinstance(figures, list):
        v.error("$.figures must be a list")
        return
    for index, item in enumerate(figures):
        path = f"$.figures[{index}]"
        if not isinstance(item, dict):
            v.error(f"{path} must be an object")
            continue
        for key in ["id", "path", "caption", "derived_from_steps", "derived_from_inputs", "evidence_type", "status"]:
            require_key(v, item, key, path, allow_unknown=(key == "evidence_type"))
        if item.get("evidence_type") not in EVIDENCE_TYPES:
            v.error(f"{path}.evidence_type must be one of {sorted(EVIDENCE_TYPES)}")


def validate_environment(v: Validation, manifest: dict) -> None:
    env = manifest.get("environment")
    if not isinstance(env, dict):
        v.error("$.environment must be an object")
        return
    require_key(v, env, "working_directory", "$.environment")
    require_key(v, env, "os", "$.environment", allow_unknown=True)
    require_key(v, env, "execution_time", "$.environment", allow_unknown=True)
    if env.get("git_repo") is True:
        require_key(v, env, "git_commit", "$.environment")
        require_key(v, env, "git_dirty", "$.environment")


def validate_code_artifacts(v: Validation, manifest: dict) -> None:
    artifacts = manifest.get("code_artifacts")
    if not isinstance(artifacts, list):
        v.error("$.code_artifacts must be a list")
        return
    for index, item in enumerate(artifacts):
        path = f"$.code_artifacts[{index}]"
        if not isinstance(item, dict):
            v.error(f"{path} must be an object")
            continue
        for key in ["path", "role"]:
            require_key(v, item, key, path)
        if not item.get("sha256") and not item.get("git_status"):
            v.error(f"{path} requires sha256 or git_status")


def validate_claims(v: Validation, manifest: dict) -> None:
    claims = manifest.get("claims")
    if not isinstance(claims, dict):
        v.error("$.claims must be an object")
        return
    for key in ["allowed", "not_supported", "requiring_external_evidence"]:
        if key not in claims:
            v.error(f"$.claims.{key} is missing")
        elif not isinstance(claims[key], list):
            v.error(f"$.claims.{key} must be a list")


def validate_review_targets(v: Validation, manifest: dict, status: str) -> None:
    targets = manifest.get("review_targets")
    if not isinstance(targets, list):
        v.error("$.review_targets must be a list")
    elif status == "complete" and not targets:
        v.error("$.review_targets must list manual attack points for complete reports")


def validate_blockers(v: Validation, manifest: dict, status: str) -> None:
    blockers = manifest.get("blockers")
    if not isinstance(blockers, list):
        v.error("$.blockers must be a list")
    elif status == "blocked" and not blockers:
        v.error("$.blockers must explain why audit_status is blocked")
    elif status == "complete" and blockers:
        v.error("$.blockers must be empty when audit_status is complete")


def validate_placeholders(v: Validation, manifest: dict) -> None:
    for path, value in iter_values(manifest):
        if is_placeholder(value):
            message = f"{path} still contains a placeholder"
            if v.allow_draft:
                v.warn(message)
            else:
                v.error(message)


def validate_complete(v: Validation, manifest: dict, repro: str, confidence: str) -> None:
    if repro != "reproducible":
        v.error("complete reports must set reproducibility to reproducible")
    if confidence == "not_assessed":
        v.error("complete reports cannot have scientific_confidence not_assessed")
    for path, value in iter_values(manifest):
        if is_unknown(value):
            v.error(f"complete report has unknown value at {path}")


def validate_manifest(v: Validation, manifest: dict) -> None:
    if not manifest:
        return
    status, repro, confidence = validate_top_level(v, manifest)
    validate_inputs(v, manifest, status)
    validate_steps(v, manifest, status)
    validate_outputs(v, manifest, status)
    validate_figures(v, manifest, status)
    validate_environment(v, manifest)
    validate_code_artifacts(v, manifest)
    validate_claims(v, manifest)
    validate_review_targets(v, manifest, status)
    validate_blockers(v, manifest, status)
    validate_placeholders(v, manifest)
    if status == "complete":
        validate_complete(v, manifest, repro, confidence)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", help="Report package directory to validate.")
    parser.add_argument("--allow-draft", action="store_true", help="Allow initialized templates with TODO placeholders.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    package_dir = Path(args.package_dir)
    v = Validation(allow_draft=args.allow_draft)

    if not package_dir.is_dir():
        print(f"ERROR: package directory not found: {package_dir}", file=sys.stderr)
        return 2

    validate_files(v, package_dir)
    manifest = load_manifest(v, package_dir)
    validate_manifest(v, manifest)

    for warning in v.warnings:
        print(f"WARNING: {warning}")
    for error in v.errors:
        print(f"ERROR: {error}")

    if v.errors:
        print(f"Validation failed: {len(v.errors)} error(s), {len(v.warnings)} warning(s)")
        return 1
    print(f"Validation passed: {len(v.warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
