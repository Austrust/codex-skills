#!/usr/bin/env python3
"""Store and resolve user-selected knowledge-base locations outside the skill folder."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from typing import Any


CONFIG_VERSION = 1


def codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def config_path() -> Path:
    override = os.environ.get("MAINTAIN_KB_CONFIG")
    if override:
        return Path(override).expanduser()
    return codex_home() / "maintain-knowledge-base" / "config.json"


def empty_config() -> dict[str, Any]:
    return {"version": CONFIG_VERSION, "default": None, "knowledge_bases": {}}


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return empty_config()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read configuration {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("knowledge_bases"), dict):
        raise ValueError(f"Invalid configuration structure: {path}")
    if data.get("version") != CONFIG_VERSION:
        raise ValueError(
            f"Unsupported configuration version {data.get('version')!r}; expected {CONFIG_VERSION}"
        )
    data.setdefault("default", None)
    return data


def save_config(data: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Configure knowledge-base locations for maintain-knowledge-base"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    show = subparsers.add_parser("show", help="Show all configured knowledge bases")
    show.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    resolve = subparsers.add_parser("resolve", help="Resolve a configured knowledge base")
    resolve.add_argument("--name", help="Resolve a named knowledge base instead of the default")
    resolve.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    set_command = subparsers.add_parser("set", help="Register or update a knowledge-base path")
    set_command.add_argument("name", help="Short stable name, for example main or laboratory")
    set_command.add_argument("path", type=Path, help="Existing knowledge-base directory")
    set_command.add_argument(
        "--default", action="store_true", help="Also make this the default knowledge base"
    )

    default = subparsers.add_parser("default", help="Select the default knowledge base")
    default.add_argument("name", help="Previously registered knowledge-base name")

    return parser


def validate_name(name: str) -> str:
    value = name.strip()
    if not value or any(character in value for character in "\\/:*?\"<>|"):
        raise ValueError("Name must be non-empty and must not contain filesystem separators")
    return value


def cmd_show(data: dict[str, Any], as_json: bool) -> int:
    payload = {
        "config_path": str(config_path()),
        "default": data.get("default"),
        "knowledge_bases": data.get("knowledge_bases", {}),
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Configuration: {payload['config_path']}")
        print(f"Default: {payload['default'] or '(not configured)'}")
        for name, record in payload["knowledge_bases"].items():
            marker = "*" if name == payload["default"] else "-"
            print(f"{marker} {name}: {record.get('path', '')}")
    return 0


def cmd_resolve(data: dict[str, Any], name: str | None, as_json: bool) -> int:
    selected = name or data.get("default")
    if not selected:
        payload = {
            "configured": False,
            "reason": "no-default-knowledge-base",
            "config_path": str(config_path()),
        }
        if as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("No default knowledge base is configured.", file=sys.stderr)
        return 3

    record = data.get("knowledge_bases", {}).get(selected)
    if not isinstance(record, dict) or not record.get("path"):
        payload = {
            "configured": False,
            "reason": "unknown-knowledge-base",
            "name": selected,
            "config_path": str(config_path()),
        }
        if as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Configured knowledge base does not exist in the registry: {selected}", file=sys.stderr)
        return 3

    root = Path(record["path"]).expanduser().resolve(strict=False)
    exists = root.is_dir()
    payload = {
        "configured": True,
        "available": exists,
        "name": selected,
        "path": str(root),
        "config_path": str(config_path()),
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif exists:
        print(root)
    else:
        print(f"Configured knowledge-base path is unavailable: {root}", file=sys.stderr)
    return 0 if exists else 4


def cmd_set(data: dict[str, Any], name: str, root: Path, make_default: bool) -> int:
    clean_name = validate_name(name)
    resolved = root.expanduser().resolve(strict=False)
    if not resolved.is_dir():
        raise ValueError(
            f"Knowledge-base path must already exist as a directory: {resolved}. "
            "Run init_kb.py first when creating a new knowledge base."
        )
    record = data["knowledge_bases"].get(clean_name, {})
    record.update({"path": str(resolved), "updated_at": timestamp()})
    record.setdefault("configured_at", timestamp())
    data["knowledge_bases"][clean_name] = record
    if make_default or not data.get("default"):
        data["default"] = clean_name
    save_config(data)
    print(f"Configured {clean_name}: {resolved}")
    if data.get("default") == clean_name:
        print(f"Default knowledge base: {clean_name}")
    print(f"Configuration saved to: {config_path()}")
    return 0


def cmd_default(data: dict[str, Any], name: str) -> int:
    clean_name = validate_name(name)
    if clean_name not in data.get("knowledge_bases", {}):
        raise ValueError(f"Unknown knowledge base: {clean_name}")
    data["default"] = clean_name
    save_config(data)
    print(f"Default knowledge base: {clean_name}")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    try:
        data = load_config()
        if args.command == "show":
            return cmd_show(data, args.json)
        if args.command == "resolve":
            return cmd_resolve(data, args.name, args.json)
        if args.command == "set":
            return cmd_set(data, args.name, args.path, args.default)
        if args.command == "default":
            return cmd_default(data, args.name)
        raise ValueError(f"Unsupported command: {args.command}")
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
