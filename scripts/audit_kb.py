#!/usr/bin/env python3
"""Audit the structural integrity of a local research and operations knowledge base."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import date, timedelta
import json
from pathlib import Path
import re
import sys
from typing import Iterable


ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+$")
URL_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)

REQUIRED_PATHS = (
    "README.md",
    "AGENTS.md",
    "catalog/entities.csv",
    "catalog/projects.csv",
    "catalog/relations.csv",
    "catalog/vocabulary.md",
    "domains",
    "knowledge",
    "projects",
    "sources",
    "templates",
    "inbox",
    "archive",
)

CSV_HEADERS = {
    "catalog/entities.csv": {
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
    },
    "catalog/projects.csv": {
        "project_id",
        "project_kind",
        "area",
        "objective",
        "owner",
        "started_at",
        "target_end",
        "ended_at",
        "updated_at",
    },
    "catalog/relations.csv": {
        "from_id",
        "relation",
        "to_id",
        "context",
        "evidence_path",
        "valid_from",
        "valid_to",
        "updated_at",
    },
}

DATE_FIELDS = {
    "created_at",
    "verified_at",
    "updated_at",
    "started_at",
    "target_end",
    "ended_at",
    "valid_from",
    "valid_to",
}

ACTIVE_STATUSES = {"active", "available", "in_use", "maintenance", "validated"}
KNOWN_STATUSES = ACTIVE_STATUSES | {
    "planned",
    "blocked",
    "completed",
    "cancelled",
    "retired",
    "lost",
    "inactive",
    "unknown",
    "draft",
    "candidate",
    "deprecated",
    "archived",
}

KNOWN_RELATIONS = {
    "uses",
    "produces",
    "applies",
    "derived_from",
    "supports",
    "contradicts",
    "part_of",
    "instance_of",
    "located_at",
    "owned_by",
    "supersedes",
    "related_to",
}


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    path: str
    message: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit a long-term local knowledge base")
    parser.add_argument("root", type=Path, help="Knowledge-base root directory")
    parser.add_argument(
        "--stale-days",
        type=int,
        default=180,
        help="Warn when active facts have not been verified for this many days",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    return parser.parse_args()


def add(issues: list[Issue], severity: str, code: str, path: str, message: str) -> None:
    issues.append(Issue(severity, code, path.replace("\\", "/"), message))


def read_csv(
    root: Path, relative: str, issues: list[Issue]
) -> list[dict[str, str]]:
    path = root / relative
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = set(reader.fieldnames or [])
            missing = CSV_HEADERS[relative] - headers
            if missing:
                add(
                    issues,
                    "error",
                    "missing-csv-columns",
                    relative,
                    "Missing columns: " + ", ".join(sorted(missing)),
                )
            return [
                {key: (value or "").strip() for key, value in row.items() if key is not None}
                for row in reader
            ]
    except (OSError, csv.Error, UnicodeError) as exc:
        add(issues, "error", "unreadable-csv", relative, str(exc))
        return []


def valid_relative_path(root: Path, value: str) -> tuple[bool, str]:
    if not value or URL_PATTERN.match(value):
        return True, ""
    candidate = Path(value)
    if candidate.is_absolute():
        return False, "Path must be relative to the knowledge-base root"
    resolved = (root / candidate).resolve(strict=False)
    try:
        resolved.relative_to(root.resolve(strict=False))
    except ValueError:
        return False, "Path escapes the knowledge-base root"
    if not resolved.exists():
        return False, "Path does not exist"
    return True, ""


def check_date(
    issues: list[Issue], relative: str, row_number: int, field: str, value: str
) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        add(
            issues,
            "error",
            "invalid-date",
            relative,
            f"Row {row_number}, {field}={value!r} is not YYYY-MM-DD",
        )
        return None


def parse_frontmatter(path: Path) -> dict[str, str] | None:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        return None
    if not lines or lines[0].strip() != "---":
        return None
    values: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return values
        if not line or line[0].isspace() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"\'')
    return None


def check_markdown(
    root: Path, issues: list[Issue], entity_ids: dict[str, dict[str, str]]
) -> None:
    knowledge_root = root / "knowledge"
    if knowledge_root.is_dir():
        for path in knowledge_root.rglob("*.md"):
            if path.name.casefold() in {"readme.md", "index.md"}:
                continue
            relative = path.relative_to(root).as_posix()
            metadata = parse_frontmatter(path)
            if metadata is None:
                add(issues, "warning", "missing-frontmatter", relative, "Knowledge note has no readable YAML front matter")
                continue
            for field in ("id", "title", "kind", "status", "updated_at"):
                if not metadata.get(field):
                    add(issues, "warning", "missing-metadata", relative, f"Missing metadata field: {field}")
            note_id = metadata.get("id", "")
            if note_id and note_id not in entity_ids:
                add(issues, "warning", "knowledge-without-entity", relative, f"{note_id} is not registered in entities.csv")
            if "sources" not in metadata:
                add(issues, "warning", "missing-sources-field", relative, "Knowledge note should declare sources, even when the list is empty")


def audit(root: Path, stale_days: int) -> tuple[list[Issue], dict[str, int]]:
    issues: list[Issue] = []
    counts = {"entities": 0, "projects": 0, "relations": 0}

    if not root.is_dir():
        add(issues, "error", "missing-root", str(root), "Knowledge-base root is not a directory")
        return issues, counts

    for relative in REQUIRED_PATHS:
        if not (root / relative).exists():
            add(issues, "error", "missing-required-path", relative, "Required path is missing")

    entities = read_csv(root, "catalog/entities.csv", issues)
    projects = read_csv(root, "catalog/projects.csv", issues)
    relations = read_csv(root, "catalog/relations.csv", issues)
    counts.update(entities=len(entities), projects=len(projects), relations=len(relations))

    entity_ids: dict[str, dict[str, str]] = {}
    stale_before = date.today() - timedelta(days=max(stale_days, 0))

    for row_number, row in enumerate(entities, start=2):
        entity_id = row.get("entity_id", "")
        if not entity_id:
            add(issues, "error", "missing-id", "catalog/entities.csv", f"Row {row_number} has no entity_id")
            continue
        if not ID_PATTERN.fullmatch(entity_id):
            add(issues, "warning", "unusual-id", "catalog/entities.csv", f"Row {row_number} has unusual ID {entity_id!r}")
        if entity_id in entity_ids:
            add(issues, "error", "duplicate-id", "catalog/entities.csv", f"Duplicate entity_id: {entity_id}")
        entity_ids[entity_id] = row

        if not row.get("type") or not row.get("name"):
            add(issues, "error", "missing-identity-field", "catalog/entities.csv", f"Row {row_number} requires type and name")
        if not row.get("canonical_path"):
            add(issues, "error", "missing-canonical-path", "catalog/entities.csv", f"{entity_id} has no canonical_path")
        status = row.get("status", "")
        if status and status not in KNOWN_STATUSES:
            add(issues, "warning", "unknown-status", "catalog/entities.csv", f"Row {row_number} uses undeclared status {status!r}")

        for field in DATE_FIELDS & row.keys():
            parsed = check_date(issues, "catalog/entities.csv", row_number, field, row.get(field, ""))
            if field == "verified_at" and parsed and status in ACTIVE_STATUSES and parsed < stale_before:
                add(issues, "warning", "stale-verification", "catalog/entities.csv", f"{entity_id} was last verified on {parsed.isoformat()}")

        for field in ("canonical_path", "evidence_path"):
            value = row.get(field, "")
            valid, message = valid_relative_path(root, value)
            if not valid:
                severity = "error" if field == "canonical_path" else "warning"
                add(issues, severity, "invalid-path", "catalog/entities.csv", f"{entity_id} {field}: {message} ({value})")

    project_ids: set[str] = set()
    for row_number, row in enumerate(projects, start=2):
        project_id = row.get("project_id", "")
        if not project_id:
            add(issues, "error", "missing-project-id", "catalog/projects.csv", f"Row {row_number} has no project_id")
            continue
        if project_id in project_ids:
            add(issues, "error", "duplicate-project-id", "catalog/projects.csv", f"Duplicate project_id: {project_id}")
        project_ids.add(project_id)
        entity = entity_ids.get(project_id)
        if entity is None:
            add(issues, "error", "project-without-entity", "catalog/projects.csv", f"{project_id} is not registered in entities.csv")
        elif entity.get("type") != "project":
            add(issues, "error", "wrong-project-type", "catalog/entities.csv", f"{project_id} must have type=project")
        else:
            canonical = entity.get("canonical_path", "")
            if canonical:
                project_file = root / canonical / "PROJECT.md"
                if not project_file.is_file():
                    add(issues, "error", "missing-project-entry", project_file.relative_to(root).as_posix(), f"{project_id} has no PROJECT.md")
                else:
                    metadata = parse_frontmatter(project_file)
                    if metadata is None:
                        add(issues, "warning", "missing-frontmatter", project_file.relative_to(root).as_posix(), "PROJECT.md has no readable front matter")
                    elif metadata.get("id") != project_id:
                        add(issues, "error", "project-id-mismatch", project_file.relative_to(root).as_posix(), f"Front matter ID does not match {project_id}")
                    elif metadata.get("status") and metadata.get("status") != entity.get("status"):
                        add(issues, "warning", "project-status-drift", project_file.relative_to(root).as_posix(), f"PROJECT.md status differs from entities.csv for {project_id}")

        for field in DATE_FIELDS & row.keys():
            check_date(issues, "catalog/projects.csv", row_number, field, row.get(field, ""))

    relation_keys: set[tuple[str, str, str, str, str, str]] = set()
    for row_number, row in enumerate(relations, start=2):
        from_id = row.get("from_id", "")
        to_id = row.get("to_id", "")
        relation = row.get("relation", "")
        if not from_id or not to_id or not relation:
            add(issues, "error", "incomplete-relation", "catalog/relations.csv", f"Row {row_number} requires from_id, relation, and to_id")
            continue
        if relation not in KNOWN_RELATIONS:
            add(issues, "warning", "unknown-relation", "catalog/relations.csv", f"Row {row_number} uses undeclared relation {relation!r}")
        if from_id not in entity_ids:
            add(issues, "error", "missing-relation-endpoint", "catalog/relations.csv", f"Row {row_number}: unknown from_id {from_id}")
        if to_id not in entity_ids:
            add(issues, "error", "missing-relation-endpoint", "catalog/relations.csv", f"Row {row_number}: unknown to_id {to_id}")
        key = (
            from_id,
            relation,
            to_id,
            row.get("context", ""),
            row.get("valid_from", ""),
            row.get("valid_to", ""),
        )
        if key in relation_keys:
            add(issues, "warning", "duplicate-relation", "catalog/relations.csv", f"Row {row_number} duplicates an existing relation")
        relation_keys.add(key)

        valid, message = valid_relative_path(root, row.get("evidence_path", ""))
        if not valid:
            add(issues, "warning", "invalid-evidence-path", "catalog/relations.csv", f"Row {row_number}: {message}")
        for field in DATE_FIELDS & row.keys():
            check_date(issues, "catalog/relations.csv", row_number, field, row.get(field, ""))

    check_markdown(root, issues, entity_ids)
    return issues, counts


def print_text(root: Path, issues: Iterable[Issue], counts: dict[str, int]) -> None:
    issue_list = list(issues)
    errors = sum(issue.severity == "error" for issue in issue_list)
    warnings = sum(issue.severity == "warning" for issue in issue_list)
    print(f"Knowledge-base audit: {root}")
    print(
        f"Entities: {counts['entities']}; projects: {counts['projects']}; "
        f"relations: {counts['relations']}"
    )
    print(f"Errors: {errors}; warnings: {warnings}")
    for issue in issue_list:
        print(f"[{issue.severity.upper()}] {issue.code} | {issue.path} | {issue.message}")


def main() -> int:
    args = parse_args()
    root = args.root.expanduser().resolve(strict=False)
    issues, counts = audit(root, args.stale_days)
    errors = sum(issue.severity == "error" for issue in issues)
    warnings = sum(issue.severity == "warning" for issue in issues)

    if args.json:
        print(
            json.dumps(
                {
                    "root": str(root),
                    "counts": counts,
                    "errors": errors,
                    "warnings": warnings,
                    "issues": [asdict(issue) for issue in issues],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print_text(root, issues, counts)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
