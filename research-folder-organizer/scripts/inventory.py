#!/usr/bin/env python3
"""Read-only inventory for research-folder-organizer.

The script scans a research project folder and writes dry-run reports. It does
not move, delete, stage, commit, install, or rebuild anything.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


CONFIG_NAMES = (
    "AGENTS.md",
    "README.md",
    "README.txt",
    "ProjectWiki.md",
    "项目Wiki.md",
    ".gitignore",
    ".graphifyignore",
)

PROTECTED_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "env",
    ".conda",
    "conda-meta",
    "graphify-out",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
}

PROTECTED_EXTS = {
    ".zarr",
    ".mat",
    ".npz",
    ".npy",
    ".h5",
    ".hdf5",
    ".nc",
    ".heic",
    ".mov",
    ".mp4",
    ".avi",
    ".tif",
    ".tiff",
}

CACHE_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".ipynb_checkpoints",
    "dist",
    "build",
    "target",
    ".cache",
}

ARCHIVE_TOKENS = (
    "archive",
    "_archive",
    "backup",
    "bak",
    "old",
    "copy",
    "temp",
    "tmp",
    "trash",
    "归档",
    "旧版",
    "备份",
    "副本",
    "临时",
)

CURRENT_TOKENS = (
    "current",
    "main",
    "manuscript",
    "report",
    "README",
    "wiki",
    "当前",
    "稿件",
    "主线",
    "报告",
)

EVIDENCE_TOKENS = (
    "analysis",
    "package",
    "figures",
    "tables",
    "metrics",
    "validation",
    "evidence",
    "审计",
    "证据",
    "图表",
    "分析包",
)

REPRO_TOKENS = (
    "output",
    "outputs",
    "dist",
    "build",
    "generated",
    "export",
    "public",
    "assets",
    "输出",
    "导出",
)


@dataclass
class EntrySummary:
    path: str
    kind: str
    files: int = 0
    dirs: int = 0
    bytes: int = 0
    ext_counts: dict[str, int] | None = None
    last_modified: str | None = None
    lifecycle: str = "supporting_evidence"
    reasons: list[str] | None = None


def rel(path: Path, root: Path) -> str:
    try:
        value = path.relative_to(root)
    except ValueError:
        return str(path)
    return "." if str(value) == "." else value.as_posix()


def safe_read(path: Path, limit: int = 200_000) -> str:
    try:
        data = path.read_bytes()[:limit]
    except OSError:
        return ""
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return data.decode(encoding, errors="ignore")
        except UnicodeError:
            continue
    return ""


def load_project_config(root: Path) -> dict:
    files = {}
    for name in CONFIG_NAMES:
        path = root / name
        if path.exists() and path.is_file():
            files[name] = safe_read(path)

    readmes = sorted(root.glob("README*"))
    for path in readmes:
        if path.is_file() and path.name not in files:
            files[path.name] = safe_read(path)

    config_text = "\n".join(files.values()).lower()
    graphify_present = (root / "graphify-out").exists() or "graphify" in config_text
    venv_required = ".venv" in config_text and "python" in config_text
    has_git = (root / ".git").exists()

    ignore_patterns = []
    for name in (".gitignore", ".graphifyignore"):
        for line in files.get(name, "").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                ignore_patterns.append(stripped)

    return {
        "files_found": sorted(files),
        "has_git": has_git,
        "graphify_present": graphify_present,
        "graphify_required": False,
        "project_venv_required": venv_required,
        "ignore_patterns": ignore_patterns,
        "language": detect_language(root, files),
        "organizer_wiki_name": "整理Wiki.md" if detect_language(root, files) == "zh" else "OrganizationWiki.md",
    }


def detect_language(root: Path, files: dict[str, str]) -> str:
    sample = root.name + "\n" + "\n".join(files.keys()) + "\n" + "\n".join(v[:4000] for v in files.values())
    cjk = sum(1 for ch in sample if "\u4e00" <= ch <= "\u9fff")
    ascii_letters = sum(1 for ch in sample if ch.isascii() and ch.isalpha())
    return "zh" if cjk >= max(8, ascii_letters // 15) else "en"


def git_status(root: Path) -> dict:
    if not (root / ".git").exists():
        return {"is_repo": False, "status_short": [], "error": None}
    try:
        proc = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(root),
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
    except Exception as exc:  # pragma: no cover - defensive for unusual hosts
        return {"is_repo": True, "status_short": [], "error": str(exc)}
    return {
        "is_repo": True,
        "status_short": proc.stdout.splitlines(),
        "error": proc.stderr.strip() or None,
    }


def match_patterns(path: str, patterns: Iterable[str]) -> list[str]:
    matches = []
    normalized = path.replace("\\", "/")
    for pattern in patterns:
        p = pattern.replace("\\", "/").strip("/")
        if not p:
            continue
        if fnmatch.fnmatch(normalized, p) or fnmatch.fnmatch(normalized, p + "/*"):
            matches.append(pattern)
        elif p.endswith("/") and normalized.startswith(p.rstrip("/") + "/"):
            matches.append(pattern)
    return matches


def classify(path: str, kind: str, config: dict) -> tuple[str, list[str]]:
    lowered = path.lower()
    name = Path(path).name.lower()
    reasons: list[str] = []
    ignore_matches = match_patterns(path, config.get("ignore_patterns", []))
    if ignore_matches:
        reasons.append("matches project ignore pattern: " + ", ".join(ignore_matches[:3]))

    suffix = Path(path).suffix.lower()
    parts = set(Path(path).parts)
    if name in PROTECTED_DIR_NAMES or suffix in PROTECTED_EXTS or name.startswith("dataset"):
        reasons.append("protected scientific/system path")
        return "protected_data", reasons
    if any(part in PROTECTED_DIR_NAMES for part in parts):
        reasons.append("under protected directory")
        return "protected_data", reasons
    if name in CACHE_NAMES or any(token in lowered for token in ("__pycache__", ".cache", "cache", "tmp", "temp")):
        reasons.append("cache or temporary naming")
        return "cache_or_temp", reasons
    if any(token in lowered for token in ARCHIVE_TOKENS):
        reasons.append("archive/stale/copy naming")
        return "archive_candidate", reasons
    if any(token.lower() in lowered for token in CURRENT_TOKENS):
        reasons.append("current/mainline naming")
        return "current_mainline", reasons
    if any(token.lower() in lowered for token in REPRO_TOKENS):
        reasons.append("generated/output naming")
        return "reproducible_output", reasons
    if any(token.lower() in lowered for token in EVIDENCE_TOKENS):
        reasons.append("evidence/package naming")
        return "supporting_evidence", reasons
    if kind == "file" and suffix in {".md", ".txt", ".csv", ".py", ".ipynb", ".xlsx", ".docx", ".pptx", ".pdf"}:
        reasons.append("research document/script/table type")
        return "supporting_evidence", reasons
    reasons.append("default supporting material")
    return "supporting_evidence", reasons


def scan_tree(root: Path, config: dict) -> dict:
    top_entries: list[EntrySummary] = []
    ext_counter: Counter[str] = Counter()
    lifecycle_counter: Counter[str] = Counter()
    protected_examples: list[dict] = []
    archive_examples: list[dict] = []
    cache_examples: list[dict] = []
    total_files = 0
    total_dirs = 0
    total_bytes = 0
    errors: list[str] = []

    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if child.name == "_organizer":
            continue
        summary = summarize_entry(child, root, config)
        top_entries.append(summary)
        lifecycle_counter[summary.lifecycle] += 1
        if summary.lifecycle == "protected_data":
            protected_examples.append({"path": summary.path, "reasons": summary.reasons})
        elif summary.lifecycle == "archive_candidate":
            archive_examples.append({"path": summary.path, "reasons": summary.reasons})
        elif summary.lifecycle == "cache_or_temp":
            cache_examples.append({"path": summary.path, "reasons": summary.reasons})

    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        rel_current = rel(current_path, root)
        if rel_current.startswith("_organizer"):
            dirs[:] = []
            continue
        total_dirs += len(dirs)
        for filename in files:
            path = current_path / filename
            try:
                stat = path.stat()
            except OSError as exc:
                errors.append(f"{rel(path, root)}: {exc}")
                continue
            total_files += 1
            total_bytes += stat.st_size
            ext_counter[path.suffix.lower() or "[no extension]"] += 1

    return {
        "totals": {
            "files": total_files,
            "dirs": total_dirs,
            "bytes": total_bytes,
        },
        "top_entries": [asdict(item) for item in top_entries],
        "extension_counts": dict(ext_counter.most_common(30)),
        "lifecycle_counts": dict(lifecycle_counter),
        "protected_examples": protected_examples[:20],
        "archive_examples": archive_examples[:20],
        "cache_examples": cache_examples[:20],
        "task_readme_audit": scan_task_readmes(root),
        "errors": errors[:50],
    }


def scan_task_readmes(root: Path) -> list[dict]:
    tasks_root = root / "10_tasks"
    if not tasks_root.exists() or not tasks_root.is_dir():
        return []

    rows = []
    for task_dir in sorted(tasks_root.iterdir(), key=lambda p: p.name.lower()):
        if not task_dir.is_dir() or not task_dir.name.startswith("T"):
            continue
        readme_path = task_dir / "README.md"
        readme_text = safe_read(readme_path) if readme_path.exists() else ""
        runs_root = task_dir / "runs"
        runs = []
        if runs_root.exists() and runs_root.is_dir():
            runs = sorted([p.name for p in runs_root.iterdir() if p.is_dir()])
        documented_runs = [run for run in runs if run in readme_text]
        missing_runs = [run for run in runs if run not in readme_text]
        rows.append(
            {
                "task": rel(task_dir, root),
                "has_readme": readme_path.exists(),
                "runs": len(runs),
                "runs_documented_by_name": len(documented_runs),
                "missing_run_mentions": missing_runs[:8],
            }
        )
    return rows


def summarize_entry(path: Path, root: Path, config: dict) -> EntrySummary:
    path_rel = rel(path, root)
    lifecycle, reasons = classify(path_rel, "dir" if path.is_dir() else "file", config)
    if path.is_file():
        try:
            stat = path.stat()
            modified = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
            size = stat.st_size
        except OSError:
            modified = None
            size = 0
        return EntrySummary(
            path=path_rel,
            kind="file",
            files=1,
            dirs=0,
            bytes=size,
            ext_counts={path.suffix.lower() or "[no extension]": 1},
            last_modified=modified,
            lifecycle=lifecycle,
            reasons=reasons,
        )

    files = 0
    dirs_count = 0
    bytes_total = 0
    ext_counts: Counter[str] = Counter()
    newest = None
    for current, dirs, filenames in os.walk(path, topdown=True, followlinks=False):
        dirs_count += len(dirs)
        for filename in filenames:
            file_path = Path(current) / filename
            try:
                stat = file_path.stat()
            except OSError:
                continue
            files += 1
            bytes_total += stat.st_size
            ext_counts[file_path.suffix.lower() or "[no extension]"] += 1
            newest = stat.st_mtime if newest is None else max(newest, stat.st_mtime)
    modified = datetime.fromtimestamp(newest).isoformat(timespec="seconds") if newest else None
    return EntrySummary(
        path=path_rel,
        kind="dir",
        files=files,
        dirs=dirs_count,
        bytes=bytes_total,
        ext_counts=dict(ext_counts.most_common(12)),
        last_modified=modified,
        lifecycle=lifecycle,
        reasons=reasons,
    )


def human_size(num: int) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024.0
    return f"{num} B"


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_report(path: Path, data: dict) -> None:
    lines = []
    root = data["root"]
    scan = data["scan"]
    config = data["project_config"]
    git = data["git"]
    lines.append("# Research Folder Organizer Inventory")
    lines.append("")
    lines.append(f"- Root: `{root}`")
    lines.append(f"- Generated: `{data['generated_at']}`")
    lines.append(f"- Mode: dry-run, report-only")
    lines.append(f"- Project language: `{config['language']}`")
    lines.append(f"- Suggested organizer wiki: `{config['organizer_wiki_name']}`")
    lines.append(f"- Config files found: {', '.join(config['files_found']) or 'none'}")
    lines.append(f"- Graphify present or mentioned: `{config.get('graphify_present', False)}`")
    lines.append("- Graphify maintenance: disabled by this skill")
    lines.append(f"- Project venv required: `{config['project_venv_required']}`")
    lines.append(f"- Git repo: `{git['is_repo']}`")
    if git["status_short"]:
        lines.append(f"- Dirty worktree entries: `{len(git['status_short'])}`")
    if git.get("error"):
        lines.append(f"- Git status error: `{git['error']}`")
    lines.append("")
    lines.append("## Totals")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | ---: |")
    lines.append(f"| Files | {scan['totals']['files']} |")
    lines.append(f"| Directories | {scan['totals']['dirs']} |")
    lines.append(f"| Size | {human_size(scan['totals']['bytes'])} |")
    lines.append("")
    lines.append("## Top-Level Entries")
    lines.append("")
    lines.append("| Path | Lifecycle | Files | Size | Last Modified | Reasons |")
    lines.append("| --- | --- | ---: | ---: | --- | --- |")
    for entry in scan["top_entries"]:
        reasons = "; ".join(entry.get("reasons") or [])
        lines.append(
            f"| `{entry['path']}` | `{entry['lifecycle']}` | {entry['files']} | "
            f"{human_size(entry['bytes'])} | {entry.get('last_modified') or ''} | {reasons} |"
        )
    lines.append("")
    lines.append("## Task README Run Index Audit")
    lines.append("")
    task_rows = scan.get("task_readme_audit") or []
    if task_rows:
        lines.append("| Task | README | Runs | Runs Mentioned In README | Missing Run Mentions |")
        lines.append("| --- | --- | ---: | ---: | --- |")
        for row in task_rows:
            missing = ", ".join(f"`{name}`" for name in row["missing_run_mentions"]) or ""
            if len(row["missing_run_mentions"]) >= 8:
                missing += ", ..."
            lines.append(
                f"| `{row['task']}` | `{row['has_readme']}` | {row['runs']} | "
                f"{row['runs_documented_by_name']} | {missing} |"
            )
    else:
        lines.append("- No `10_tasks/T###` task folders found.")
    lines.append("")
    lines.append("## Extension Counts")
    lines.append("")
    lines.append("| Extension | Files |")
    lines.append("| --- | ---: |")
    for ext, count in scan["extension_counts"].items():
        lines.append(f"| `{ext}` | {count} |")
    lines.append("")
    lines.append("## Notable Candidates")
    lines.append("")
    lines.append("### Protected examples")
    for item in scan["protected_examples"] or [{"path": "none", "reasons": []}]:
        lines.append(f"- `{item['path']}`: {'; '.join(item.get('reasons') or [])}")
    lines.append("")
    lines.append("### Archive candidates")
    for item in scan["archive_examples"] or [{"path": "none", "reasons": []}]:
        lines.append(f"- `{item['path']}`: {'; '.join(item.get('reasons') or [])}")
    lines.append("")
    lines.append("### Cache/temp candidates")
    for item in scan["cache_examples"] or [{"path": "none", "reasons": []}]:
        lines.append(f"- `{item['path']}`: {'; '.join(item.get('reasons') or [])}")
    lines.append("")
    lines.append("## Git Status Snapshot")
    lines.append("")
    if git["status_short"]:
        lines.extend(f"- `{line}`" for line in git["status_short"][:80])
        if len(git["status_short"]) > 80:
            lines.append(f"- ... {len(git['status_short']) - 80} more")
    else:
        lines.append("- Clean or not a Git repo.")
    lines.append("")
    lines.append("## Safety Note")
    lines.append("")
    lines.append("This report is a dry-run inventory. It did not move, delete, stage, commit, install, or rebuild anything.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_batches(path: Path, data: dict) -> None:
    config = data["project_config"]
    scan = data["scan"]
    lines = [
        "# Proposed Organizer Batches",
        "",
        "All batches require explicit user approval before execution.",
        "",
        "## Batch 1: Entry Points And Indexes",
        "",
        "- Create or update each `10_tasks/T###_*/README.md` as the canonical task landing page.",
        "- Each task README should explain the task in low-context prose and include a short entry for every `runs/*` folder.",
        f"- Create or update organizer wiki: `{config['organizer_wiki_name']}`.",
        "- Keep existing project README/Wiki untouched unless separately approved.",
        "- Link this inventory and future execution records from `_organizer/README.md`.",
        "",
        "## Batch 2: Archive Review",
        "",
        "- New archive moves should target `_archive/YYYY-MM-DD_description/`.",
        "- Existing `99_旧版归档_*` or similar archives should only be consolidated after separate approval.",
    ]
    archive_examples = scan["archive_examples"]
    if archive_examples:
        lines.append("- Review these candidates first:")
        lines.extend(f"  - `{item['path']}`" for item in archive_examples[:12])
    else:
        lines.append("- No top-level archive candidates found by name.")

    lines.extend(
        [
            "",
            "## Batch 3: Cache And Temporary Material",
            "",
            "- Report cache/temp paths first; do not delete by default.",
        ]
    )
    cache_examples = scan["cache_examples"]
    if cache_examples:
        lines.extend(f"- `{item['path']}`" for item in cache_examples[:12])
    else:
        lines.append("- No top-level cache/temp candidates found by name.")

    lines.extend(
        [
            "",
            "## Batch 4: Git",
            "",
            "- Stage only organizer-created files or approved archive moves.",
            "- Do not include unrelated dirty worktree changes.",
            "- Do not update or stage graphify outputs as part of this organizer workflow.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_inventory(root: Path) -> dict:
    config = load_project_config(root)
    return {
        "root": str(root),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project_config": config,
        "git": git_status(root),
        "scan": scan_tree(root, config),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only research project folder inventory.")
    parser.add_argument("--root", required=True, help="Project root to scan.")
    parser.add_argument("--out", help="Output directory. Defaults to <root>/_organizer.")
    parser.add_argument("--format", choices=("json", "md", "both"), default="both")
    parser.add_argument("--dry-run", action="store_true", help="Required. The script is report-only.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.dry_run:
        raise SystemExit("inventory.py only supports --dry-run in this version.")
    root = Path(args.root).resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Root is not a directory: {root}")
    out = Path(args.out).resolve() if args.out else root / "_organizer"
    out.mkdir(parents=True, exist_ok=True)

    data = build_inventory(root)
    if args.format in ("json", "both"):
        write_json(out / "inventory.json", data)
    if args.format in ("md", "both"):
        write_report(out / "inventory_report.md", data)
        write_batches(out / "proposed_batches.md", data)
    print(f"Wrote dry-run inventory to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
