---
name: to-kanban
description: Summarize the current Codex conversation into verified task outcomes, preview Planka card state/comment/checklist changes, and after explicit confirmation sync those changes plus one prioritized next task through the planka-kanban skill. Use only when the user explicitly invokes $to-kanban or explicitly asks to close out the current conversation into Kanban.
---

# To Kanban

Turn the current conversation into a reviewable Planka update. Use `planka-kanban` for all board discovery and writes; do not reimplement authentication or REST calls.

## Prerequisites

1. Locate and read the installed `planka-kanban/SKILL.md`.
2. Require its normal `PLANKA_BASE_URL` and authentication environment variables.
3. Load `$CODEX_HOME/to-kanban.json`; when `CODEX_HOME` is unset, load `~/.codex/to-kanban.json`.
4. Require this configuration shape and exact list names:

```json
{
  "boardId": "1784117505569063970",
  "lists": {
    "todo": "待办",
    "in_progress": "进行中",
    "blocked": "等待反馈",
    "review": "待审核",
    "done": "已完成"
  },
  "taskListName": "下一步"
}
```

Never store Planka credentials in this file.

## Workflow

### 1. Inspect the board without writing

Fetch the configured board with `planka_cli.py board --board-id <boardId>`. Confirm that all five configured list names exist exactly once.

Match each independent conversation task in this order:

1. An explicitly supplied card ID.
2. One exact card title.
3. One normalized title whose description contains an exact workspace marker.

Treat multiple matches as an error. Do not use a semantic-only similarity match. When no card matches, mark the task as a proposed new card; creation still requires the preview confirmation below.

### 2. Summarize only evidenced work

Split independent objectives into separate task records. For each record, capture:

- `title`
- `status`: `todo`, `in_progress`, `blocked`, `review`, or `done`
- one-sentence `summary`
- verified `completed` items
- verified `artifacts` such as paths, commits, or URLs
- remaining `openItems`
- optional matched `cardId`

Classify status conservatively:

- `done`: the requested outcome exists and was verified.
- `review`: the artifact exists but needs human acceptance or review.
- `blocked`: progress requires missing input, permission, or an external condition.
- `in_progress`: meaningful work exists but the objective remains unfinished.
- `todo`: the objective was identified but not started.

Choose exactly one `primaryNextTask`. Use `relationship: "continuation"` with `parentTaskTitle` when it belongs on the current card, or `relationship: "new"` when it deserves a separate todo card.

Do not include credentials, tokens, cookies, authorization headers, unverified completion claims, or speculative artifact paths.

### 3. Compile a deterministic update plan

Write the summary and board snapshot as short-lived UTF-8 JSON files. Prefer a file-writing tool or Python with explicit UTF-8; do not pipe Chinese JSON through PowerShell.

Run:

```powershell
py <to-kanban-skill>/scripts/compile_plan.py `
  --input <conversation-summary.json> `
  --board <board-snapshot.json> `
  --output <planka-plan.json>
```

Pass `--config <path>` only when using a non-default configuration path. The compiler:

- validates the five-state mapping and summary schema;
- resolves only safe card matches;
- emits `complete-card`, `publish-card`, and `comment` operations accepted by `planka_cli.py apply-plan`;
- adds a stable `[to-kanban:<hash>]` marker and `append-once` comments;
- completes all existing checklist items only when an existing task is classified `done`;
- adds a continuation as a deduplicated checklist item, or creates one independent todo card.

### 4. Preview and request confirmation

Run:

```powershell
py <planka-kanban-skill>/scripts/planka_cli.py apply-plan --file <planka-plan.json> --dry-run
```

Show a compact preview containing every current card, source and target list, checklist completion/addition, comment summary, and proposed next card. Ask the user to confirm the displayed writes. Do not write during the same turn as the first preview.

### 5. Revalidate, apply, and verify

After confirmation:

1. Fetch a fresh board snapshot.
2. Recompile and rerun the dry-run.
3. Compare card IDs, target lists, and planned actions with the confirmed preview.
4. If they changed, stop and show a revised preview.
5. Otherwise run `apply-plan` without `--dry-run`.
6. Re-fetch affected cards or the board and verify their final list, checklist counts, comments, and next card.

If `apply-plan` reports a partial failure, report `completedSteps` and `failedStep`. Do not blindly retry completed operations.

## Final Report

Report:

- cards created or updated;
- old and new statuses;
- checklist items completed, added, and still open;
- comments added or skipped as duplicates;
- the single highest-priority next task;
- any failed or unverified operation.

Keep the report grounded in the post-write board snapshot.
