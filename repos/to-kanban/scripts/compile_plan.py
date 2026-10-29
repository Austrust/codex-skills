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
from kanban_context import state_root, ContextError
from shared_policy import read_board_policy, policy_cards, PolicyError


STATUSES = ("inbox", "todo", "in_progress", "blocked", "review", "done")
STATUS_LABELS = {
    "inbox": "收集箱",
    "todo": "待办",
    "in_progress": "进行中",
    "blocked": "等外部",
    "review": "等验收",
    "done": "已完成",
}
SUMMARY_KEYS = {"tasks", "primaryNextTask", "workspaceMarkers", "operationId", "batchReason"}
CONFIG_KEYS = {"boardId", "lists", "taskListName", "acceptanceListName", "wipLimit", "wipLists", "policySource"}
TASK_KEYS = {
    "goalId", "taskKey", "newCardReason", "independentValue", "splitReason", "dueDate",
    "intent", "evidence", "dependencyEvidence",
    "title",
    "status",
    "summary",
    "deliverable",
    "acceptanceCriteria",
    "dependencies",
    "steps",
    "completed",
    "artifacts",
    "openItems",
    "cardId",
}
NEXT_KEYS = {
    "goalId", "taskKey", "newCardReason", "independentValue", "splitReason", "cardId",
    "dependencyEvidence",
    "title",
    "relationship",
    "parentTaskTitle",
    "summary",
    "deliverable",
    "acceptanceCriteria",
    "dependencies",
    "steps",
    "dueDate",
}
SECRET_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{12,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\b(?:PLANKA_API_KEY|PLANKA_PASSWORD|Authorization)\s*[:=]", re.IGNORECASE),
)


class ValidationError(ValueError):
    """Raised when the config, summary, or board snapshot is unsafe or invalid."""


def default_config_path() -> Path:
    return state_root() / "current-route.json"


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


def unique_string_list(value: Any, label: str) -> list[str]:
    values = string_list(value, label)
    if len(values) != len(set(values)):
        raise ValidationError(f"{label} must not contain duplicate entries")
    return values


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
    task_list_name = optional_string(config.get("taskListName"), "config.taskListName") or "执行步骤"
    acceptance_list_name = (
        optional_string(config.get("acceptanceListName"), "config.acceptanceListName") or "验收条件"
    )
    if task_list_name == acceptance_list_name:
        raise ValidationError("config.taskListName and config.acceptanceListName must be different")
    limit = config.get("wipLimit")
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValidationError("config.wipLimit must be a positive integer")
    return {
        "policySource": config.get("policySource", {"kind": "missing"}),
        "wipLimit": limit,
        "wipLists": unique_string_list(config.get("wipLists"), "config.wipLists"),
        "boardId": board_id,
        "lists": normalized_lists,
        "taskListName": task_list_name,
        "acceptanceListName": acceptance_list_name,
    }


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

    marker = f"[kanban-item:{task['_itemKey']}]" if task.get('_itemKey') else None
    keyed = [card for card in cards if marker and marker in (card.get('description') or '')]
    if len(keyed) > 1:
        raise ValidationError("multiple cards share a work item key; resolve duplicates before writing")
    if keyed:
        return keyed[0]['id'], 'work_item_key', keyed[0]['name']

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
    if not isinstance(raw_tasks, list):
        raise ValidationError("summary.tasks must be an array")

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
                **{key: optional_string(task.get(key), key) for key in
                   ('goalId', 'taskKey', 'newCardReason', 'independentValue', 'splitReason', 'dueDate')},
                "intent": task.get("intent", "propose"),
                "evidence": evidence_map(task.get("evidence"), "evidence"),
                "dependencyEvidence": evidence_map(task.get("dependencyEvidence"), "dependencyEvidence"),
                "title": title,
                "status": status,
                "summary": require_string(task.get("summary"), f"summary.tasks[{index}].summary"),
                "deliverable": optional_string(
                    task.get("deliverable"), f"summary.tasks[{index}].deliverable"
                ),
                "acceptanceCriteria": unique_string_list(
                    task.get("acceptanceCriteria"), f"summary.tasks[{index}].acceptanceCriteria"
                ),
                "dependencies": unique_string_list(
                    task.get("dependencies"), f"summary.tasks[{index}].dependencies"
                ),
                "steps": unique_string_list(task.get("steps"), f"summary.tasks[{index}].steps"),
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
            'operationId': optional_string(summary.get('operationId'), 'operationId'),
            'batchReason': optional_string(summary.get('batchReason'), 'batchReason'),
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
        **{key: optional_string(next_task.get(key), key) for key in
           ('goalId', 'taskKey', 'newCardReason', 'independentValue', 'splitReason', 'cardId')},
        "title": require_string(next_task.get("title"), "summary.primaryNextTask.title"),
        "dependencyEvidence": evidence_map(next_task.get("dependencyEvidence"), "dependencyEvidence"),
        "relationship": relationship,
        "parentTaskTitle": parent_title,
        "summary": optional_string(next_task.get("summary"), "summary.primaryNextTask.summary"),
        "deliverable": optional_string(next_task.get("deliverable"), "summary.primaryNextTask.deliverable"),
        "acceptanceCriteria": unique_string_list(
            next_task.get("acceptanceCriteria"), "summary.primaryNextTask.acceptanceCriteria"
        ),
        "dependencies": unique_string_list(
            next_task.get("dependencies"), "summary.primaryNextTask.dependencies"
        ),
        "steps": unique_string_list(next_task.get("steps"), "summary.primaryNextTask.steps"),
        "dueDate": optional_string(next_task.get("dueDate"), "summary.primaryNextTask.dueDate"),
    }
    return {
        'operationId': optional_string(summary.get('operationId'), 'operationId'),
        'batchReason': optional_string(summary.get('batchReason'), 'batchReason'),
        "tasks": tasks,
        "primaryNextTask": normalized_next,
        "workspaceMarkers": string_list(summary.get("workspaceMarkers"), "summary.workspaceMarkers"),
    }


def stable_update_id(config: dict[str, Any], summary: dict[str, Any]) -> str:
    # Use the original normalized input, never resolved IDs or live acceptance state.
    payload = {"boardId": config["boardId"], "summary": summary}
    if summary.get('operationId'):
        payload = {'boardId': config['boardId'], 'operationId': summary['operationId']}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def item_key(config, task, workspace_markers):
    identity = [task.get('goalId') or normalize_title(task['title']), task.get('taskKey')]
    payload = [config['boardId'], sorted(set(workspace_markers)), identity]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode('utf-8')).hexdigest()[:24]


def validate_granularity(tasks, batch_reason):
    """Reject unsupported splits; never guess how to merge states or evidence."""
    groups = {}
    for task in tasks:
        groups.setdefault(task.get('goalId') or task['title'], []).append(task)
    for group in groups.values():
        if len(group) > 1 and any(not all(t.get(k) for k in
                ('taskKey', 'independentValue', 'splitReason')) for t in group):
            raise ValidationError('same goal must stay in one card; a split requires taskKey, independentValue and splitReason for each part')
    new = [t for t in tasks if not t.get('cardId')]
    if len(new) > 1 and any(not t.get('goalId') or not t.get('newCardReason') for t in new):
        raise ValidationError('multiple new cards require goalId and newCardReason; merge steps into the existing goal first')
    if len(new) > 3 and not batch_reason:
        raise ValidationError('more than three new cards requires batchReason after a merge review')
    return {'newCardCount': len(new), 'updatedCardCount': len(tasks) - len(new),
            'batchReason': batch_reason}


def bullet_section(label: str, values: list[str]) -> list[str]:
    if not values:
        return []
    return [f"{label}：", *[f"- {value}" for value in values]]


def validate_actionable_card(item: dict[str, Any], label: str) -> None:
    if item.get("status") == "inbox":
        return
    if not item.get("deliverable"):
        raise ValidationError(f"{label}.deliverable is required for a new card")
    if not item.get("acceptanceCriteria"):
        raise ValidationError(f"{label}.acceptanceCriteria requires at least one pass/fail condition")


def work_item_description(item: dict[str, Any]) -> str:
    dependencies = item.get("dependencies") or []
    lines = [
        f"目标：{item.get('summary') or '未提供'}",
        "",
        f"交付物：{item.get('deliverable') or '待澄清'}",
        "",
        "前置条件：",
    ]
    lines.extend([f"- {value}" for value in dependencies] or ["- 无"])
    return "\n".join(lines)


def task_comment(task: dict[str, Any], update_id: str, next_task: dict[str, Any] | None) -> str:
    lines = [
        f"[to-kanban:{update_id}]",
        f"状态：{STATUS_LABELS[task['status']]}",
        f"摘要：{task['summary']}",
    ]
    if task.get("deliverable"):
        lines.append(f"交付物：{task['deliverable']}")
    lines.extend(bullet_section("验收条件", task.get("acceptanceCriteria") or []))
    lines.extend(bullet_section("前置条件", task.get("dependencies") or ["无"]))
    lines.extend(bullet_section("执行步骤", task.get("steps") or []))
    lines.extend(bullet_section("验收证据", [f"{k}: {v}" for k, v in task["evidence"].items()]))
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
        "workItemKey": task.get('_itemKey'),
        "title": task["title"],
        "sourceList": config["lists"][task["status"]],
    }



def evidence_map(value, label):
    if value is None:
        return {}
    return {require_string(k, label): require_string(v, label)
            for k, v in require_object(value, label).items()}


def validate_flow(config, summary, board):
    tasks = summary["tasks"]
    policy_ids = {c["id"] for c in policy_cards(board)} if board else set()
    cards = [c for c in board_cards(board) if c["id"] not in policy_ids] if board else []
    included = board.get("included", {}) if board else {}
    lists = {x["id"]: x["name"] for x in included.get("lists", [])}
    active_names = config["wipLists"] or [config["lists"][x] for x in
                    ("in_progress", "blocked", "review") if x in config["lists"]]
    if any(name not in lists.values() for name in active_names):
        raise ValidationError("wipLists must exist in the live board")
    if config["wipLists"] and any(config["lists"][x] not in active_names for x in
            ("in_progress", "blocked", "review") if x in config["lists"]):
        raise ValidationError("wipLists cannot exclude mapped started states")
    active = {c["id"] for c in cards if lists.get(c.get("listId")) in active_names}
    before = len(active)
    warnings = []
    done_name = config["lists"].get("done")
    seen_ids = set()
    for t in tasks:
        if t["intent"] not in ("propose", "record"):
            raise ValidationError("intent must be propose or record")
        if t.get("cardId"):
            if t["cardId"] in seen_ids:
                raise ValidationError("multiple task records target the same card")
            seen_ids.add(t["cardId"])
        if t["status"] == "done":
            validate_actionable_card(t, t["title"])
            if t.get("cardId") and (board is None or not all(isinstance(included.get(k), list) for k in ("taskLists", "tasks"))):
                raise ValidationError("existing done requires live taskLists and tasks")
            task_lists = {x["id"] for x in included.get("taskLists", [])
                          if x.get("cardId") == t.get("cardId") and x.get("name") == config["acceptanceListName"]}
            live = [x for x in included.get("tasks", []) if x.get("taskListId") in task_lists]
            criteria = set(t["acceptanceCriteria"]) | {x["name"] for x in live}
            if t["openItems"] or any(not t["evidence"].get(c) for c in criteria):
                raise ValidationError(f"{t['title']}: done requires evidence for every acceptance criterion and no openItems")
            t["_completeNames"] = [x["name"] for x in live if t["evidence"].get(x["name"])] if t.get("cardId") else t["acceptanceCriteria"]
    next_task = summary.get("primaryNextTask")
    if next_task and next_task["relationship"] == "continuation":
        parent = next(t for t in tasks if t["title"] == next_task["parentTaskTitle"])
        if parent["status"] == "done":
            raise ValidationError("a done card cannot have an unfinished continuation")
    # Evaluate dependencies against current live state, never a speculative future completion.
    for t in tasks + ([dict(next_task, status="todo", intent="propose")] if next_task and next_task["relationship"] == "new" else []):
        if t["status"] not in ("todo", "in_progress", "review"):
            continue
        validate_actionable_card(t, t["title"])
        for dep in t["dependencies"]:
            if dep == "无":
                continue
            matches = [c for c in cards if c["id"] == dep or c["name"] == dep]
            satisfied = len(matches) == 1 and done_name is not None and lists.get(matches[0].get("listId")) == done_name
            if not matches:
                satisfied = bool(t["dependencyEvidence"].get(dep))
            if not satisfied:
                message = f"{t['title']}: unresolved or ambiguous dependency {dep!r}"
                if t["intent"] == "record" and t["status"] != "todo":
                    warnings.append(message)
                else:
                    raise ValidationError(message)
    for t in tasks:
        key = t.get("cardId") or "new:" + t["title"]
        target_active = config["lists"][t["status"]] in active_names
        entering = target_active and key not in active
        if entering:
            complete_mapping = bool(config["wipLists"]) or all(x in config["lists"] for x in ("in_progress", "blocked", "review"))
            problem = None
            if board is None or not complete_mapping or config["wipLimit"] is None:
                problem = "starting work requires a live board, complete WIP mapping and configured wipLimit"
            elif any(c.get("listId") not in lists for c in cards):
                problem = "live cards have missing or unknown listId; WIP cannot be counted reliably"
            elif len(active) >= config["wipLimit"]:
                problem = f"WIP limit {config['wipLimit']} reached"
            if problem:
                if t["intent"] == "record":
                    warnings.append(f"{t['title']}: {problem}")
                else:
                    raise ValidationError(problem)
        if target_active:
            active.add(key)
        elif key in active:
            if t["status"] != "done":
                raise ValidationError("started work cannot be moved to inbox/todo to hide WIP")
            active.remove(key)
    if config["wipLimit"] and len(active) > config["wipLimit"]:
        warnings.append("Board remains above its WIP limit; finish or unblock existing work first")
    return {"wipBefore": before, "wipAfter": len(active), "wipLimit": config["wipLimit"],
            "wipLists": active_names, "warnings": warnings, "policySource": config["policySource"]}


def compile_plan(config_raw: Any, summary_raw: Any, board_raw: Any | None = None) -> dict[str, Any]:
    summary = validate_summary(summary_raw)
    update_id = stable_update_id(config_raw, summary)
    next_preview = deepcopy(summary['primaryNextTask'])
    if next_preview and next_preview['relationship'] == 'new':
        # Match next work through the same path as every other task.
        next_record = {k: v for k, v in next_preview.items() if k in TASK_KEYS}
        next_record.update(status='todo', summary=next_record.get('summary') or next_record['title'])
        normalized = validate_summary({'tasks': [next_record]})['tasks'][0]
        normalized['_nextCandidate'] = True
        summary['tasks'].append(normalized)
        summary['primaryNextTask'] = None
    required_statuses = {task["status"] for task in summary["tasks"]}
    try:
        remote = read_board_policy(board_raw) if board_raw is not None else {"wipLimit": None, "wipLists": [], "policySource": {"kind": "missing"}}
    except PolicyError as exc:
        raise ValidationError(str(exc)) from exc
    config = validate_config({**require_object(config_raw, "config"), **remote}, required_statuses)
    board = validate_board(config, board_raw) if board_raw is not None else None
    resolved = deepcopy(summary)
    match_preview = []
    policy_ids = {c["id"] for c in policy_cards(board)} if board else set()
    cards = [c for c in board_cards(board) if c["id"] not in policy_ids] if board else []
    if any(t.get("cardId") in policy_ids or t["title"].startswith("[kanban-policy:") for t in resolved["tasks"]):
        raise ValidationError("Policy cards cannot be treated as work items")
    for task in resolved["tasks"]:
        task['_itemKey'] = item_key(config, task, resolved['workspaceMarkers'])
        if board is not None:
            card_id, matched_by, matched_card_title = resolve_card_id(task, cards, resolved["workspaceMarkers"])
            task["cardId"] = card_id
            task["_matchedCardTitle"] = matched_card_title
            task['_matchedBy'] = matched_by
            if card_id and task.get('_nextCandidate'):
                live = next(c for c in cards if c['id'] == card_id)
                live_list = next((x['name'] for x in board['included']['lists'] if x['id'] == live.get('listId')), None)
                live_status = next((role for role, name in config['lists'].items() if name == live_list), None)
                if live_status is None:
                    raise ValidationError('matched next task has an unmapped live state; update it explicitly')
                # A recommendation must not rewind work that is already started/done.
                task['status'] = live_status
                task['_skipNextUpdate'] = True
                if matched_by == 'work_item_key' and live_status == 'todo':
                    included = board.get('included', {})
                    lists_by_name = {x['name']: x['id'] for x in included.get('taskLists', [])
                                     if x.get('cardId') == card_id}
                    for list_name, names in ((config['acceptanceListName'], task['acceptanceCriteria']),
                                             (config['taskListName'], task['steps'])):
                        present = {x['name'] for x in included.get('tasks', [])
                                   if x.get('taskListId') == lists_by_name.get(list_name)}
                        if set(names) - present:
                            # Repair an interrupted publish of this exact next-task identity.
                            task['_skipNextUpdate'] = False
        else:
            matched_by = "explicit_id" if task.get("cardId") else "proposed_create"
            matched_card_title = task["title"] if task.get("cardId") else None
        match_preview.append(
            {
                "title": task["title"],
                "goal": task["summary"],
                "deliverable": task.get("deliverable"),
                "acceptanceCriteria": task.get("acceptanceCriteria") or [],
                "dependencies": task.get("dependencies") or [],
                "cardId": task.get("cardId"),
                "cardTitle": matched_card_title,
                "matchedBy": matched_by,
                "willCreate": task.get("cardId") is None,
                "targetList": config["lists"][task["status"]],
                "status": task["status"],
                "goalId": task.get('goalId'),
                "newCardReason": task.get('newCardReason'),
                "splitReason": task.get('splitReason'),
                "independentValue": task.get('independentValue'),
            }
        )

    for index, task in enumerate(resolved["tasks"]):
        if task.get("cardId") is None:
            validate_actionable_card(task, f"summary.tasks[{index}]")

    actionable = [t for t in resolved['tasks'] if not t.get('_skipNextUpdate')]
    granularity = validate_granularity(actionable, resolved.get('batchReason'))
    keys = [t['_itemKey'] for t in actionable]
    if len(keys) != len(set(keys)):
        raise ValidationError('duplicate work item identity; combine records for the same task')
    # Existing recommendations are informational; no completion or state mutation.
    flow_summary = {**resolved, 'tasks': [t for t in resolved['tasks'] if not t.get('_skipNextUpdate')]}
    flow = validate_flow(config, flow_summary, board)
    operations: list[dict[str, Any]] = []
    next_task = resolved["primaryNextTask"]

    for task in resolved["tasks"]:
        if task.get('_skipNextUpdate'):
            continue
        target_list = config["lists"][task["status"]]
        continuation = bool(
            next_task
            and next_task["relationship"] == "continuation"
            and next_task["parentTaskTitle"] == task["title"]
        )
        comment = task_comment(task, update_id, next_task)

        if task.get("cardId"):
            if task.get('_matchedBy') == 'work_item_key':
                # A lost create response may leave a card without its checklists.
                included = board.get('included', {})
                acceptance_lists = {x['id'] for x in included.get('taskLists', [])
                                    if x.get('cardId') == task['cardId'] and x.get('name') == config['acceptanceListName']}
                existing_names = {x['name'] for x in included.get('tasks', []) if x.get('taskListId') in acceptance_lists}
                missing = [name for name in task['acceptanceCriteria'] if name not in existing_names]
                if missing:
                    operations.append({'action': 'publish-card', 'boardId': config['boardId'],
                        'cardId': task['cardId'], 'title': task['_matchedCardTitle'],
                        'list': target_list, 'type': 'project', 'taskList': config['acceptanceListName'],
                        'tasks': missing, 'moveExistingToTargetList': True})
                    if task['status'] == 'done':
                        task['_completeNames'] = list(dict.fromkeys(task['_completeNames'] + missing))
            complete_operation: dict[str, Any] = {
                "action": "complete-card",
                "boardId": config["boardId"],
                "cardId": task["cardId"],
                "moveToList": target_list,
                "comment": comment,
                "commentMode": "append-once",
            }
            if task["status"] == "done":
                complete_operation["completeTasks"] = task["_completeNames"]
                complete_operation["evidence"] = task["evidence"]
            operations.append(complete_operation)
            execution_steps = list(task.get('steps') or [])
            if continuation:
                execution_steps.append(next_task['title'])
            if execution_steps:
                operations.append(
                    {
                        "action": "publish-card",
                        "boardId": config["boardId"],
                        "list": target_list,
                        "title": task.get("_matchedCardTitle") or task["title"],
                        "cardId": task['cardId'],
                        "type": "project",
                        "taskList": config["taskListName"],
                        "tasks": list(dict.fromkeys(execution_steps)),
                        "moveExistingToTargetList": True,
                    }
                )
        else:
            publish_operation: dict[str, Any] = {
                "action": "publish-card",
                "boardId": config["boardId"],
                "list": target_list,
                "title": task["title"],
                "workItemKey": task['_itemKey'],
                "description": work_item_description(task),
                "type": "project",
                "taskList": config["acceptanceListName"],
                "tasks": task["acceptanceCriteria"],
                "moveExistingToTargetList": True,
            }
            if task.get('dueDate'):
                publish_operation['dueDate'] = task['dueDate']
            operations.append(publish_operation)
            execution_steps = list(task.get("steps") or [])
            if continuation:
                execution_steps.append(next_task["title"])
            if execution_steps:
                operations.append(
                    {
                        "action": "publish-card",
                        "boardId": config["boardId"],
                        "list": target_list,
                        "title": task["title"],
                        "workItemKey": task['_itemKey'],
                        "type": "project",
                        "taskList": config["taskListName"],
                        "tasks": execution_steps,
                        "moveExistingToTargetList": True,
                    }
                )
            if task["status"] == "done":
                operations.append(
                    {
                        "action": "complete-card",
                        **card_reference(config, task),
                        "moveToList": target_list,
                        "completeTasks": task["_completeNames"],
                        "evidence": task["evidence"],
                        "comment": comment,
                        "commentMode": "append-once",
                    }
                )

    return {
        "metadata": {
            "schemaVersion": 5,
            "granularity": granularity,
            "flow": flow,
            "updateId": update_id,
            "boardId": config["boardId"],
            "taskMatches": match_preview,
            "primaryNextTask": next_preview,
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
        help="Route config JSON; defaults to current-route.json in the configured state folder",
    )
    parser.add_argument(
        "--board",
        type=Path,
        help="Board JSON; defaults to current-board.json in the configured state folder when present",
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
    except (ValidationError, ContextError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
