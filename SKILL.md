---
name: to-kanban
description: Turn the current Codex conversation into a Planka todo or verified task update, automatically infer the destination board and list from a shared offline board snapshot plus personalized routing memory, preview all writes, and sync through planka-kanban after confirmation. Use when the user explicitly invokes $to-kanban or asks to send the current conversation to Kanban without naming a board.
---

# To Kanban

Treat this skill as the conversation-facing collection layer over `planka-kanban`. Infer where the work belongs, while delegating Planka authentication, reads, and writes to `planka-kanban`.

## Shared state

Use one state directory that every Codex conversation can access:

- `$CODEX_HOME/to-kanban/` when `CODEX_HOME` is set;
- otherwise `~/.codex/to-kanban/`.

The bundled `scripts/kanban_context.py` owns:

- `memory.json`: non-secret routing preferences and confirmed route history;
- `offline-board.json`: sanitized projects, boards, lists, cards, labels, and checklists used for routing;
- `current-route.json`: the compiler configuration for the currently inferred board;
- `current-board.json`: the matching offline board payload used by `compile_plan.py`.

Never put credentials, cookies, users, email addresses, authorization headers, or full conversation transcripts in these files. Keep only the minimum task title, summary, workspace marker, route, and outcome needed to improve future routing.

## Bootstrap and refresh

1. Locate and read the installed `planka-kanban/SKILL.md` before using its scripts.
2. Initialize shared state:

```powershell
py <to-kanban-skill>/scripts/kanban_context.py init
```

3. Inspect snapshot status:

```powershell
py <to-kanban-skill>/scripts/kanban_context.py status
```

4. Run `refresh` when the snapshot is absent or older than `preferences.snapshotMaxAgeMinutes` (15 by default):

```powershell
py <to-kanban-skill>/scripts/kanban_context.py refresh
```

`refresh` calls `planka_cli.py` and replaces the sanitized offline snapshot atomically. If refresh fails but a prior snapshot exists, routing may continue from it only after clearly reporting its age. If no snapshot exists, stop before planning a write and report the Planka connection problem.

## 1. Summarize the conversation

Choose one of two modes:

- Quick capture: create one new `todo` from the current conversation. Set `primaryNextTask` to `null`.
- Closeout: split independent objectives into task records, update matched cards, and optionally sync one highest-priority next task.

Each task record contains `title`, `status`, `summary`, `completed[]`, `artifacts[]`, `openItems[]`, and optional `cardId`.

Classify conservatively:

- `done`: requested outcome exists and was verified;
- `review`: artifact exists but needs human acceptance;
- `blocked`: progress needs missing input, permission, or an external condition;
- `in_progress`: meaningful work exists but the objective remains unfinished;
- `todo`: captured work that has not started.

For a closeout, `primaryNextTask` is either `relationship: "continuation"` with `parentTaskTitle`, or `relationship: "new"`. Only one next task is promoted; keep other open items in their task comments. Never claim unverified work or include secrets.

## 2. Infer the destination

Write a short-lived UTF-8 route input:

```json
{
  "title": "任务标题",
  "summary": "一句话上下文",
  "status": "todo",
  "workspaceMarkers": ["C:/exact/workspace/path"],
  "keywords": ["project-code", "domain-term"]
}
```

Run:

```powershell
py <to-kanban-skill>/scripts/kanban_context.py route --input <route-input.json> --output <route-result.json>
```

The router scores exact workspace markers, board/project names, current board content, list-role names, and previously confirmed routes. It writes `current-route.json` and `current-board.json` only when one candidate clears both the confidence threshold and ambiguity margin.

When `selected` is present, use it without asking the user to name a board. When `needsConfirmation` is true, show the top candidates with their project, board, target list, score, and reasons, and ask the user to choose once. Persist the chosen IDs with:

```powershell
py <to-kanban-skill>/scripts/kanban_context.py select --input <selection.json>
```

Selection input is `{"boardId":"...","listId":"...","status":"todo"}`. Never resolve ambiguous destinations from semantic similarity alone.

## 3. Compile the Planka plan

Fetch a fresh live payload for the selected board before card matching. Match an existing card only by:

1. explicit `cardId`;
2. one exact title;
3. one normalized title with an exact workspace marker.

Multiple matches are an error. A non-matching quick capture becomes a new card.

Write the structured conversation summary as UTF-8 JSON. Prefer a file-writing tool or Python with explicit UTF-8; do not pipe Chinese JSON through PowerShell. Then run:

```powershell
py <to-kanban-skill>/scripts/compile_plan.py `
  --input <conversation-summary.json> `
  --board <fresh-board.json> `
  --output <planka-plan.json>
```

The default configuration is the inferred `current-route.json`; the default offline board is `current-board.json`. `compile_plan.py` emits operations accepted by `planka_cli.py apply-plan`, uses stable `[to-kanban:<hash>]` markers and `append-once` comments, and supports partial list mappings when only a quick `todo` capture is needed.

## 4. Preview and confirm

Run:

```powershell
py <planka-kanban-skill>/scripts/planka_cli.py apply-plan --file <planka-plan.json> --dry-run
```

Show every proposed card, source and target list, checklist completion/addition, comment summary, and new card. Ask for confirmation. Do not perform the first write in the same turn as the first preview.

After confirmation, refresh the offline snapshot, reroute, fetch the selected board live, recompile, and dry-run again. If the destination, card IDs, target lists, or actions changed, show a revised preview and stop for reconfirmation.

## 5. Apply, learn, and verify

If the second dry-run is unchanged, run `apply-plan` without `--dry-run`. Re-fetch the affected cards or board and verify the actual list, checklist, comments, and new card.

Only after a verified successful write, persist a compact learning record:

```powershell
py <to-kanban-skill>/scripts/kanban_context.py learn --input <learning.json>
```

Learning input contains `title`, optional `summary`, `status`, optional `workspaceMarkers`, `boardId`, `listId`, `listName`, and optional `cardId`. This personalizes future routing without requiring the user to specify a Kanban.

Run `refresh` once more so the offline board reflects the verified write. If `apply-plan` partially fails, report `completedSteps` and `failedStep`; do not blindly replay completed operations and do not learn a failed route as successful.

## Final report

Report the inferred destination, why it was selected, cards created or updated, status changes, checklist changes, duplicate comments skipped, the highest-priority next task, snapshot refresh result, and anything failed or unverified. Ground the report in the post-write board state.
