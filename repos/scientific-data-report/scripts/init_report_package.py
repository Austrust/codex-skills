#!/usr/bin/env python3
"""Initialize an auditable scientific data-processing report package."""

from __future__ import annotations

import argparse
import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any
from report_core import report_template, manifest_template


MODES = {"formal", "exploratory", "repair", "reproduce"}
CONFIG_RELATIVE_PATH = Path("00_project") / "scientific_data_report_config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": "2.0",
    "default_language": "zh",
    "workflow": {"formal_requires_plan_confirmation": False, "prefer_task_package_runs": True},
    "report_package": {"profile": "lean"},
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def config_path(root: Path) -> Path:
    return root / CONFIG_RELATIVE_PATH


def load_project_config(root: Path, custom_path: str = "") -> tuple[dict[str, Any], Path, bool]:
    path = (root / custom_path).resolve() if custom_path else config_path(root)
    if custom_path and not path.is_file():
        raise SystemExit(f"Config not found: {path}")
    if not path.exists():
        return deepcopy(DEFAULT_CONFIG), path, False
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Project config is invalid JSON: {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise SystemExit(f"Project config root must be a JSON object: {path}")
    return deep_merge(DEFAULT_CONFIG, loaded), path, True


def init_project_config(root: Path, *, force: bool = False, custom_path: str = "") -> Path:
    path = (root / custom_path).resolve() if custom_path else config_path(root)
    if path.exists() and not force:
        print(f"Project config already exists: {path}")
        return path

    cfg = deepcopy(DEFAULT_CONFIG)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text(path, json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
    print(f"Project config written: {path}")
    return path


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:60] or "task"


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def looks_like_task_package(path: Path) -> bool:
    return (path / "README.md").exists() and ((path / "inputs").exists() or (path / "runs").exists())


def choose_output_root(args: argparse.Namespace, root: Path, config: dict[str, Any]) -> tuple[Path, str, str]:
    if args.output_root:
        return (root / args.output_root).resolve(), "custom", "--output-root was provided"
    if args.task_package:
        task_package = Path(args.task_package)
        if not task_package.is_absolute():
            task_package = root / task_package
        return task_package.resolve() / args.run_dir_name, "task_package_runs", "--task-package was provided"
    if args.cross_task_report:
        return root / ("50_reports" if (root / "50_reports").is_dir() else "reports"), "cross_task_reports", "--cross-task-report was provided"
    if config.get("workflow", {}).get("prefer_task_package_runs", True) and looks_like_task_package(root):
        return root / args.run_dir_name, "task_package_runs", "root looks like a task package"
    return root / "data_processing_reports", "data_processing_reports", "no task package or cross-task placement was specified"


def create_package(args: argparse.Namespace) -> Path:
    root = Path(args.root).resolve()
    config, cfg_path, cfg_loaded = load_project_config(root, args.config)

    language = args.language
    if language == "auto":
        language = str(config.get("default_language", "auto"))

    slug = slugify(args.slug or args.task)
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root, placement_policy, placement_reason = choose_output_root(args, root, config)
    package_dir = (root / args.package_dir).resolve() if args.package_dir else output_root / f"{timestamp}_{slug}"
    if args.package_dir and package_dir.exists():
        raise SystemExit(f"Package destination already exists; edit existing reports in place: {package_dir}")

    counter = 1
    original = package_dir
    while package_dir.exists():
        package_dir = original.with_name(f"{original.name}_{counter:02d}")
        counter += 1

    profile = args.profile or config.get("report_package", {}).get("profile", "lean")
    if profile not in {"lean", "audited"}:
        raise SystemExit("report_package.profile must be lean or audited")
    package_dir.mkdir(parents=True)
    write_text(package_dir / "REPORT.md", report_template(args.task, language, args.mode, profile))
    if profile == "audited":
        manifest = manifest_template(package_dir, args.task, args.mode)
        manifest["placement"] = {"policy": placement_policy, "reason": placement_reason}
        write_text(package_dir / "AUDIT_MANIFEST.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return package_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root. Default: current directory.")
    parser.add_argument("--task", default="", help="Short task title.")
    parser.add_argument("--slug", default="", help="Optional ASCII slug for the run directory.")
    parser.add_argument("--profile", choices=["lean", "audited"], default=None)
    parser.add_argument("--mode", choices=sorted(MODES), default="exploratory")
    parser.add_argument("--language", default="auto", help="Report language policy, such as auto, zh, en. auto uses 00_project config when available.")
    parser.add_argument("--config", default="", help="Optional existing config path, relative to root or absolute.")
    parser.add_argument("--package-dir", default="", help="Exact new package directory; no timestamp or extra nesting. Relative to root.")
    parser.add_argument("--run-dir-name", default="runs", help="Existing run-container name for task placement.")
    parser.add_argument("--output-root", default="", help="Optional report root directory.")
    parser.add_argument("--task-package", default="", help="Task package path. Writes under the selected task run container.")
    parser.add_argument("--cross-task-report", action="store_true", help="Use existing 50_reports, otherwise reports; override with --output-root.")
    parser.add_argument("--timestamp", default="", help="Optional timestamp for deterministic tests.")
    parser.add_argument("--user-preapproved", action="store_true", help="Compatibility option; record actual prior authorization in the report when relevant.")
    parser.add_argument("--init-config", action="store_true", help="Create 00_project/scientific_data_report_config.json using conservative defaults.")
    parser.add_argument("--force-config", action="store_true", help="Overwrite an existing project config when used with --init-config.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    if args.init_config:
        init_project_config(root, force=args.force_config, custom_path=args.config)
        return 0
    if not args.task:
        raise SystemExit("--task is required unless --init-config is used")
    package_dir = create_package(args)
    print(package_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
