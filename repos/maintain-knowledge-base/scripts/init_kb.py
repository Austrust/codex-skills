#!/usr/bin/env python3
"""Initialize a safe, plain-text research and operations knowledge base."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys


DIRECTORIES = (
    "catalog",
    "domains/equipment",
    "domains/software",
    "domains/datasets",
    "domains/samples",
    "domains/organizations",
    "domains/standards",
    "knowledge/concepts",
    "knowledge/methods",
    "knowledge/protocols",
    "knowledge/troubleshooting",
    "knowledge/lessons",
    "projects",
    "sources/manuals",
    "sources/papers",
    "sources/standards",
    "sources/references",
    "templates",
    "inbox",
    "archive",
)

CATALOGS = {
    "catalog/entities.csv": [
        "entity_id",
        "type",
        "subtype",
        "name",
        "status",
        "canonical_path",
        "evidence_path",
        "created_at",
        "verified_at",
        "updated_at",
    ],
    "catalog/projects.csv": [
        "project_id",
        "project_kind",
        "area",
        "objective",
        "owner",
        "started_at",
        "target_end",
        "ended_at",
        "updated_at",
    ],
    "catalog/relations.csv": [
        "from_id",
        "relation",
        "to_id",
        "context",
        "evidence_path",
        "valid_from",
        "valid_to",
        "updated_at",
    ],
}

TEMPLATE_TARGETS = {
    "knowledge-base-readme.md": "README.md",
    "knowledge-base-agents.md": "AGENTS.md",
    "vocabulary.md": "catalog/vocabulary.md",
    "entity.md": "templates/entity.md",
    "knowledge.md": "templates/knowledge.md",
    "project-research.md": "templates/project-research.md",
    "project-administrative.md": "templates/project-administrative.md",
    "decision.md": "templates/decision.md",
    "source.md": "templates/source.md",
    "protocol.md": "templates/protocol.md",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create missing files for a durable research and operations knowledge base."
    )
    parser.add_argument("root", type=Path, help="Knowledge-base root directory")
    parser.add_argument("--name", default="长期知识库", help="Human-readable knowledge-base name")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show planned changes without writing files"
    )
    return parser.parse_args()


def ensure_within_root(root: Path, target: Path) -> None:
    try:
        target.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError as exc:
        raise ValueError(f"Refusing to write outside knowledge-base root: {target}") from exc


def write_text_if_missing(path: Path, content: str, dry_run: bool) -> str:
    if path.exists():
        return "skipped"
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    return "created"


def write_csv_if_missing(path: Path, headers: list[str], dry_run: bool) -> str:
    if path.exists():
        return "skipped"
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerow(headers)
    return "created"


def main() -> int:
    args = parse_args()
    root = args.root.expanduser().resolve(strict=False)
    skill_root = Path(__file__).resolve().parent.parent
    template_root = skill_root / "assets" / "templates"

    if root.exists() and not root.is_dir():
        print(f"ERROR: root exists but is not a directory: {root}", file=sys.stderr)
        return 2

    actions: list[tuple[str, str]] = []

    for relative in DIRECTORIES:
        target = root / relative
        ensure_within_root(root, target)
        if target.exists():
            actions.append(("skipped", relative + "/"))
        else:
            if not args.dry_run:
                target.mkdir(parents=True, exist_ok=True)
            actions.append(("created", relative + "/"))

    for relative, headers in CATALOGS.items():
        target = root / relative
        ensure_within_root(root, target)
        actions.append((write_csv_if_missing(target, headers, args.dry_run), relative))

    for source_name, relative in TEMPLATE_TARGETS.items():
        source = template_root / source_name
        if not source.is_file():
            print(f"ERROR: bundled template is missing: {source}", file=sys.stderr)
            return 2
        target = root / relative
        ensure_within_root(root, target)
        content = source.read_text(encoding="utf-8").replace("{{KB_NAME}}", args.name)
        actions.append((write_text_if_missing(target, content, args.dry_run), relative))

    mode = "DRY RUN" if args.dry_run else "INITIALIZED"
    created = sum(1 for action, _ in actions if action == "created")
    skipped = sum(1 for action, _ in actions if action == "skipped")
    print(f"{mode}: {root}")
    print(f"Created: {created}; skipped existing: {skipped}")
    for action, relative in actions:
        print(f"[{action}] {relative}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
