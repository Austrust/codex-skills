#!/usr/bin/env python3
"""Build a safe Zotero attachment manifest for a generated guide PDF."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_TAGS = ["codex-literature-guide", "guide-needs-review"]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def load_json(path: Path | None) -> dict | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def content_review_passed(status_data: dict | None) -> bool:
    if not isinstance(status_data, dict):
        return False
    nested = status_data.get("content_review")
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


def build_manifest(
    zotero_item_key: str,
    package_dir: Path,
    attachment_mode: str,
    validation_status: str,
    existing_guide_attachments: list[dict],
    package_status: dict | None = None,
    harness_report: dict | None = None,
    allow_harness_warn: bool = False,
    zotero_source_attachment_key: str | None = None,
    zotero_guide_attachment_key: str | None = None,
) -> dict:
    guide_pdf = (package_dir / "literature_guide.pdf").resolve()
    status = "ready_to_attach"
    errors: list[str] = []
    if isinstance(package_status, dict):
        zotero_source_attachment_key = (
            zotero_source_attachment_key
            or package_status.get("zotero_source_attachment_key")
            or package_status.get("source_attachment_key")
        )
        zotero_guide_attachment_key = (
            zotero_guide_attachment_key
            or package_status.get("zotero_guide_attachment_key")
            or package_status.get("guide_attachment_key")
        )

    if validation_status not in {"pass", "warn"}:
        status = "blocked"
        errors.append(f"validation status does not allow attachment: {validation_status}")
    if not guide_pdf.exists():
        status = "blocked"
        errors.append("literature_guide.pdf does not exist")
    elif guide_pdf.stat().st_size <= 0:
        status = "blocked"
        errors.append("literature_guide.pdf is empty")
    if package_status:
        package_state = str(package_status.get("state") or "")
        package_simple_status = str(package_status.get("status") or "")
        if package_state != "ready_to_attach" or package_simple_status not in {"ready-to-attach", "ready_to_attach"}:
            status = "blocked"
            errors.append(
                f"package status is not ready_to_attach: state={package_state}, status={package_simple_status}"
            )
        if package_status.get("translation_model") and not content_review_passed(package_status):
            status = "blocked"
            errors.append(
                "translation_model is present but no Codex/human content review evidence is recorded"
            )
    if harness_report:
        harness_status = str(harness_report.get("status") or "")
        if harness_status == "fail":
            status = "blocked"
            errors.append("harness_report status is fail")
        elif harness_status == "warn" and not allow_harness_warn:
            status = "blocked"
            errors.append("harness_report status is warn and --allow-harness-warn was not provided")
    if existing_guide_attachments and status == "ready_to_attach":
        status = "requires_duplicate_decision"
    elif existing_guide_attachments:
        errors.append("existing guide attachments detected; duplicate decision is still required after blockers are fixed")

    return {
        "schema_version": "0.1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "zotero_item_key": zotero_item_key,
        "attachment_mode": attachment_mode,
        "package_dir": str(package_dir.resolve()),
        "guide_pdf": {
            "path": str(guide_pdf),
            "title": "文献导读.pdf",
            "mime_type": mimetypes.guess_type(str(guide_pdf))[0] or "application/pdf",
        },
        "default_tags": DEFAULT_TAGS,
        "optional_updates": {"note": None},
        "existing_guide_attachments": existing_guide_attachments,
        "zotero_source_attachment_key": zotero_source_attachment_key,
        "zotero_guide_attachment_key": zotero_guide_attachment_key,
        "validation_status": validation_status,
        "package_status": {
            "state": package_status.get("state"),
            "status": package_status.get("status"),
            "translation_model": package_status.get("translation_model"),
            "content_review": package_status.get("content_review"),
            "zotero_source_attachment_key": package_status.get("zotero_source_attachment_key"),
            "zotero_guide_attachment_key": package_status.get("zotero_guide_attachment_key"),
        } if isinstance(package_status, dict) else None,
        "harness_status": harness_report.get("status") if isinstance(harness_report, dict) else None,
        "status": status,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create attachment_manifest.json")
    parser.add_argument("--zotero-item-key", required=True)
    parser.add_argument("--package-dir", required=True, type=Path)
    parser.add_argument("--validation-status", choices=["pass", "warn", "fail"], required=True)
    parser.add_argument("--attachment-mode", choices=["stored", "linked"], default="stored")
    parser.add_argument("--existing-guide-attachments-json", default="[]")
    parser.add_argument("--status-json", type=Path, help="status.json for readiness/content-review checks")
    parser.add_argument("--harness-report-json", type=Path, help="harness report JSON for package gate checks")
    parser.add_argument("--allow-harness-warn", action="store_true", help="allow documented harness warn status")
    parser.add_argument("--zotero-source-attachment-key", help="Original paper PDF attachment key used as input")
    parser.add_argument("--zotero-guide-attachment-key", help="Existing/new guide PDF attachment key, if already known")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        existing = json.loads(args.existing_guide_attachments_json)
        if not isinstance(existing, list):
            raise ValueError("existing-guide-attachments-json must decode to a list")
    except Exception as exc:
        print(f"invalid existing-guide-attachments-json: {exc}", file=sys.stderr)
        return 2

    manifest = build_manifest(
        zotero_item_key=args.zotero_item_key,
        package_dir=args.package_dir,
        attachment_mode=args.attachment_mode,
        validation_status=args.validation_status,
        existing_guide_attachments=existing,
        package_status=load_json(args.status_json or (args.package_dir / "status.json")),
        harness_report=load_json(args.harness_report_json),
        allow_harness_warn=args.allow_harness_warn,
        zotero_source_attachment_key=args.zotero_source_attachment_key,
        zotero_guide_attachment_key=args.zotero_guide_attachment_key,
    )

    output = args.output or (args.package_dir / "attachment_manifest.json")
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(str(output))
    return 0 if manifest["status"] in {"ready_to_attach", "requires_duplicate_decision"} else 1


if __name__ == "__main__":
    sys.exit(main())
