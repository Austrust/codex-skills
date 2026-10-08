#!/usr/bin/env python3
"""Initialize an auditable scientific data-processing report package."""

from __future__ import annotations

import argparse
import json
import platform
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


MODES = {"formal", "exploratory", "repair", "reproduce"}
CONFIG_RELATIVE_PATH = Path("00_project") / "scientific_data_report_config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": "1.0",
    "skill": "scientific-data-report",
    "default_language": "zh",
    "report_style": {
        "reader_orientation": "required",
        "context_policy": "minimal_but_self_contained",
        "technical_id_policy": "technical_ids_must_have_plain_language_labels",
        "report_detail": "summary_in_report_full_audit_in_sidecars",
        "figure_caption_detail": "compact_in_report_complete_in_figure_index",
    },
    "workflow": {
        "formal_requires_plan_confirmation": True,
        "raw_data_read_only": True,
        "prefer_task_package_runs": True,
    },
    "report_package": {
        "required_files": [
            "PROCESSING_PLAN.md",
            "REPORT.md",
            "AUDIT_MANIFEST.json",
            "COMMAND_LOG.md",
            "QC_CHECKLIST.md",
            "FIGURE_INDEX.md",
        ],
        "required_dirs": ["outputs", "figures", "tables", "logs"],
    },
    "reader_orientation_prompts": {
        "project_problem": "用一句话说明本处理属于哪个研究问题。",
        "dataset_input_family": "用一句话说明本次使用的数据族、实验/仿真来源或报告包来源，不要只写路径。",
        "processing_goal": "用一句话说明本次处理要生成、修正或验证什么。",
        "terms": "列出报告后文会重复使用、但读者可能不知道的缩写、变量、step ID 或标签。",
    },
    "claims_boundary": {
        "separate_allowed_unsupported_external": True,
        "avoid_mechanism_upgrade_without_evidence_chain": True,
    },
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


def load_project_config(root: Path) -> tuple[dict[str, Any], Path, bool]:
    path = config_path(root)
    if not path.exists():
        return deepcopy(DEFAULT_CONFIG), path, False
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Project config is invalid JSON: {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise SystemExit(f"Project config root must be a JSON object: {path}")
    return deep_merge(DEFAULT_CONFIG, loaded), path, True


def prompt_default(prompt: str, default: Any) -> Any:
    if not hasattr(__import__("sys"), "stdin") or not __import__("sys").stdin.isatty():
        return default
    raw = input(f"{prompt} [{default}]: ").strip()
    return raw if raw else default


def prompt_bool(prompt: str, default: bool) -> bool:
    default_text = "yes" if default else "no"
    if not hasattr(__import__("sys"), "stdin") or not __import__("sys").stdin.isatty():
        return default
    raw = input(f"{prompt} [{default_text}]: ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes", "true", "1", "是", "对"}


def init_project_config(root: Path, *, force: bool = False) -> Path:
    path = config_path(root)
    if path.exists() and not force:
        print(f"Project config already exists: {path}")
        return path

    cfg = deepcopy(DEFAULT_CONFIG)
    cfg["default_language"] = str(prompt_default("Default report language (zh/en/auto)", cfg["default_language"]))
    cfg["report_style"]["context_policy"] = str(
        prompt_default("REPORT.md context policy", cfg["report_style"]["context_policy"])
    )
    cfg["report_style"]["technical_id_policy"] = str(
        prompt_default("Technical ID policy", cfg["report_style"]["technical_id_policy"])
    )
    cfg["workflow"]["formal_requires_plan_confirmation"] = prompt_bool(
        "Formal mode requires plan confirmation", cfg["workflow"]["formal_requires_plan_confirmation"]
    )
    cfg["workflow"]["prefer_task_package_runs"] = prompt_bool(
        "Prefer task-package runs placement", cfg["workflow"]["prefer_task_package_runs"]
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    write_text(path, json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
    print(f"Project config written: {path}")
    return path


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:60] or "task"


def initial_status(mode: str) -> str:
    if mode == "formal":
        return "blocked"
    if mode == "exploratory":
        return "exploratory"
    return "partial"


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def is_zh(language: str) -> bool:
    return language.lower().startswith("zh")


def manifest_template(
    package_dir: Path,
    task: str,
    slug: str,
    mode: str,
    language: str,
    user_preapproved: bool,
    config_file: Path,
    config_loaded: bool,
    config: dict[str, Any],
) -> dict[str, Any]:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    return {
        "schema_version": "1.0",
        "generated_at": now,
        "task": {
            "title": task,
            "slug": slug,
            "mode": mode,
        },
        "language": language,
        "project_config": {
            "path": str(config_file),
            "loaded": config_loaded,
            "default_language": config.get("default_language", "auto"),
            "report_style": config.get("report_style", {}),
            "workflow": config.get("workflow", {}),
        },
        "audit_status": initial_status(mode),
        "reproducibility": "not_assessed",
        "scientific_confidence": "not_assessed",
        "report_package_root": str(package_dir.resolve()),
        "placement": {
            "policy": "task_package_runs | cross_task_50_reports | data_processing_reports | custom",
            "reason": "",
        },
        "plan": {
            "required": True,
            "approved_by_user": False,
            "user_preapproved": user_preapproved,
            "approval_evidence": "",
        },
        "blockers": [
            "Draft package initialized; fill provenance, steps, outputs, QC, and execution evidence before final delivery."
        ],
        "inputs": [],
        "steps": [],
        "outputs": [],
        "figures": [],
        "environment": {
            "working_directory": str(Path.cwd().resolve()),
            "os": platform.platform(),
            "python": platform.python_version(),
            "packages": {},
            "git_repo": None,
            "git_commit": "",
            "git_dirty": None,
            "execution_time": "",
            "random_seed": "",
        },
        "code_artifacts": [],
        "review_targets": [],
        "claims": {
            "allowed": [],
            "not_supported": [],
            "requiring_external_evidence": [],
        },
    }


def plan_template(task: str, mode: str, user_preapproved: bool, language: str) -> str:
    approval = "yes" if user_preapproved else "no"
    if is_zh(language):
        approval_zh = "是" if user_preapproved else "否"
        return f"""# 处理计划

任务：{task}
模式：{mode}
用户是否预先批准执行：{approval_zh}

## 目标

TODO：说明本次科学/数据处理目标，以及输出将用于探索、图件、表格、报告、稿件或审计中的哪一类用途。

## 计划输入

| ID | 路径 | 角色 | 预期格式 | 必要元数据 | 指纹方案 |
| --- | --- | --- | --- | --- | --- |
| TODO | TODO | raw_data | TODO | 单位、形状、采样/尺度 | sha256 或 fallback |

## 计划关键步骤

| Step ID | 目的 | 方法/算法 | 参数 | 方法依据 | 假设 | 风险 | 验证 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| step_01 | TODO | TODO | TODO | TODO | TODO | TODO | TODO |

## 计划输出

| Output ID | 路径 | 角色 | 来源 | 需要复核什么 |
| --- | --- | --- | --- | --- |
| TODO | TODO | figure/table/data/statistic | TODO | TODO |

## 阻断或降级条件

- TODO：缺少原始数据 provenance、单位、尺度、代码版本、参数、执行证据或其他关键元数据。

## 批准状态

- Formal 工作必须等待用户确认，除非 `user_preapproved` 为 true。
- 批准证据：TODO
"""
    return f"""# Processing Plan

Task: {task}
Mode: {mode}
User preapproved execution: {approval}

## Objective

TODO: State the scientific/data-processing objective and intended use of the outputs.

## Planned Inputs

| ID | Path | Role | Expected format | Required metadata | Fingerprint plan |
| --- | --- | --- | --- | --- | --- |
| TODO | TODO | raw_data | TODO | units, shape, sampling/scale | sha256 or fallback |

## Planned Key Steps

| Step ID | Purpose | Method/algorithm | Parameters | Method basis | Assumptions | Risks | Verification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| step_01 | TODO | TODO | TODO | TODO | TODO | TODO | TODO |

## Planned Outputs

| Output ID | Path | Role | Derived from | Review need |
| --- | --- | --- | --- | --- |
| TODO | TODO | figure/table/data/statistic | TODO | TODO |

## Blocking Or Downgrade Conditions

- TODO: Missing raw data provenance, units, scale, code version, parameters, execution evidence, or other critical metadata.

## Approval

- Formal work must wait for user confirmation unless `user_preapproved` is true.
- Approval evidence: TODO
"""


def report_template(task: str, language: str) -> str:
    if is_zh(language):
        return f"""# Scientific Data Processing Report

Task: {task}

Audit status: TODO
Reproducibility: TODO
Scientific confidence: TODO

## 读者定位

- 项目/问题：TODO：一句话说明本处理属于哪个研究问题，不要假设读者知道本次 run 的内部上下文。
- 数据/输入族：TODO：一句话说明本次使用的数据族、实验/仿真来源或报告包来源，不要只写路径或缩写。
- 处理目标：TODO：一句话说明本次处理要生成、修正或验证什么。
- 后文术语：TODO：定义报告后文会重复使用、但读者可能不知道的 ID、缩写、变量、step label 或 output label。

## 处理摘要

TODO：用一小段说明处理了什么、产出了什么、状态是 final/partial/exploratory/blocked 中哪一种。不要出现未解释的文件名、变量名或上一轮上下文。

## 输入

| ID | 读者标签 | 路径 | 角色 | 为什么与本次处理有关 | Provenance status |
| --- | --- | --- | --- | --- | --- |
| TODO | 易懂名称 | TODO | raw_data/config/metadata | TODO | fingerprinted / fallback / missing |

## 处理流程

| Step ID | 读者标签 | 做了什么 | 关键参数 | 证据 | 验证 |
| --- | --- | --- | --- | --- | --- |
| step_01 | 易懂步骤名 | TODO | TODO | executed_this_session / existing_file / inferred_from_code / gui_manual / user_provided | TODO |

## 输出

| Output ID | 读者标签 | 路径 | 类型 | 来源 | 状态 / 用途 |
| --- | --- | --- | --- | --- | --- |
| TODO | 易懂输出名 | TODO | figure/table/data/statistic | input labels + step labels | exploratory/final/blocked |

## 关键图件

TODO：只嵌入或链接理解结果必需的图。这里用读者不打开 `FIGURE_INDEX.md` 也能理解的一句话图注；完整图件元数据放入 `FIGURE_INDEX.md` 和 `AUDIT_MANIFEST.json`。

```text
Figure 1. TODO：用普通语言说明图中结果；来源 input/step 标签；关键单位/尺度；必要 caveat。
```

## QC 与复核重点

- TODO：单位/坐标/尺度/标定状态，一句话。
- TODO：滤波/统计/阈值/敏感性状态，一句话。
- TODO：3-5 个最高优先级人工复核点、blocker 或降级原因。

## Claims Boundary

Allowed by this processing: TODO

Not supported by this processing: TODO

Requires external evidence: TODO

## Reproduction

TODO：精确命令、脚本/Notebook/软件路径、工作目录、环境和预期输出。如果不可复现，说明原因。

## 详细审计文件

- `AUDIT_MANIFEST.json`：provenance、指纹、step lineage、环境、输出和 claims。
- `COMMAND_LOG.md`：只记录已执行命令和手工操作。
- `QC_CHECKLIST.md`：完整科学与图件级 QC 清单。
- `FIGURE_INDEX.md`：完整图注和 derivation metadata。
"""
    return f"""# Scientific Data Processing Report

Task: {task}

Audit status: TODO
Reproducibility: TODO
Scientific confidence: TODO

## Reader Orientation

- Project/problem: TODO: one sentence understandable without prior run context.
- Dataset/input family: TODO: one sentence naming the data in plain language, not only a path or acronym.
- Processing goal: TODO: one sentence explaining what this run tries to produce or verify.
- Terms used below: TODO: define any IDs, abbreviations, variables, or labels that are not obvious.

## Processing Summary

TODO: In one short paragraph, state what was processed, what was produced, and whether the result is final, partial, exploratory, or blocked. Avoid unexplained filenames or prior-context references.

## Inputs

| ID | Reader label | Path | Role | Why it matters here | Provenance status |
| --- | --- | --- | --- | --- | --- |
| TODO | Plain-language name | TODO | raw_data/config/metadata | TODO | fingerprinted / fallback / missing |

## Processing Flow

| Step ID | Reader label | What happened | Key parameters | Evidence | Verification |
| --- | --- | --- | --- | --- | --- |
| step_01 | Plain-language step name | TODO | TODO | executed_this_session / existing_file / inferred_from_code / gui_manual / user_provided | TODO |

## Outputs

| Output ID | Reader label | Path | Type | Derived from | Status / use |
| --- | --- | --- | --- | --- | --- |
| TODO | Plain-language output name | TODO | figure/table/data/statistic | input labels + step labels | exploratory/final/blocked |

## Key Figures

TODO: Embed or link only figures needed to follow the result. Use one-sentence captions that are understandable without opening `FIGURE_INDEX.md`; keep full figure metadata in `FIGURE_INDEX.md` and `AUDIT_MANIFEST.json`.

```text
Figure 1. TODO: Plain-language finding; source input/step labels; key unit/scale; one caveat if needed.
```

## QC And Review Targets

- TODO: Units/coordinates/scale/calibration status in one line.
- TODO: Filters/statistics/thresholds/sensitivity status in one line.
- TODO: 3-5 highest-priority manual review targets, blockers, or downgrade reasons.

## Claims Boundary

Allowed by this processing: TODO

Not supported by this processing: TODO

Requires external evidence: TODO

## Reproduction

TODO: Exact command/script/notebook/software path, working directory, environment, and expected outputs. If not reproducible, explain why.

## Detailed Audit Files

- `AUDIT_MANIFEST.json`: provenance, fingerprints, step lineage, environment, outputs, and claims.
- `COMMAND_LOG.md`: executed commands and manual actions only.
- `QC_CHECKLIST.md`: full scientific and figure-level review checklist.
- `FIGURE_INDEX.md`: full figure captions and derivation metadata.
"""


def command_log_template(language: str) -> str:
    if is_zh(language):
        return """# Command Log

只记录实际执行证据。不要把推断出的流程描述放在这里。

| Time | Working directory | Command/action | Evidence type | Exit/status | Key output |
| --- | --- | --- | --- | --- | --- |
| TODO | TODO | TODO | executed_this_session / existing_file / inferred_from_code / gui_manual / user_provided | TODO | TODO |

## 失败与修正

TODO
"""
    return """# Command Log

Record actual executed evidence only. Do not place inferred workflow descriptions here.

| Time | Working directory | Command/action | Evidence type | Exit/status | Key output |
| --- | --- | --- | --- | --- | --- |
| TODO | TODO | TODO | executed_this_session / existing_file / inferred_from_code / gui_manual / user_provided | TODO | TODO |

## Failures And Corrections

TODO
"""


def qc_template(language: str) -> str:
    if is_zh(language):
        return """# QC Checklist

## Provenance 与可复现性

- [ ] 原始输入有路径和 SHA256 或 documented fallback fingerprint。
- [ ] 代码 artifact 和环境已记录。
- [ ] 命令/手工操作已按 evidence type 记录。
- [ ] 输出可追溯到 input IDs 和 step IDs。
- [ ] 复核相关图件已列入 FIGURE_INDEX.md，并在 REPORT.md 中嵌入或链接。
- [ ] 每张图都有数据来源、step IDs、参数、单位/尺度和 caveat。
- [ ] 提供 reproduction entry，或明确降级。

## 科学检查

- [ ] 单位、坐标、尺度、标定和采样已检查。
- [ ] 滤波/平滑/插值/重采样选择有方法依据。
- [ ] 阈值/默认参数已说明依据。
- [ ] 离群值和缺失数据策略已记录。
- [ ] 拟合/统计假设已说明。
- [ ] 敏感性检查已执行，或标记 `not_assessed` 并说明原因。
- [ ] 物理/统计合理性已评估。
- [ ] 图件坐标轴、单位、colorbar、legend、注释、裁剪、归一化和图注已检查。
- [ ] 已说明什么情况会使结果失效。

## Claims Boundary

- [ ] 允许主张与不支持主张已分开。
- [ ] 需要外部证据的主张已列出。
- [ ] Formal 输出列出 3-5 个最高优先级人工复核点。

## Blockers

TODO：列出 blocker；若无 blocker，说明已检查的 attack surfaces。
"""
    return """# QC Checklist

## Provenance And Reproducibility

- [ ] Raw inputs have paths and fingerprints or documented fallback fingerprints.
- [ ] Code artifacts and environment are recorded.
- [ ] Commands/manual actions are recorded with evidence type.
- [ ] Outputs trace to input IDs and step IDs.
- [ ] Review-relevant figures are listed in FIGURE_INDEX.md and embedded or linked in REPORT.md.
- [ ] Every figure has a caption with data source, step IDs, parameters, units/scale, and caveats.
- [ ] A reproduction entry or explicit downgrade is provided.

## Scientific Checks

- [ ] Units, coordinates, scale, calibration, and sampling are checked.
- [ ] Filtering/smoothing/interpolation/resampling choices have method basis.
- [ ] Thresholds/default parameters are justified.
- [ ] Outlier and missing-data policies are documented.
- [ ] Fitting/statistics assumptions are stated.
- [ ] Sensitivity checks are performed or marked `not_assessed` with reason.
- [ ] Physical/statistical plausibility is assessed.
- [ ] Figure axes, units, colorbars, legends, annotations, cropping, normalization, and captions are checked.
- [ ] What would invalidate the result is stated.

## Claims Boundary

- [ ] Allowed claims are separated from unsupported claims.
- [ ] Claims requiring external evidence are listed.
- [ ] Formal outputs have 3-5 manual review targets.

## Blockers

TODO: List blockers, or state that no blockers remain and identify checked attack surfaces.
"""


def figure_index_template(language: str) -> str:
    if is_zh(language):
        return """# Figure Index

| Figure ID | Path | Caption | Derived from inputs | Derived from steps | Evidence type | Status | Review notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TODO | figures/TODO.png | TODO：图中显示什么、数据来源、step IDs、参数、单位/尺度、caveat | TODO | TODO | executed_this_session / existing_file / inferred_from_code | exploratory/final | TODO |
"""
    return """# Figure Index

| Figure ID | Path | Caption | Derived from inputs | Derived from steps | Evidence type | Status | Review notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TODO | figures/TODO.png | TODO: what is shown, source data, step IDs, parameters, units/scale, caveat | TODO | TODO | executed_this_session / existing_file / inferred_from_code | exploratory/final | TODO |
"""


def looks_like_task_package(path: Path) -> bool:
    return (path / "README.md").exists() and ((path / "inputs").exists() or (path / "runs").exists())


def choose_output_root(args: argparse.Namespace, root: Path, config: dict[str, Any]) -> tuple[Path, str, str]:
    if args.output_root:
        return Path(args.output_root).resolve(), "custom", "--output-root was provided"
    if args.task_package:
        task_package = Path(args.task_package)
        if not task_package.is_absolute():
            task_package = root / task_package
        return task_package.resolve() / "runs", "task_package_runs", "--task-package was provided"
    if args.cross_task_report:
        return root / "50_reports", "cross_task_50_reports", "--cross-task-report was provided"
    if config.get("workflow", {}).get("prefer_task_package_runs", True) and looks_like_task_package(root):
        return root / "runs", "task_package_runs", "root looks like a task package"
    return root / "data_processing_reports", "data_processing_reports", "no task package or cross-task placement was specified"


def create_package(args: argparse.Namespace) -> Path:
    root = Path(args.root).resolve()
    config, cfg_path, cfg_loaded = load_project_config(root)
    if not cfg_loaded and (root / "00_project").exists():
        cfg_path = init_project_config(root)
        config, cfg_path, cfg_loaded = load_project_config(root)

    language = args.language
    if language == "auto":
        language = str(config.get("default_language", "auto"))

    slug = slugify(args.slug or args.task)
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root, placement_policy, placement_reason = choose_output_root(args, root, config)
    package_dir = output_root / f"{timestamp}_{slug}"

    counter = 1
    original = package_dir
    while package_dir.exists():
        package_dir = original.with_name(f"{original.name}_{counter:02d}")
        counter += 1

    package_dir.mkdir(parents=True)
    for name in config.get("report_package", {}).get("required_dirs", ["outputs", "figures", "tables", "logs"]):
        (package_dir / name).mkdir()

    manifest = manifest_template(
        package_dir,
        args.task,
        slug,
        args.mode,
        language,
        args.user_preapproved,
        cfg_path,
        cfg_loaded,
        config,
    )
    manifest["placement"]["policy"] = placement_policy
    manifest["placement"]["reason"] = placement_reason
    write_text(package_dir / "PROCESSING_PLAN.md", plan_template(args.task, args.mode, args.user_preapproved, language))
    write_text(package_dir / "REPORT.md", report_template(args.task, language))
    write_text(package_dir / "AUDIT_MANIFEST.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    write_text(package_dir / "COMMAND_LOG.md", command_log_template(language))
    write_text(package_dir / "QC_CHECKLIST.md", qc_template(language))
    write_text(package_dir / "FIGURE_INDEX.md", figure_index_template(language))
    return package_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root. Default: current directory.")
    parser.add_argument("--task", default="", help="Short task title.")
    parser.add_argument("--slug", default="", help="Optional ASCII slug for the run directory.")
    parser.add_argument("--mode", choices=sorted(MODES), default="exploratory")
    parser.add_argument("--language", default="auto", help="Report language policy, such as auto, zh, en. auto uses 00_project config when available.")
    parser.add_argument("--output-root", default="", help="Optional report root directory.")
    parser.add_argument("--task-package", default="", help="Task package path. Writes the report under <task-package>/runs.")
    parser.add_argument("--cross-task-report", action="store_true", help="Write under <root>/50_reports.")
    parser.add_argument("--timestamp", default="", help="Optional timestamp for deterministic tests.")
    parser.add_argument("--user-preapproved", action="store_true", help="Mark that the user explicitly approved execution.")
    parser.add_argument("--init-config", action="store_true", help="Create 00_project/scientific_data_report_config.json using a short wizard/defaults.")
    parser.add_argument("--force-config", action="store_true", help="Overwrite an existing project config when used with --init-config.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    if args.init_config:
        init_project_config(root, force=args.force_config)
        return 0
    if not args.task:
        raise SystemExit("--task is required unless --init-config is used")
    package_dir = create_package(args)
    print(package_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
