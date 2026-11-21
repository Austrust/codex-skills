---
name: homebox-cli
description: Inspect and edit the HomeBox inventory (items, locations, tags, photos/attachments, maintenance records) through its REST API with the bundled dependency-free `homebox` CLI. Use for "where is <device>", adding or editing equipment, moving things between locations, attaching photos/manuals, recording maintenance, CSV export, and collection statistics; triggers on 设备台账, 库存, 物品, 位置, HomeBox.
---

# HomeBox CLI

`homebox` is a dependency-free Python CLI (`scripts/homebox.py`) for a HomeBox v0.27.x instance. It wraps `/api/v1`, resolves names to IDs, keeps full-replacement updates from wiping unrelated fields, and prints the created/updated object so a write can be verified.

Use it instead of hand-written curl for normal inventory work.

## Setup on this machine

1. Read [references/local-context.md](references/local-context.md). It records the instance URL, the CLI config file, and the collections available on this deployment.
2. If `homebox` is not on `PATH`, either call `"$HOME/.local/bin/homebox"` or run [scripts/install-cli.sh](scripts/install-cli.sh) once.
3. Verify connectivity before changing anything:

```bash
homebox status        # server health, version, collection
homebox whoami        # which user the API key belongs to
```

The CLI reads `$HOMEBOX_CONFIG` or `~/.config/homebox/config.json` (`url`, `api_key`, `tenant`). `--url`, `--api-key`, `--tenant` flags and `HOMEBOX_URL`, `HOMEBOX_API_KEY`, `HOMEBOX_TENANT` environment variables override that file. Global flags may be placed before or after the subcommand.

## Command map

| Intent | Command |
|---|---|
| Search everything | `homebox search 示波器` |
| List/filter items | `homebox list --location 实验室A --tag 待维修` |
| Location hierarchy | `homebox tree --with-items` |
| Inspect one entity | `homebox show <UUID, 000-001, or unique name>` |
| Create an item | `homebox item add "示波器 X1" --location "实验室A" --tag 待维修 --model X1` |
| Create a location | `homebox location add "3号柜" --parent "实验室A"` |
| Edit fields | `homebox update "示波器 X1" --serial SN001 --purchase-price 1200 --purchase-date 2026-11-21` |
| Move | `homebox move "示波器 X1" --to "3号柜"` |
| Delete | `homebox delete <ref> --yes` |
| Tags | `homebox tag list`, `homebox tag add 待维修`, `homebox tag delete <id> --yes` |
| Photo / attachment | `homebox attach "示波器 X1" ./photo.jpg --primary` |
| Maintenance | `homebox maintenance add "示波器 X1" --name 校准 --completed 2026-11-21 --cost 120`, `homebox maintenance list <ref>` |
| CSV export | `homebox export -o inventory.csv` (stdout without `-o`) |
| Statistics | `homebox stats` |
| QR image | `homebox qrcode "示波器 X1" -o label.jpg` |
| API keys | `homebox keys list` |

All commands accept `--json` for raw API output. Name references must be unique; if the CLI exits `5` it prints the candidate list — pick a UUID and retry. Asset IDs are accepted as `000-001` or `#000-001`.

Add `--dry-run` to any write command to see the exact JSON payload without sending it.

Writable content: item/location names, descriptions, quantity, serial/model/
manufacturer, asset ID, purchase price/date/source, warranty expiry/details,
notes, tags, custom fields (as text), parent/location, archived flag; tags with
name/description/color/parent; attachments of any file type (photos default to
`photo`, 10 MB server default cap); maintenance entries; API keys. The CLI
cannot create entity types, collections, members, or import CSV; sold fields,
insurance, lifetime-warranty and template/label features are UI/API-only.

## Operating rules

- Read before write: `search` / `show` / `tree` first, then create or update. Report the entity UUID after a write.
- Deletions, tag deletion and key deletion require `--yes`; only do them when the user actually asked for a deletion of that object. Do not clean up "similar looking" objects.
- Moving a location changes the parent of everything under it. Confirm the target with `show` first; the CLI refuses to move a location under an item.
- Updates are merge-by-flag: only the fields you pass change. Do not fetch-modify-write by hand when `homebox update` already covers the field.
- `--tag` on `update` replaces the whole tag set. Use `--clear-tags` to remove all tags. Tags must already exist.
- Writes normally do not need extra confirmation, but never invent inventory data: if a serial, location, or owner is unknown, leave the field empty and say so.
- Never print, copy into a repository, or commit the API key. The local config file is mode `600` and `references/local-context.md` is gitignored.
- Exit codes: `0` ok, `1` error, `2` usage / missing confirmation, `3` auth, `4` not found, `5` ambiguous reference.

## Common sequences

Add a shelf and an item on it:

```bash
homebox location add "3号柜" --parent "实验室A"
homebox item add "信号发生器 DG1022" --location "3号柜" --manufacturer RIGOL --model DG1022 --tag 已校准
```

Attach a photo, then verify:

```bash
homebox attach "信号发生器 DG1022" ./dg1022.jpg --primary
homebox show "信号发生器 DG1022"
```

Move an item after checking both ends:

```bash
homebox show "信号发生器 DG1022"
homebox move "信号发生器 DG1022" --to "4号柜"
```

## Reference

- [references/api.md](references/api.md): endpoint list, entity model, field formats, and API-level quirks and limits.
- [references/local-context.md](references/local-context.md): this deployment's URL, collections and credential location (machine-local, gitignored).
- [references/local-context.example.md](references/local-context.example.md): template when configuring another machine.
