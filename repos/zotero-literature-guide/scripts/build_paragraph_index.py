#!/usr/bin/env python3
"""Build an initial semantic paragraph index from MinerU content_list.json."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


SKIP_TYPES = {"header", "footer", "page_number", "aside_text"}
NON_BODY_SECTIONS = {
    "references",
    "acknowledgements",
    "acknowledgments",
    "funding",
    "author contributions",
    "competing interests",
    "data availability",
}
TERMINAL_RE = re.compile(r"[.!?。！？;；:：)\]]\s*$")
LIST_START_RE = re.compile(r"^\(?[ivxlcdm0-9a-z]+\)|^[a-z]\)")
REAL_SECTION_RE = re.compile(r"^(\d+\.|abstract\b|references\b|appendix\b|conclusions?\b)", re.I)
FRONT_MATTER_RE = re.compile(
    r"^(by\b|<sub>by</sub>|institut|department|university|\(received|received\s+\d|doi\b|https?://)",
    re.I,
)


def clean_text(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = re.sub(r"-\s+([a-z])", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def is_section_heading(item: dict, text: str) -> bool:
    level = item.get("text_level")
    if isinstance(level, int) and level > 0:
        return True
    return bool(REAL_SECTION_RE.match(text))


def is_real_section_heading(text: str) -> bool:
    return bool(REAL_SECTION_RE.match(text))


def should_merge(previous: dict, current: dict) -> bool:
    if previous.get("kind") != "body" or current.get("kind") != "body":
        return False
    if previous.get("section") != current.get("section"):
        return False
    prev_text = str(previous.get("text", "")).strip()
    curr_text = str(current.get("text", "")).strip()
    if not prev_text or not curr_text:
        return False
    if LIST_START_RE.match(curr_text):
        return False
    if prev_text.endswith("-"):
        return True
    if not TERMINAL_RE.search(prev_text) and curr_text[:1].islower():
        return True
    return False


def is_front_matter_text(text: str) -> bool:
    wc = word_count(text)
    if FRONT_MATTER_RE.match(text):
        return True
    if wc <= 20 and not TERMINAL_RE.search(text):
        return True
    return False


def classify(section: str, before_first_section: bool, text: str) -> tuple[str, str, bool]:
    if before_first_section:
        if is_front_matter_text(text):
            return section, "metadata", False
        return "Abstract", "body", True
    section_lc = section.strip().lower()
    if section_lc in NON_BODY_SECTIONS or section_lc.startswith("references"):
        return section, "reference", False
    return section, "body", True


def build_index(content_list: list[dict]) -> tuple[dict, list[str]]:
    current_section = "Front matter"
    before_first_section = True
    records: list[dict] = []
    boundary_notes: list[str] = []

    for item in content_list:
        if not isinstance(item, dict):
            continue
        typ = str(item.get("type", "text"))
        if typ in SKIP_TYPES:
            continue
        if typ != "text":
            continue
        text = clean_text(str(item.get("text") or ""))
        if not text:
            continue
        if is_section_heading(item, text):
            if is_real_section_heading(text):
                current_section = text
                before_first_section = False
            else:
                current_section = "Front matter"
            continue

        section, kind, guide = classify(current_section, before_first_section, text)
        record = {
            "section": section,
            "kind": kind,
            "guide": guide,
            "text": text,
            "word_count": word_count(text),
            "page_idx": item.get("page_idx"),
            "boundary_confidence": "high",
            "boundary_note": "",
            "extraction_risks": [],
        }
        if records and should_merge(records[-1], record):
            records[-1]["text"] = clean_text(str(records[-1]["text"]) + " " + text)
            records[-1]["word_count"] = word_count(str(records[-1]["text"]))
            records[-1]["boundary_confidence"] = "medium"
            records[-1]["boundary_note"] = "Merged likely PDF/parser split with following text block."
            boundary_notes.append(f"merged page {records[-1].get('page_idx')} into section {records[-1].get('section')}")
        else:
            records.append(record)

    numbered: list[dict] = []
    for index, record in enumerate(records, start=1):
        numbered.append({"id": f"P{index:03d}", **record})

    return {
        "schema_version": "0.1",
        "source": "mineru content_list with conservative semantic reconstruction",
        "paragraphs": numbered,
    }, boundary_notes


def main() -> int:
    parser = argparse.ArgumentParser(description="Build paragraph_index.json from MinerU content_list.json")
    parser.add_argument("--content-list", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--boundary-report", type=Path)
    args = parser.parse_args()

    content = json.loads(args.content_list.read_text(encoding="utf-8-sig"))
    if not isinstance(content, list):
        raise ValueError("content_list must be a JSON list")
    index, boundary_notes = build_index(content)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.boundary_report:
        args.boundary_report.parent.mkdir(parents=True, exist_ok=True)
        report = ["# Paragraph Boundary Report", ""]
        if boundary_notes:
            report.extend(f"- {note}" for note in boundary_notes)
        else:
            report.append("- No automatic merge was applied.")
        args.boundary_report.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
