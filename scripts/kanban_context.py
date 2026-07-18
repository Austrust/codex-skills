#!/usr/bin/env python3
"""Maintain global To Kanban memory, an offline Planka snapshot, and automatic routing."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import unicodedata
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATUSES = ("todo", "in_progress", "blocked", "review", "done")
ROLE_TERMS = {
    "todo": ("待办", "待处理", "任务池", "收集箱", "todo", "to do", "backlog", "inbox", "tasks"),
    "in_progress": ("进行中", "处理中", "执行中", "doing", "in progress", "active", "working"),
    "blocked": ("等待反馈", "等待", "受阻", "暂停", "blocked", "waiting", "on hold"),
    "review": ("待审核", "审核", "评审", "review", "checking", "qa"),
    "done": ("已完成", "完成", "归档", "done", "complete", "completed", "finished"),
}
SECRET_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{12,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\b(?:PLANKA_API_KEY|PLANKA_PASSWORD|Authorization)\s*[:=]", re.IGNORECASE),
)
PROJECT_FIELDS = ("id", "name")
BOARD_FIELDS = ("id", "projectId", "name", "position")
INCLUDED_FIELDS = {
    "lists": ("id", "boardId", "name", "type", "position"),
    "cards": (
        "id",
        "boardId",
        "listId",
        "name",
        "description",
        "type",
        "dueDate",
        "isDueCompleted",
        "position",
    ),
    "taskLists": ("id", "cardId", "name", "position"),
    "tasks": ("id", "taskListId", "name", "isCompleted", "position"),
    "labels": ("id", "boardId", "name", "color", "position"),
    "cardLabels": ("id", "cardId", "labelId"),
}
DEFAULT_MEMORY = {
    "schemaVersion": 1,
    "updatedAt": None,
    "preferences": {
        "taskListName": "下一步",
        "autoRouteThreshold": 0.72,
        "ambiguityMargin": 0.12,
        "snapshotMaxAgeMinutes": 15,
        "todoListAliases": [],
        "boardAliases": {},
    },
    "workspaceRoutes": [],
    "routingHistory": [],
}


class ContextError(ValueError):
    """Raised when global context, snapshots, or routing input is invalid."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def state_root() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    root = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return root / "to-kanban"


def state_paths(root: Path | None = None) -> dict[str, Path]:
    base = (root or state_root()).expanduser()
    return {
        "root": base,
        "memory": base / "memory.json",
        "snapshot": base / "offline-board.json",
        "route": base / "current-route.json",
        "board": base / "current-board.json",
    }


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ContextError(f"JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContextError(f"Invalid JSON in {path}: {exc}") from exc


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def reject_secret(text: str, label: str) -> None:
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        raise ContextError(f"{label} appears to contain a credential or authorization secret")


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContextError(f"{label} must be a non-empty string")
    text = value.strip()
    reject_secret(text, label)
    return text


def string_list(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ContextError(f"{label} must be an array of strings")
    return [require_string(item, f"{label}[{index}]") for index, item in enumerate(value)]


def load_memory(path: Path) -> dict[str, Any]:
    if not path.exists():
        memory = deepcopy(DEFAULT_MEMORY)
        atomic_write_json(path, memory)
        return memory
    raw = load_json(path)
    if not isinstance(raw, dict) or raw.get("schemaVersion") != 1:
        raise ContextError("memory.json must be a schemaVersion 1 object")
    memory = deepcopy(DEFAULT_MEMORY)
    memory.update({key: raw[key] for key in ("updatedAt", "workspaceRoutes", "routingHistory") if key in raw})
    if isinstance(raw.get("preferences"), dict):
        memory["preferences"].update(raw["preferences"])
    if not isinstance(memory["workspaceRoutes"], list) or not isinstance(memory["routingHistory"], list):
        raise ContextError("memory workspaceRoutes and routingHistory must be arrays")
    return memory


def clean_fields(value: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in fields if key in value}


def build_offline_snapshot(
    projects_payload: dict[str, Any], board_payloads: dict[str, dict[str, Any]], refreshed_at: str | None = None
) -> dict[str, Any]:
    projects = [clean_fields(item, PROJECT_FIELDS) for item in projects_payload.get("items", []) if isinstance(item, dict)]
    projects_by_id = {str(item.get("id")): item for item in projects}
    discovered_boards = projects_payload.get("included", {}).get("boards", [])
    boards = []
    for discovered in discovered_boards:
        if not isinstance(discovered, dict) or not discovered.get("id"):
            continue
        board_id = str(discovered["id"])
        payload = board_payloads.get(board_id)
        if not isinstance(payload, dict):
            continue
        item = clean_fields(payload.get("item") or discovered, BOARD_FIELDS)
        project = projects_by_id.get(str(item.get("projectId")), {})
        included = payload.get("included") if isinstance(payload.get("included"), dict) else {}
        sanitized = {
            key: [clean_fields(entry, fields) for entry in included.get(key, []) if isinstance(entry, dict)]
            for key, fields in INCLUDED_FIELDS.items()
        }
        boards.append({"projectName": project.get("name"), "item": item, "included": sanitized})
    boards.sort(key=lambda value: (str(value.get("projectName") or ""), str(value.get("item", {}).get("name") or "")))
    return {
        "schemaVersion": 1,
        "refreshedAt": refreshed_at or utc_now(),
        "projects": projects,
        "boards": boards,
    }


def locate_planka_cli(explicit: Path | None = None) -> Path:
    candidates = []
    if explicit:
        candidates.append(explicit)
    if os.environ.get("PLANKA_CLI_PATH"):
        candidates.append(Path(os.environ["PLANKA_CLI_PATH"]))
    codex_home = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
    candidates.append(codex_home / "skills" / "planka-kanban" / "scripts" / "planka_cli.py")
    skill_path = Path(__file__).resolve()
    candidates.append(skill_path.parents[2] / "planka-kanban" / "scripts" / "planka_cli.py")
    for candidate in candidates:
        if candidate.expanduser().is_file():
            return candidate.expanduser().resolve()
    raise ContextError("Could not locate planka-kanban/scripts/planka_cli.py")


def run_planka_json(cli: Path, arguments: list[str]) -> dict[str, Any]:
    process = subprocess.run(
        [sys.executable, str(cli), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if process.returncode != 0:
        message = (process.stderr or process.stdout).strip()
        raise ContextError(f"planka_cli.py {' '.join(arguments)} failed: {message}")
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise ContextError(f"planka_cli.py returned invalid JSON for {' '.join(arguments)}") from exc
    if not isinstance(payload, dict):
        raise ContextError("planka_cli.py response must be a JSON object")
    return payload


def refresh_snapshot(paths: dict[str, Path], cli_path: Path | None = None) -> dict[str, Any]:
    cli = locate_planka_cli(cli_path)
    projects = run_planka_json(cli, ["projects"])
    board_payloads = {}
    for board in projects.get("included", {}).get("boards", []):
        if isinstance(board, dict) and board.get("id"):
            board_id = str(board["id"])
            board_payloads[board_id] = run_planka_json(cli, ["board", "--board-id", board_id])
    snapshot = build_offline_snapshot(projects, board_payloads)
    atomic_write_json(paths["snapshot"], snapshot)
    return snapshot


def normalize(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\s\-_—–:：/\\]+", " ", text).strip()


def text_features(value: str) -> set[str]:
    text = normalize(value)
    features = {token for token in re.findall(r"[a-z0-9][a-z0-9.]+", text) if len(token) >= 2}
    for sequence in re.findall(r"[\u3400-\u9fff]+", text):
        if len(sequence) == 1:
            features.add(sequence)
        for size in (2, 3):
            features.update(sequence[index : index + size] for index in range(max(0, len(sequence) - size + 1)))
    return features


def feature_coverage(query: set[str], target: set[str]) -> float:
    return len(query & target) / len(query) if query else 0.0


def list_role_score(name: str, status: str, memory: dict[str, Any]) -> float:
    normalized = normalize(name)
    terms = list(ROLE_TERMS[status])
    if status == "todo":
        terms.extend(string_list(memory["preferences"].get("todoListAliases"), "preferences.todoListAliases"))
    normalized_terms = [normalize(term) for term in terms]
    if normalized in normalized_terms:
        return 1.0
    if any(term and term in normalized for term in normalized_terms):
        return 0.85
    overlap = max((feature_coverage(text_features(term), text_features(name)) for term in terms), default=0.0)
    return 0.6 if overlap >= 0.6 else 0.0


def board_text(board: dict[str, Any], memory: dict[str, Any]) -> str:
    parts = [str(board.get("projectName") or ""), str(board.get("item", {}).get("name") or "")]
    board_id = str(board.get("item", {}).get("id") or "")
    aliases = memory["preferences"].get("boardAliases", {})
    if isinstance(aliases, dict):
        parts.extend(string_list(aliases.get(board_id), f"preferences.boardAliases.{board_id}"))
    included = board.get("included", {})
    for key in ("lists", "cards", "taskLists", "tasks", "labels"):
        for item in included.get(key, []):
            if isinstance(item, dict):
                parts.extend(str(item.get(field) or "") for field in ("name", "description"))
    return "\n".join(parts)


def infer_list_map(board: dict[str, Any], memory: dict[str, Any]) -> tuple[dict[str, str], dict[str, float]]:
    lists = board.get("included", {}).get("lists", [])
    mapping: dict[str, str] = {}
    scores: dict[str, float] = {}
    for status in STATUSES:
        ranked = sorted(
            ((list_role_score(str(item.get("name") or ""), status, memory), item) for item in lists if isinstance(item, dict)),
            key=lambda pair: pair[0],
            reverse=True,
        )
        if ranked and ranked[0][0] >= 0.55:
            mapping[status] = str(ranked[0][1]["name"])
            scores[status] = ranked[0][0]
    return mapping, scores


def validate_route_input(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ContextError("route input must be a JSON object")
    allowed = {"title", "summary", "status", "workspaceMarkers", "keywords"}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ContextError(f"route input contains unsupported fields: {', '.join(unknown)}")
    status = str(raw.get("status") or "todo")
    if status not in STATUSES:
        raise ContextError(f"route input status must be one of {', '.join(STATUSES)}")
    return {
        "title": require_string(raw.get("title"), "route.title"),
        "summary": require_string(raw["summary"], "route.summary") if raw.get("summary") else "",
        "status": status,
        "workspaceMarkers": string_list(raw.get("workspaceMarkers"), "route.workspaceMarkers"),
        "keywords": string_list(raw.get("keywords"), "route.keywords"),
    }


def matching_workspace_boost(
    memory: dict[str, Any], markers: list[str], status: str, board_id: str, list_id: str
) -> tuple[float, list[str]]:
    normalized_markers = [normalize(marker) for marker in markers]
    for route in memory.get("workspaceRoutes", []):
        if not isinstance(route, dict) or route.get("status") != status:
            continue
        learned = normalize(str(route.get("marker") or ""))
        marker_matches = any(learned and (learned in marker or marker in learned) for marker in normalized_markers)
        if marker_matches and str(route.get("boardId")) == board_id and str(route.get("listId")) == list_id:
            return 0.55, ["learned workspace route"]
    return 0.0, []


def history_boost(memory: dict[str, Any], query_features: set[str], status: str, board_id: str, list_id: str) -> float:
    matches = 0
    for item in memory.get("routingHistory", [])[-200:]:
        if not isinstance(item, dict) or item.get("status") != status:
            continue
        if str(item.get("boardId")) != board_id or str(item.get("listId")) != list_id:
            continue
        historical = text_features(f"{item.get('title', '')} {item.get('summary', '')}")
        if feature_coverage(query_features, historical) >= 0.25:
            matches += 1
    return min(0.25, 0.08 * matches)


def route_task(snapshot_raw: Any, memory: dict[str, Any], route_raw: Any) -> dict[str, Any]:
    if not isinstance(snapshot_raw, dict) or snapshot_raw.get("schemaVersion") != 1:
        raise ContextError("offline-board.json must be a schemaVersion 1 object")
    route = validate_route_input(route_raw)
    query_text = " ".join([route["title"], route["summary"], *route["keywords"], *route["workspaceMarkers"]])
    query_normalized = normalize(query_text)
    query_features = text_features(query_text)
    candidates = []

    for board in snapshot_raw.get("boards", []):
        if not isinstance(board, dict):
            continue
        board_id = str(board.get("item", {}).get("id") or "")
        if not board_id:
            continue
        lists = [item for item in board.get("included", {}).get("lists", []) if isinstance(item, dict)]
        list_map, list_scores = infer_list_map(board, memory)
        target_name = list_map.get(route["status"])
        target = next((item for item in lists if str(item.get("name")) == target_name), None)

        if target is None:
            learned_routes = [
                item
                for item in memory.get("workspaceRoutes", [])
                if isinstance(item, dict)
                and item.get("status") == route["status"]
                and str(item.get("boardId")) == board_id
            ]
            learned_routes.sort(key=lambda item: int(item.get("useCount") or 0), reverse=True)
            for learned in learned_routes:
                target = next((item for item in lists if str(item.get("id")) == str(learned.get("listId"))), None)
                if target:
                    target_name = str(target.get("name"))
                    list_map[route["status"]] = target_name
                    list_scores[route["status"]] = 0.8
                    break
        if target is None:
            continue

        target_id = str(target.get("id"))
        searchable = board_text(board, memory)
        searchable_normalized = normalize(searchable)
        reasons = []
        score = 0.25 * list_scores.get(route["status"], 0.0)
        if list_scores.get(route["status"], 0.0):
            reasons.append(f"{route['status']} list name match")

        lexical = feature_coverage(query_features, text_features(searchable))
        if lexical:
            score += 0.45 * lexical
            reasons.append("conversation terms match board content")

        board_name = normalize(str(board.get("item", {}).get("name") or ""))
        project_name = normalize(str(board.get("projectName") or ""))
        if any(name and name in query_normalized for name in (board_name, project_name)):
            score += 0.25
            reasons.append("project or board name appears in conversation")

        normalized_markers = [normalize(marker) for marker in route["workspaceMarkers"]]
        if any(marker and marker in searchable_normalized for marker in normalized_markers):
            score += 0.35
            reasons.append("workspace marker appears in board content")

        learned, learned_reasons = matching_workspace_boost(
            memory, route["workspaceMarkers"], route["status"], board_id, target_id
        )
        score += learned
        reasons.extend(learned_reasons)
        history = history_boost(memory, query_features, route["status"], board_id, target_id)
        if history:
            score += history
            reasons.append("similar confirmed routes")

        compile_lists = {status: name for status, name in list_map.items()}
        candidates.append(
            {
                "projectName": board.get("projectName"),
                "boardId": board_id,
                "boardName": board.get("item", {}).get("name"),
                "listId": target_id,
                "listName": target_name,
                "status": route["status"],
                "score": score,
                "reasons": reasons,
                "compileConfig": {
                    "boardId": board_id,
                    "lists": compile_lists,
                    "taskListName": memory["preferences"].get("taskListName") or "下一步",
                },
            }
        )

    if len(candidates) == 1:
        candidates[0]["score"] += 0.5
        candidates[0]["reasons"].append("only routable board")
    for candidate in candidates:
        candidate["score"] = round(min(1.0, candidate["score"]), 4)
    candidates.sort(key=lambda item: item["score"], reverse=True)

    threshold = float(memory["preferences"].get("autoRouteThreshold", 0.72))
    required_margin = float(memory["preferences"].get("ambiguityMargin", 0.12))
    top = candidates[0] if candidates else None
    runner_up = candidates[1]["score"] if len(candidates) > 1 else 0.0
    margin = round((top["score"] - runner_up) if top else 0.0, 4)
    selected = top if top and top["score"] >= threshold and (len(candidates) == 1 or margin >= required_margin) else None
    return {
        "schemaVersion": 1,
        "snapshotRefreshedAt": snapshot_raw.get("refreshedAt"),
        "selected": deepcopy(selected),
        "needsConfirmation": selected is None,
        "confidence": selected["score"] if selected else (top["score"] if top else 0.0),
        "margin": margin,
        "candidates": candidates[:5],
    }


def board_snapshot_for(snapshot: dict[str, Any], board_id: str) -> dict[str, Any]:
    board = next((item for item in snapshot.get("boards", []) if str(item.get("item", {}).get("id")) == board_id), None)
    if not board:
        raise ContextError(f"Selected board not found in offline snapshot: {board_id}")
    return {"item": board["item"], "included": board["included"]}


def persist_route(paths: dict[str, Path], snapshot: dict[str, Any], result: dict[str, Any]) -> None:
    selected = result.get("selected")
    if not selected:
        for key in ("route", "board"):
            if paths[key].exists():
                paths[key].unlink()
        return
    atomic_write_json(paths["route"], selected["compileConfig"])
    atomic_write_json(paths["board"], board_snapshot_for(snapshot, str(selected["boardId"])))


def select_route(snapshot: dict[str, Any], memory: dict[str, Any], raw: Any) -> dict[str, Any]:
    """Persist a user-confirmed route when automatic routing is ambiguous."""
    if not isinstance(raw, dict):
        raise ContextError("selection input must be a JSON object")
    allowed = {"boardId", "listId", "status"}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ContextError(f"selection input contains unsupported fields: {', '.join(unknown)}")
    board_id = require_string(raw.get("boardId"), "selection.boardId")
    list_id = require_string(raw.get("listId"), "selection.listId")
    status = str(raw.get("status") or "todo")
    if status not in STATUSES:
        raise ContextError(f"selection.status must be one of {', '.join(STATUSES)}")
    board = next(
        (item for item in snapshot.get("boards", []) if str(item.get("item", {}).get("id")) == board_id),
        None,
    )
    if not board:
        raise ContextError(f"Selected board not found in offline snapshot: {board_id}")
    lists = [item for item in board.get("included", {}).get("lists", []) if isinstance(item, dict)]
    target = next((item for item in lists if str(item.get("id")) == list_id), None)
    if not target:
        raise ContextError(f"Selected list not found on board {board_id}: {list_id}")
    list_map, _ = infer_list_map(board, memory)
    list_map[status] = str(target.get("name"))
    selected = {
        "projectName": board.get("projectName"),
        "boardId": board_id,
        "boardName": board.get("item", {}).get("name"),
        "listId": list_id,
        "listName": target.get("name"),
        "status": status,
        "score": 1.0,
        "reasons": ["user-confirmed ambiguous route"],
        "compileConfig": {
            "boardId": board_id,
            "lists": list_map,
            "taskListName": memory["preferences"].get("taskListName") or "下一步",
        },
    }
    return {
        "schemaVersion": 1,
        "snapshotRefreshedAt": snapshot.get("refreshedAt"),
        "selected": selected,
        "needsConfirmation": False,
        "confidence": 1.0,
        "margin": 1.0,
        "candidates": [selected],
    }


def validate_learning_input(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ContextError("learning input must be a JSON object")
    required = ("title", "status", "boardId", "listId", "listName")
    for key in required:
        require_string(raw.get(key), f"learning.{key}")
    status = str(raw["status"])
    if status not in STATUSES:
        raise ContextError(f"learning.status must be one of {', '.join(STATUSES)}")
    return {
        "title": require_string(raw["title"], "learning.title"),
        "summary": require_string(raw["summary"], "learning.summary") if raw.get("summary") else "",
        "status": status,
        "workspaceMarkers": string_list(raw.get("workspaceMarkers"), "learning.workspaceMarkers"),
        "boardId": require_string(raw["boardId"], "learning.boardId"),
        "listId": require_string(raw["listId"], "learning.listId"),
        "listName": require_string(raw["listName"], "learning.listName"),
        "cardId": require_string(raw["cardId"], "learning.cardId") if raw.get("cardId") else None,
    }


def learn_route(memory: dict[str, Any], raw: Any, learned_at: str | None = None) -> dict[str, Any]:
    learning = validate_learning_input(raw)
    timestamp = learned_at or utc_now()
    updated = deepcopy(memory)
    for marker in learning["workspaceMarkers"]:
        normalized_marker = normalize(marker)
        existing = next(
            (
                item
                for item in updated["workspaceRoutes"]
                if isinstance(item, dict)
                and normalize(str(item.get("marker") or "")) == normalized_marker
                and item.get("status") == learning["status"]
                and str(item.get("boardId")) == learning["boardId"]
                and str(item.get("listId")) == learning["listId"]
            ),
            None,
        )
        if existing:
            existing["useCount"] = int(existing.get("useCount") or 0) + 1
            existing["lastUsedAt"] = timestamp
            existing["listName"] = learning["listName"]
        else:
            updated["workspaceRoutes"].append(
                {
                    "marker": marker,
                    "status": learning["status"],
                    "boardId": learning["boardId"],
                    "listId": learning["listId"],
                    "listName": learning["listName"],
                    "useCount": 1,
                    "lastUsedAt": timestamp,
                }
            )
    history = {**learning, "recordedAt": timestamp}
    updated["routingHistory"] = [*updated["routingHistory"], history][-200:]
    updated["updatedAt"] = timestamp
    return updated


def snapshot_age_minutes(snapshot: dict[str, Any]) -> float | None:
    value = snapshot.get("refreshedAt")
    if not isinstance(value, str):
        return None
    try:
        refreshed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (datetime.now(timezone.utc) - refreshed).total_seconds() / 60.0)


def write_or_print(payload: Any, output: Path | None) -> None:
    if output:
        atomic_write_json(output, payload)
        print(f"wrote {output}")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, help="Override the global $CODEX_HOME/to-kanban state directory")
    sub = parser.add_subparsers(required=True)

    command = sub.add_parser("init", help="Create the global personalization memory if missing")
    command.set_defaults(action="init")

    command = sub.add_parser("refresh", help="Fetch all accessible Planka boards into the offline snapshot")
    command.add_argument("--planka-cli", type=Path)
    command.set_defaults(action="refresh")

    command = sub.add_parser("route", help="Route one conversation task using the offline snapshot and memory")
    command.add_argument("--input", type=Path, required=True)
    command.add_argument("--output", type=Path)
    command.set_defaults(action="route")

    command = sub.add_parser("select", help="Persist a user-confirmed board/list after ambiguous routing")
    command.add_argument("--input", type=Path, required=True)
    command.add_argument("--output", type=Path)
    command.set_defaults(action="select")

    command = sub.add_parser("learn", help="Record one confirmed successful route in global memory")
    command.add_argument("--input", type=Path, required=True)
    command.set_defaults(action="learn")

    command = sub.add_parser("status", help="Report global memory and offline snapshot freshness")
    command.set_defaults(action="status")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = state_paths(args.state_dir)
    try:
        memory = load_memory(paths["memory"])
        if args.action == "init":
            write_or_print({key: str(value) for key, value in paths.items()}, None)
        elif args.action == "refresh":
            snapshot = refresh_snapshot(paths, args.planka_cli)
            write_or_print(
                {
                    "ok": True,
                    "snapshotPath": str(paths["snapshot"]),
                    "refreshedAt": snapshot["refreshedAt"],
                    "projectCount": len(snapshot["projects"]),
                    "boardCount": len(snapshot["boards"]),
                },
                None,
            )
        elif args.action == "route":
            snapshot = load_json(paths["snapshot"])
            result = route_task(snapshot, memory, load_json(args.input))
            persist_route(paths, snapshot, result)
            result["statePaths"] = {key: str(value) for key, value in paths.items() if key != "root"}
            write_or_print(result, args.output)
        elif args.action == "select":
            snapshot = load_json(paths["snapshot"])
            result = select_route(snapshot, memory, load_json(args.input))
            persist_route(paths, snapshot, result)
            result["statePaths"] = {key: str(value) for key, value in paths.items() if key != "root"}
            write_or_print(result, args.output)
        elif args.action == "learn":
            updated = learn_route(memory, load_json(args.input))
            atomic_write_json(paths["memory"], updated)
            write_or_print(
                {
                    "ok": True,
                    "memoryPath": str(paths["memory"]),
                    "historyCount": len(updated["routingHistory"]),
                    "workspaceRouteCount": len(updated["workspaceRoutes"]),
                },
                None,
            )
        elif args.action == "status":
            snapshot = load_json(paths["snapshot"]) if paths["snapshot"].exists() else None
            write_or_print(
                {
                    "memoryPath": str(paths["memory"]),
                    "snapshotPath": str(paths["snapshot"]),
                    "snapshotExists": snapshot is not None,
                    "snapshotRefreshedAt": snapshot.get("refreshedAt") if snapshot else None,
                    "snapshotAgeMinutes": round(snapshot_age_minutes(snapshot), 2) if snapshot and snapshot_age_minutes(snapshot) is not None else None,
                    "boardCount": len(snapshot.get("boards", [])) if snapshot else 0,
                    "historyCount": len(memory["routingHistory"]),
                    "workspaceRouteCount": len(memory["workspaceRoutes"]),
                },
                None,
            )
        return 0
    except ContextError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
