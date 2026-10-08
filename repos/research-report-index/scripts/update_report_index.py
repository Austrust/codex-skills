from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "language": "zh-CN",
    "index_path": "REPORT_INDEX.md",
    "updates_path": "PROJECT_UPDATES.md",
    "annotations_path": "00_project/navigation_annotations.md",
    "task_roots": ["10_tasks"],
    "task_pattern": "T[0-9][0-9][0-9]_*",
    "run_dir_name": "runs",
    "report_file": "REPORT.md",
    "manifest_file": "AUDIT_MANIFEST.json",
    "related_files": [
        "AUDIT_MANIFEST.json",
        "FIGURE_INDEX.md",
        "PROCESSING_PLAN.md",
        "QC_CHECKLIST.md",
        "COMMAND_LOG.md",
    ],
    "max_topic_chars": 180,
    "max_summary_chars": 260,
}


@dataclass
class RunEntry:
    name: str
    rel_path: str
    report_rel_path: str
    topic: str
    summary: str
    status: str
    related_links: list[tuple[str, str]]


@dataclass
class TaskEntry:
    name: str
    rel_path: str
    topic: str
    runs: list[RunEntry]


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def relpath(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def normalize_key(value: str) -> str:
    value = value.strip().strip("`").strip()
    return value.replace("\\", "/").rstrip("/")


def truncate(value: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 1)].rstrip() + "..."


def load_config(project_root: Path, config_path: Path | None) -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    path = config_path or project_root / "00_project" / "dashboard_config.json"
    if path.exists():
        loaded = json.loads(read_text(path))
        if not isinstance(loaded, dict):
            raise ValueError(f"Config must be a JSON object: {path}")
        config.update(loaded)
    return config


def load_annotations(project_root: Path, config: dict[str, Any]) -> dict[str, dict[str, str]]:
    path = project_root / config["annotations_path"]
    if not path.exists():
        return {}

    annotations: dict[str, dict[str, str]] = {}
    current_key: str | None = None
    in_code = False
    heading_pattern = re.compile(r"^##\s+(.+?)\s*$")
    kv_pattern = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*)$")

    for raw_line in read_text(path).splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue

        heading_match = heading_pattern.match(line)
        if heading_match:
            current_key = normalize_key(heading_match.group(1))
            annotations.setdefault(current_key, {})
            continue

        if current_key is None or not line or line.startswith("#"):
            continue

        kv_match = kv_pattern.match(line)
        if kv_match:
            key, value = kv_match.group(1).strip(), kv_match.group(2).strip()
            annotations[current_key][key] = value

    return annotations


def humanize_name(name: str) -> str:
    return re.sub(r"[_-]+", " ", name).strip()


def first_paragraph_from_markdown(text: str, *, max_chars: int) -> str:
    paragraphs: list[str] = []
    current: list[str] = []
    in_code = False
    metadata_prefixes = (
        "生成时间",
        "报告包",
        "审计状态",
        "复现状态",
        "科学置信度",
        "Audit status",
        "Reproducibility",
        "Scientific confidence",
        "Package validation",
    )

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue

        if not line:
            if current:
                paragraphs.append(" ".join(current))
                break
            continue

        if line.startswith("#") or line.startswith(">"):
            continue
        if line.startswith("|") or re.fullmatch(r"[-:| ]+", line):
            continue
        if any(re.match(rf"^{re.escape(prefix)}\s*[:：]", line, flags=re.IGNORECASE) for prefix in metadata_prefixes):
            continue
        if line.startswith(("-", "*")) and len(current) == 0:
            continue

        current.append(line)

    if not paragraphs and current:
        paragraphs.append(" ".join(current))

    return truncate(paragraphs[0], max_chars) if paragraphs else ""


def labelled_line_from_markdown(text: str, labels: tuple[str, ...], *, max_chars: int) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("-* ").strip()
        for label in labels:
            pattern = rf"^{re.escape(label)}\s*[:：]\s*(.+)$"
            match = re.match(pattern, line, flags=re.IGNORECASE)
            if match:
                return truncate(match.group(1), max_chars)
    return ""


def extract_task_topic(task_dir: Path, project_root: Path, annotations: dict[str, dict[str, str]], config: dict[str, Any]) -> str:
    task_key = relpath(task_dir, project_root)
    annotation = annotations.get(task_key, {})
    if annotation.get("topic"):
        return truncate(annotation["topic"], config["max_topic_chars"])

    readme = task_dir / "README.md"
    if readme.exists():
        text = read_text(readme)
        labelled = labelled_line_from_markdown(
            text,
            ("主题", "任务目的", "目的", "角色", "说明"),
            max_chars=config["max_topic_chars"],
        )
        if labelled:
            return labelled
        paragraph = first_paragraph_from_markdown(text, max_chars=config["max_topic_chars"])
        if paragraph:
            return paragraph

    return humanize_name(task_dir.name)


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(read_text(path))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def extract_report_summary(report_path: Path, config: dict[str, Any]) -> str:
    text = read_text(report_path)
    labelled = labelled_line_from_markdown(
        text,
        ("简要描述", "摘要", "Summary", "结论", "Conclusion"),
        max_chars=config["max_summary_chars"],
    )
    if labelled:
        return labelled
    return first_paragraph_from_markdown(text, max_chars=config["max_summary_chars"])


def status_from_manifest(manifest: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, label in (
        ("audit_status", "audit"),
        ("scientific_confidence", "confidence"),
        ("reproducibility", "reproducibility"),
    ):
        value = manifest.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(f"{label}: {value.strip()}")
    return "; ".join(parts)


def collect_related_links(run_dir: Path, project_root: Path, config: dict[str, Any]) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for filename in config["related_files"]:
        path = run_dir / filename
        if path.exists():
            links.append((filename, relpath(path, project_root)))
    return links


def collect_project(project_root: Path, config: dict[str, Any], annotations: dict[str, dict[str, str]]) -> list[TaskEntry]:
    tasks: list[TaskEntry] = []
    for task_root_name in config["task_roots"]:
        task_root = project_root / task_root_name
        if not task_root.exists():
            continue

        for task_dir in sorted(task_root.glob(config["task_pattern"]), key=lambda p: p.name):
            if not task_dir.is_dir():
                continue

            runs: list[RunEntry] = []
            runs_dir = task_dir / config["run_dir_name"]
            if runs_dir.exists():
                for run_dir in sorted((p for p in runs_dir.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True):
                    report_path = run_dir / config["report_file"]
                    if not report_path.exists():
                        continue

                    run_key = relpath(run_dir, project_root)
                    annotation = annotations.get(run_key, {})
                    manifest = load_manifest(run_dir / config["manifest_file"])

                    manifest_task = manifest.get("task")
                    topic = annotation.get("topic") or (manifest_task if isinstance(manifest_task, str) else "") or humanize_name(run_dir.name)
                    summary = annotation.get("summary") or extract_report_summary(report_path, config)
                    if not summary:
                        summary = topic

                    runs.append(
                        RunEntry(
                            name=run_dir.name,
                            rel_path=run_key,
                            report_rel_path=relpath(report_path, project_root),
                            topic=truncate(topic, config["max_topic_chars"]),
                            summary=truncate(summary, config["max_summary_chars"]),
                            status=status_from_manifest(manifest),
                            related_links=collect_related_links(run_dir, project_root, config),
                        )
                    )

            tasks.append(
                TaskEntry(
                    name=task_dir.name,
                    rel_path=relpath(task_dir, project_root),
                    topic=extract_task_topic(task_dir, project_root, annotations, config),
                    runs=runs,
                )
            )

    return tasks


def markdown_link(label: str, target: str) -> str:
    return f"[{label}]({target})"


def build_report_index(tasks: list[TaskEntry], config: dict[str, Any], now_text: str) -> str:
    report_count = sum(len(task.runs) for task in tasks)
    task_roots = ", ".join(f"`{root}`" for root in config["task_roots"])
    lines: list[str] = [
        "# Report Index",
        "",
        "> 自动生成的报告导航索引。不要直接手工编辑本文件；需要覆盖主题或描述时，请编辑 `00_project/navigation_annotations.md` 后重新运行 skill。",
        "",
        f"更新时间：{now_text}",
        f"扫描范围：{task_roots} 下的 `{config['run_dir_name']}/*/{config['report_file']}`",
        f"任务包数量：{len(tasks)}",
        f"报告数量：{report_count}",
        "",
        "## 使用说明",
        "",
        "- `T###` 是长期科研主题包。",
        "- `runs/YYYYMMDD_label` 是该主题下的一次具体执行、审计或报告包。",
        "- 每个 run 只暴露主题、简要描述、状态、报告链接和相关链接，避免把索引变成第二份报告。",
        "",
        "## 任务报告",
        "",
    ]

    for task in tasks:
        lines.extend(
            [
                f"## {task.name}",
                "",
                f"主题：{task.topic}",
                f"任务入口：{markdown_link(task.rel_path, task.rel_path + '/')}",
                "",
            ]
        )

        if not task.runs:
            lines.extend(["暂无 `REPORT.md` 报告。", ""])
            continue

        for run in task.runs:
            related = " / ".join(markdown_link(label, target) for label, target in run.related_links)
            lines.extend(
                [
                    f"### {run.name}",
                    "",
                    f"主题：{run.topic}",
                    f"简要描述：{run.summary}",
                ]
            )
            if run.status:
                lines.append(f"状态：{run.status}")
            lines.append(f"报告链接：{markdown_link('REPORT.md', run.report_rel_path)}")
            if related:
                lines.append(f"相关链接：{related}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def append_update_log(
    project_root: Path,
    config: dict[str, Any],
    now_text: str,
    update_summary: str,
    changed_paths: list[str],
    tasks: list[TaskEntry],
) -> None:
    updates_path = project_root / config["updates_path"]
    if updates_path.exists():
        existing = read_text(updates_path).rstrip()
    else:
        existing = "\n".join(
            [
                "# Project Updates",
                "",
                "> 每个 agent 回合追加一条批次记录。这里记录人类可读的语义摘要，不替代 git diff 或 REPORT.md。",
            ]
        )

    report_count = sum(len(task.runs) for task in tasks)
    summary_lines = [line.strip("- ").strip() for line in update_summary.splitlines() if line.strip()]
    if not summary_lines:
        summary_lines = ["本轮未提供人工摘要；仅记录 report index 自动刷新。"]

    entry: list[str] = [
        "",
        "",
        f"## {now_text} - agent update",
        "",
        "变动摘要：",
    ]
    entry.extend(f"- {line}" for line in summary_lines)

    if changed_paths:
        entry.extend(["", "受影响路径："])
        entry.extend(f"- `{path}`" for path in changed_paths)

    entry.extend(
        [
            "",
            "扫描结果：",
            f"- 任务包：{len(tasks)}",
            f"- 报告：{report_count}",
            "",
            "维护动作：",
            f"- `{config['index_path']}` refreshed",
        ]
    )

    write_text(updates_path, existing + "\n".join(entry) + "\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh a task-based research report index.")
    parser.add_argument("--project-root", default=".", help="Project root directory.")
    parser.add_argument("--config", default=None, help="Optional config JSON path.")
    parser.add_argument("--update-summary", default="", help="Human-readable summary for PROJECT_UPDATES.md.")
    parser.add_argument("--changed-path", action="append", default=[], help="Path affected by this agent turn. Can be repeated.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    project_root = Path(args.project_root).resolve()
    config_path = Path(args.config).resolve() if args.config else None
    config = load_config(project_root, config_path)
    annotations = load_annotations(project_root, config)
    tasks = collect_project(project_root, config, annotations)

    now_text = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    index_text = build_report_index(tasks, config, now_text)
    write_text(project_root / config["index_path"], index_text)
    append_update_log(project_root, config, now_text, args.update_summary, args.changed_path, tasks)

    report_count = sum(len(task.runs) for task in tasks)
    print(json.dumps({"tasks": len(tasks), "reports": report_count, "index_path": config["index_path"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
