#!/usr/bin/env python3
"""Small dependency-free PLANKA API helper for Codex skills."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid


SECRET_KEYS = {"password", "token", "apiKey", "api_key", "pendingToken", "Authorization"}


class PlankaError(RuntimeError):
    def __init__(self, status: int | None, message: str, body: object | None = None):
        super().__init__(message)
        self.status = status
        self.body = body


def redact(value):
    if isinstance(value, dict):
        return {k: ("<redacted>" if k in SECRET_KEYS else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def print_json(value):
    print(json.dumps(redact(value), ensure_ascii=True, indent=2, sort_keys=True))


def env(name: str, required: bool = True) -> str | None:
    value = os.environ.get(name)
    if required and not value:
        raise SystemExit(f"Missing environment variable: {name}")
    return value


class PlankaClient:
    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(self, method: str, path: str, data: dict | None = None, token: str | None = None):
        url = self.base_url + path
        body = None
        headers = {"Accept": "application/json"}
        bearer = token if token is not None else self.token
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        if data is not None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"

        req = urllib.request.Request(url, data=body, method=method.upper(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                parsed = raw
            message = f"HTTP {exc.code}"
            if isinstance(parsed, dict) and parsed.get("message"):
                message += f": {parsed['message']}"
            raise PlankaError(exc.code, message, parsed) from exc

    def request_multipart(
        self,
        method: str,
        path: str,
        fields: dict,
        token: str | None = None,
    ):
        boundary = f"----codex-planka-{uuid.uuid4().hex}"
        chunks = []
        for key, value in fields.items():
            chunks.append(f"--{boundary}\r\n".encode("ascii"))
            chunks.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("ascii"))
            chunks.append(str(value).encode("utf-8"))
            chunks.append(b"\r\n")
        chunks.append(f"--{boundary}--\r\n".encode("ascii"))

        headers = {
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }
        bearer = token if token is not None else self.token
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"

        req = urllib.request.Request(
            self.base_url + path,
            data=b"".join(chunks),
            method=method.upper(),
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                parsed = raw
            message = f"HTTP {exc.code}"
            if isinstance(parsed, dict) and parsed.get("message"):
                message += f": {parsed['message']}"
            raise PlankaError(exc.code, message, parsed) from exc

    def login(self, username: str, password: str):
        payload = {
            "emailOrUsername": username,
            "password": password,
            "withHttpOnlyToken": False,
        }
        data = self.request("POST", "/api/access-tokens", payload, token=None)
        self.token = data["item"]
        return self.token


def decode_jwt_subject(token: str | None) -> str | None:
    if not token or token.count(".") < 2:
        return None
    part = token.split(".")[1]
    part += "=" * (-len(part) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(part.encode("ascii")).decode("utf-8"))
        return payload.get("sub")
    except Exception:
        return None


def make_client() -> PlankaClient:
    base_url = env("PLANKA_BASE_URL")
    token = os.environ.get("PLANKA_API_KEY") or os.environ.get("PLANKA_TOKEN")
    client = PlankaClient(base_url, token)
    if not token:
        username = env("PLANKA_USERNAME")
        password = env("PLANKA_PASSWORD")
        client.login(username, password)
    return client


def load_json_arg(args):
    if getattr(args, "file", None):
        with open(args.file, "r", encoding="utf-8-sig") as handle:
            return json.load(handle)

    if getattr(args, "stdin", False):
        return json.load(sys.stdin)

    raise SystemExit("Provide --file <utf8-json> or --stdin")


def load_optional_json_payload(args):
    if getattr(args, "data", None):
        return json.loads(args.data)
    if getattr(args, "file", None) or getattr(args, "stdin", False):
        return load_json_arg(args)
    return None


def require_string(data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"Missing required string field: {key}")
    return value.strip()


def optional_string(data: dict, key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise SystemExit(f"Field must be a string: {key}")
    return value


def ensure_list_of_strings(data: dict, key: str) -> list[str]:
    value = data.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SystemExit(f"Field must be a list of strings: {key}")
    return [item for item in value if item.strip()]


def find_exact(records, field, value):
    matches = [record for record in records if record.get(field) == value]
    if len(matches) > 1:
        ids = ", ".join(record["id"] for record in matches)
        raise SystemExit(f"Ambiguous {field}={value!r}; matching ids: {ids}")
    return matches[0] if matches else None


def max_position(records) -> float:
    positions = [record.get("position") or 0 for record in records]
    return max(positions) if positions else 0


def summarize_error(exc):
    if isinstance(exc, PlankaError):
        return {
            "type": "PlankaError",
            "status": exc.status,
            "message": str(exc),
            "body": exc.body,
        }
    if isinstance(exc, SystemExit):
        return {
            "type": "SystemExit",
            "message": str(exc.code),
        }
    return {
        "type": type(exc).__name__,
        "message": str(exc),
    }


def resolve_project_and_board(client: PlankaClient, spec: dict, dry_run: bool):
    projects_payload = client.request("GET", "/api/projects")
    projects = projects_payload.get("items", [])
    boards = projects_payload.get("included", {}).get("boards", [])

    project_id = optional_string(spec, "projectId")
    project_name = optional_string(spec, "project")
    board_id = optional_string(spec, "boardId")
    board_name = optional_string(spec, "board")
    create_board_if_missing = bool(spec.get("createBoardIfMissing", False))

    project = None
    if project_id:
        project = find_exact(projects, "id", project_id)
        if not project:
            raise SystemExit(f"Project not found: {project_id}")
    elif project_name:
        project = find_exact(projects, "name", project_name)
        if not project:
            raise SystemExit(f"Project not found: {project_name}")
    elif create_board_if_missing and len(projects) == 1:
        project = projects[0]

    if board_id:
        board = find_exact(boards, "id", board_id)
    elif board_name:
        candidates = boards
        if project:
            candidates = [board for board in boards if board.get("projectId") == project["id"]]
        board = find_exact(candidates, "name", board_name)
    else:
        raise SystemExit("Missing board or boardId")

    created_board = False
    planned_board_create = False
    if not board:
        if not create_board_if_missing or not board_name:
            raise SystemExit(f"Board not found: {board_id or board_name}")

        if not project:
            raise SystemExit("Creating a missing board requires project or projectId")

        project_boards = [item for item in boards if item.get("projectId") == project["id"]]
        position = spec.get("boardPosition", max_position(project_boards) + 65536)
        if dry_run:
            planned_board_create = True
            board = {
                "id": None,
                "name": board_name,
                "projectId": project["id"],
                "position": position,
            }
        else:
            try:
                board = client.request_multipart(
                    "POST",
                    f"/api/projects/{urllib.parse.quote(project['id'])}/boards",
                    {
                        "position": position,
                        "name": board_name,
                    },
                )["item"]
            except PlankaError as exc:
                if exc.status == 404:
                    raise SystemExit(
                        "Board creation failed: project not found or current user lacks "
                        "project-manager permission"
                    ) from exc
                raise
            created_board = True

    if not project:
        project = find_exact(projects, "id", board["projectId"])

    return project, board, created_board, planned_board_create


def resolve_or_plan_list(client: PlankaClient, board_id: str, spec: dict, dry_run: bool):
    list_id = optional_string(spec, "listId")
    list_name = optional_string(spec, "list") or "To Do"
    if board_id is None and dry_run:
        return {
            "id": None,
            "name": list_name,
            "type": "active",
            "position": spec.get("listPosition", 65536),
        }, True

    snapshot = client.request("GET", f"/api/boards/{urllib.parse.quote(board_id)}")
    lists = snapshot.get("included", {}).get("lists", [])
    active_lists = [item for item in lists if item.get("type") == "active"]

    target = find_exact(lists, "id", list_id) if list_id else find_exact(active_lists, "name", list_name)
    if list_id and not target:
        raise SystemExit(f"List not found: {list_id}")

    planned_create = False
    if not target:
        if dry_run:
            planned_create = True
            target = {
                "id": None,
                "name": list_name,
                "type": "active",
                "position": max_position(active_lists) + 65536,
            }
        else:
            target = client.request(
                "POST",
                f"/api/boards/{urllib.parse.quote(board_id)}/lists",
                {
                    "type": "active",
                    "position": max_position(active_lists) + 65536,
                    "name": list_name,
                },
            )["item"]

    if target.get("type") != "active":
        raise SystemExit(f"Target list is not active: {target.get('name') or target.get('type')}")

    return target, planned_create


def resolve_existing_list(snapshot: dict, list_id: str | None = None, list_name: str | None = None, label: str = "list"):
    lists = snapshot.get("included", {}).get("lists", [])
    active_lists = [item for item in lists if item.get("type") == "active"]
    if list_id:
        target = find_exact(lists, "id", list_id)
        if not target:
            raise SystemExit(f"{label} not found: {list_id}")
        return target
    if list_name:
        target = find_exact(active_lists, "name", list_name)
        if not target:
            raise SystemExit(f"{label} not found: {list_name}")
        return target
    return None


def resolve_move_target_list(snapshot: dict, spec: dict):
    target_list_id = optional_string(spec, "moveToListId") or optional_string(spec, "targetListId")
    target_list_name = optional_string(spec, "moveToList") or optional_string(spec, "targetList")
    return resolve_existing_list(snapshot, target_list_id, target_list_name, "target list")


def source_list_from_spec(snapshot: dict, spec: dict):
    source_list_id = optional_string(spec, "sourceListId")
    source_list_name = optional_string(spec, "sourceList")
    return resolve_existing_list(snapshot, source_list_id, source_list_name, "source list")


def find_cards_by_title(snapshot, board_id: str, title: str):
    cards = snapshot.get("included", {}).get("cards", [])
    return [card for card in cards if card.get("boardId") == board_id and card.get("name") == title]


def find_existing_card(snapshot, board_id: str, list_id: str | None, title: str, allow_board_fallback: bool = False):
    candidates = find_cards_by_title(snapshot, board_id, title)
    if list_id:
        in_list = [card for card in candidates if card.get("listId") == list_id]
        if len(in_list) == 1:
            return in_list[0]
        if len(in_list) > 1:
            ids = ", ".join(card["id"] for card in in_list)
            raise SystemExit(f"Multiple cards with same title in target list: {ids}")
        if not allow_board_fallback:
            return None
    if allow_board_fallback:
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            ids = ", ".join(card["id"] for card in candidates)
            raise SystemExit(f"Multiple cards with same title on board: {ids}")
    return None


def resolve_card_reference(client: PlankaClient, spec: dict):
    card_id = optional_string(spec, "cardId")
    if card_id:
        card_payload = client.request("GET", f"/api/cards/{urllib.parse.quote(card_id)}")
        card = card_payload["item"]
        board_id = card.get("boardId") or optional_string(spec, "boardId")
        if not board_id:
            raise SystemExit("Card payload does not include boardId; provide boardId")
        board_payload = client.request("GET", f"/api/boards/{urllib.parse.quote(board_id)}")
        board = board_payload.get("item") if isinstance(board_payload.get("item"), dict) else None
        if not board:
            board = {"id": board_id, "name": None}
        return None, board, board_payload, card

    title = require_string(spec, "title")
    project, board, _created_board, _planned_board_create = resolve_project_and_board(client, spec, dry_run=False)
    snapshot = client.request("GET", f"/api/boards/{urllib.parse.quote(board['id'])}")
    source_list = source_list_from_spec(snapshot, spec)
    candidates = find_cards_by_title(snapshot, board["id"], title)
    if source_list:
        candidates = [card for card in candidates if card.get("listId") == source_list["id"]]
    if len(candidates) == 0:
        location = f" in source list {source_list['name']!r}" if source_list else ""
        raise SystemExit(f"Card not found by title {title!r}{location}")
    if len(candidates) > 1:
        ids = ", ".join(card["id"] for card in candidates)
        raise SystemExit(f"Multiple cards match title {title!r}; matching ids: {ids}")
    return project, board, snapshot, candidates[0]


def list_name_for_card(snapshot: dict, card: dict):
    current_list = find_exact(snapshot.get("included", {}).get("lists", []), "id", card.get("listId"))
    return current_list.get("name") if current_list else None


def comments_for_card(client: PlankaClient, card_id: str):
    payload = client.request("GET", f"/api/cards/{urllib.parse.quote(card_id)}/comments")
    return payload.get("items", [])


def comment_text_exists(comments: list[dict], text: str):
    return any(item.get("text") == text for item in comments)


def summarize_card(client: PlankaClient, card_id: str, include_comments: bool = False):
    card_payload = client.request("GET", f"/api/cards/{urllib.parse.quote(card_id)}")
    card = card_payload["item"]
    tasks = card_payload.get("included", {}).get("tasks", [])
    board_id = card.get("boardId")
    list_name = None
    if board_id:
        snapshot = client.request("GET", f"/api/boards/{urllib.parse.quote(board_id)}")
        list_name = list_name_for_card(snapshot, card)
    result = {
        "id": card["id"],
        "name": card.get("name"),
        "boardId": board_id,
        "listId": card.get("listId"),
        "list": list_name,
        "type": card.get("type"),
        "taskCount": len(tasks),
        "completedTaskCount": sum(1 for task in tasks if task.get("isCompleted")),
        "commentsTotal": card.get("commentsTotal"),
    }
    if include_comments:
        comments = comments_for_card(client, card_id)
        result["commentCount"] = len(comments)
        result["lastCommentText"] = comments[-1].get("text") if comments else None
    return result


def validate_publish_spec(spec: dict):
    if not isinstance(spec, dict):
        raise SystemExit("Publish spec must be a JSON object")
    require_string(spec, "title")
    ensure_list_of_strings(spec, "tasks")
    card_type = spec.get("type", "project")
    if card_type not in {"project", "story"}:
        raise SystemExit("type must be project or story")
    if card_type == "story" and ensure_list_of_strings(spec, "tasks"):
        raise SystemExit("Use type=project for cards with task lists; story cards do not render checklists")


def resolve_project(client: PlankaClient, spec: dict):
    projects_payload = client.request("GET", "/api/projects")
    projects = projects_payload.get("items", [])
    project_id = optional_string(spec, "projectId")
    project_name = optional_string(spec, "project")

    if project_id:
        project = find_exact(projects, "id", project_id)
        if not project:
            raise SystemExit(f"Project not found: {project_id}")
        return project

    if project_name:
        project = find_exact(projects, "name", project_name)
        if not project:
            raise SystemExit(f"Project not found: {project_name}")
        return project

    if len(projects) == 1:
        return projects[0]

    raise SystemExit("Missing project or projectId")


def user_identity_match(user: dict, username: str | None, email: str | None):
    return (username and user.get("username") == username) or (email and user.get("email") == email)


def ensure_user(client: PlankaClient, user_spec: dict):
    username = optional_string(user_spec, "username")
    email = optional_string(user_spec, "email")
    if not username and not email:
        raise SystemExit("Each user requires username or email")

    users_payload = client.request("GET", "/api/users")
    users = users_payload.get("items", [])
    user = next((item for item in users if user_identity_match(item, username, email)), None)
    created = False
    updated = False
    preserve_role = bool(user_spec.get("preserveRole", False))

    desired_role = user_spec.get("role", "projectOwner")
    if desired_role not in {"admin", "projectOwner", "boardUser"}:
        raise SystemExit(f"Invalid user role: {desired_role}")

    if not user:
        payload = {
            "email": require_string(user_spec, "email"),
            "password": require_string(user_spec, "password"),
            "role": desired_role,
            "name": user_spec.get("name") or username or email,
            "username": username,
            "language": user_spec.get("language", "zh-CN"),
        }
        for key in [
            "phone",
            "organization",
            "subscribeToOwnCards",
            "subscribeToCardWhenCommenting",
            "turnOffRecentCardHighlighting",
        ]:
            if key in user_spec:
                payload[key] = user_spec[key]
        user = client.request("POST", "/api/users", payload)["item"]
        created = True
    elif not preserve_role and user.get("role") != desired_role:
        user = client.request("PATCH", f"/api/users/{urllib.parse.quote(user['id'])}", {"role": desired_role})[
            "item"
        ]
        updated = True

    return user, created, updated


def ensure_project_managers(client: PlankaClient, spec: dict):
    project = resolve_project(client, spec)
    users_spec = spec.get("users")
    if not isinstance(users_spec, list) or not users_spec:
        raise SystemExit("Spec requires a non-empty users array")

    results = []
    for item in users_spec:
        if not isinstance(item, dict):
            raise SystemExit("Each users entry must be an object")
        user, created_user, updated_user = ensure_user(client, item)
        manager_created = False
        manager_exists = False
        try:
            client.request(
                "POST",
                f"/api/projects/{urllib.parse.quote(project['id'])}/project-managers",
                {"userId": user["id"]},
            )
            manager_created = True
        except PlankaError as exc:
            if exc.status == 409:
                manager_exists = True
            else:
                raise

        results.append(
            {
                "user": {
                    "id": user["id"],
                    "username": user.get("username"),
                    "email": user.get("email"),
                    "role": user.get("role"),
                },
                "createdUser": created_user,
                "updatedUser": updated_user,
                "createdProjectManager": manager_created,
                "alreadyProjectManager": manager_exists,
            }
        )

    return {
        "project": {"id": project["id"], "name": project["name"]},
        "users": results,
    }


def publish_card(client: PlankaClient, spec: dict, dry_run: bool = False, update_existing: bool = True):
    validate_publish_spec(spec)
    project, board, created_board, planned_board_create = resolve_project_and_board(client, spec, dry_run)
    target_list, would_create_list = resolve_or_plan_list(client, board["id"], spec, dry_run)
    title = require_string(spec, "title")
    description = optional_string(spec, "description")
    due_date = optional_string(spec, "dueDate")
    card_type = spec.get("type", "project")
    tasks = ensure_list_of_strings(spec, "tasks")
    task_list_name = optional_string(spec, "taskList") or "Tasks"
    move_existing_to_target = bool(spec.get("moveExistingToTargetList", False))

    snapshot = {"included": {"cards": []}} if board.get("id") is None else client.request(
        "GET",
        f"/api/boards/{urllib.parse.quote(board['id'])}",
    )
    same_title_cards = find_cards_by_title(snapshot, board["id"], title)
    same_title_elsewhere = [
        card for card in same_title_cards if target_list.get("id") and card.get("listId") != target_list.get("id")
    ]
    existing_card = find_existing_card(
        snapshot,
        board["id"],
        target_list.get("id"),
        title,
        allow_board_fallback=move_existing_to_target,
    )
    planned_actions = []

    if dry_run:
        if planned_board_create:
            planned_actions.append({"action": "create-board", "name": board["name"]})
        if would_create_list:
            planned_actions.append({"action": "create-list", "name": target_list["name"]})
        planned_actions.append(
            {
                "action": "update-card" if existing_card and update_existing else "create-card",
                "title": title,
                "type": card_type,
                "taskCount": len(tasks),
                "targetList": target_list.get("name"),
            }
        )
        if existing_card and target_list.get("id") and existing_card.get("listId") != target_list.get("id"):
            planned_actions.append(
                {
                    "action": "move-existing-card",
                    "cardId": existing_card["id"],
                    "fromListId": existing_card.get("listId"),
                    "toListId": target_list.get("id"),
                    "toList": target_list.get("name"),
                }
            )
        return {
            "dryRun": True,
            "project": {"id": project["id"], "name": project["name"]} if project else None,
            "board": {"id": board["id"], "name": board["name"]},
            "list": {"id": target_list.get("id"), "name": target_list.get("name")},
            "existingCardId": existing_card.get("id") if existing_card else None,
            "sameTitleElsewhere": [
                {"id": card["id"], "listId": card.get("listId")} for card in same_title_elsewhere
            ],
            "plannedActions": planned_actions,
        }

    card_payload = {
        "type": card_type,
        "name": title,
    }
    if description is not None:
        card_payload["description"] = description
    if due_date is not None:
        card_payload["dueDate"] = due_date
        card_payload["isDueCompleted"] = bool(spec.get("isDueCompleted", False))

    created_card = False
    updated_card = False
    if existing_card:
        card = existing_card
        if update_existing:
            update_payload = dict(card_payload)
            if card.get("type") != card_type:
                update_payload["type"] = card_type
            card = client.request("PATCH", f"/api/cards/{urllib.parse.quote(card['id'])}", update_payload)[
                "item"
            ]
            updated_card = True
        if target_list.get("id") and card.get("listId") != target_list["id"]:
            if not move_existing_to_target:
                raise SystemExit(
                    "Existing card is outside the target list; set moveExistingToTargetList=true to move it"
                )
            list_cards = [
                item
                for item in snapshot.get("included", {}).get("cards", [])
                if item.get("listId") == target_list["id"]
            ]
            card = client.request(
                "PATCH",
                f"/api/cards/{urllib.parse.quote(card['id'])}",
                {
                    "listId": target_list["id"],
                    "position": spec.get("position", max_position(list_cards) + 65536),
                },
            )["item"]
    else:
        list_cards = [
            card
            for card in snapshot.get("included", {}).get("cards", [])
            if card.get("listId") == target_list["id"]
        ]
        card_payload["position"] = spec.get("position", max_position(list_cards) + 65536)
        card = client.request(
            "POST", f"/api/lists/{urllib.parse.quote(target_list['id'])}/cards", card_payload
        )["item"]
        created_card = True

    card_snapshot = client.request("GET", f"/api/cards/{urllib.parse.quote(card['id'])}")
    task_lists = card_snapshot.get("included", {}).get("taskLists", [])
    task_list = find_exact(task_lists, "name", task_list_name)
    created_task_list = False
    if tasks and not task_list:
        task_list = client.request(
            "POST",
            f"/api/cards/{urllib.parse.quote(card['id'])}/task-lists",
            {
                "position": max_position(task_lists) + 65536,
                "name": task_list_name,
                "showOnFrontOfCard": True,
                "hideCompletedTasks": False,
            },
        )["item"]
        created_task_list = True

    created_tasks = []
    if tasks:
        card_snapshot = client.request("GET", f"/api/cards/{urllib.parse.quote(card['id'])}")
        existing_tasks = [
            task
            for task in card_snapshot.get("included", {}).get("tasks", [])
            if task.get("taskListId") == task_list["id"]
        ]
        existing_names = {task.get("name") for task in existing_tasks}
        next_position = max_position(existing_tasks)
        for task_name in tasks:
            if task_name in existing_names:
                continue
            next_position += 65536
            task = client.request(
                "POST",
                f"/api/task-lists/{urllib.parse.quote(task_list['id'])}/tasks",
                {
                    "position": next_position,
                    "name": task_name,
                    "isCompleted": False,
                },
            )["item"]
            created_tasks.append(task)

    final_card = client.request("GET", f"/api/cards/{urllib.parse.quote(card['id'])}")
    final_task_lists = final_card.get("included", {}).get("taskLists", [])
    final_tasks = final_card.get("included", {}).get("tasks", [])
    final_task_list = find_exact(final_task_lists, "name", task_list_name) if tasks else None
    final_tasks_in_list = [
        task for task in final_tasks if final_task_list and task.get("taskListId") == final_task_list["id"]
    ]
    final_task_names = {task.get("name") for task in final_tasks_in_list}
    missing_tasks = [task_name for task_name in tasks if task_name not in final_task_names]

    if tasks and final_card["item"].get("type") != "project":
        raise SystemExit("Published card has tasks but is not type=project")
    if tasks and not final_task_lists:
        raise SystemExit("Published card is missing task list after create")
    if missing_tasks:
        raise SystemExit(f"Published card is missing requested tasks: {missing_tasks}")

    return {
        "ok": True,
        "dryRun": False,
        "project": {"id": project["id"], "name": project["name"]} if project else None,
        "board": {"id": board["id"], "name": board["name"]},
        "list": {"id": target_list["id"], "name": target_list.get("name")},
        "card": {
            "id": final_card["item"]["id"],
            "name": final_card["item"]["name"],
            "type": final_card["item"].get("type"),
            "created": created_card,
            "updated": updated_card,
        },
        "taskListCount": len(final_task_lists),
        "taskCount": len(final_tasks),
        "requestedTaskCount": len(tasks),
        "verifiedRequestedTaskCount": len(tasks) - len(missing_tasks),
        "missingTasks": missing_tasks,
        "sameTitleElsewhere": [
            {"id": item["id"], "listId": item.get("listId")} for item in same_title_elsewhere
        ],
        "createdBoard": created_board,
        "createdTaskList": created_task_list,
        "createdTaskCount": len(created_tasks),
    }


def requested_tasks_to_complete(spec: dict, tasks: list[dict]):
    complete_tasks = spec.get("completeTasks")
    all_tasks = bool(spec.get("allTasks", False)) or complete_tasks == "all"
    if all_tasks:
        return tasks

    task_names = spec.get("taskNames")
    if task_names is None and isinstance(complete_tasks, list):
        task_names = complete_tasks
    if task_names is None:
        return []
    if not isinstance(task_names, list) or any(not isinstance(item, str) for item in task_names):
        raise SystemExit("taskNames or completeTasks must be a list of strings, or completeTasks must be 'all'")

    wanted = [item for item in task_names if item.strip()]
    missing = [name for name in wanted if not any(task.get("name") == name for task in tasks)]
    if missing:
        raise SystemExit(f"Requested tasks not found on card: {missing}")
    return [task for task in tasks if task.get("name") in set(wanted)]


def comment_card(client: PlankaClient, spec: dict, dry_run: bool = False):
    text = optional_string(spec, "comment") or optional_string(spec, "text")
    if text is None or not text.strip():
        raise SystemExit("Missing comment text")
    _project, board, snapshot, card = resolve_card_reference(client, spec)
    mode = optional_string(spec, "commentMode") or "append-once"
    if mode not in {"append-once", "always"}:
        raise SystemExit("commentMode must be append-once or always")

    comments = comments_for_card(client, card["id"])
    already_exists = comment_text_exists(comments, text)
    should_create = mode == "always" or not already_exists

    if dry_run:
        return {
            "dryRun": True,
            "action": "comment",
            "board": {"id": board.get("id"), "name": board.get("name")},
            "card": {"id": card["id"], "name": card.get("name")},
            "list": {"id": card.get("listId"), "name": list_name_for_card(snapshot, card)},
            "commentMode": mode,
            "wouldCreateComment": should_create,
            "alreadyExists": already_exists,
        }

    created_comment = None
    if should_create:
        created_comment = client.request(
            "POST",
            f"/api/cards/{urllib.parse.quote(card['id'])}/comments",
            {"text": text},
        )["item"]

    final_comments = comments_for_card(client, card["id"])
    if not comment_text_exists(final_comments, text):
        raise SystemExit("Comment verification failed: expected text was not found after write")

    return {
        "ok": True,
        "action": "comment",
        "board": {"id": board.get("id"), "name": board.get("name")},
        "card": summarize_card(client, card["id"], include_comments=True),
        "comment": {
            "created": created_comment is not None,
            "skippedBecauseExists": created_comment is None and already_exists,
            "id": created_comment.get("id") if created_comment else None,
        },
    }


def complete_card(client: PlankaClient, spec: dict, dry_run: bool = False):
    _project, board, snapshot, card = resolve_card_reference(client, spec)
    card_snapshot = client.request("GET", f"/api/cards/{urllib.parse.quote(card['id'])}")
    card = card_snapshot["item"]
    tasks = card_snapshot.get("included", {}).get("tasks", [])
    target_list = resolve_move_target_list(snapshot, spec)
    tasks_to_complete = requested_tasks_to_complete(spec, tasks)
    comment_text = optional_string(spec, "comment") or optional_string(spec, "text")
    comment_mode = optional_string(spec, "commentMode") or "append-once"
    if comment_text and comment_mode not in {"append-once", "always"}:
        raise SystemExit("commentMode must be append-once or always")

    actions = []
    if target_list:
        actions.append(
            {
                "action": "move-card",
                "needed": card.get("listId") != target_list["id"],
                "fromListId": card.get("listId"),
                "fromList": list_name_for_card(snapshot, card),
                "toListId": target_list["id"],
                "toList": target_list.get("name"),
            }
        )
    if tasks_to_complete:
        actions.append(
            {
                "action": "complete-tasks",
                "taskCount": len(tasks_to_complete),
                "alreadyCompletedCount": sum(1 for task in tasks_to_complete if task.get("isCompleted")),
            }
        )
    if comment_text:
        comments = comments_for_card(client, card["id"])
        actions.append(
            {
                "action": "comment",
                "commentMode": comment_mode,
                "alreadyExists": comment_text_exists(comments, comment_text),
            }
        )

    if dry_run:
        return {
            "dryRun": True,
            "action": "complete-card",
            "board": {"id": board.get("id"), "name": board.get("name")},
            "card": {
                "id": card["id"],
                "name": card.get("name"),
                "listId": card.get("listId"),
                "list": list_name_for_card(snapshot, card),
            },
            "plannedActions": actions,
        }

    moved = False
    if target_list and card.get("listId") != target_list["id"]:
        list_cards = [
            item
            for item in snapshot.get("included", {}).get("cards", [])
            if item.get("listId") == target_list["id"]
        ]
        card = client.request(
            "PATCH",
            f"/api/cards/{urllib.parse.quote(card['id'])}",
            {
                "listId": target_list["id"],
                "position": spec.get("position", max_position(list_cards) + 65536),
            },
        )["item"]
        moved = True

    changed_tasks = []
    for task in tasks_to_complete:
        if task.get("isCompleted"):
            continue
        changed = client.request(
            "PATCH",
            f"/api/tasks/{urllib.parse.quote(task['id'])}",
            {"isCompleted": True},
        )["item"]
        changed_tasks.append(changed)

    comment_result = None
    if comment_text:
        comment_spec = dict(spec)
        comment_spec["cardId"] = card["id"]
        comment_result = comment_card(client, comment_spec, dry_run=False)["comment"]

    final_card_payload = client.request("GET", f"/api/cards/{urllib.parse.quote(card['id'])}")
    final_card = final_card_payload["item"]
    final_tasks = final_card_payload.get("included", {}).get("tasks", [])
    final_task_by_id = {task["id"]: task for task in final_tasks}
    incomplete_requested = [
        task.get("name")
        for task in tasks_to_complete
        if not final_task_by_id.get(task["id"], {}).get("isCompleted")
    ]
    if incomplete_requested:
        raise SystemExit(f"Task completion verification failed: {incomplete_requested}")
    if target_list and final_card.get("listId") != target_list["id"]:
        raise SystemExit("Card move verification failed: card is not in target list after write")

    return {
        "ok": True,
        "action": "complete-card",
        "board": {"id": board.get("id"), "name": board.get("name")},
        "card": summarize_card(client, card["id"], include_comments=bool(comment_text)),
        "moved": moved,
        "completedTaskCount": len(changed_tasks),
        "requestedTaskCount": len(tasks_to_complete),
        "comment": comment_result,
    }


def apply_plan(client: PlankaClient, spec: dict, dry_run: bool = False):
    operations = spec.get("operations")
    if not isinstance(operations, list) or not operations:
        raise SystemExit("Plan spec requires a non-empty operations array")

    results = []
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            return {
                "ok": False,
                "dryRun": dry_run,
                "completedSteps": results,
                "failedStep": {
                    "index": index,
                    "error": {"type": "SystemExit", "message": "Each operation must be a JSON object"},
                },
            }
        try:
            action = require_string(operation, "action")
            if action == "publish-card":
                result = publish_card(
                    client,
                    operation,
                    dry_run=dry_run,
                    update_existing=not bool(operation.get("noUpdateExisting", False)),
                )
            elif action == "complete-card":
                result = complete_card(client, operation, dry_run=dry_run)
            elif action == "comment":
                result = comment_card(client, operation, dry_run=dry_run)
            else:
                raise SystemExit(f"Unsupported plan operation: {action}")
            results.append({"index": index, "action": action, "result": result})
        except (PlankaError, SystemExit) as exc:
            return {
                "ok": False,
                "dryRun": dry_run,
                "completedSteps": results,
                "failedStep": {
                    "index": index,
                    "action": operation.get("action"),
                    "error": summarize_error(exc),
                },
            }

    return {
        "ok": True,
        "dryRun": dry_run,
        "steps": results,
    }


def cmd_whoami(args):
    client = make_client()
    user_id = decode_jwt_subject(client.token)
    result = {"tokenReceived": bool(client.token), "userId": user_id}
    if user_id:
        try:
            result["user"] = client.request("GET", f"/api/users/{urllib.parse.quote(user_id)}")
        except PlankaError as exc:
            result["userLookup"] = {"status": exc.status, "body": exc.body}
    print_json(result)


def cmd_projects(args):
    client = make_client()
    print_json(client.request("GET", "/api/projects"))


def cmd_board(args):
    client = make_client()
    print_json(client.request("GET", f"/api/boards/{args.board_id}"))


def cmd_cards(args):
    client = make_client()
    print_json(client.request("GET", f"/api/lists/{args.list_id}/cards"))


def cmd_create_list(args):
    client = make_client()
    payload = {"type": args.type, "position": args.position, "name": args.name}
    print_json(client.request("POST", f"/api/boards/{args.board_id}/lists", payload))


def cmd_create_card(args):
    client = make_client()
    payload = {"type": args.type, "name": args.name}
    if args.position is not None:
        payload["position"] = args.position
    else:
        cards_payload = client.request("GET", f"/api/lists/{urllib.parse.quote(args.list_id)}/cards")
        payload["position"] = max_position(cards_payload.get("items", [])) + 65536
    if args.description is not None:
        payload["description"] = args.description
    if args.due_date is not None:
        payload["dueDate"] = args.due_date
    print_json(client.request("POST", f"/api/lists/{args.list_id}/cards", payload))


def cmd_update_card(args):
    client = make_client()
    payload = {}
    for cli_name, api_name in [
        ("board_id", "boardId"),
        ("list_id", "listId"),
        ("position", "position"),
        ("name", "name"),
        ("description", "description"),
        ("due_date", "dueDate"),
        ("is_due_completed", "isDueCompleted"),
        ("is_subscribed", "isSubscribed"),
    ]:
        value = getattr(args, cli_name)
        if value is not None:
            payload[api_name] = value
    if not payload:
        raise SystemExit("No card update fields were provided")
    print_json(client.request("PATCH", f"/api/cards/{args.card_id}", payload))


def cmd_move_card(args):
    client = make_client()
    payload = {"listId": args.list_id, "position": args.position}
    if args.board_id:
        payload["boardId"] = args.board_id
    print_json(client.request("PATCH", f"/api/cards/{args.card_id}", payload))


def cmd_comment(args):
    client = make_client()
    if args.file or args.stdin:
        spec = load_json_arg(args)
    else:
        if not args.card_id:
            raise SystemExit("Provide --card-id or a JSON spec with --file/--stdin")
        if args.text is None:
            raise SystemExit("Provide --text or a JSON spec with --file/--stdin")
        spec = {
            "cardId": args.card_id,
            "comment": args.text,
            "commentMode": "append-once" if args.skip_if_exists else "always",
        }
    print_json(comment_card(client, spec, dry_run=args.dry_run))


def cmd_publish_card(args):
    client = make_client()
    spec = load_json_arg(args)
    print_json(publish_card(client, spec, dry_run=args.dry_run, update_existing=not args.no_update_existing))


def cmd_complete_card(args):
    client = make_client()
    spec = load_json_arg(args)
    print_json(complete_card(client, spec, dry_run=args.dry_run))


def cmd_apply_plan(args):
    client = make_client()
    spec = load_json_arg(args)
    print_json(apply_plan(client, spec, dry_run=args.dry_run))


def cmd_ensure_project_managers(args):
    client = make_client()
    spec = load_json_arg(args)
    print_json(ensure_project_managers(client, spec))


def cmd_raw(args):
    client = make_client()
    payload = load_optional_json_payload(args)
    print_json(client.request(args.method, args.path, payload))


def build_parser():
    parser = argparse.ArgumentParser(description="PLANKA REST API helper")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("whoami")
    p.set_defaults(func=cmd_whoami)

    p = sub.add_parser("projects")
    p.set_defaults(func=cmd_projects)

    p = sub.add_parser("board")
    p.add_argument("--board-id", required=True)
    p.set_defaults(func=cmd_board)

    p = sub.add_parser("cards")
    p.add_argument("--list-id", required=True)
    p.set_defaults(func=cmd_cards)

    p = sub.add_parser("create-list")
    p.add_argument("--board-id", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--type", default="active", choices=["active", "closed"])
    p.add_argument("--position", type=float, default=65536)
    p.set_defaults(func=cmd_create_list)

    p = sub.add_parser("create-card")
    p.add_argument("--list-id", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--type", default="project", choices=["project", "story"])
    p.add_argument("--position", type=float)
    p.add_argument("--description")
    p.add_argument("--due-date")
    p.set_defaults(func=cmd_create_card)

    p = sub.add_parser("update-card")
    p.add_argument("--card-id", required=True)
    p.add_argument("--board-id")
    p.add_argument("--list-id")
    p.add_argument("--position", type=float)
    p.add_argument("--name")
    p.add_argument("--description")
    p.add_argument("--due-date")
    p.add_argument("--is-due-completed", type=lambda v: v.lower() == "true")
    p.add_argument("--is-subscribed", type=lambda v: v.lower() == "true")
    p.set_defaults(func=cmd_update_card)

    p = sub.add_parser("move-card")
    p.add_argument("--card-id", required=True)
    p.add_argument("--list-id", required=True)
    p.add_argument("--position", type=float, required=True)
    p.add_argument("--board-id")
    p.set_defaults(func=cmd_move_card)

    p = sub.add_parser("comment")
    p.add_argument("--card-id")
    p.add_argument("--text")
    p.add_argument("--file", help="UTF-8 JSON comment spec")
    p.add_argument("--stdin", action="store_true", help="Read UTF-8 JSON comment spec from stdin")
    p.add_argument("--dry-run", action="store_true", help="Resolve the target and duplicate status only")
    p.add_argument("--skip-if-exists", action="store_true", help="Skip creating a duplicate exact comment")
    p.set_defaults(func=cmd_comment)

    p = sub.add_parser("publish-card")
    p.add_argument("--file", help="UTF-8 JSON publish spec")
    p.add_argument("--stdin", action="store_true", help="Read UTF-8 JSON publish spec from stdin")
    p.add_argument("--dry-run", action="store_true", help="Resolve targets and show planned writes only")
    p.add_argument(
        "--no-update-existing",
        action="store_true",
        help="Do not update an existing card with the same title; still avoids duplicate tasks",
    )
    p.set_defaults(func=cmd_publish_card)

    p = sub.add_parser("complete-card")
    p.add_argument("--file", help="UTF-8 JSON complete-card spec")
    p.add_argument("--stdin", action="store_true", help="Read UTF-8 JSON complete-card spec from stdin")
    p.add_argument("--dry-run", action="store_true", help="Resolve targets and show planned writes only")
    p.set_defaults(func=cmd_complete_card)

    p = sub.add_parser("apply-plan")
    p.add_argument("--file", help="UTF-8 JSON ordered operation plan")
    p.add_argument("--stdin", action="store_true", help="Read UTF-8 JSON ordered operation plan from stdin")
    p.add_argument("--dry-run", action="store_true", help="Resolve all operations without modifying PLANKA")
    p.set_defaults(func=cmd_apply_plan)

    p = sub.add_parser("ensure-project-managers")
    p.add_argument("--file", help="UTF-8 JSON spec")
    p.add_argument("--stdin", action="store_true", help="Read UTF-8 JSON spec from stdin")
    p.set_defaults(func=cmd_ensure_project_managers)

    p = sub.add_parser("raw")
    p.add_argument("--method", required=True)
    p.add_argument("--path", required=True)
    p.add_argument("--data")
    p.add_argument("--file", help="UTF-8 JSON request body")
    p.add_argument("--stdin", action="store_true", help="Read UTF-8 JSON request body from stdin")
    p.set_defaults(func=cmd_raw)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
        return 0
    except PlankaError as exc:
        print_json({"status": exc.status, "error": str(exc), "body": exc.body})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
