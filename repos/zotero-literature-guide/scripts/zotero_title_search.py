#!/usr/bin/env python3
"""Search Zotero local API by paper title and report candidate item keys."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


def fetch_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def normalize(text: str) -> str:
    return " ".join(text.casefold().replace("–", "-").replace("—", "-").split())


def score_title(query: str, title: str) -> float:
    q = normalize(query)
    t = normalize(title)
    if not q or not t:
        return 0.0
    if q == t:
        return 1.0
    ratio = SequenceMatcher(None, q, t).ratio()
    if q in t or t in q:
        ratio = max(ratio, min(len(q), len(t)) / max(len(q), len(t)))
    return round(ratio, 4)


def compact_item(item: dict[str, Any], query: str) -> dict[str, Any]:
    data = item.get("data") or {}
    creators = data.get("creators") or []
    first_author = ""
    if creators:
        first = creators[0]
        first_author = first.get("lastName") or first.get("name") or ""
    title = str(data.get("title") or "")
    return {
        "key": data.get("key"),
        "itemType": data.get("itemType"),
        "title": title,
        "score": score_title(query, title),
        "year": str(data.get("date") or "")[:4],
        "first_author": first_author,
        "DOI": data.get("DOI"),
        "url": item.get("links", {}).get("alternate", {}).get("href"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Search Zotero local API by paper title.")
    parser.add_argument("--title", required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--min-score", type=float, default=0.86)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    query = urllib.parse.quote(args.title)
    base = "http://127.0.0.1:23119/api/users/0/items"
    url = f"{base}?format=json&limit={args.limit}&q={query}"
    try:
        raw = fetch_json(url)
    except Exception as exc:
        print(f"Zotero local API title search failed: {exc}", file=sys.stderr)
        return 2

    candidates = [compact_item(item, args.title) for item in raw if isinstance(item, dict)]
    candidates.sort(key=lambda item: item.get("score", 0), reverse=True)
    exact = [item for item in candidates if item.get("score", 0) >= args.min_score]
    result = {
        "query_title": args.title,
        "endpoint": url,
        "status": "exact_or_high_confidence_match" if len(exact) == 1 else "ambiguous_or_missing",
        "selected": exact[0] if len(exact) == 1 else None,
        "candidates": candidates,
        "min_score": args.min_score,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["selected"]:
            item = result["selected"]
            print(f"{item['key']}\t{item['score']}\t{item['title']}")
        else:
            for item in candidates:
                print(f"{item.get('key')}\t{item.get('score')}\t{item.get('title')}")
    return 0 if result["selected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
