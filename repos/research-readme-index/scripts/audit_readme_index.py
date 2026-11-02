#!/usr/bin/env python3
"""Read-only README navigation audit for research projects and knowledge bases.

The script only reports; it never edits README files. By default it prints a
summary to stdout and writes nothing. Reports are written only with --out.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlsplit

DEFAULT_RUN_DIR_NAME = "runs"
ENTRY_NAMES = ("README.md", "REPORT.md", "PROJECT.md")
NAV_ENTRY = "README.md"

# Generated, private, cached or config-only folders are never navigation pages.
SKIP_PARTS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "intermediate",
    "_organizer",
    "cache",
    "tmp",
    "temp",
    "figures",
    "images",
    ".scratch",
    "skill-backups",
    ".test-state",
    "private",
    "configs",
    "__MACOSX",
}
# Knowledge bases additionally treat the capture area as non-navigation.
KB_SKIP_PARTS = {"inbox"}
KB_SECTION_ROOTS = ("catalog", "domains", "knowledge", "projects", "sources")
KB_AUX_SECTION = "catalog"

LINK_RE = re.compile(r"\[[^\]]*\]\(\s*([^)]*?)\s*\)")
REMOTE_SCHEMES = {"http", "https", "mailto", "ftp", "ssh", "tel"}
OBJECT_BUNDLE_RE = re.compile(r"^[A-Z]{2,6}-\d{3,}$")


class ScopeError(Exception):
    """Raised when no explicit, change-based or requested scan scope exists."""


def rel(path: Path, root: Path) -> str:
    try:
        value = path.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return str(path)
    return "." if str(value) == "." else value.as_posix()


def safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="utf-8-sig", errors="ignore")
        except OSError:
            return ""
    except OSError:
        return ""


def norm(path: Path) -> str:
    try:
        return os.path.normcase(str(path.resolve()))
    except OSError:
        return os.path.normcase(str(path))


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def entry_names(args: argparse.Namespace | None = None) -> tuple[str, ...]:
    custom = getattr(args, "entry_file", None) if args is not None else None
    if custom:
        return tuple(custom)
    return ENTRY_NAMES


def entry_file(directory: Path, names: Iterable[str]) -> Path | None:
    """Return the object's single landing file. README wins over REPORT/PROJECT."""
    for name in names:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def skipped_parts(kb_root: Path | None) -> set[str]:
    return SKIP_PARTS | (KB_SKIP_PARTS if kb_root is not None else set())


def is_skipped(path: Path, root: Path, kb_root: Path | None) -> bool:
    if path.is_symlink():
        return True
    if not is_within(path, root):
        return False
    try:
        parts = path.resolve().relative_to(root.resolve()).parts
    except (ValueError, OSError):
        return True
    return any(part in skipped_parts(kb_root) for part in parts)


def walk_dirs(root: Path, kb_root: Path | None) -> list[Path]:
    directories: list[Path] = []
    for current, dirs, _ in os.walk(root, followlinks=False):
        here = Path(current)
        keep: list[str] = []
        for name in dirs:
            child = here / name
            if child.is_symlink():
                continue
            if name in skipped_parts(kb_root):
                continue
            keep.append(name)
        dirs[:] = keep
        directories.append(here)
    return directories


def git_changed_paths(root: Path) -> list[Path] | None:
    """Return changed paths from Git, or None when Git cannot provide them."""
    try:
        top = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if top.returncode != 0:
            return None
        repo = Path(top.stdout.strip())
        status = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain=v1", "-z"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if status.returncode != 0:
        return None
    paths: list[Path] = []
    for record in status.stdout.split("\0"):
        if not record:
            continue
        raw = record[3:] if len(record) > 3 and record[2] == " " else record[2:]
        raw = raw.strip()
        if not raw or " -> " in raw:
            continue
        candidate = (repo / raw).resolve()
        if candidate == root.resolve() or root.resolve() in candidate.parents:
            paths.append(candidate)
    return paths


def mtime_changed_paths(root: Path, hours: float, names: Iterable[str]) -> list[Path]:
    cutoff = datetime.now() - timedelta(hours=hours)
    found: list[Path] = []
    for directory in walk_dirs(root, None):
        entry = entry_file(directory, names)
        if entry is not None:
            try:
                if datetime.fromtimestamp(entry.stat().st_mtime) >= cutoff:
                    found.append(entry)
            except OSError:
                continue
    return found


def discover_scope(root: Path, args: argparse.Namespace) -> tuple[list[Path], str, str]:
    """Explicit paths > generated change set (Git) > explicit mtime. Never full."""
    names = entry_names(args)
    if args.paths:
        paths = []
        for item in args.paths:
            path = Path(item)
            paths.append((path if path.is_absolute() else root / path))
        return paths, "paths", "explicit --paths"
    if args.full:
        return [], "full", "explicit --full"
    if args.mtime_hours is not None:
        return mtime_changed_paths(root, args.mtime_hours, names), "mtime", (
            f"explicit --mtime-hours {args.mtime_hours}"
        )
    changed = git_changed_paths(root)
    if changed is not None:
        return changed, "git", "Git porcelain change set"
    raise ScopeError(
        "Cannot determine scan scope: no explicit --paths/--full, and Git is "
        "unavailable here. Pass --paths, --mtime-hours, or --full explicitly. "
        "The script does not fall back to a full scan."
    )


def split_target(raw: str) -> str | None:
    target = raw.strip()
    if not target:
        return None
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    if target.startswith("#"):
        return None
    target = unquote(target).replace("\\", "/")
    # Drop optional Markdown title: [x](path "title")
    match = re.match(r"^(.*?)\s+[\"'].*[\"']$", target)
    if match:
        target = match.group(1).strip()
    return target or None


def resolve_target(entry: Path, raw: str, root: Path) -> dict:
    """Classify one link target as valid, stale, stale_external or unchecked."""
    target = split_target(raw)
    if target is None:
        return {"state": "valid", "note": "anchor only"}
    split = urlsplit(target)
    if split.scheme.lower() in REMOTE_SCHEMES or target.startswith("//"):
        return {"state": "unchecked", "reason": "remote URL", "target": raw}
    path_only = target.split("#", 1)[0].split("?", 1)[0]
    if not path_only:
        return {"state": "valid", "note": "anchor only"}
    candidate = Path(path_only)
    if not candidate.is_absolute():
        candidate = entry.parent / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return {"state": "unchecked", "reason": "unresolvable path", "target": raw}
    inside = resolved == root.resolve() or root.resolve() in resolved.parents
    try:
        exists = resolved.exists()
    except OSError:
        exists = False
    if inside:
        if exists:
            return {"state": "valid", "path": resolved, "target": raw}
        return {"state": "stale", "path": resolved, "target": raw}
    if exists:
        return {"state": "valid", "external": True, "path": resolved, "target": raw}
    return {"state": "stale_external", "external": True, "path": resolved, "target": raw}


def resolve_entry_links(entry: Path, root: Path) -> list[dict]:
    links: list[dict] = []
    for match in LINK_RE.finditer(safe_read(entry)):
        links.append(resolve_target(entry, match.group(1), root))
    return links


def determine_role(entry: Path, root: Path, kb_root: Path | None) -> str:
    """Role priority: known entry -> catalog (KB auxiliary) -> unknown."""
    parent = entry.parent
    if entry.name in ("REPORT.md", "PROJECT.md"):
        return "entry"
    if kb_root is not None and is_within(parent, kb_root):
        try:
            parts = parent.resolve().relative_to(kb_root.resolve()).parts
        except (ValueError, OSError):
            parts = ()
        if not parts:
            return "navigation"
        if parts[0] == KB_AUX_SECTION:
            return "auxiliary"
        if parts[0] in KB_SECTION_ROOTS and len(parts) == 1:
            return "navigation"
        return "unknown"
    return "navigation"


def referencable(path: Path | None) -> Path | None:
    if path is None:
        return None
    try:
        return path if path.is_dir() else path.parent
    except OSError:
        return None


def build_index(
    root: Path,
    mode: str,
    input_paths: list[Path],
    args: argparse.Namespace,
    kb_root: Path | None,
) -> tuple[set[Path], dict[Path, Path], set[Path], dict[Path, str]]:
    names = entry_names(args)
    candidates: set[Path] = set()
    entries: dict[Path, Path] = {}
    forced: set[Path] = set()

    if mode == "full":
        seed_dirs: Iterable[Path] = walk_dirs(root, kb_root)
    else:
        seeds: set[Path] = set()
        for path in input_paths:
            current = path if path.is_dir() else path.parent
            if not current.exists():
                current = current.parent
            if not is_within(current, root):
                continue
            while True:
                if is_within(current, root):
                    seeds.add(current)
                if current == root or current.parent == current:
                    break
                current = current.parent
        seed_dirs = sorted(seeds)

    for directory in seed_dirs:
        if is_skipped(directory, root, kb_root):
            continue
        landing = entry_file(directory, names)
        if landing is not None:
            candidates.add(directory)
            entries[directory] = landing
        elif directory == root:
            candidates.add(directory)

    for item in args.require_entry or []:
        required = Path(item)
        required = required if required.is_absolute() else root / required
        required = required.resolve()
        if required.is_dir() and is_within(required, root) and not is_skipped(required, root, kb_root):
            candidates.add(required)
            forced.add(required)

    if kb_root is not None:
        for section in KB_SECTION_ROOTS:
            section_dir = (kb_root / section).resolve()
            if section_dir.is_dir() and not is_skipped(section_dir, root, kb_root):
                candidates.add(section_dir)
                forced.add(section_dir)

    for path in input_paths:
        current = path if path.is_dir() else path.parent
        if current.is_dir() and is_within(current, root) and not is_skipped(current, root, kb_root):
            candidates.add(current.resolve())
            forced.add(current.resolve())

    # A parent README link is a navigational promise: the linked directory or
    # the directory holding a linked entry file becomes a candidate too.
    queue = list(entries)
    seen: set[str] = set()
    while queue:
        directory = queue.pop()
        if norm(directory) in seen:
            continue
        seen.add(norm(directory))
        for link in resolve_entry_links(entries[directory], root):
            if link.get("state") != "valid":
                continue
            target_dir = referencable(link.get("path"))
            if target_dir is None or target_dir == root:
                continue
            if not is_within(target_dir, root) or is_skipped(target_dir, root, kb_root):
                continue
            target_dir = target_dir.resolve()
            if is_object_bundle(target_dir, names):
                continue
            candidates.add(target_dir)
            if target_dir not in entries:
                landing = entry_file(target_dir, names)
                if landing is not None:
                    entries[target_dir] = landing
                    queue.append(target_dir)

    filtered: set[Path] = set()
    for directory in candidates:
        if not directory.is_dir() or directory.is_symlink():
            continue
        if not is_within(directory, root) or is_skipped(directory, root, kb_root):
            continue
        filtered.add(directory.resolve())

    fixed_entries: dict[Path, Path] = {}
    for directory in filtered:
        landing = entries.get(directory)
        if landing is None:
            landing = entry_file(directory, names)
        if landing is not None:
            fixed_entries[directory] = landing
    roles = {
        directory: determine_role(landing, root, kb_root)
        for directory, landing in fixed_entries.items()
    }
    # In a knowledge base, a README that lists two or more direct children is a
    # category navigation page; record/entity READMEs stay "unknown".
    for directory, landing in fixed_entries.items():
        if roles.get(directory) != "unknown":
            continue
        direct_children = 0
        for link in resolve_entry_links(landing, root):
            if link.get("state") != "valid":
                continue
            target = referencable(link.get("path"))
            if target is not None and target.parent == directory:
                direct_children += 1
        if direct_children >= 2:
            roles[directory] = "navigation"
    return filtered, fixed_entries, forced, roles


def is_object_bundle(directory: Path, names: Iterable[str]) -> bool:
    """A record bundle (SRC-0010/...) is an object, not a navigation level."""
    if not OBJECT_BUNDLE_RE.match(directory.name):
        return False
    if entry_file(directory, names) is not None:
        return False
    try:
        return any(item.is_file() for item in directory.iterdir())
    except OSError:
        return False


def is_pure_resource(directory: Path, kb_root: Path | None) -> bool:
    """A folder of non-Markdown assets with no subfolders needs no entry page."""
    try:
        children = list(directory.iterdir())
    except OSError:
        return True
    subdirs = [
        item for item in children
        if item.is_dir() and not item.is_symlink()
        and item.name not in skipped_parts(kb_root)
    ]
    markdown = [item for item in children if item.is_file() and item.suffix.lower() == ".md"]
    return not subdirs and not markdown


def check_missing_entries(
    root: Path,
    candidates: Iterable[Path],
    entries: dict[Path, Path],
    forced: set[Path],
    kb_root: Path | None,
) -> list[dict]:
    gaps: list[dict] = []
    for directory in sorted(candidates):
        if directory in entries:
            continue
        if directory != root and directory not in forced and is_pure_resource(directory, kb_root):
            continue
        gaps.append({
            "type": "missing_entry",
            "severity": "error",
            "folder": rel(directory, root),
            "message": "Navigation candidate has no README.md, REPORT.md or PROJECT.md entry file.",
        })
    return gaps


def nearest_navigation_entry(
    directory: Path,
    root: Path,
    entries: dict[Path, Path],
    roles: dict[Path, str],
) -> tuple[Path, Path] | None:
    current = directory.parent
    while True:
        landing = entries.get(current)
        if landing is not None:
            if roles.get(current) == "navigation":
                return current, landing
            # An object/unknown entry page is not a navigation level; do not
            # escalate its children to a higher navigation ancestor.
            return None
        if current == root or current.parent == current:
            return None
        current = current.parent


def referenced_dirs(entry: Path, root: Path) -> dict[str, Path]:
    referenced: dict[str, Path] = {}
    for link in resolve_entry_links(entry, root):
        if link.get("state") != "valid":
            continue
        target_dir = referencable(link.get("path"))
        if target_dir is not None:
            referenced[norm(target_dir)] = target_dir
    return referenced


def check_parent_links(
    root: Path,
    candidates: Iterable[Path],
    entries: dict[Path, Path],
    roles: dict[Path, str],
    strict_index: bool,
) -> list[dict]:
    gaps: list[dict] = []
    seen_cross: set[tuple[str, str]] = set()
    for child in sorted(candidates):
        if child == root:
            continue
        parent = nearest_navigation_entry(child, root, entries, roles)
        if parent is None:
            continue
        parent_dir, parent_entry = parent
        referenced = referenced_dirs(parent_entry, root)
        child_resolved = child.resolve()
        covered = any(
            target == child_resolved or child_resolved in target.parents
            for target in referenced.values()
        )
        if not covered:
            gaps.append({
                "type": "missing_parent_link",
                "severity": "error",
                "readme": rel(parent_entry, root),
                "child": rel(child, root),
                "message": "Parent navigation entry does not link this direct navigation child.",
            })
        elif strict_index:
            for target in referenced.values():
                try:
                    parts = target.resolve().relative_to(parent_dir.resolve()).parts
                except (ValueError, OSError):
                    continue
                if len(parts) <= 1:
                    continue
                key = (str(parent_entry), str(target))
                if key in seen_cross:
                    continue
                seen_cross.add(key)
                gaps.append({
                    "type": "cross_level_entry",
                    "severity": "warning",
                    "readme": rel(parent_entry, root),
                    "target": rel(target, root),
                    "message": "Navigation entry links below its direct-child level.",
                })
                break
    return gaps


def check_links(
    root: Path,
    entries: dict[Path, Path],
    metrics: dict[str, int],
) -> list[dict]:
    gaps: list[dict] = []
    for directory, landing in sorted(entries.items()):
        targets: dict[str, int] = {}
        for match in LINK_RE.finditer(safe_read(landing)):
            link = resolve_target(landing, match.group(1), root)
            state = link["state"]
            metrics[state] = metrics.get(state, 0) + 1
            if state == "unchecked":
                reason = link.get("reason", "unchecked")
                metrics[f"unchecked:{reason}"] = metrics.get(f"unchecked:{reason}", 0) + 1
                continue
            target = link.get("target", match.group(1))
            if state == "valid":
                key = norm(link["path"]) if link.get("path") else target
                targets[key] = targets.get(key, 0) + 1
                continue
            gaps.append({
                "type": "stale_link" if state == "stale" else "stale_external_link",
                "severity": "error" if state == "stale" else "warning",
                "readme": rel(landing, root),
                "target": target,
                "message": "Link target does not exist."
                           + ("" if state == "stale" else " Target is outside the project root."),
            })
        for key, count in targets.items():
            if count > 1:
                gaps.append({
                    "type": "duplicate_entry",
                    "severity": "warning",
                    "readme": rel(landing, root),
                    "target": key,
                    "message": f"Same link target is listed {count} times in one entry page.",
                })
    return gaps


def check_budget(
    root: Path,
    entries: dict[Path, Path],
    roles: dict[Path, str],
    max_links: int,
) -> list[dict]:
    if not max_links:
        return []
    gaps: list[dict] = []
    for directory, landing in sorted(entries.items()):
        if roles.get(directory) != "navigation":
            continue
        count = len(LINK_RE.findall(safe_read(landing)))
        if count > max_links:
            gaps.append({
                "type": "budget_exceeded",
                "severity": "warning",
                "readme": rel(landing, root),
                "links": count,
                "max_links": max_links,
                "message": f"Navigation page lists {count} links; budget is a hint only: {max_links}.",
            })
    return gaps


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, data: dict) -> None:
    lines = [
        "# README Index Audit",
        "",
        f"- Generated: `{data['generated_at']}`",
        f"- Project root: `{data['project_root']}`",
        f"- Mode: `{data['mode']}` ({data['scope_source']})",
        f"- KB mode: `{data['kb_mode']}`",
        "",
        "## Scope",
        "",
    ]
    if data["input_paths"]:
        lines.extend(f"- `{item}`" for item in data["input_paths"])
    else:
        lines.append("- No explicit input paths; scope from change set or full scan.")
    lines.extend(["", "## Gaps", ""])
    if not data["gaps"]:
        lines.append("- No README navigation gaps found in scope.")
    else:
        grouped: dict[str, list[dict]] = {}
        for gap in data["gaps"]:
            grouped.setdefault(gap["type"], []).append(gap)
        for gap_type, items in grouped.items():
            lines.extend([f"### {gap_type}", ""])
            for item in items:
                details = ", ".join(
                    f"{key}=`{value}`" for key, value in item.items()
                    if key not in {"type", "message", "severity"}
                )
                lines.append(f"- [{item['severity']}] {item['message']} {details}".rstrip())
            lines.append("")
    lines.extend(["## Link metrics", ""])
    for key, value in sorted(data["link_metrics"].items()):
        lines.append(f"- `{key}`: {value}")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit README navigation. Read-only: prints only, writes files only with --out."
    )
    parser.add_argument("--project-root", default=".",
                        help="Project or knowledge-base root. Defaults to current directory.")
    parser.add_argument("--paths", nargs="*", help="Explicit changed paths (files or directories).")
    parser.add_argument("--full", action="store_true", help="Explicit full-project scan. Never implied.")
    parser.add_argument("--mtime-hours", type=float, default=None,
                        help="Explicit mtime fallback in hours (never implied).")
    parser.add_argument("--run-dir-name", default=DEFAULT_RUN_DIR_NAME,
                        help="Existing run-container directory name. Defaults to runs.")
    parser.add_argument("--entry-file", action="append", default=None,
                        help="Entry file name, repeatable. Defaults to README.md, REPORT.md, PROJECT.md.")
    parser.add_argument("--require-entry", action="append", default=None,
                        help="Directory that must have an entry file, repeatable.")
    parser.add_argument("--kb-root", default=None,
                        help="Knowledge-base root. Enables KB roles: catalog/ is auxiliary, "
                             "section roots need entries, inbox/ is skipped.")
    parser.add_argument("--max-entry-links", type=int, default=0,
                        help="Hint threshold for navigation-page links (0 = off).")
    parser.add_argument("--strict-index", action="store_true",
                        help="Also warn about links below the direct-child level.")
    parser.add_argument("--check", action="store_true",
                        help="Report only; exit 1 when error-level findings exist.")
    parser.add_argument("--strict", action="store_true",
                        help="With --check, treat warnings as failures too.")
    parser.add_argument("--out", default=None,
                        help="Write JSON+Markdown report to this directory. Defaults to no files.")
    parser.add_argument("--json", action="store_true", help="Print the JSON result to stdout.")
    parser.add_argument("--quiet", action="store_true", help="Do not print the human summary.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.project_root).resolve()
    if not root.is_dir():
        print(f"Project root does not exist or is not a directory: {root}", file=sys.stderr)
        return 2

    kb_root: Path | None = None
    if args.kb_root:
        kb_root = Path(args.kb_root)
        kb_root = (kb_root if kb_root.is_absolute() else root / kb_root).resolve()
        if not kb_root.is_dir() or not is_within(kb_root, root):
            print(f"KB root must be an existing directory inside the project root: {kb_root}", file=sys.stderr)
            return 2

    try:
        input_paths, mode, scope_source = discover_scope(root, args)
    except ScopeError as error:
        print(str(error), file=sys.stderr)
        return 2
    normalized_paths = [(path if path.is_absolute() else root / path) for path in input_paths]

    candidates, entries, forced, roles = build_index(root, mode, normalized_paths, args, kb_root)

    metrics: dict[str, int] = {}
    gaps: list[dict] = []
    gaps.extend(check_missing_entries(root, candidates, entries, forced, kb_root))
    gaps.extend(check_parent_links(root, candidates, entries, roles, args.strict_index))
    gaps.extend(check_links(root, entries, metrics))
    gaps.extend(check_budget(root, entries, roles, args.max_entry_links))

    errors = [gap for gap in gaps if gap["severity"] == "error"]
    warnings = [gap for gap in gaps if gap["severity"] == "warning"]

    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project_root": str(root),
        "mode": mode,
        "scope_source": scope_source,
        "kb_mode": kb_root is not None,
        "run_dir_name": args.run_dir_name,
        "entry_files": [rel(path, root) for path in sorted(entries.values())],
        "candidates": [rel(path, root) for path in sorted(candidates)],
        "input_paths": [
            rel(path, root) if is_within(path, root) else str(path)
            for path in normalized_paths
        ],
        "gaps": gaps,
        "counts": {"error": len(errors), "warning": len(warnings), "total": len(gaps)},
        "link_metrics": metrics,
    }

    out_dir: Path | None = None
    if args.out:
        out_dir = Path(args.out)
        out_dir = out_dir if out_dir.is_absolute() else root / out_dir
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            write_json(out_dir / "readme_index_audit.json", data)
            write_markdown(out_dir / "readme_index_audit.md", data)
        except OSError as error:
            print(f"Cannot write report: {error}", file=sys.stderr)
            return 2

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif not args.quiet:
        print(f"README index audit: {mode} ({scope_source})")
        print(f"Candidates: {len(candidates)}  Entries: {len(entries)}  Gaps: {len(gaps)} "
              f"(error={len(errors)}, warning={len(warnings)})")
        shown = 0
        for gap in gaps:
            details = ", ".join(
                f"{key}={value}" for key, value in gap.items()
                if key not in {"type", "message", "severity"}
            )
            message = f"  [{gap['severity']}] {gap['type']}: {gap['message']}"
            if details:
                message += f" ({details})"
            print(message)
            shown += 1
            if shown >= 20:
                print("  ... (see --json or --out for the full list)")
                break
        if out_dir is not None:
            print(f"Wrote report to {out_dir}")

    if args.check:
        if errors:
            return 1
        if args.strict and warnings:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
