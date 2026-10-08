#!/usr/bin/env python3
"""Lookup a Zotero item and PDF child attachments through the local API."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen


def fetch_json(url: str):
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=15) as response:
        raw = response.read().decode("utf-8-sig")
    return json.loads(raw)


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_url_to_path(href: str) -> str | None:
    parsed = urlparse(href)
    if parsed.scheme != "file":
        return None
    decoded = unquote(parsed.path)
    if parsed.netloc:
        return f"//{parsed.netloc}{decoded}"
    if len(decoded) >= 3 and decoded[0] == "/" and decoded[2] == ":":
        decoded = decoded[1:]
    return decoded.replace("/", "\\")


def is_pdf_attachment(child: dict) -> bool:
    data = child.get("data") or {}
    links = child.get("links") or {}
    enclosure = links.get("enclosure") or {}
    filename = str(data.get("filename") or enclosure.get("title") or "")
    return (
        data.get("itemType") == "attachment"
        and (
            data.get("contentType") == "application/pdf"
            or str(enclosure.get("type") or "") == "application/pdf"
            or filename.lower().endswith(".pdf")
        )
    )


def resolve_pdf_path(child: dict, zotero_data_dir: Path | None) -> str | None:
    data = child.get("data") or {}
    links = child.get("links") or {}
    enclosure = links.get("enclosure") or {}

    href = enclosure.get("href")
    if isinstance(href, str) and href.startswith("file:"):
        candidate = file_url_to_path(href)
        if candidate:
            return candidate

    data_path = data.get("path")
    if isinstance(data_path, str):
        candidate = Path(data_path)
        if candidate.is_absolute():
            return str(candidate)

    filename = data.get("filename") or enclosure.get("title")
    key = child.get("key") or data.get("key")
    if zotero_data_dir and filename and key:
        candidate = zotero_data_dir / "storage" / str(key) / str(filename)
        if candidate.exists():
            return str(candidate)

    return None


def compact_attachment(child: dict, zotero_data_dir: Path | None) -> dict:
    data = child.get("data") or {}
    links = child.get("links") or {}
    enclosure = links.get("enclosure") or {}
    path = resolve_pdf_path(child, zotero_data_dir)
    return {
        "key": child.get("key") or data.get("key"),
        "title": data.get("title"),
        "filename": data.get("filename") or enclosure.get("title"),
        "linkMode": data.get("linkMode"),
        "contentType": data.get("contentType") or enclosure.get("type"),
        "size": enclosure.get("length"),
        "href": enclosure.get("href"),
        "path": path,
        "path_exists": Path(path).exists() if path else False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Lookup Zotero item metadata and PDF child attachments")
    parser.add_argument("--item-key", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--attachment-key")
    parser.add_argument("--base-url", default="http://127.0.0.1:23119/api")
    parser.add_argument("--user-prefix", default="users/0")
    parser.add_argument("--zotero-data-dir", type=Path)
    parser.add_argument("--json", action="store_true", help="print lookup summary JSON")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    prefix = args.user_prefix.strip("/")
    item_url = f"{base}/{prefix}/items/{args.item_key}?format=json"
    children_url = f"{base}/{prefix}/items/{args.item_key}/children?format=json"

    try:
        item = fetch_json(item_url)
        children = fetch_json(children_url)
    except Exception as exc:
        print(f"Zotero local lookup failed: {exc}", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    save_json(args.output_dir / "zotero_item.json", item)
    save_json(args.output_dir / "zotero_children.json", children)

    pdfs = [compact_attachment(child, args.zotero_data_dir) for child in children if is_pdf_attachment(child)]

    selected = None
    status = "needs_attachment_key"
    errors: list[str] = []
    if args.attachment_key:
        matches = [pdf for pdf in pdfs if pdf.get("key") == args.attachment_key]
        if matches:
            selected = matches[0]
            status = "resolved" if selected.get("path_exists") else "missing_pdf_path"
        else:
            status = "attachment_key_not_found"
            errors.append(f"attachment_key is not a PDF child attachment: {args.attachment_key}")
    elif len(pdfs) == 0:
        status = "no_pdf_attachments"
        errors.append("no PDF child attachments found")
    elif len(pdfs) == 1:
        selected = pdfs[0]
        status = "resolved" if selected.get("path_exists") else "missing_pdf_path"
    else:
        status = "multiple_pdf_attachments"
        errors.append("multiple PDF attachments found; provide --attachment-key")

    if selected and not selected.get("path_exists"):
        errors.append("could not resolve a local PDF path; provide --zotero-data-dir or manual PDF path")

    data = item.get("data") or {}
    creators = data.get("creators") or []
    first_author = None
    if creators:
        first = creators[0]
        first_author = first.get("lastName") or first.get("name")

    summary = {
        "schema_version": "0.1",
        "status": status,
        "zotero_item_key": args.item_key,
        "item": {
            "title": data.get("title"),
            "itemType": data.get("itemType"),
            "date": data.get("date"),
            "year": str(data.get("date") or "")[:4],
            "first_author": first_author,
            "DOI": data.get("DOI"),
            "citationKey": data.get("citationKey"),
        },
        "pdf_attachments": pdfs,
        "selected_pdf": selected,
        "errors": errors,
        "saved": {
            "zotero_item_json": str((args.output_dir / "zotero_item.json").resolve()),
            "zotero_children_json": str((args.output_dir / "zotero_children.json").resolve()),
        },
    }
    save_json(args.output_dir / "zotero_lookup.json", summary)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(str((args.output_dir / "zotero_lookup.json").resolve()))
    return 0 if status == "resolved" else 1


if __name__ == "__main__":
    sys.exit(main())
