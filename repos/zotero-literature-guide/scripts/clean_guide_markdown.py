#!/usr/bin/env python3
"""Clean generated literature_guide.md before validation and rendering."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote


HTML_COMMENT_RE = re.compile(r"<!--.*?-->", flags=re.DOTALL)
IMAGE_LINK_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
ASSET_ID_RE = re.compile(r"\b(equation|image|table)_\d{3,}\b")
FORMULA_HEADING_RE = re.compile(r"\*\*equation_\d{3,}（公式，源页 ([^)]+)）\*\*")
IMAGE_HEADING_RE = re.compile(r"\*\*image_\d{3,}（图像，源页 ([^)]+)）\*\*")


def normalize_link_path(value: str) -> str:
    path = unquote(value.strip().split(maxsplit=1)[0].strip("<>\"'")).replace("\\", "/")
    if path.startswith("./"):
        path = path[2:]
    return path


def manifest_asset_keys(asset_manifest_path: Path | None) -> tuple[set[str], set[str]]:
    if not asset_manifest_path:
        return set(), set()
    data = json.loads(asset_manifest_path.read_text(encoding="utf-8-sig"))
    formula_keys: set[str] = set()
    all_keys: set[str] = set()
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        typ = str(item.get("type", "")).lower()
        rel = item.get("path")
        if not isinstance(rel, str):
            continue
        norm = normalize_link_path(rel)
        all_keys.add(norm)
        all_keys.add(Path(norm).name)
        if typ in {"formula", "equation"}:
            formula_keys.add(norm)
            formula_keys.add(Path(norm).name)
    return formula_keys, all_keys


def clean_markdown(text: str, formula_keys: set[str], all_asset_keys: set[str]) -> tuple[str, list[str], int, int]:
    comments = HTML_COMMENT_RE.findall(text)
    cleaned = HTML_COMMENT_RE.sub("", text)
    cleaned, formula_headings = FORMULA_HEADING_RE.subn(r"**公式（源页 \1）**", cleaned)
    cleaned, image_headings = IMAGE_HEADING_RE.subn(r"**图像（源页 \1）**", cleaned)

    image_alt_cleared = 0

    def replace_image(match: re.Match[str]) -> str:
        nonlocal image_alt_cleared
        alt = match.group(1)
        target = match.group(2)
        norm = normalize_link_path(target)
        formula_asset = formula_keys and (norm in formula_keys or Path(norm).name in formula_keys)
        manifest_asset = all_asset_keys and (norm in all_asset_keys or Path(norm).name in all_asset_keys)
        if manifest_asset and alt.strip() and (formula_asset or ASSET_ID_RE.search(alt)):
            image_alt_cleared += 1
            return f"![]({target})"
        return match.group(0)

    cleaned = IMAGE_LINK_RE.sub(replace_image, cleaned)
    cleaned = re.sub(r"\n{4,}", "\n\n\n", cleaned)
    return cleaned.rstrip() + "\n", comments, image_alt_cleared, formula_headings + image_headings


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove hidden HTML comments from generated guide Markdown")
    parser.add_argument("--guide", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="default: overwrite --guide when --in-place is set")
    parser.add_argument("--in-place", action="store_true", help="overwrite --guide")
    parser.add_argument("--asset-manifest", type=Path, help="clear captions from formula/equation image links")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    if args.output and args.in_place:
        print("Use either --output or --in-place, not both", file=sys.stderr)
        return 2
    if not args.output and not args.in_place:
        print("Specify --output or --in-place", file=sys.stderr)
        return 2

    original = args.guide.read_text(encoding="utf-8-sig")
    formula_keys, all_asset_keys = manifest_asset_keys(args.asset_manifest)
    cleaned, comments, image_alt_cleared, internal_labels_cleaned = clean_markdown(
        original, formula_keys, all_asset_keys
    )
    output = args.guide if args.in_place else args.output
    assert output is not None
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(cleaned, encoding="utf-8")

    report = {
        "schema_version": "0.1",
        "guide": str(args.guide.resolve()),
        "output": str(output.resolve()),
        "html_comments_removed": len(comments),
        "image_alt_text_cleared": image_alt_cleared,
        "internal_asset_labels_cleaned": internal_labels_cleaned,
        "changed": cleaned != original,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
