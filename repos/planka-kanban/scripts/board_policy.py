"""Shared WIP policy stored in a PLANKA card; no network or local preferences."""
import hashlib
import json
import re

MARKER = "[kanban-policy:v1]"
TITLE = MARKER + " WIP 规则"
BLOCK = re.compile(r"^```kanban-policy\s*\n(.*?)\n```\s*$", re.M | re.S)


class PolicyError(ValueError):
    pass


def policy_cards(board):
    return [c for c in board.get("included", {}).get("cards", [])
            if str(c.get("name", "")).startswith(MARKER)]


def validate_policy(raw, board):
    if not isinstance(raw, dict) or set(raw) != {"schemaVersion", "wipLimit", "wipListIds"}:
        raise PolicyError("Policy requires exactly schemaVersion, wipLimit and wipListIds")
    if type(raw["schemaVersion"]) is not int or raw["schemaVersion"] != 1:
        raise PolicyError("Unsupported WIP policy schemaVersion")
    if type(raw["wipLimit"]) is not int or raw["wipLimit"] < 1:
        raise PolicyError("wipLimit must be a positive integer")
    ids = raw["wipListIds"]
    if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise PolicyError("wipListIds must be a non-empty array of unique string IDs")
    lists = board.get("included", {}).get("lists", [])
    selected = []
    for list_id in ids:
        matches = [item for item in lists if item.get("id") == list_id]
        if len(matches) != 1:
            raise PolicyError(f"WIP list ID is missing or ambiguous: {list_id}")
        selected.append(matches[0])
    names = [item.get("name") for item in selected]
    if any(not isinstance(name, str) or not name for name in names) or len(set(names)) != len(names):
        raise PolicyError("WIP list names must be non-empty and distinct")
    if any(sum(x.get("name") == name for x in lists) != 1 for name in names):
        raise PolicyError("WIP list names are ambiguous on this board")
    return {"schemaVersion": 1, "wipLimit": raw["wipLimit"], "wipListIds": sorted(ids)}


def fingerprint(policy):
    return hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_board_policy(board):
    candidates = policy_cards(board)
    if len(candidates) > 1:
        raise PolicyError("Multiple WIP policy cards; resolve duplicates before planning")
    if not candidates:
        return {"wipLimit": None, "wipLists": [], "policySource": {"kind": "missing"}}
    card = candidates[0]
    description = card.get("description") or ""
    blocks = BLOCK.findall(description)
    if len(blocks) != 1 or description.count("```kanban-policy") != 1:
        raise PolicyError("Policy card must contain exactly one kanban-policy JSON code block")
    try:
        raw = json.loads(blocks[0])
    except (TypeError, json.JSONDecodeError) as exc:
        raise PolicyError("Invalid JSON in WIP policy card") from exc
    policy = validate_policy(raw, board)
    names = {item["id"]: item["name"] for item in board["included"]["lists"]}
    return {"wipLimit": policy["wipLimit"], "wipLists": [names[i] for i in policy["wipListIds"]],
            "policySource": {"kind": "planka-card", "cardId": card["id"],
                             "fingerprint": fingerprint(policy), "wipListIds": policy["wipListIds"]}}


def render_policy(policy, previous=""):
    block = "```kanban-policy\n" + json.dumps(policy, ensure_ascii=False, indent=2) + "\n```"
    if BLOCK.search(previous):
        if previous.count("```kanban-policy") != 1:
            raise PolicyError("Cannot replace multiple policy blocks")
        return BLOCK.sub(lambda _: block, previous)
    if "```kanban-policy" in previous:
        raise PolicyError("Repair malformed policy block before updating")
    intro = previous.rstrip() or "共享 WIP 规则。此卡是看板配置，不是执行任务；技能读取此处规则。"
    return intro + "\n\n" + block + "\n"


def wip_count(board, source):
    ids = set(source.get("wipListIds", []))
    policy_ids = {c["id"] for c in policy_cards(board)}
    return sum(c.get("listId") in ids for c in board.get("included", {}).get("cards", []) if c["id"] not in policy_ids)
