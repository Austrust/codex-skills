#!/usr/bin/env python3
"""Compile a conversation closeout summary into a planka-kanban apply-plan spec."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from copy import deepcopy
from pathlib import Path
from typing import Any


STATUSES = ("todo", "in_progress", "blocked", "review", "done")
STATUS_LABELS = {
    "todo": "待办",
    "in_progress": "进行中",
    "blocked": "等待/受阻",
    "review": "待审核",
    "done": "已完成",
}
SUMMARY_KEYS = {"tasks", "primaryNextTask", "workspaceMarkers"}
CONFIG_KEYS = {"boardId", "lists", "taskListName"}
TASK_KEYS = {"title", "status", "summary", "completed", "artifacts", "openItems", "cardId"}
NEXT_KEYS = {"title", "relationship", "parentTaskTitle", "summary", "steps", "dueDate"}
SECRET_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{12,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\b(?:PLANKA_API_KEY|PLANKA_PASSWORD|Authorization)\s*[:=]", re.IGNORECASE),
)


class ValidationError(ValueError):
    """Raised when the config, summary, or board snapshot is unsafe or invalid."""


def default_config_path() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    root = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return root / "to-kanban" / "current-route.json"


def default_board_path() -> Path:
    return default_config_path().with_name("current-board.json")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ValidationError(f"JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Invalid JSON in {path}: {exc}") from exc


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be a JSON object")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must be a non-empty string")
    text = value.strip()
    reject_secret(text, label)
    return text


def optional_string(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return require_string(value, label)


def string_list(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValidationError(f"{label} must be an array of strings")
    return [require_string(item, f"{label}[{index}]") for index, item in enumerate(value)]


def reject_unknown_keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValidationError(f"{label} contains unsupported fields: {', '.join(unknown)}")


def reject_secret(text: str, label: str) -> None:
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        raise ValidationError(f"{label} appears to contain a credential or authorization secret")


def validate_config(raw: Any, required_statuses: set[str] | None = None) -> dict[str, Any]:
    config = require_object(raw, "config")
    reject_unknown_keys(config, CONFIG_KEYS, "config")
    board_id = require_string(config.get("boardId"), "config.boardId")
    lists = require_object(config.get("lists"), "config.lists")
    extra = sorted(set(lists) - set(STATUSES))
    required = required_statuses or set()
    missing = sorted(status for status in required if status not in lists)
    if missing or extra or not lists:
        details = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if extra:
            details.append(f"unsupported: {', '.join(extra)}")
        if not lists:
            details.append("no list mappings")
        raise ValidationError(f"config.lists does not satisfy the requested task states ({'; '.join(details)})")
    normalized_lists = {status: require_string(name, f"config.lists.{status}") for status, name in lists.items()}
    duplicate_names = sorted({name for name in normalized_lists.values() if list(normalized_lists.values()).count(name) > 1})
    if duplicate_names:
        raise ValidationError(f"config.lists values must be unique: {', '.join(duplicate_names)}")
    task_list_name = optional_string(config.get("taskListName"), "config.taskListName") or "下一步"
    return {"boardId": board_id, "lists": normalized_lists, "taskListName": task_list_name}


def normalize_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[\s\-_—–:：/\\]+", " ", normalized)
    return normalized.strip()


def board_cards(board: dict[str, Any]) -> list[dict[str, Any]]:
    included = board.get("included")
    if not isinstance(included, dict) or not isinstance(included.get("cards"), list):
        raise ValidationError("board snapshot must contain included.cards")
    cards = []
    for index, card in enumerate(included["cards"]):
        if not isinstance(card, dict):
            raise ValidationError(f"board included.cards[{index}] must be an object")
        if not isinstance(card.get("id"), str) or not isinstance(card.get("name"), str):
            raise ValidationError(f"board included.cards[{index}] requires string id and name")
        cards.append(card)
    return cards


def validate_board(config: dict[str, Any], raw: Any) -> dict[str, Any]:
    board = require_object(raw, "board snapshot")
    item = board.get("item")
    if isinstance(item, dict) and item.get("id") is not None and str(item.get("id")) != config["boardId"]:
        raise ValidationError(
            f"board snapshot id {item.get('id')} does not match configured boardId {config['boardId']}"
        )
    included = require_object(board.get("included"), "board snapshot.included")
    lists = included.get("lists")
    if not isinstance(lists, list):
        raise ValidationError("board snapshot must contain included.lists")
    names = [item.get("name") for item in lists if isinstance(item, dict)]
    for status, expected in config["lists"].items():
        count = names.count(expected)
        if count != 1:
            raise ValidationError(
                f"configured {status} list {expected!r} must exist exactly once in board snapshot; found {count}"
            )
    board_cards(board)
    return board


def workspace_match(card: dict[str, Any], markers: list[str]) -> bool:
    if not markers:
        return False
    description = str(card.get("description") or "").casefold()
    return any(marker.casefold() in description for marker in markers)


def resolve_card_id(
    task: dict[str, Any], cards: list[dict[str, Any]], workspace_markers: list[str]
) -> tuple[str | None, str, str | None]:
    explicit = task.get("cardId")
    if explicit:
        matches = [card for card in cards if card["id"] == explicit]
        if len(matches) != 1:
            raise ValidationError(f"task {task['title']!r} cardId {explicit!r} was not found exactly once")
        return explicit, "explicit_id", matches[0]["name"]

    exact = [card for card in cards if card["name"] == task["title"]]
    if len(exact) == 1:
        return exact[0]["id"], "exact_title", exact[0]["name"]
    if len(exact) > 1:
        raise ValidationError(f"task {task['title']!r} has multiple exact-title card matches")

    normalized_title = normalize_title(task["title"])
    normalized = [card for card in cards if normalize_title(card["name"]) == normalized_title]
    qualified = [card for card in normalized if workspace_match(card, workspace_markers)]
    if len(qualified) == 1:
        return qualified[0]["id"], "normalized_title_workspace", qualified[0]["name"]
    if len(normalized) > 1 or len(qualified) > 1:
        raise ValidationError(f"task {task['title']!r} has ambiguous normalized-title card matches")
    return None, "proposed_create", None


def validate_summary(raw: Any) -> dict[str, Any]:
    summary = require_object(raw, "summary")
    reject_unknown_keys(summary, SUMMARY_KEYS, "summary")
    raw_tasks = summary.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ValidationError("summary.tasks must be a non-empty array")

    tasks = []
    titles = set()
    for index, raw_task in enumerate(raw_tasks):
        task = require_object(raw_task, f"summary.tasks[{index}]")
        reject_unknown_keys(task, TASK_KEYS, f"summary.tasks[{index}]")
        title = require_string(task.get("title"), f"summary.tasks[{index}].title")
        if title in titles:
            raise ValidationError(f"duplicate task title: {title!r}")
        titles.add(title)
        status = require_string(task.get("status"), f"summary.tasks[{index}].status")
        if status not in STATUSES:
            raise ValidationError(f"summary.tasks[{index}].status must be one of {', '.join(STATUSES)}")
        tasks.append(
            {
                "title": title,
                "status": status,
                "summary": require_string(task.get("summary"), f"summary.tasks[{index}].summary"),
                "completed": string_list(task.get("completed"), f"summary.tasks[{index}].completed"),
                "artifacts": string_list(task.get("artifacts"), f"summary.tasks[{index}].artifacts"),
                "openItems": string_list(task.get("openItems"), f"summary.tasks[{index}].openItems"),
                "cardId": optional_string(task.get("cardId"), f"summary.tasks[{index}].cardId"),
            }
        )

    raw_next_task = summary.get("primaryNextTask")
    if raw_next_task is None:
        normalized_next = None
        return {
            "tasks": tasks,
            "primaryNextTask": normalized_next,
            "workspaceMarkers": string_list(summary.get("workspaceMarkers"), "summary.workspaceMarkers"),
        }

    next_task = require_object(raw_next_task, "summary.primaryNextTask")
    reject_unknown_keys(next_task, NEXT_KEYS, "summary.primaryNextTask")
    relationship = require_string(next_task.get("relationship"), "summary.primaryNextTask.relationship")
    if relationship not in {"continuation", "new"}:
        raise ValidationError("summary.primaryNextTask.relationship must be continuation or new")
    parent_title = optional_string(next_task.get("parentTaskTitle"), "summary.primaryNextTask.parentTaskTitle")
    if relationship == "continuation" and parent_title not in titles:
        raise ValidationError("a continuation primaryNextTask requires parentTaskTitle matching one task title")
    if relationship == "new" and parent_title is not None:
        raise ValidationError("a new primaryNextTask must not set parentTaskTitle")

    normalized_next = {
        "title": require_string(next_task.get("title"), "summary.primaryNextTask.title"),
        "relationship": relationship,
        "parentTaskTitle": parent_title,
        "summary": optional_string(next_task.get("summary"), "summary.primaryNextTask.summary"),
        "steps": string_list(next_task.get("steps"), "summary.primaryNextTask.steps"),
        "dueDate": optional_string(next_task.get("dueDate"), "summary.primaryNextTask.dueDate"),
    }
    return {
        "tasks": tasks,
        "primaryNextTask": normalized_next,
        "workspaceMarkers": string_list(summary.get("workspaceMarkers"), "summary.workspaceMarkers"),
    }


def stable_update_id(config: dict[str, Any], summary: dict[str, Any]) -> str:
    payload = {"boardId": config["boardId"], "summary": summary}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def bullet_section(label: str, values: list[str]) -> list[str]:
    if not values:
        return []
    return [f"{label}：", *[f"- {value}" for value in values]]


def task_comment(task: dict[str, Any], update_id: str, next_task: dict[str, Any] | None) -> str:
    lines = [
        f"[to-kanban:{update_id}]",
        f"状态：{STATUS_LABELS[task['status']]}",
        f"摘要：{task['summary']}",
    ]
    lines.extend(bullet_section("已完成", task["completed"]))
    lines.extend(bullet_section("产物/证据", task["artifacts"]))
    lines.extend(bullet_section("未完成/阻塞", task["openItems"]))
    if next_task and next_task["relationship"] == "continuation" and next_task["parentTaskTitle"] == task["title"]:
        lines.extend(["下一步：", f"- {next_task['title']}"])
    return "\n".join(lines)


def card_reference(config: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    if task.get("cardId"):
        return {"boardId": config["boardId"], "cardId": task["cardId"]}
    return {
        "boardId": config["boardId"],
        "title": task["title"],
        "sourceList": config["lists"][task["status"]],
    }


def compile_plan(config_raw: Any, summary_raw: Any, board_raw: Any | None = None) -> dict[str, Any]:
    summary = validate_summary(summary_raw)
    required_statuses = {task["status"] for task in summary["tasks"]}
    if summary["primaryNextTask"] and summary["primaryNextTask"]["relationship"] == "new":
        required_statuses.add("todo")
    config = validate_config(config_raw, required_statuses)
    board = validate_board(config, board_raw) if board_raw is not None else None
    resolved = deepcopy(summary)
    match_preview = []
    cards = board_cards(board) if board is not None else []
    for task in resolved["tasks"]:
        if board is not None:
            card_id, matched_by, matched_card_title = resolve_card_id(task, cards, resolved["workspaceMarkers"])
            task["cardId"] = card_id
            task["_matchedCardTitle"] = matched_card_title
        else:
            matched_by = "explicit_id" if task.get("cardId") else "proposed_create"
            matched_card_title = task["title"] if task.get("cardId") else None
        match_preview.append(
            {
                "title": task["title"],
                "cardId": task.get("cardId"),
                "cardTitle": matched_card_title,
                "matchedBy": matched_by,
                "willCreate": task.get("cardId") is None,
                "targetList": config["lists"][task["status"]],
                "status": task["status"],
            }
        )

    update_id = stable_update_id(config, resolved)
    operations: list[dict[str, Any]] = []
    next_task = resolved["primaryNextTask"]

    for task in resolved["tasks"]:
        target_list = config["lists"][task["status"]]
        continuation = bool(
            next_task
            and next_task["relationship"] == "continuation"
            and next_task["parentTaskTitle"] == task["title"]
        )
        comment = task_comment(task, update_id, next_task)

        if task.get("cardId"):
            complete_operation: dict[str, Any] = {
                "action": "complete-card",
                "boardId": config["boardId"],
                "cardId": task["cardId"],
                "moveToList": target_list,
                "comment": comment,
                "commentMode": "append-once",
            }
            if task["status"] == "done":
                complete_operation["completeTasks"] = "all"
            operations.append(complete_operation)
            if continuation:
                operations.append(
                    {
                        "action": "publish-card",
                        "boardId": config["boardId"],
                        "list": target_list,
                        "title": task.get("_matchedCardTitle") or task["title"],
                        "type": "project",
                        "taskList": config["taskListName"],
                        "tasks": [next_task["title"]],
                        "moveExistingToTargetList": True,
                    }
                )
        else:
            publish_operation: dict[str, Any] = {
                "action": "publish-card",
                "boardId": config["boardId"],
                "list": target_list,
                "title": task["title"],
                "type": "project",
                "moveExistingToTargetList": True,
            }
            if continuation:
                publish_operation.update(
                    {
                        "taskList": config["taskListName"],
                        "tasks": [next_task["title"]],
                    }
                )
            operations.append(publish_operation)
            operations.append(
                {
                    "action": "comment",
                    **card_reference(config, task),
                    "text": comment,
                    "commentMode": "append-once",
                }
            )

    if next_task and next_task["relationship"] == "new":
        next_publish: dict[str, Any] = {
            "action": "publish-card",
            "boardId": config["boardId"],
            "list": config["lists"]["todo"],
            "title": next_task["title"],
            "type": "project",
            "taskList": config["taskListName"],
            "tasks": next_task["steps"],
            "moveExistingToTargetList": True,
        }
        if next_task["summary"]:
            next_publish["description"] = next_task["summary"]
        if next_task["dueDate"]:
            next_publish["dueDate"] = next_task["dueDate"]
        operations.append(next_publish)
        operations.append(
            {
                "action": "comment",
                "boardId": config["boardId"],
                "title": next_task["title"],
                "sourceList": config["lists"]["todo"],
                "text": f"[to-kanban:{update_id}]\n来源：本次对话收尾生成\n下一步：{next_task['title']}",
                "commentMode": "append-once",
            }
        )

    return {
        "metadata": {
            "schemaVersion": 1,
            "updateId": update_id,
            "boardId": config["boardId"],
            "taskMatches": match_preview,
            "primaryNextTask": next_task,
        },
        "operations": operations,
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="UTF-8 conversation summary JSON")
    parser.add_argument(
        "--config",
        type=Path,
        help="Route config JSON; defaults to $CODEX_HOME/to-kanban/current-route.json",
    )
    parser.add_argument(
        "--board",
        type=Path,
        help="Board JSON; defaults to $CODEX_HOME/to-kanban/current-board.json when present",
    )
    parser.add_argument("--output", type=Path, help="Write the apply-plan JSON here; otherwise print to stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_json(args.config or default_config_path())
        summary = load_json(args.input)
        board_path = args.board or default_board_path()
        board = load_json(board_path) if board_path.exists() else None
        plan = compile_plan(config, summary, board)
        if args.output:
            write_json(args.output, plan)
            print(f"wrote {args.output}")
        else:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    except ValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
