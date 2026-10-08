#!/usr/bin/env python3
"""Normalize a local MinerU /file_parse JSON response into package files."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote


def pick_result(data: dict, result_name: str | None) -> tuple[str, dict]:
    results = data.get("results")
    if not isinstance(results, dict) or not results:
        raise ValueError("MinerU response has no results object")
    if result_name:
        if result_name not in results:
            raise ValueError(f"result name not found: {result_name}")
        item = results[result_name]
        if not isinstance(item, dict):
            raise ValueError(f"result is not an object: {result_name}")
        return result_name, item
    first_name = next(iter(results))
    item = results[first_name]
    if not isinstance(item, dict):
        raise ValueError(f"result is not an object: {first_name}")
    return first_name, item


def decode_content_list(value):
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


def decode_image_value(value: str) -> bytes:
    if value.startswith("data:"):
        _, payload = value.split(",", 1)
        return base64.b64decode(payload)
    return base64.b64decode(value)


def normalize_image_key(value: str | None) -> str:
    if value is None:
        return ""
    key = unquote(str(value)).replace("\\", "/").strip()
    if key.startswith("./"):
        key = key[2:]
    return key


def save_images(images: dict, assets_dir: Path) -> dict[str, str]:
    image_dir = assets_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    saved: dict[str, str] = {}
    for name, value in images.items():
        if not isinstance(value, str):
            continue
        safe_name = Path(unquote(name)).name
        output = image_dir / safe_name
        output.write_bytes(decode_image_value(value))
        key = normalize_image_key(name)
        saved[key] = str(output)
        saved[Path(key).name] = str(output)
        saved[f"images/{Path(key).name}"] = str(output)
    return saved


IMAGE_LINK_RE = re.compile(r"(!\[[^\]]*\]\()([^)]+)(\))")


def split_link_target(raw_target: str) -> tuple[str, str]:
    raw = raw_target.strip()
    if raw.startswith("<") and ">" in raw:
        path_part, rest = raw[1:].split(">", 1)
        return path_part, rest.strip()
    parts = raw.split(maxsplit=1)
    if len(parts) == 1:
        return parts[0].strip("\"'"), ""
    return parts[0].strip("\"'"), parts[1].strip()


def rewrite_markdown_image_paths(markdown: str, image_map: dict[str, str], output_dir: Path) -> str:
    def replace(match: re.Match[str]) -> str:
        path_part, title_part = split_link_target(match.group(2))
        key = normalize_image_key(path_part)
        target = image_map.get(key) or image_map.get(Path(key).name) or image_map.get(f"images/{Path(key).name}")
        if not target:
            return match.group(0)
        relative = Path(os.path.relpath(Path(target).resolve(), output_dir.resolve())).as_posix()
        replacement = relative if not title_part else f"{relative} {title_part}"
        return f"{match.group(1)}{replacement}{match.group(3)}"

    return IMAGE_LINK_RE.sub(replace, markdown)


def build_asset_manifest(content_list, image_map: dict[str, str], package_dir: Path) -> list[dict]:
    if not isinstance(content_list, list):
        return []
    manifest: list[dict] = []
    for idx, item in enumerate(content_list, start=1):
        if not isinstance(item, dict):
            continue
        typ = item.get("type")
        if typ not in {"image", "equation", "table"}:
            continue
        img_path = normalize_image_key(item.get("img_path"))
        saved = image_map.get(img_path) or image_map.get(Path(img_path).name)
        if not saved:
            continue
        source_path = Path(saved)
        try:
            rel = source_path.resolve().relative_to(package_dir.resolve()).as_posix()
        except ValueError:
            rel = source_path.as_posix()
        caption = None
        if typ == "image":
            captions = item.get("image_caption") or []
            if isinstance(captions, list):
                caption = " ".join(str(x) for x in captions)
            elif captions:
                caption = str(captions)
        manifest.append(
            {
                "asset_id": f"{typ}_{idx:03d}",
                "type": "formula" if typ == "equation" else typ,
                "source": "mineru",
                "source_pdf_page": item.get("page_idx"),
                "bbox": item.get("bbox"),
                "path": rel,
                "source_img_path": img_path,
                "caption_or_label": caption or item.get("text"),
            }
        )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract md_content and content_list from MinerU JSON")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--assets-dir", type=Path, help="default: <output-dir>/../assets")
    parser.add_argument("--result-name")
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8-sig"))
    if data.get("status") != "completed":
        print(f"MinerU response is not completed: {data.get('status')} error={data.get('error')}", file=sys.stderr)
        return 1

    result_name, item = pick_result(data, args.result_name)
    md = item.get("md_content") or item.get("md") or item.get("markdown")
    if not isinstance(md, str) or not md.strip():
        print(f"MinerU result has no non-empty md_content: {result_name}", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    package_dir = args.output_dir.parent
    assets_dir = args.assets_dir or (package_dir / "assets")
    extracted_path = args.output_dir / "extracted.md"
    content_list_path = args.output_dir / "content_list.json"
    manifest_path = args.output_dir / "extraction_manifest.json"
    asset_manifest_path = package_dir / "asset_manifest.json"

    content_list = decode_content_list(item.get("content_list"))
    if content_list is not None:
        content_list_path.write_text(json.dumps(content_list, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    images = item.get("images")
    image_map: dict[str, str] = {}
    if isinstance(images, dict) and images:
        image_map = save_images(images, assets_dir)
        md = rewrite_markdown_image_paths(md, image_map, args.output_dir)

    extracted_path.write_text(md.rstrip() + "\n", encoding="utf-8")

    asset_manifest = build_asset_manifest(content_list, image_map, package_dir)
    if asset_manifest:
        asset_manifest_path.write_text(json.dumps(asset_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "schema_version": "0.1",
        "source_response": str(args.input.resolve()),
        "result_name": result_name,
        "task_id": data.get("task_id"),
        "status": data.get("status"),
        "backend": data.get("backend"),
        "version": data.get("version"),
        "status_url": data.get("status_url"),
        "result_url": data.get("result_url"),
        "outputs": {
            "extracted_md": str(extracted_path.resolve()),
            "content_list_json": str(content_list_path.resolve()) if content_list is not None else None,
            "asset_manifest_json": str(asset_manifest_path.resolve()) if asset_manifest else None,
            "assets_dir": str(assets_dir.resolve()) if image_map else None,
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(str(manifest_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
