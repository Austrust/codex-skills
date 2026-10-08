#!/usr/bin/env python3
"""Attach a verified literature-guide PDF through Zotero Guide Helper.

The Zotero Guide Helper plugin exposes a local HTTP API inside Zotero Desktop:

- GET  /guide-helper/health
- GET  /guide-helper/items/{itemKey}/guide-attachments
- POST /guide-helper/attach-guide

This client keeps the safety gates outside Zotero: PDF header/SHA256 checks,
duplicate policy, local API verification, and a JSON report.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_ZOTERO_PORT = 23119
DEFAULT_TOKEN = "zotero-guide-helper-dev"
DEFAULT_TITLE = "文献导读.pdf"
DEFAULT_TAGS = ["codex-literature-guide", "guide-needs-review"]
READY_STATUSES = {"ready_to_attach", "ready-to-attach"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_url_to_path(href: str) -> Path:
    parsed = urllib.parse.urlparse(href)
    if parsed.scheme != "file":
        raise ValueError(f"Not a file URL: {href}")
    path = urllib.request.url2pathname(parsed.path)
    if len(path) >= 3 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    return Path(path)


def request_json(
    url: str,
    *,
    method: str = "GET",
    data: dict[str, Any] | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    body = None
    headers = {"Accept": "application/json"}
    if data is not None:
        body = json.dumps(data, ensure_ascii=True).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.URLError as exc:
        if isinstance(exc, urllib.error.HTTPError):
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {"ok": False, "error": raw.strip() or str(exc)}
            payload["httpStatus"] = exc.code
            raise RuntimeError(json.dumps(payload, ensure_ascii=False, indent=2)) from exc
        raise RuntimeError(f"Zotero Guide Helper is not reachable at {url}: {exc}") from exc


def resolve_from_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    package_dir = Path(manifest.get("package_dir") or manifest_path.parent)
    guide_pdf = manifest.get("guide_pdf") or {}
    pdf_path = Path(guide_pdf.get("path") or package_dir / "literature_guide.pdf")
    return {
        "manifest": manifest,
        "manifest_path": manifest_path,
        "package_dir": package_dir,
        "status": str(manifest.get("status") or manifest.get("state") or ""),
        "item_key": manifest.get("zotero_item_key"),
        "library_id": manifest.get("libraryID") or manifest.get("library_id"),
        "pdf_path": pdf_path,
        "title": guide_pdf.get("title") or DEFAULT_TITLE,
        "tags": manifest.get("default_tags") or DEFAULT_TAGS,
        "known_attachment_key": manifest.get("zotero_guide_attachment_key"),
    }


def resolve_inputs(args: argparse.Namespace) -> dict[str, Any]:
    if args.manifest:
        resolved = resolve_from_manifest(Path(args.manifest).resolve())
    else:
        if not args.item_key or not args.pdf:
            raise SystemExit("Either --manifest or both --item-key and --pdf are required")
        pdf_path = Path(args.pdf).resolve()
        resolved = {
            "manifest": None,
            "manifest_path": None,
            "package_dir": pdf_path.parent,
            "status": "manual",
            "item_key": args.item_key,
            "library_id": args.library_id,
            "pdf_path": pdf_path,
            "title": args.title or DEFAULT_TITLE,
            "tags": args.tag or DEFAULT_TAGS,
            "known_attachment_key": args.known_attachment_key,
        }
    if args.library_id:
        resolved["library_id"] = args.library_id
    if args.title:
        resolved["title"] = args.title
    if args.tag:
        resolved["tags"] = args.tag
    if args.known_attachment_key:
        resolved["known_attachment_key"] = args.known_attachment_key
    return resolved


def validate_preflight(resolved: dict[str, Any], *, force: bool) -> None:
    if not resolved["item_key"]:
        raise SystemExit("Missing Zotero item key")
    pdf_path = Path(resolved["pdf_path"])
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")
    if pdf_path.stat().st_size <= 0:
        raise SystemExit(f"PDF is empty: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise SystemExit(f"Expected a .pdf file: {pdf_path}")
    with pdf_path.open("rb") as handle:
        if handle.read(5) != b"%PDF-":
            raise SystemExit(f"File does not start with %PDF- header: {pdf_path}")
    if resolved.get("manifest") and not force:
        status = str(resolved.get("status") or "")
        if status not in READY_STATUSES:
            raise SystemExit(f"Manifest status is not ready_to_attach: {status!r}. Use --force only for manual smoke tests.")


def find_child(children: list[dict[str, Any]], attachment_key: str) -> dict[str, Any] | None:
    for child in children:
        if child.get("key") == attachment_key:
            return child
    return None


def tags_from_child(child: dict[str, Any]) -> list[str]:
    return [tag.get("tag") for tag in child.get("data", {}).get("tags", []) if tag.get("tag")]


def verify_zotero_child(
    base_url: str,
    item_key: str,
    plugin_result: dict[str, Any],
    *,
    expected_title: str,
    expected_sha256: str,
    required_tags: list[str],
) -> dict[str, Any]:
    attachment_key = plugin_result.get("attachmentKey")
    if not attachment_key:
        raise RuntimeError("Plugin response did not include attachmentKey")
    children_url = f"{base_url}/api/users/0/items/{item_key}/children?format=json"
    children = request_json(children_url)
    if not isinstance(children, list):
        raise RuntimeError("Unexpected Zotero children response shape")
    child = find_child(children, attachment_key)
    if not child:
        raise RuntimeError(f"Zotero local API did not show new attachment key {attachment_key}")
    data = child.get("data") or {}
    tags = tags_from_child(child)
    checks = {
        "title": data.get("title") == expected_title,
        "linkMode": data.get("linkMode") == "imported_file",
        "contentType": data.get("contentType") == "application/pdf",
        "tags": all(tag in tags for tag in required_tags),
    }
    storage_path = None
    enclosure = (child.get("links") or {}).get("enclosure") or {}
    if enclosure.get("href"):
        storage_path = file_url_to_path(enclosure["href"])
    elif plugin_result.get("storagePath"):
        storage_path = Path(plugin_result["storagePath"])
    storage_sha256 = None
    if storage_path and storage_path.exists():
        storage_sha256 = sha256_file(storage_path)
        checks["storageSha256"] = storage_sha256 == expected_sha256
    else:
        checks["storageSha256"] = False
    return {
        "childrenURL": children_url,
        "attachmentKey": attachment_key,
        "zoteroChild": child,
        "storagePath": str(storage_path) if storage_path else None,
        "storageSha256": storage_sha256,
        "checks": checks,
        "verified": all(checks.values()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", help="Path to attachment_manifest.json")
    parser.add_argument("--item-key", help="Zotero parent item key when not using --manifest")
    parser.add_argument("--library-id", type=int, help="Zotero library ID; defaults to user library in plugin")
    parser.add_argument("--pdf", help="Guide PDF path when not using --manifest")
    parser.add_argument("--title", help="Attachment title override")
    parser.add_argument("--tag", action="append", help="Attachment tag; repeatable")
    parser.add_argument("--known-attachment-key", help="Prior guide attachment key for duplicate detection")
    parser.add_argument("--token", default=DEFAULT_TOKEN, help="Helper token; prototype default is zotero-guide-helper-dev")
    parser.add_argument("--port", type=int, default=DEFAULT_ZOTERO_PORT, help="Zotero local server port")
    parser.add_argument("--duplicate-policy", default="error", choices=["error", "keep-both"], help="Duplicate behavior")
    parser.add_argument("--force", action="store_true", help="Allow non-ready manifest status for manual smoke tests")
    parser.add_argument("--skip-zotero-api-verify", action="store_true", help="Only call plugin; do not run local API/SHA256 verification")
    parser.add_argument("--report", help="Report JSON path; defaults to package_dir/zotero_helper_attach_report.json")
    args = parser.parse_args(argv)

    resolved = resolve_inputs(args)
    validate_preflight(resolved, force=args.force)
    pdf_path = Path(resolved["pdf_path"]).resolve()
    pdf_sha256 = sha256_file(pdf_path)
    base_url = f"http://127.0.0.1:{args.port}"

    health = request_json(f"{base_url}/guide-helper/health")
    if health.get("plugin") != "zotero-guide-helper":
        raise RuntimeError("Zotero Guide Helper plugin is not installed or did not return the expected health payload")

    request_payload = {
        "schemaVersion": "0.1",
        "itemKey": resolved["item_key"],
        "pdfPath": str(pdf_path),
        "expectedSha256": pdf_sha256,
        "title": resolved["title"] or DEFAULT_TITLE,
        "tags": resolved["tags"] or DEFAULT_TAGS,
        "duplicatePolicy": args.duplicate_policy,
    }
    if resolved.get("library_id"):
        request_payload["libraryID"] = int(resolved["library_id"])
    if resolved.get("known_attachment_key"):
        request_payload["knownAttachmentKey"] = resolved["known_attachment_key"]

    plugin_result = request_json(f"{base_url}/guide-helper/attach-guide", method="POST", data=request_payload, token=args.token)
    verification = None
    if not args.skip_zotero_api_verify:
        verification = verify_zotero_child(
            base_url,
            resolved["item_key"],
            plugin_result,
            expected_title=request_payload["title"],
            expected_sha256=pdf_sha256,
            required_tags=request_payload["tags"],
        )
        if not verification["verified"]:
            raise RuntimeError(json.dumps({"verification": verification}, ensure_ascii=False, indent=2))

    report = {
        "status": "attached" if verification is None or verification["verified"] else "verification_failed",
        "method": "zotero_guide_helper_plugin",
        "createdAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "health": health,
        "request": request_payload,
        "pluginResult": plugin_result,
        "verification": verification,
        "manifestPath": str(resolved["manifest_path"]) if resolved.get("manifest_path") else None,
    }
    report_path = Path(args.report) if args.report else Path(resolved["package_dir"]) / "zotero_helper_attach_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Report written: {report_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
