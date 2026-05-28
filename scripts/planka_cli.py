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


def find_existing_card(snapshot, board_id: str, list_id: str | None, title: str):
    cards = snapshot.get("included", {}).get("cards", [])
    candidates = [card for card in cards if card.get("boardId") == board_id and card.get("name") == title]
    if list_id:
        in_list = [card for card in candidates if card.get("listId") == list_id]
        if len(in_list) == 1:
            return in_list[0]
        if len(in_list) > 1:
            ids = ", ".join(card["id"] for card in in_list)
            raise SystemExit(f"Multiple cards with same title in target list: {ids}")
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        ids = ", ".join(card["id"] for card in candidates)
        raise SystemExit(f"Multiple cards with same title on board: {ids}")
    return None


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

    snapshot = {"included": {"cards": []}} if board.get("id") is None else client.request(
        "GET",
        f"/api/boards/{urllib.parse.quote(board['id'])}",
    )
    existing_card = find_existing_card(snapshot, board["id"], target_list.get("id"), title)
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
            }
        )
        return {
            "dryRun": True,
            "project": {"id": project["id"], "name": project["name"]} if project else None,
            "board": {"id": board["id"], "name": board["name"]},
            "list": {"id": target_list.get("id"), "name": target_list.get("name")},
            "existingCardId": existing_card.get("id") if existing_card else None,
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

    if tasks and final_card["item"].get("type") != "project":
        raise SystemExit("Published card has tasks but is not type=project")
    if tasks and not final_task_lists:
        raise SystemExit("Published card is missing task list after create")

    return {
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
        "createdBoard": created_board,
        "createdTaskList": created_task_list,
        "createdTaskCount": len(created_tasks),
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
    payload = {"text": args.text}
    print_json(client.request("POST", f"/api/cards/{args.card_id}/comments", payload))


def cmd_publish_card(args):
    client = make_client()
    spec = load_json_arg(args)
    print_json(publish_card(client, spec, dry_run=args.dry_run, update_existing=not args.no_update_existing))


def cmd_ensure_project_managers(args):
    client = make_client()
    spec = load_json_arg(args)
    print_json(ensure_project_managers(client, spec))


def cmd_raw(args):
    client = make_client()
    payload = json.loads(args.data) if args.data else None
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
    p.add_argument("--card-id", required=True)
    p.add_argument("--text", required=True)
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

    p = sub.add_parser("ensure-project-managers")
    p.add_argument("--file", help="UTF-8 JSON spec")
    p.add_argument("--stdin", action="store_true", help="Read UTF-8 JSON spec from stdin")
    p.set_defaults(func=cmd_ensure_project_managers)

    p = sub.add_parser("raw")
    p.add_argument("--method", required=True)
    p.add_argument("--path", required=True)
    p.add_argument("--data")
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
