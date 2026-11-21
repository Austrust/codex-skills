#!/usr/bin/env python3
"""homebox - a small, dependency-free CLI for the HomeBox inventory API.

HomeBox (https://homebox.software) models items and locations as "entities"
under /api/v1/entities. This CLI wraps the parts of the API that are useful for
inventory work: lookup, create, edit, move, delete, tags, photos/attachments,
maintenance notes, CSV export and collection statistics.

Configuration is read from (in order of precedence):
  1. explicit flags: --url / --api-key / --tenant
  2. environment: HOMEBOX_URL / HOMEBOX_API_KEY / HOMEBOX_TENANT
  3. JSON file: $HOMEBOX_CONFIG or ~/.config/homebox/config.json

See references/api.md next to this skill for the exact API shapes, and
references/local-context.md for the machine-specific instance notes.
"""

import argparse
import datetime
import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

VERSION = "1.0.0"

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
ASSET_RE = re.compile(r"^(#)?\d{3}-\d{3}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_AUTH = 3
EXIT_NOT_FOUND = 4
EXIT_AMBIGUOUS = 5

DEFAULT_TIMEOUT = 30
DEFAULT_CONFIG = Path.home() / ".config" / "homebox" / "config.json"


# ---------------------------------------------------------------------------
# errors


class CliError(Exception):
    """A user-facing error. `code` is the process exit code."""

    def __init__(self, message, code=EXIT_ERROR):
        super().__init__(message)
        self.code = code


class ApiError(CliError):
    def __init__(self, message, status=None, details=None):
        code = EXIT_ERROR
        if status in (401, 403):
            code = EXIT_AUTH
        elif status == 404:
            code = EXIT_NOT_FOUND
        super().__init__(message, code)
        self.status = status
        self.details = details


class AmbiguousError(CliError):
    def __init__(self, ref, candidates):
        self.ref = ref
        self.candidates = candidates
        super().__init__("ambiguous reference '%s'" % ref, EXIT_AMBIGUOUS)


# ---------------------------------------------------------------------------
# configuration


def config_path():
    raw = os.environ.get("HOMEBOX_CONFIG")
    return Path(raw).expanduser() if raw else DEFAULT_CONFIG


def load_config(args):
    cfg = {}
    path = config_path()
    if path.exists():
        try:
            cfg = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CliError("cannot read config %s: %s" % (path, exc))
        if not isinstance(cfg, dict):
            raise CliError("config %s must contain a JSON object" % path)

    for key, env in (("url", "HOMEBOX_URL"), ("api_key", "HOMEBOX_API_KEY"), ("tenant", "HOMEBOX_TENANT")):
        value = os.environ.get(env)
        if value:
            cfg[key] = value

    if args.url:
        cfg["url"] = args.url
    if args.api_key:
        cfg["api_key"] = args.api_key
    if args.tenant is not None:
        cfg["tenant"] = args.tenant
    if args.timeout:
        cfg["timeout"] = args.timeout
    return cfg


def mask_secret(value):
    if not value:
        return "(unset)"
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "..." + value[-2:]


# ---------------------------------------------------------------------------
# HTTP client


class Client:
    def __init__(self, cfg, as_json=False):
        self.url = (cfg.get("url") or "").rstrip("/")
        self.api_key = cfg.get("api_key") or ""
        self.timeout = int(cfg.get("timeout") or DEFAULT_TIMEOUT)
        self.json_out = as_json
        self._tenant_input = cfg.get("tenant") or ""
        self._tenant_id = None

    # -- low level ---------------------------------------------------------

    def request(self, method, path, params=None, body=None, files=None, raw=False, tenant=True):
        if not self.url:
            raise CliError("no HomeBox URL configured; run 'homebox config init --url ...' or set HOMEBOX_URL")
        url = self.url + "/api/v1" + path
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != []}
            if clean:
                url += "?" + urllib.parse.urlencode(clean, doseq=True)

        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        if tenant:
            tid = self.tenant_id()
            if tid:
                headers["X-Tenant"] = tid

        data = None
        if files is not None:
            data, content_type = files
            headers["Content-Type"] = content_type
        elif body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = resp.read()
                if raw:
                    return payload
                if not payload:
                    return None
                try:
                    return json.loads(payload.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    raise CliError("unexpected non-JSON response from %s %s: %s"
                                   % (method, path, payload[:300].decode("utf-8", "replace")))
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            message = None
            details = None
            try:
                parsed = json.loads(payload.decode("utf-8")) if payload else None
                if isinstance(parsed, dict):
                    message = parsed.get("error") or parsed.get("message")
                    details = parsed if not message else parsed
                else:
                    details = parsed
            except (ValueError, UnicodeDecodeError):
                message = payload.decode("utf-8", "replace").strip()[:500] or None
            if not message and isinstance(details, dict):
                message = "; ".join("%s: %s" % (key, value) for key, value in details.items())
            if not message:
                message = "HTTP %s for %s %s" % (exc.code, method, path)
            hint = ""
            if exc.code == 401:
                hint = " (API key invalid or expired; see 'homebox config show')"
            elif exc.code == 403:
                hint = " (the user/key may not belong to this collection; check --tenant)"
            elif exc.code == 404:
                hint = " (object not found in the selected collection)"
            elif exc.code == 413:
                hint = " (body too large; HomeBox's default upload cap is 10 MB and can be raised with web.max_file_upload)"
            raise ApiError(message + hint, status=exc.code, details=details)
        except urllib.error.URLError as exc:
            raise CliError("cannot reach %s: %s" % (self.url, exc.reason))

    # -- convenience -------------------------------------------------------

    def get(self, path, params=None, raw=False, tenant=True):
        return self.request("GET", path, params=params, raw=raw, tenant=tenant)

    def post(self, path, body=None):
        return self.request("POST", path, body=body)

    def put(self, path, body=None):
        return self.request("PUT", path, body=body)

    def delete(self, path):
        return self.request("DELETE", path)

    # -- tenant ------------------------------------------------------------

    def tenant_id(self):
        if not self._tenant_input:
            return None
        if UUID_RE.match(self._tenant_input):
            self._tenant_id = self._tenant_input
            return self._tenant_id
        if self._tenant_id:
            return self._tenant_id
        groups = self.request("GET", "/groups/all", tenant=False) or []
        wanted = self._tenant_input.casefold()
        matches = [g for g in groups if (g.get("name") or "").casefold() == wanted]
        if not matches:
            names = ", ".join(g.get("name", "?") for g in groups) or "(none visible)"
            raise CliError("collection '%s' not found; available: %s" % (self._tenant_input, names))
        self._tenant_id = matches[0]["id"]
        return self._tenant_id

    def tenant_name(self):
        tid = self.tenant_id()
        if not tid:
            return "(server default)"
        groups = self.request("GET", "/groups/all", tenant=False) or []
        for group in groups:
            if group.get("id") == tid:
                return group.get("name") or tid
        return tid


# ---------------------------------------------------------------------------
# output helpers


def out(args):
    return sys.stdout


def die(message, code=EXIT_ERROR):
    raise CliError(message, code)


def print_json(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def truncate(text, width):
    text = "" if text is None else str(text)
    if len(text) <= width:
        return text
    return text[: max(0, width - 1)] + "…"


def print_table(headers, rows, widths=None):
    rows = [[("" if cell is None else str(cell)) for cell in row] for row in rows]
    if not rows:
        return
    if widths is None:
        widths = []
        for index, header in enumerate(headers):
            longest = max([len(header)] + [len(row[index]) for row in rows if index < len(row)])
            widths.append(longest)
    line = "  ".join(header.ljust(widths[i]) for i, header in enumerate(headers))
    print(line.rstrip())
    print("  ".join("-" * widths[i] for i in range(len(headers))).rstrip())
    for row in rows:
        print("  ".join(truncate(row[i], widths[i]).ljust(widths[i]) for i in range(len(headers))).rstrip())


def entity_label(entity):
    return "%s (%s)" % (entity.get("name", "?"), entity.get("id", "?"))


def short_id(value, length=8):
    return (value or "")[:length]


# ---------------------------------------------------------------------------
# lookups


def is_location(entity):
    return bool((entity.get("entityType") or {}).get("isLocation"))


def entity_type_name(entity):
    return (entity.get("entityType") or {}).get("name") or "?"


def fetch_entity(client, entity_id):
    return client.get("/entities/" + entity_id)


def fetch_entity_path(client, entity_id):
    try:
        return client.get("/entities/%s/path" % entity_id) or []
    except ApiError:
        return []


def search_entities(client, ref, kind=None, include_archived=False):
    """Return [(kind, entity)] for a text reference."""
    kinds = [kind] if kind else ["item", "location"]
    results = []
    for wanted in kinds:
        params = {"q": ref, "pageSize": 50}
        if wanted == "item":
            params["isLocation"] = "false"
        elif wanted == "location":
            params["isLocation"] = "true"
        if include_archived:
            params["includeArchived"] = "true"
        data = client.get("/entities", params=params) or {}
        for entity in data.get("items", []):
            results.append((wanted, entity))
    return results


def resolve_entity(client, ref, kind=None):
    """Resolve a UUID, asset ID (#000-001), or unique name to an entity."""
    ref = (ref or "").strip()
    if not ref:
        raise CliError("empty entity reference")
    if UUID_RE.match(ref):
        return fetch_entity(client, ref)

    if ASSET_RE.match(ref):
        asset = ref.lstrip("#")
        data = client.get("/entities", params={"q": "#" + asset, "pageSize": 10}) or {}
        items = data.get("items", [])
        if len(items) == 1:
            return items[0]
        if len(items) > 1:
            raise AmbiguousError(ref, [("item", e) for e in items])
        raise CliError("no entity with asset ID %s" % asset, EXIT_NOT_FOUND)

    results = search_entities(client, ref, kind=kind)
    exact = [(k, e) for k, e in results if (e.get("name") or "").casefold() == ref.casefold()]
    if len(exact) == 1:
        return exact[0][1]
    if not results:
        archived = search_entities(client, ref, kind=kind, include_archived=True)
        archived_exact = [(k, e) for k, e in archived if (e.get("name") or "").casefold() == ref.casefold()]
        if len(archived_exact) == 1:
            return archived_exact[0][1]
        if archived:
            raise AmbiguousError(ref, archived_exact or archived)
        raise CliError("no item or location matches '%s'" % ref, EXIT_NOT_FOUND)
    raise AmbiguousError(ref, exact or results)


def resolve_location(client, ref):
    entity = resolve_entity(client, ref)
    if not is_location(entity):
        raise CliError("'%s' is an item, not a location (type: %s)" % (entity.get("name"), entity_type_name(entity)))
    return entity


def resolve_tags(client, names):
    tags = client.get("/tags") or []
    by_name = {(tag.get("name") or "").casefold(): tag for tag in tags}
    ids = []
    missing = []
    for name in names:
        tag = by_name.get(name.casefold())
        if tag:
            ids.append(tag["id"])
        else:
            missing.append(name)
    if missing:
        available = ", ".join(sorted(tag.get("name", "?") for tag in tags)) or "(no tags yet)"
        raise CliError("unknown tag(s): %s; existing tags: %s; create with 'homebox tag add NAME'" % (", ".join(missing), available))
    return ids


def resolve_entity_type(client, name, want_location):
    types = client.get("/entity-types") or []
    if name:
        if UUID_RE.match(name):
            matches = [t for t in types if t.get("id") == name]
        else:
            matches = [t for t in types if (t.get("name") or "").casefold() == name.casefold()]
        if not matches:
            available = ", ".join("%s%s" % (t.get("name"), " [location]" if t.get("isLocation") else "") for t in types)
            raise CliError("unknown entity type '%s'; available: %s" % (name, available))
        if bool(matches[0].get("isLocation")) != want_location:
            raise CliError("entity type '%s' is %s; a %s is required" % (
                matches[0].get("name"),
                "a location type" if matches[0].get("isLocation") else "an item type",
                "location" if want_location else "item",
            ))
        return matches[0]
    for entity_type in types:
        if bool(entity_type.get("isLocation")) == want_location:
            return entity_type
    # The server auto-creates the default type on first create only for items.
    raise CliError("no %s entity type in this collection; create one in the HomeBox UI or via 'homebox types'"
                   % ("location" if want_location else "item"))


# ---------------------------------------------------------------------------
# entity payloads


def entity_to_update_payload(entity):
    """Build a full EntityUpdate payload from an EntityOut response."""
    payload = {
        "name": entity.get("name", ""),
        "description": entity.get("description", ""),
        "quantity": entity.get("quantity", 0),
        "modelNumber": entity.get("modelNumber", ""),
        "manufacturer": entity.get("manufacturer", ""),
        "serialNumber": entity.get("serialNumber", ""),
        "warrantyDetails": entity.get("warrantyDetails", ""),
        "warrantyExpires": entity.get("warrantyExpires", ""),
        "purchaseDate": entity.get("purchaseDate", ""),
        "purchaseFrom": entity.get("purchaseFrom", ""),
        "purchasePrice": entity.get("purchasePrice", 0),
        "soldDate": entity.get("soldDate", ""),
        "soldTo": entity.get("soldTo", ""),
        "soldPrice": entity.get("soldPrice", 0),
        "soldNotes": entity.get("soldNotes", ""),
        "notes": entity.get("notes", ""),
        "insured": bool(entity.get("insured")),
        "archived": bool(entity.get("archived")),
        "lifetimeWarranty": bool(entity.get("lifetimeWarranty")),
        "syncChildEntityLocations": bool(entity.get("syncChildEntityLocations")),
        "tagIds": [tag.get("id") for tag in (entity.get("tags") or [])],
        "fields": entity.get("fields") or [],
        "assetId": entity.get("assetId") or "",
    }
    if entity.get("entityType"):
        payload["entityTypeId"] = entity["entityType"]["id"]
    if entity.get("parent"):
        payload["parentId"] = entity["parent"]["id"]
    if entity.get("locationId"):
        payload["locationId"] = entity["locationId"]
    return payload


def set_field(fields, name, value):
    """Merge one custom field into a fields list (by name)."""
    for field in fields:
        if (field.get("name") or "").casefold() == name.casefold():
            field["textValue"] = value
            return fields
    fields.append({"type": "text", "name": name, "textValue": value, "numberValue": 0, "booleanValue": False})
    return fields


def parse_field_args(values):
    parsed = []
    for item in values or []:
        if "=" not in item:
            raise CliError("--field expects NAME=VALUE, got '%s'" % item)
        name, value = item.split("=", 1)
        parsed.append((name.strip(), value))
    return parsed


def validate_date(value, label):
    if value in (None, ""):
        return ""
    if not DATE_RE.match(value):
        raise CliError("%s must be YYYY-MM-DD, got '%s'" % (label, value))
    try:
        datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise CliError("%s is not a valid date (%s)" % (label, exc))
    return value


# ---------------------------------------------------------------------------
# rendering


def entity_row(entity):
    parent = entity.get("parent") or {}
    location = entity.get("location") or parent
    tags = ", ".join(tag.get("name", "?") for tag in (entity.get("tags") or []))
    return [
        entity.get("id", ""),
        entity_type_name(entity),
        entity.get("name", ""),
        location.get("name", ""),
        entity.get("assetId", ""),
        entity.get("quantity", ""),
        tags,
    ]


def print_entities(items, json_out):
    if json_out:
        print_json(items)
        return
    rows = [entity_row(entity) for entity in items]
    print_table(
        ["ID", "TYPE", "NAME", "LOCATION", "ASSET", "QTY", "TAGS"],
        rows,
        widths=[36, 10, 32, 22, 8, 5, 20],
    )
    print("\n%d entit%s" % (len(items), "y" if len(items) == 1 else "ies"))


def print_entity(entity, path=None, json_out=False):
    if json_out:
        print_json(entity)
        return
    lines = []
    lines.append("ID:        %s" % entity.get("id"))
    lines.append("Name:      %s" % entity.get("name"))
    lines.append("Type:      %s%s" % (entity_type_name(entity), " (location)" if is_location(entity) else ""))
    if entity.get("assetId"):
        lines.append("Asset ID:  %s" % entity["assetId"])
    lines.append("Quantity:  %s" % entity.get("quantity"))
    parent = entity.get("parent") or {}
    if parent:
        lines.append("Parent:    %s (%s)" % (parent.get("name"), parent.get("id")))
    if path:
        lines.append("Path:      %s" % " / ".join(part.get("name", "?") for part in path))
    if entity.get("description"):
        lines.append("Desc:      %s" % entity["description"])
    if entity.get("serialNumber"):
        lines.append("Serial:    %s" % entity["serialNumber"])
    if entity.get("modelNumber"):
        lines.append("Model:     %s" % entity["modelNumber"])
    if entity.get("manufacturer"):
        lines.append("Maker:     %s" % entity["manufacturer"])
    tags = entity.get("tags") or []
    if tags:
        lines.append("Tags:      %s" % ", ".join(tag.get("name", "?") for tag in tags))
    if entity.get("purchasePrice"):
        lines.append("Price:     %s" % entity["purchasePrice"])
    if entity.get("purchaseDate") or entity.get("purchaseFrom"):
        lines.append("Purchase:  %s %s" % (entity.get("purchaseDate", ""), entity.get("purchaseFrom", "")))
    if entity.get("warrantyExpires") or entity.get("warrantyDetails"):
        lines.append("Warranty:  %s %s" % (entity.get("warrantyExpires", ""), entity.get("warrantyDetails", "")))
    if entity.get("notes"):
        lines.append("Notes:     %s" % entity["notes"])
    if entity.get("archived"):
        lines.append("Archived:  yes")
    attachments = entity.get("attachments") or []
    if attachments:
        lines.append("Files:")
        for attachment in attachments:
            marker = "primary " if attachment.get("primary") else ""
            lines.append("  - %s [%s%s] %s" % (attachment.get("title") or attachment.get("path"), marker, attachment.get("type"), attachment.get("id")))
    fields = entity.get("fields") or []
    if fields:
        lines.append("Fields:")
        for field in fields:
            value = field.get("textValue")
            if value in (None, ""):
                value = field.get("numberValue") or field.get("booleanValue")
            lines.append("  - %s: %s" % (field.get("name"), value))
    children = entity.get("children") or []
    if children:
        lines.append("Children:")
        for child in children:
            lines.append("  - %s (%s)" % (child.get("name"), child.get("id")))
    lines.append("Created:   %s" % entity.get("createdAt"))
    lines.append("Updated:   %s" % entity.get("updatedAt"))
    print("\n".join(lines))


# ---------------------------------------------------------------------------
# commands


def cmd_status(client, args):
    data = client.get("/status", tenant=False)
    if args.json:
        print_json(data)
        return
    print("HomeBox:   %s" % ("healthy" if data.get("health") else "unhealthy"))
    build = data.get("build") or {}
    latest = data.get("latest") or {}
    print("Version:   %s (build %s)" % (data.get("title"), build.get("version")))
    print("Commit:    %s  %s" % (build.get("commit", "?"), build.get("buildTime", "")))
    print("Upstream:  %s" % latest.get("version", "?"))
    print("OIDC:      %s" % ("enabled" if (data.get("oidc") or {}).get("enabled") else "disabled"))
    try:
        print("Config:    %s" % client.url)
        print("Collection: %s" % client.tenant_name())
    except CliError:
        pass


def cmd_config(client_cfg, args, cfg):
    if args.config_command == "show":
        print("config file: %s%s" % (config_path(), "" if config_path().exists() else " (missing)"))
        print("url:         %s" % (cfg.get("url") or "(unset)"))
        print("api key:     %s" % mask_secret(cfg.get("api_key")))
        print("tenant:      %s" % (cfg.get("tenant") or "(server default)"))
        if args.test:
            probe = Client(cfg, as_json=args.json)
            data = probe.get("/users/self", tenant=False)
            user = data.get("item", data) if isinstance(data, dict) else data
            print("connection:  ok (%s / %s)" % (user.get("name"), user.get("email")))
            if cfg.get("tenant"):
                print("collection:  %s" % probe.tenant_name())
        return

    if args.config_command == "init":
        if not args.url:
            raise CliError("config init requires --url")
        if not args.api_key:
            raise CliError("config init requires --api-key (create one in HomeBox Profile -> API Keys)")
        path = config_path()
        if path.exists() and not args.force:
            raise CliError("%s already exists; re-run with --force to overwrite" % path)
        payload = {"url": args.url.rstrip("/"), "api_key": args.api_key}
        if args.tenant:
            payload["tenant"] = args.tenant
        path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(str(path.parent), 0o700)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.chmod(str(path), 0o600)
        print("wrote %s (mode 600)" % path)
        return

    raise CliError("unknown config command")


def cmd_whoami(client, args):
    data = client.get("/users/self", tenant=False)
    user = data.get("item", data)
    if args.json:
        print_json(user)
        return
    print("User:      %s / %s" % (user.get("name"), user.get("email")))
    print("ID:        %s" % user.get("id"))
    print("Superuser: %s" % bool(user.get("isSuperuser")))
    print("Default:   %s" % user.get("defaultGroupId"))
    print("Groups:    %s" % ", ".join(user.get("groupIds") or []))


def cmd_collections(client, args):
    groups = client.get("/groups/all", tenant=False) or []
    if args.json:
        print_json(groups)
        return
    print_table(
        ["ID", "NAME", "CURRENCY", "UPDATED"],
        [[g.get("id", ""), g.get("name", ""), g.get("currency", ""), g.get("updatedAt", "")] for g in groups],
        widths=[36, 22, 10, 24],
    )


def cmd_types(client, args):
    types = client.get("/entity-types") or []
    if args.json:
        print_json(types)
        return
    print_table(
        ["ID", "NAME", "LOCATION?", "DESCRIPTION"],
        [[t.get("id", ""), t.get("name", ""), "yes" if t.get("isLocation") else "no", t.get("description", "")] for t in types],
        widths=[36, 24, 10, 36],
    )


def cmd_tree(client, args):
    tree = client.get("/entities/tree", params={"withItems": "true" if args.with_items else "false"}) or []
    if args.json:
        print_json(tree)
        return

    def walk(nodes, depth):
        for node in nodes:
            marker = "[location]" if node.get("type") == "location" else "[item]"
            print("  " * depth + "%s %s (%s)" % (marker, node.get("name"), node.get("id")))
            walk(node.get("children") or [], depth + 1)

    walk(tree, 0)
    if not tree:
        print("(empty collection)")


def build_list_params(args, kind):
    params = {"pageSize": args.page_size}
    if args.query:
        params["q"] = args.query
    if kind == "location":
        params["isLocation"] = "true"
    elif kind == "item":
        params["isLocation"] = "false"
    if args.location:
        params["parentIds"] = [resolve_location(args.client, args.location)["id"]]
    if args.tag:
        params["tags"] = resolve_tags(args.client, args.tag)
        if args.all_tags:
            params["matchAllTags"] = "true"
    if args.archived:
        params["includeArchived"] = "true"
    if args.page:
        params["page"] = args.page
    if args.order_by:
        params["orderBy"] = args.order_by
    if args.desc:
        params["orderDirection"] = "desc"
    return params


def cmd_list(client, args):
    kinds = ["item"] if args.kind == "item" else (["location"] if args.kind == "location" else ["item", "location"])
    items = []
    for kind in kinds:
        params = build_list_params(args, kind)
        data = client.get("/entities", params=params) or {}
        items.extend(data.get("items", []))
    if args.json:
        print_json(items)
        return
    print_entities(items, args.json)
    if args.query:
        print("query: %s" % args.query)


def cmd_search(client, args):
    query = " ".join(args.query)
    kinds = ["item"] if args.kind == "item" else (["location"] if args.kind == "location" else ["item", "location"])
    items = []
    seen = set()
    for kind in kinds:
        params = {"q": query, "pageSize": args.limit}
        if kind == "item":
            params["isLocation"] = "false"
        else:
            params["isLocation"] = "true"
        data = client.get("/entities", params=params) or {}
        for entity in data.get("items", []):
            if entity.get("id") not in seen:
                seen.add(entity.get("id"))
                items.append(entity)
    if not items:
        print("no matches for '%s' in %s" % (query, client.tenant_name()))
        return
    if args.json:
        print_json(items)
        return
    print("matches for '%s' in %s:" % (query, client.tenant_name()))
    print()
    print_entities(items, False)


def cmd_show(client, args):
    entity = resolve_entity(client, args.ref)
    path = fetch_entity_path(client, entity["id"])
    print_entity(entity, path=path, json_out=args.json)


def cmd_item_add(client, args):
    entity_type = resolve_entity_type(client, args.type, want_location=False)
    payload = {
        "name": args.name,
        "description": args.description or "",
        "quantity": args.quantity,
        "entityTypeId": entity_type["id"],
        "modelNumber": args.model or "",
        "manufacturer": args.manufacturer or "",
    }
    parent = None
    if args.location:
        parent = resolve_entity(client, args.location)
        payload["parentId"] = parent["id"]
    tag_ids = resolve_tags(client, args.tag) if args.tag else []
    if tag_ids:
        payload["tagIds"] = tag_ids
    fields = parse_field_args(args.field)
    if args.dry_run:
        print_json({"method": "POST", "path": "/entities", "payload": payload})
        if fields:
            print_json({"method": "PUT", "path": "/entities/{id}", "fields": fields})
        return
    created = client.post("/entities", payload)
    if fields:
        full = entity_to_update_payload(created)
        for name, value in fields:
            set_field(full["fields"], name, value)
        created = client.put("/entities/" + created["id"], full)
    if args.json:
        print_json(created)
        return
    print("created %s item: %s" % (entity_type_name(created), created["id"]))
    print("  name:     %s" % created.get("name"))
    if parent:
        print("  location: %s (%s)" % (parent.get("name"), parent.get("id")))
    if created.get("assetId"):
        print("  asset id: %s" % created.get("assetId"))


def cmd_location_add(client, args):
    entity_type = resolve_entity_type(client, args.type, want_location=True)
    payload = {
        "name": args.name,
        "description": args.description or "",
        "quantity": 1,
        "entityTypeId": entity_type["id"],
    }
    parent = None
    if args.parent:
        parent = resolve_location(client, args.parent)
        payload["parentId"] = parent["id"]
    tag_ids = resolve_tags(client, args.tag) if args.tag else []
    if tag_ids:
        payload["tagIds"] = tag_ids
    fields = parse_field_args(args.field)
    if args.dry_run:
        print_json({"method": "POST", "path": "/entities", "payload": payload})
        if fields:
            print_json({"method": "PUT", "path": "/entities/{id}", "fields": fields})
        return
    created = client.post("/entities", payload)
    if fields:
        full = entity_to_update_payload(created)
        for name, value in fields:
            set_field(full["fields"], name, value)
        created = client.put("/entities/" + created["id"], full)
    if args.json:
        print_json(created)
        return
    print("created location: %s" % created["id"])
    print("  name: %s" % created.get("name"))
    if parent:
        print("  parent: %s (%s)" % (parent.get("name"), parent.get("id")))


def cmd_update(client, args):
    entity = resolve_entity(client, args.ref)
    payload = entity_to_update_payload(entity)
    changed = []

    if args.name is not None:
        payload["name"] = args.name
        changed.append("name")
    if args.description is not None:
        payload["description"] = args.description
        changed.append("description")
    if args.quantity is not None:
        payload["quantity"] = args.quantity
        changed.append("quantity")
    if args.notes is not None:
        payload["notes"] = args.notes
        changed.append("notes")
    if args.serial is not None:
        payload["serialNumber"] = args.serial
        changed.append("serialNumber")
    if args.model is not None:
        payload["modelNumber"] = args.model
        changed.append("modelNumber")
    if args.manufacturer is not None:
        payload["manufacturer"] = args.manufacturer
        changed.append("manufacturer")
    if args.asset_id is not None:
        payload["assetId"] = args.asset_id
        changed.append("assetId")
    if args.purchase_price is not None:
        payload["purchasePrice"] = args.purchase_price
        changed.append("purchasePrice")
    if args.purchase_date is not None:
        payload["purchaseDate"] = validate_date(args.purchase_date, "--purchase-date")
        changed.append("purchaseDate")
    if args.purchase_from is not None:
        payload["purchaseFrom"] = args.purchase_from
        changed.append("purchaseFrom")
    if args.warranty_expires is not None:
        payload["warrantyExpires"] = validate_date(args.warranty_expires, "--warranty-expires")
        changed.append("warrantyExpires")
    if args.warranty_details is not None:
        payload["warrantyDetails"] = args.warranty_details
        changed.append("warrantyDetails")
    if args.type:
        want_location = is_location(entity)
        entity_type = resolve_entity_type(client, args.type, want_location=want_location)
        payload["entityTypeId"] = entity_type["id"]
        changed.append("entityTypeId")
    if args.tag is not None and args.clear_tags:
        raise CliError("use either --tag or --clear-tags, not both")
    if args.clear_tags:
        payload["tagIds"] = []
        changed.append("tags")
    elif args.tag is not None:
        payload["tagIds"] = resolve_tags(client, args.tag) if args.tag else []
        changed.append("tags")
    if args.field:
        for name, value in parse_field_args(args.field):
            set_field(payload["fields"], name, value)
        changed.append("fields")
    if args.archive:
        payload["archived"] = True
        changed.append("archived")
    if args.unarchive:
        payload["archived"] = False
        changed.append("archived")
    if args.parent is not None and args.location is not None:
        raise CliError("use either --parent or --location, not both")
    if args.parent is not None:
        payload.pop("locationId", None)
        if args.parent == "":
            payload.pop("parentId", None)
        else:
            target = resolve_entity(client, args.parent)
            payload["parentId"] = target["id"]
            if not is_location(entity) and not is_location(target):
                parent_location = target.get("location") or {}
                if parent_location.get("id"):
                    payload["locationId"] = parent_location["id"]
        changed.append("parent")
    if args.location is not None:
        payload.pop("locationId", None)
        if args.location == "":
            payload.pop("parentId", None)
        else:
            target = resolve_location(client, args.location)
            payload["parentId"] = target["id"]
        changed.append("location")

    if not changed:
        raise CliError("nothing to update: pass at least one option (see 'homebox update -h')")
    if args.dry_run:
        print_json({"method": "PUT", "path": "/entities/" + entity["id"], "payload": payload, "changed": changed})
        return
    updated = client.put("/entities/" + entity["id"], payload)
    if args.json:
        print_json(updated)
        return
    print("updated %s (%s): %s" % (updated.get("name"), updated.get("id"), ", ".join(changed)))


def cmd_move(client, args):
    entity = resolve_entity(client, args.ref)
    target = resolve_entity(client, args.to)
    if is_location(entity) and not is_location(target):
        raise CliError("a location can only be moved under another location")
    if entity["id"] == target["id"]:
        raise CliError("cannot move an entity under itself")
    path = fetch_entity_path(client, entity["id"])
    payload = entity_to_update_payload(entity)
    payload["parentId"] = target["id"]
    payload.pop("locationId", None)
    if not is_location(entity) and not is_location(target):
        # item parented to another item: keep the target's nearest location explicit
        target_location = target.get("location") or {}
        if target_location.get("id"):
            payload["locationId"] = target_location["id"]
    if args.dry_run:
        print_json({"method": "PUT", "path": "/entities/" + entity["id"], "parentId": target["id"], "target": target.get("name")})
        return
    updated = client.put("/entities/" + entity["id"], payload)
    new_path = fetch_entity_path(client, updated["id"])
    if args.json:
        print_json({"entity": updated, "previous_path": [p.get("name") for p in path], "path": [p.get("name") for p in new_path]})
        return
    print("moved %s -> %s" % (entity.get("name"), target.get("name")))
    print("  previous: %s" % (" / ".join(p.get("name", "?") for p in path) or "(root)"))
    print("  now:      %s" % (" / ".join(p.get("name", "?") for p in new_path) or "(root)"))


def cmd_delete(client, args):
    entity = resolve_entity(client, args.ref)
    if not args.yes:
        raise CliError(
            "refusing to delete %s (%s) without --yes; pass --yes to confirm" % (entity.get("name"), entity.get("id")),
            EXIT_USAGE,
        )
    if args.dry_run:
        print_json({"method": "DELETE", "path": "/entities/" + entity["id"], "name": entity.get("name")})
        return
    client.delete("/entities/" + entity["id"])
    if args.json:
        print_json({"deleted": entity["id"], "name": entity.get("name")})
        return
    print("deleted %s (%s)" % (entity.get("name"), entity.get("id")))


def cmd_tags(client, args):
    if args.tag_command in (None, "list"):
        tags = client.get("/tags") or []
        if args.json:
            print_json(tags)
            return
        print_table(
            ["ID", "NAME", "DESCRIPTION", "COLOR", "PARENT"],
            [[t.get("id", ""), t.get("name", ""), t.get("description", ""), t.get("color", ""), (t.get("parent") or {}).get("name", "")] for t in tags],
            widths=[36, 24, 30, 10, 16],
        )
        print("\n%d tag(s)" % len(tags))
        return
    if args.tag_command == "add":
        payload = {"name": args.name, "description": args.description or "", "color": args.color or "", "icon": ""}
        if args.parent:
            payload["parentId"] = resolve_entity_tag(client, args.parent)["id"]
        if args.dry_run:
            print_json({"method": "POST", "path": "/tags", "payload": payload})
            return
        tag = client.post("/tags", payload)
        if args.json:
            print_json(tag)
            return
        print("created tag %s (%s)" % (tag.get("name"), tag.get("id")))
        return
    if args.tag_command == "delete":
        if not args.yes:
            raise CliError("refusing to delete tag %s without --yes" % args.id, EXIT_USAGE)
        client.delete("/tags/" + args.id)
        print("deleted tag %s" % args.id)
        return
    raise CliError("unknown tag command")


def resolve_entity_tag(client, name):
    tags = client.get("/tags") or []
    for tag in tags:
        if (tag.get("name") or "").casefold() == name.casefold() or tag.get("id") == name:
            return tag
    raise CliError("unknown tag '%s'" % name, EXIT_NOT_FOUND)


def cmd_attach(client, args):
    entity = resolve_entity(client, args.ref)
    path = Path(args.file).expanduser()
    if not path.is_file():
        raise CliError("file not found: %s" % path)
    size = path.stat().st_size
    if size > 10 * 1024 * 1024 and not args.force_large:
        raise CliError(
            "file is %.1f MB; HomeBox's default upload cap is 10 MB (server-configured via "
            "web.max_file_upload). Re-run with --force-large to attempt anyway, or link the "
            "file from an external URL in the HomeBox UI." % (size / 1048576.0)
        )
    name = args.name or path.name
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    fields = {"name": name}
    if args.type:
        fields["type"] = args.type
    fields["primary"] = "true" if args.primary else "false"
    body, content_type = build_multipart("file", name, path.read_bytes(), mime, fields)
    if args.dry_run:
        print_json({"method": "POST", "path": "/entities/%s/attachments" % entity["id"], "file": str(path), "name": name, "type": args.type or "auto", "primary": bool(args.primary)})
        return
    result = client.request("POST", "/entities/%s/attachments" % entity["id"], files=(body, content_type))
    attachments = result.get("attachments") or []
    if args.json:
        print_json(result)
        return
    print("attached %s to %s (%s)" % (name, entity.get("name"), entity.get("id")))
    print("  attachments now: %d" % len(attachments))


def build_multipart(field_name, filename, data, mime, fields):
    boundary = "----homeboxcli" + uuid.uuid4().hex
    chunks = []
    for key, value in fields.items():
        chunks.append(("--%s\r\n" % boundary).encode())
        chunks.append(('Content-Disposition: form-data; name="%s"\r\n\r\n' % key).encode())
        chunks.append(str(value).encode("utf-8") + b"\r\n")
    chunks.append(("--%s\r\n" % boundary).encode())
    chunks.append(('Content-Disposition: form-data; name="%s"; filename="%s"\r\n' % (field_name, filename)).encode("utf-8"))
    chunks.append(("Content-Type: %s\r\n\r\n" % mime).encode())
    chunks.append(data + b"\r\n")
    chunks.append(("--%s--\r\n" % boundary).encode())
    return b"".join(chunks), "multipart/form-data; boundary=" + boundary


def cmd_maintenance(client, args):
    entity = resolve_entity(client, args.ref)
    if args.maintenance_command in (None, "list"):
        entries = client.get("/entities/%s/maintenance" % entity["id"]) or []
        if args.json:
            print_json(entries)
            return
        print("maintenance for %s (%s):" % (entity.get("name"), entity.get("id")))
        print_table(
            ["ID", "NAME", "COMPLETED", "SCHEDULED", "COST"],
            [[e.get("id", ""), e.get("name", ""), e.get("completedDate", ""), e.get("scheduledDate", ""), e.get("cost", "")] for e in entries],
            widths=[36, 28, 12, 12, 8],
        )
        if not entries:
            print("(no maintenance entries)")
        return
    if args.maintenance_command == "add":
        if not args.completed and not args.scheduled:
            raise CliError("maintenance add requires --completed and/or --scheduled")
        payload = {
            "name": args.name,
            "description": args.description or "",
            "completedDate": validate_date(args.completed, "--completed"),
            "scheduledDate": validate_date(args.scheduled, "--scheduled"),
            "cost": str(args.cost) if args.cost is not None else "0",
        }
        if args.dry_run:
            print_json({"method": "POST", "path": "/entities/%s/maintenance" % entity["id"], "payload": payload})
            return
        entry = client.post("/entities/%s/maintenance" % entity["id"], payload)
        if args.json:
            print_json(entry)
            return
        print("added maintenance entry %s to %s" % (entry.get("id"), entity.get("name")))
        print("  name:      %s" % entry.get("name"))
        print("  completed: %s" % (entry.get("completedDate") or "-"))
        print("  scheduled: %s" % (entry.get("scheduledDate") or "-"))
        return
    raise CliError("unknown maintenance command")


def cmd_export(client, args):
    data = client.get("/entities/export", raw=True)
    if args.output:
        path = Path(args.output).expanduser()
        path.write_bytes(data)
        print("wrote %d bytes to %s" % (len(data), path))
        return
    sys.stdout.write(data.decode("utf-8", "replace"))


def cmd_stats(client, args):
    data = client.get("/groups/statistics") or {}
    if args.json:
        print_json(data)
        return
    print("collection:    %s" % client.tenant_name())
    print("items:         %s" % data.get("totalItems"))
    print("locations:     %s" % data.get("totalLocations"))
    print("tags:          %s" % data.get("totalTags"))
    print("users:         %s" % data.get("totalUsers"))
    print("item price:    %s" % data.get("totalItemPrice"))
    print("with warranty: %s" % data.get("totalWithWarranty"))


def cmd_keys(client, args):
    if args.keys_command in (None, "list"):
        keys = client.get("/users/self/api-keys") or []
        if args.json:
            print_json(keys)
            return
        print_table(
            ["ID", "NAME", "CREATED", "EXPIRES", "LAST USED"],
            [[k.get("id", ""), k.get("name", ""), (k.get("createdAt") or "")[:10], (k.get("expiresAt") or "-")[:10], (k.get("lastUsedAt") or "-")[:10]] for k in keys],
            widths=[36, 20, 12, 12, 12],
        )
        return
    if args.keys_command == "create":
        payload = {"name": args.name}
        if args.expires:
            payload["expiresAt"] = validate_date(args.expires, "--expires") + "T00:00:00Z"
        if args.dry_run:
            print_json({"method": "POST", "path": "/users/self/api-keys", "payload": payload})
            return
        created = client.post("/users/self/api-keys", payload)
        if args.json:
            print_json(created)
            return
        print("created API key %s (%s)" % (created.get("name"), created.get("id")))
        print("token (shown once, store it securely): %s" % created.get("token"))
        return
    if args.keys_command == "delete":
        if not args.yes:
            raise CliError("refusing to delete API key %s without --yes" % args.id, EXIT_USAGE)
        client.delete("/users/self/api-keys/" + args.id)
        print("deleted API key %s" % args.id)
        return
    raise CliError("unknown keys command")


def cmd_qrcode(client, args):
    if args.data:
        payload = args.data
    else:
        entity = resolve_entity(client, args.ref)
        kind = "location" if is_location(entity) else "item"
        payload = "%s/%s/%s" % (client.url, kind, entity["id"])
    data = client.get("/qrcode", params={"data": payload}, raw=True)
    if not args.output:
        raise CliError("qrcode writes an image; pass -o FILE")
    path = Path(args.output).expanduser()
    path.write_bytes(data)
    print("wrote %d bytes to %s (content: %s)" % (len(data), path, payload))


# ---------------------------------------------------------------------------
# argument parser


def add_common(parser):
    parser.add_argument("--json", action="store_true", help="print raw JSON instead of a table")
    parser.add_argument("--url", help="HomeBox base URL (overrides config/env)")
    parser.add_argument("--api-key", help="HomeBox API key (overrides config/env)")
    parser.add_argument("--tenant", help="collection name or UUID (overrides config/env)")
    parser.add_argument("--timeout", type=int, help="HTTP timeout in seconds")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="homebox",
        description="Operate a HomeBox inventory (items, locations, tags, files, maintenance) through its REST API.",
        epilog="Config: --url/--api-key/--tenant > HOMEBOX_URL/HOMEBOX_API_KEY/HOMEBOX_TENANT > "
               "$HOMEBOX_CONFIG or ~/.config/homebox/config.json. See references/api.md for API details.",
    )
    parser.add_argument("--version", action="version", version="homebox-cli " + VERSION)
    add_common(parser)

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    def add(name, help=None, aliases=None):
        return sub.add_parser(name, help=help, aliases=aliases or [])

    p = add("status", "show server health and version")
    p.set_defaults(func=cmd_status)

    p = add("config", "show or create the local connection config")
    csub = p.add_subparsers(dest="config_command")
    show = csub.add_parser("show", help="show effective config")
    show.add_argument("--test", action="store_true", help="also test authentication")
    init = csub.add_parser("init", help="write config file")
    init.add_argument("--force", action="store_true", help="overwrite an existing config")
    p.set_defaults(func=lambda client, args: cmd_config(None, args, args.cfg))

    p = add("whoami", "show the authenticated user")
    p.set_defaults(func=cmd_whoami)

    p = add("collections", aliases=["tenants", "groups"], help="list collections (tenants)")
    p.set_defaults(func=cmd_collections)

    p = add("types", "list entity types (Item / Location) of the current collection")
    p.set_defaults(func=cmd_types)

    p = add("tree", "show the location tree")
    p.add_argument("--with-items", action="store_true", help="include items under each location")
    p.set_defaults(func=cmd_tree)

    p = add("list", aliases=["ls"], help="list or filter entities")
    p.add_argument("-q", "--query", help="free-text search")
    p.add_argument("--location", help="only children of this location (name or UUID)")
    p.add_argument("--kind", choices=["item", "location", "all"], default="item", help="default: item")
    p.add_argument("--tag", action="append", metavar="NAME", help="filter by tag (repeatable)")
    p.add_argument("--all-tags", action="store_true", help="require all --tag values")
    p.add_argument("--archived", action="store_true", help="include archived entities")
    p.add_argument("--page", type=int)
    p.add_argument("--page-size", type=int, default=100)
    p.add_argument("--order-by", choices=["name", "createdAt", "updatedAt", "assetId"])
    p.add_argument("--desc", action="store_true", help="descending order")
    p.set_defaults(func=cmd_list)

    p = add("search", help="search items and locations by text")
    p.add_argument("query", nargs="+")
    p.add_argument("--kind", choices=["item", "location", "all"], default="all")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_search)

    p = add("show", "show one entity by UUID, asset ID (#000-001) or name")
    p.add_argument("ref")
    p.set_defaults(func=cmd_show)

    item = add("item", "create and manage items")
    isub = item.add_subparsers(dest="item_command", required=True)
    addc = isub.add_parser("add", aliases=["create"], help="create an item")
    addc.add_argument("name")
    addc.add_argument("--location", help="location name or UUID")
    addc.add_argument("--description")
    addc.add_argument("--quantity", type=float, default=1)
    addc.add_argument("--tag", action="append", metavar="NAME", help="tag name (repeatable)")
    addc.add_argument("--type", help="entity type name or UUID")
    addc.add_argument("--model")
    addc.add_argument("--manufacturer")
    addc.add_argument("--field", action="append", metavar="NAME=VALUE", help="custom field (repeatable)")
    addc.add_argument("--dry-run", action="store_true")
    addc.set_defaults(func=cmd_item_add)

    loc = add("location", "create locations")
    lsub = loc.add_subparsers(dest="location_command", required=True)
    addl = lsub.add_parser("add", aliases=["create"], help="create a location")
    addl.add_argument("name")
    addl.add_argument("--parent", help="parent location name or UUID")
    addl.add_argument("--description")
    addl.add_argument("--tag", action="append", metavar="NAME")
    addl.add_argument("--type", help="entity type name or UUID")
    addl.add_argument("--field", action="append", metavar="NAME=VALUE")
    addl.add_argument("--dry-run", action="store_true")
    addl.set_defaults(func=cmd_location_add)

    p = add("update", aliases=["edit"], help="edit an entity (only listed fields change)")
    p.add_argument("ref")
    p.add_argument("--name")
    p.add_argument("--description")
    p.add_argument("--quantity", type=float)
    p.add_argument("--notes")
    p.add_argument("--serial")
    p.add_argument("--model")
    p.add_argument("--manufacturer")
    p.add_argument("--asset-id")
    p.add_argument("--purchase-price", type=float)
    p.add_argument("--purchase-date")
    p.add_argument("--purchase-from")
    p.add_argument("--warranty-expires")
    p.add_argument("--warranty-details")
    p.add_argument("--type", help="change entity type (name or UUID)")
    p.add_argument("--tag", action="append", metavar="NAME", help="replace tags with these (repeatable)")
    p.add_argument("--clear-tags", action="store_true", help="remove all tags")
    p.add_argument("--field", action="append", metavar="NAME=VALUE")
    p.add_argument("--location", help="move under this location")
    p.add_argument("--parent", help="set parent (name or UUID); '' clears it")
    p.add_argument("--archive", action="store_true")
    p.add_argument("--unarchive", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_update)

    p = add("move", help="move an entity under another location or item")
    p.add_argument("ref")
    p.add_argument("--to", required=True, metavar="REF", help="new parent location/item")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_move)

    p = add("delete", aliases=["rm"], help="delete an entity (requires --yes)")
    p.add_argument("ref")
    p.add_argument("--yes", "-y", action="store_true", help="confirm deletion")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_delete)

    p = add("tag", aliases=["tags"], help="list or create tags")
    tsub = p.add_subparsers(dest="tag_command")
    tsub.add_parser("list", help="list tags")
    addt = tsub.add_parser("add", aliases=["create"], help="create a tag")
    addt.add_argument("name")
    addt.add_argument("--description")
    addt.add_argument("--color")
    addt.add_argument("--parent", help="parent tag name")
    addt.add_argument("--dry-run", action="store_true")
    delt = tsub.add_parser("delete", aliases=["rm"], help="delete a tag")
    delt.add_argument("id", help="tag UUID")
    delt.add_argument("--yes", "-y", action="store_true")
    p.set_defaults(func=cmd_tags)

    p = add("attach", "upload a photo or attachment to an entity")
    p.add_argument("ref")
    p.add_argument("file")
    p.add_argument("--name", help="attachment title/filename (default: file name)")
    p.add_argument("--type", choices=["photo", "attachment", "manual", "receipt", "warranty"], default=None)
    p.add_argument("--primary", action="store_true", help="mark as primary photo")
    p.add_argument("--force-large", action="store_true", help="attempt uploads over the default 10 MB cap")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_attach)

    p = add("maintenance", help="list or add maintenance entries")
    msub = p.add_subparsers(dest="maintenance_command")
    mlist = msub.add_parser("list")
    mlist.add_argument("ref", help="entity UUID, asset ID or name")
    madd = msub.add_parser("add")
    madd.add_argument("ref")
    madd.add_argument("--name", required=True)
    madd.add_argument("--completed", metavar="YYYY-MM-DD")
    madd.add_argument("--scheduled", metavar="YYYY-MM-DD")
    madd.add_argument("--description")
    madd.add_argument("--cost", type=float)
    madd.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_maintenance)

    p = add("export", "export the current collection as CSV")
    p.add_argument("-o", "--output", help="write CSV to this file (default: stdout)")
    p.set_defaults(func=cmd_export)

    p = add("stats", help="collection statistics")
    p.set_defaults(func=cmd_stats)

    p = add("keys", help="manage API keys of the current user")
    ksub = p.add_subparsers(dest="keys_command")
    ksub.add_parser("list")
    kcreate = ksub.add_parser("create")
    kcreate.add_argument("name")
    kcreate.add_argument("--expires", metavar="YYYY-MM-DD", help="expiry date (default: server default, 30 days)")
    kcreate.add_argument("--dry-run", action="store_true")
    kdelete = ksub.add_parser("delete")
    kdelete.add_argument("id")
    kdelete.add_argument("--yes", "-y", action="store_true")
    p.set_defaults(func=cmd_keys)

    p = add("qrcode", "write a QR code image for an entity or arbitrary data")
    p.add_argument("ref", nargs="?", help="entity UUID, asset ID or name")
    p.add_argument("--data", help="encode this text instead of an entity")
    p.add_argument("-o", "--output", help="output image path (.jpg)")
    p.set_defaults(func=cmd_qrcode)

    return parser


# ---------------------------------------------------------------------------
# entry point

GLOBAL_VALUE_FLAGS = ("--url", "--api-key", "--tenant", "--timeout")


def normalize_argv(argv):
    """Allow global flags before or after the subcommand.

    argparse only accepts the top-level optional arguments before the
    subcommand, which makes 'homebox config init --url ...' fail. Pull the
    global flags out of the argument list and put them back in front.
    """
    extracted = []
    rest = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in GLOBAL_VALUE_FLAGS:
            if index + 1 < len(argv):
                extracted.extend([arg, argv[index + 1]])
                index += 2
                continue
            rest.append(arg)
            index += 1
            continue
        if arg == "--json" or any(arg.startswith(flag + "=") for flag in GLOBAL_VALUE_FLAGS):
            extracted.append(arg)
            index += 1
            continue
        rest.append(arg)
        index += 1
    return extracted + rest


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    argv = normalize_argv(argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return EXIT_USAGE

    try:
        cfg = load_config(args)
        args.cfg = cfg
        if args.command == "config":
            if args.config_command == "init":
                cmd_config(None, args, cfg)
                return EXIT_OK
            if args.config_command is None:
                raise CliError("usage: homebox config show|init")
        client = Client(cfg, as_json=args.json)
        if args.command not in ("status", "config") and not client.api_key:
            raise CliError("no API key configured; run 'homebox config init --url ... --api-key ...' or set HOMEBOX_API_KEY")
        args.client = client
        args.func(client, args)
        return EXIT_OK
    except AmbiguousError as exc:
        print("error: %s; candidates:" % exc, file=sys.stderr)
        for kind, entity in exc.candidates[:20]:
            print("  %s  %-9s %s  [location: %s]" % (
                entity.get("id"), entity_type_name(entity), entity.get("name"),
                (entity.get("parent") or {}).get("name", "-"),
            ), file=sys.stderr)
        print("hint: pass a UUID or the full/exact name to disambiguate", file=sys.stderr)
        return exc.code
    except CliError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return exc.code
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
