#!/usr/bin/env python3
"""Read-only audit for README-based research project navigation."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Iterable


KEY_BOUNDARIES = {
    "00_project",
    "01_sources",
    "10_tasks",
    "20_methods",
    "30_literature",
    "40_reference",
    "50_reports",
    "70_manuscript",
    "80_presentations",
    "90_archive",
}

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
    "outputs",
    "intermediate",
}

STATUS_RE = re.compile(r"^[ MADRCU?!]{2}\s+(.+)$")
TASK_RE = re.compile(r"^T\d{3}_.+")
RUN_RE = re.compile(r"^\d{8}.*")
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def rel(path: Path, root: Path) -> str:
    try:
        value = path.relative_to(root)
    except ValueError:
        return str(path)
    return "." if str(value) == "." else value.as_posix()


def safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return ""


def git_changed_paths(root: Path) -> list[Path]:
    proc = subprocess.run(
        ["git", "status", "--short"],
        cwd=str(root),
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )
    if proc.returncode != 0:
        return []
    paths: list[Path] = []
    for line in proc.stdout.splitlines():
        match = STATUS_RE.match(line)
        if not match:
            continue
        raw = match.group(1)
        if " -> " in raw:
            raw = raw.split(" -> ", 1)[1]
        raw = raw.strip('"')
        if raw:
            paths.append(root / raw)
    return paths


def is_task_dir(path: Path, root: Path) -> bool:
    parts = path.relative_to(root).parts if path == root or root in path.parents else ()
    return len(parts) == 2 and parts[0] == "10_tasks" and TASK_RE.match(parts[1]) is not None


def is_run_dir(path: Path, root: Path) -> bool:
    if not (path == root or root in path.parents):
        return False
    parts = path.relative_to(root).parts
    return (
        len(parts) == 4
        and parts[0] == "10_tasks"
        and TASK_RE.match(parts[1]) is not None
        and parts[2] == "runs"
        and RUN_RE.match(parts[3]) is not None
    )


def is_stable_dir(path: Path, root: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    if not (path == root or root in path.parents):
        return False
    parts = path.relative_to(root).parts
    if not parts:
        return True
    if any(part in SKIP_PARTS for part in parts):
        return False
    if len(parts) == 1 and parts[0] in KEY_BOUNDARIES:
        return True
    if is_task_dir(path, root) or is_run_dir(path, root):
        return True
    if len(parts) == 2 and parts[0] in KEY_BOUNDARIES - {"10_tasks"}:
        return True
    return False


def nearest_existing_dir(path: Path) -> Path | None:
    current = path if path.is_dir() else path.parent
    while current != current.parent:
        if current.exists() and current.is_dir():
            return current
        current = current.parent
    return None


def affected_stable_dirs(root: Path, paths: Iterable[Path]) -> set[Path]:
    affected: set[Path] = set()
    for input_path in paths:
        current = nearest_existing_dir(input_path)
        if current is None:
            continue
        if not (current == root or root in current.parents):
            continue
        rel_parts = current.relative_to(root).parts
        candidates = [current]
        if len(rel_parts) >= 2 and rel_parts[0] == "10_tasks":
            candidates.append(root / "10_tasks" / rel_parts[1])
        if len(rel_parts) >= 4 and rel_parts[0] == "10_tasks" and rel_parts[2] == "runs":
            candidates.append(root / "10_tasks" / rel_parts[1] / "runs" / rel_parts[3])
        if rel_parts:
            candidates.append(root / rel_parts[0])
        for candidate in candidates:
            if is_stable_dir(candidate, root):
                affected.add(candidate)
    return affected


def all_stable_dirs(root: Path) -> set[Path]:
    stable: set[Path] = {root}
    for path in root.rglob("*"):
        if path.is_dir() and is_stable_dir(path, root):
            stable.add(path)
    return stable


def ancestor_chain(path: Path, root: Path) -> list[Path]:
    chain: list[Path] = []
    current = path.parent
    while current != root.parent and (current == root or root in current.parents):
        chain.append(current)
        if current == root:
            break
        current = current.parent
    return chain


def has_child_reference(readme_text: str, child: Path) -> bool:
    child_name = child.name
    child_link = child_name + "/"
    return child_name in readme_text or child_link in readme_text


def audit_parent_links(root: Path, stable_dirs: Iterable[Path]) -> list[dict]:
    gaps: list[dict] = []
    for child in sorted(stable_dirs):
        if child == root:
            continue
        for parent in ancestor_chain(child, root):
            readme = parent / "README.md"
            if not readme.exists():
                continue
            direct_child = child
            while direct_child.parent != parent and direct_child.parent != direct_child:
                direct_child = direct_child.parent
            if direct_child == parent or not is_stable_dir(direct_child, root):
                continue
            text = safe_read(readme)
            if not has_child_reference(text, direct_child):
                gaps.append(
                    {
                        "type": "missing_parent_link",
                        "readme": rel(readme, root),
                        "child": rel(direct_child, root),
                        "message": "Parent README does not mention direct stable child.",
                    }
                )
            break
    return gaps


def audit_missing_readmes(root: Path, stable_dirs: Iterable[Path]) -> list[dict]:
    gaps: list[dict] = []
    for path in sorted(stable_dirs):
        readme = path / "README.md"
        if not readme.exists():
            gaps.append(
                {
                    "type": "missing_readme",
                    "folder": rel(path, root),
                    "message": "Stable folder has no README.md.",
                }
            )
    return gaps


def task_dir_for_run(run_dir: Path, root: Path) -> Path | None:
    if not is_run_dir(run_dir, root):
        return None
    parts = run_dir.relative_to(root).parts
    return root / "10_tasks" / parts[1]


def audit_run_entries(root: Path, stable_dirs: Iterable[Path]) -> list[dict]:
    task_dirs: set[Path] = set()
    for path in stable_dirs:
        if is_task_dir(path, root):
            task_dirs.add(path)
        run_task = task_dir_for_run(path, root)
        if run_task:
            task_dirs.add(run_task)

    gaps: list[dict] = []
    for task_dir in sorted(task_dirs):
        readme = task_dir / "README.md"
        text = safe_read(readme)
        runs_root = task_dir / "runs"
        if not runs_root.exists():
            continue
        for run in sorted([p for p in runs_root.iterdir() if p.is_dir()]):
            if run.name not in text:
                gaps.append(
                    {
                        "type": "missing_run_entry",
                        "task_readme": rel(readme, root),
                        "run": rel(run, root),
                        "message": "Task README does not mention this run folder by name.",
                    }
                )
    return gaps


def audit_stale_links(root: Path, stable_dirs: Iterable[Path]) -> list[dict]:
    gaps: list[dict] = []
    readmes = {path / "README.md" for path in stable_dirs if (path / "README.md").exists()}
    for readme in sorted(readmes):
        text = safe_read(readme)
        for match in LINK_RE.finditer(text):
            target = match.group(1).strip()
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            target = target.split("#", 1)[0]
            if not target:
                continue
            target_path = (readme.parent / target).resolve()
            try:
                target_path.relative_to(root.resolve())
            except ValueError:
                continue
            if not target_path.exists():
                gaps.append(
                    {
                        "type": "possibly_stale_entry",
                        "readme": rel(readme, root),
                        "target": target,
                        "message": "README link target does not exist.",
                    }
                )
    return gaps


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, data: dict) -> None:
    lines = [
        "# README Index Audit",
        "",
        f"- Generated: `{data['generated_at']}`",
        f"- Project root: `{data['project_root']}`",
        f"- Mode: `{data['mode']}`",
        "",
        "## Scope",
        "",
    ]
    if data["input_paths"]:
        lines.extend(f"- `{item}`" for item in data["input_paths"])
    else:
        lines.append("- No explicit paths.")
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
                details = ", ".join(f"{key}=`{value}`" for key, value in item.items() if key not in {"type", "message"})
                lines.append(f"- {item['message']} {details}")
            lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit README-based research project navigation.")
    parser.add_argument("--project-root", default=".", help="Project root. Defaults to current directory.")
    parser.add_argument("--paths", nargs="*", help="Changed paths to audit. Defaults to git status paths.")
    parser.add_argument("--full", action="store_true", help="Audit the whole project instead of changed paths.")
    parser.add_argument("--out", default=None, help="Output directory. Defaults to <project-root>/_organizer.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.project_root).resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Project root does not exist: {root}")

    if args.full:
        mode = "full"
        input_paths: list[Path] = []
        stable_dirs = all_stable_dirs(root)
    else:
        mode = "paths" if args.paths else "git_status"
        input_paths = [Path(item) for item in args.paths] if args.paths else git_changed_paths(root)
        input_paths = [(path if path.is_absolute() else root / path).resolve() for path in input_paths]
        if not input_paths:
            raise SystemExit("No changed paths found. Pass --paths or --full.")
        stable_dirs = affected_stable_dirs(root, input_paths)

    gaps: list[dict] = []
    gaps.extend(audit_missing_readmes(root, stable_dirs))
    gaps.extend(audit_parent_links(root, stable_dirs))
    gaps.extend(audit_run_entries(root, stable_dirs))
    gaps.extend(audit_stale_links(root, stable_dirs))

    out_dir = Path(args.out).resolve() if args.out else root / "_organizer"
    out_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project_root": str(root),
        "mode": mode,
        "input_paths": [rel(path, root) if path.exists() or root in path.parents else str(path) for path in input_paths],
        "stable_dirs": [rel(path, root) for path in sorted(stable_dirs)],
        "gaps": gaps,
    }
    write_json(out_dir / "readme_index_audit.json", data)
    write_markdown(out_dir / "readme_index_audit.md", data)
    print(f"Wrote README index audit to {out_dir}")
    print(f"Gaps: {len(gaps)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
