---
name: planka-kanban
description: Use for inspecting or editing PLANKA kanban boards through the REST API, including login/API-key authentication, reading projects/boards/lists/cards, creating and moving cards, editing labels/tasks/comments/custom fields, and safely handling Planka write operations without browser automation.
---

# Planka Kanban

Use the PLANKA REST API instead of browser automation. Keep credentials out of chat, logs, and files; prefer environment variables.

## Workflow and evidence boundaries

This skill is the API execution layer. For conversation capture, readiness, WIP and dependency decisions, use `to-kanban` and its compiler. Direct user-directed edits remain supported; before proposing a new start, read the agreed board capacity and dependencies, and apply the same checks. Do not use raw move/publish commands to bypass a failed flow check.

- Distinguish inbox (unclarified/unready) from ready todo. Do not infer readiness solely from a title or manufacture missing acceptance conditions.
- Count started work waiting for feedback or review in WIP. Record already-observed work honestly even when over capacity, reporting the violation; do not use this exception to initiate more work.
- Completion uses explicit task names plus per-name verified `evidence`. `completeTasks: "all"` and `allTasks: true` are rejected. The CLI validates evidence coverage, not the truth of assertions; inspect artifacts or attribute explicit user confirmation before writing.
- Read all acceptance criteria before a done move, check each against evidence, and retain review/in-progress if anything is unresolved. Execution checklists and acceptance criteria are distinct. A raw move is a storage operation and does not itself validate completion or WIP.
- Re-read live state before applying a compiled plan. The API does not lock concurrent writers; report post-write discrepancies and stop before further starts.

## Shared WIP policy

Maintained Chinese work boards use 收集箱 / 待办 / 进行中 / 等外部 / 等验收 / 已完成 / 看板规则. Count 进行中, 等外部 and 等验收 by their actual list IDs; preserve each board's agreed limit. Archive-only boards use a plain-language exemption note instead of a machine policy with empty list IDs. See [references/shared-wip.md](references/shared-wip.md) for the representation and post-change cache synchronization.

Keep the dedicated 看板规则 list last, to the right of all workflow stages. If it was created first while bootstrapping a board, move it to the end once the work lists exist; preserve work-list order and verify the final placement.

Read [references/shared-wip.md](references/shared-wip.md) to configure or inspect board-owned WIP rules. Use `policy-read` and `policy-set`; do not invent a native board field. The policy card is shared through PLANKA and is not a work item. Direct start decisions must read it too. Compiled plans recheck policy/WIP before applying; this does not lock concurrent writers.

## Quick Start

1. Read `references/api.md` when endpoint details, payload fields, or permission boundaries matter.
2. Use `scripts/planka_cli.py` for common operations before hand-writing HTTP calls.
3. Authenticate with `PLANKA_BASE_URL` (also accepts `PLANK_USER_BASE_URL`) plus either `PLANKA_API_KEY` or `PLANKA_USERNAME`/`PLANKA_PASSWORD`.
4. Start with read-only discovery: projects -> board -> lists/cards -> membership role.
5. Ask for explicit confirmation before destructive or broad writes: delete, clear, move many cards, manage users/config/webhooks, or accept terms.

## Safety Rules

- Never print tokens, API keys, passwords, cookies, pending tokens, or full authorization headers.
- Redact secrets as `<redacted>` in summaries.
- Treat `POST /api/access-tokens/accept-terms` as a user-visible account state change; only call it when the user authorizes accepting terms.
- Prefer dry-run summaries for multi-card changes. Show the target project/board/list/card names and IDs before writing.
- For live boards, make the smallest change that verifies capability, then stop unless the user asked for broader edits.
- If the instance returns `403`, inspect the response `X-Exit` header and body. Common causes are `termsAcceptanceRequired`, `notEnoughRights`, or admin-only endpoints.

## Discovery Workflow

Run:

```bash
python scripts/planka_cli.py whoami
python scripts/planka_cli.py projects
python scripts/planka_cli.py board --board-id <boardId>
```

When resolving names, prefer exact matches. If names are ambiguous, ask the user which project, board, list, or card to edit.

## Editing Workflow

Do not hand-write `python -c` snippets or ad hoc API scripts for routine writes. Use the CLI commands below with UTF-8 JSON specs so Chinese text, multiline descriptions, and retry behavior stay reliable.

For publishing a user note/image/chat message as a kanban task, do not hand-write HTTP scripts. Create a UTF-8 JSON spec and use `publish-card`:

```json
{
  "boardId": "example-board-id",
  "list": "待办",
  "title": "【备忘】联系进口768及国产768厂家",
  "description": "Source and full details here.",
  "type": "project",
  "taskList": "执行清单",
  "tasks": [
    "确认联系人",
    "完成联系",
    "记录反馈"
  ],
  "dueDate": "2026-05-28T04:00:00.000Z"
}
```

Run a dry-run first when target resolution is not obvious:

```bash
python scripts/planka_cli.py publish-card --file draft.json --dry-run
python scripts/planka_cli.py publish-card --file draft.json
```

Prefer `--file` over shell arguments or stdin for Chinese, addresses, phone numbers, or multiline descriptions. This avoids Windows/PowerShell encoding problems; in PowerShell, piped Chinese JSON can be converted to `???` before Python receives it.

For finishing or advancing an existing card, use `complete-card` instead of mixing `move-card`, task patches, and comments by hand:

```json
{
  "boardId": "example-board-id",
  "title": "高压超声主机",
  "sourceList": "等待反馈",
  "moveToList": "已完成",
  "completeTasks": ["确认主机可用"],
  "evidence": {"确认主机可用": "用户确认已借用到高压主机并可进入预实验"},
  "comment": "2026-06-02 更新：目前已借用到高压主机，进入下一阶段岩石声速/含水状态预实验。",
  "commentMode": "append-once"
}
```

Run:

```bash
python scripts/planka_cli.py complete-card --file complete.json --dry-run
python scripts/planka_cli.py complete-card --file complete.json
```

For a compound user intent such as "complete the old card and create the next task", create one ordered plan and use `apply-plan`:

```json
{
  "operations": [
    {
      "action": "complete-card",
      "boardId": "example-board-id",
      "title": "高压超声主机",
      "moveToList": "已完成",
      "completeTasks": ["确认主机可用"],
  "evidence": {"确认主机可用": "用户确认已借用到高压主机并可进入预实验"},
      "comment": "2026-06-02 更新：目前已借用到高压主机。"
    },
    {
      "action": "publish-card",
      "boardId": "example-board-id",
      "list": "进行中",
      "title": "开展高压探头击穿岩石测试预实验",
      "type": "project",
      "taskList": "执行清单",
      "tasks": ["准备岩石样品", "完成含水/非含水对照", "整理结果"]
    }
  ]
}
```

Run:

```bash
python scripts/planka_cli.py apply-plan --file plan.json --dry-run
python scripts/planka_cli.py apply-plan --file plan.json
```

`apply-plan` stops at the first failed operation and reports completed steps plus the failed step, so a retry can start from a known state.

To create a new board/page while publishing, include `project` or `projectId`, `board`, and `createBoardIfMissing: true`. Board creation requires PLANKA project-manager permission:

```json
{
  "project": "Project name",
  "board": "New board/page name",
  "createBoardIfMissing": true,
  "list": "待办",
  "title": "Card title",
  "type": "project",
  "tasks": ["First task"]
}
```

For creating/reusing users and adding them as project managers, use `ensure-project-managers` with stdin or a short-lived UTF-8 JSON spec. Do not store long-lived password files:

```bash
python scripts/planka_cli.py ensure-project-managers --stdin
```

For a normal card edit:

1. Fetch the board and confirm the current user has board membership role `editor`.
2. Resolve the target list and card IDs from the board payload.
3. Use `PATCH /api/cards/{id}` for moves or field edits. Include `position` when moving to another list.
4. Re-fetch the board or card after the write and summarize the resulting state.

For a new card:

```bash
python scripts/planka_cli.py create-card --list-id <listId> --name "Card title" --type project --position 65536
```

Use `--type project` for cards that need task lists/checklists, due dates, stopwatch, or the standard task-oriented card modal. PLANKA's `story` card modal does not render task lists.

For moving a card:

```bash
python scripts/planka_cli.py move-card --card-id <cardId> --list-id <listId> --position 65536
```

## Tooling Notes

The bundled CLI is intentionally small and dependency-free. For large integrations, the official `plankapy` package is a good option, but do not install dependencies unless needed for the task.

If the PLANKA instance is only reachable through SSH tunneling, follow any repository SSH logging rules before considering the task complete.
