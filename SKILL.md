---
name: to-kanban
description: Turn the current Codex conversation into clear, independently deliverable Planka work items or verified task updates; infer the destination board and list from shared routing state, preview all writes, and sync through planka-kanban after confirmation. Use when the user explicitly invokes $to-kanban or asks to rewrite, organize, or send the current conversation to Kanban without naming a board.
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

## 1. Design Kanban-quality work items

Before routing or matching cards, rewrite the conversation into work items. Do not copy a project outline directly into cards.

Use these mandatory rules for every new actionable card:

1. Make one card represent one independently reviewable outcome. Split work when parts can be accepted separately, have different dependencies or states, need separate discussion or attachments, or could be pulled by different people.
2. Write the title as `action + deliverable + scope`. Prefer `完成三个代表工况的 UIV 主视觉图`; reject topic-only or vague titles such as `UIV 分析`, `处理论文`, or `继续修改`.
3. Preserve concrete values from the source conversation. Include named methods, dimensions, parameter conventions, case counts, figure roles, and other details needed to understand the card without reopening the transcript.
4. Give each card one concise goal, one concrete deliverable, binary acceptance criteria, and explicit dependencies. Write `无` when there is no prerequisite.
5. Use execution steps only for mechanical actions inside the same deliverable. Promote a step to its own card when it needs a separate owner, state, decision, artifact, attachment, dependency, or acceptance.
6. Keep background knowledge out of the title and acceptance list. Put only the minimum task-specific context in the goal and deliverable.

Use this card shape:

```text
Title: <action + deliverable + scope>
Goal: <one sentence explaining the intended outcome>
Deliverable: <the artifact, decision, dataset, drawing, or verified state>
Acceptance criteria:
- <observable pass/fail condition>
- <observable pass/fail condition>
Dependencies:
- <card title or external prerequisite; use 无 when empty>
Execution steps: <optional mechanical checklist>
```

Prefer 2-6 acceptance criteria. If a card needs many unrelated criteria or produces several independently reviewable artifacts, split it. Acceptance criteria define done; execution steps describe how to get there. Do not mix them.

Order proposed cards by dependency and identify the smallest pullable set. Never move downstream cards into `in_progress` while an unresolved prerequisite blocks them.

## 2. Summarize the conversation

Choose one of two modes:

- Quick capture: create one new `todo` from the current conversation. Set `primaryNextTask` to `null`.
- Closeout: split independent objectives into task records, update matched cards, and optionally sync one highest-priority next task.

Each task record contains:

- required `title`, `status`, `summary`, `deliverable`, and `acceptanceCriteria[]`;
- `dependencies[]` and optional mechanical `steps[]`;
- closeout evidence in `completed[]`, `artifacts[]`, and `openItems[]`;
- optional `cardId` for a verified existing-card match.

For an existing legacy card, reconstruct missing structured fields from the current conversation before preview. For every proposed new card, `deliverable` and at least one acceptance criterion are compiler-enforced. A new `primaryNextTask` uses the same fields; reserve `relationship: "continuation"` for a mechanical next step that remains inside its parent card.

Use this JSON shape for a proposed card:

```json
{
  "title": "完成三个代表工况的 UIV 主视觉图",
  "status": "todo",
  "summary": "用一张图证明 UIV 能解析二维流动结构。",
  "deliverable": "覆盖 epsilon_H 左侧、附近和右侧的一张候选主图",
  "acceptanceCriteria": [
    "制图前记录三个工况的选择规则",
    "每个工况包含二维平均速度和流线"
  ],
  "dependencies": ["统一论文中的 epsilon_H 定义并核对工况覆盖"],
  "steps": ["导出候选图", "检查坐标和图例"],
  "completed": [],
  "artifacts": [],
  "openItems": []
}
```

Classify conservatively:

- `done`: requested outcome exists and was verified;
- `review`: artifact exists but needs human acceptance;
- `blocked`: progress needs missing input, permission, or an external condition;
- `in_progress`: meaningful work exists but the objective remains unfinished;
- `todo`: captured work that has not started.

For a closeout, `primaryNextTask` is either `relationship: "continuation"` with `parentTaskTitle`, or `relationship: "new"`. Only one next task is promoted; keep other open items in their task comments. Never claim unverified work or include secrets.

## 3. Infer the destination

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

## 4. Compile the Planka plan

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

The default configuration is the inferred `current-route.json`; the default offline board is `current-board.json`. `compile_plan.py` emits operations accepted by `planka_cli.py apply-plan`, uses stable `[to-kanban:<hash>]` markers and `append-once` comments, and supports partial list mappings when only a quick `todo` capture is needed. For a new card it writes the goal, deliverable, and dependencies into the description; writes acceptance criteria into an `验收条件` task list; and, when present, writes mechanical steps into the configured execution task list.

## 5. Preview and confirm

Run:

```powershell
py <planka-kanban-skill>/scripts/planka_cli.py apply-plan --file <planka-plan.json> --dry-run
```

Show every proposed card with its goal, deliverable, acceptance criteria, dependencies, source and target list, checklist completion/addition, comment summary, and whether it is new or matched. Also show the proposed pull order and cards held by prerequisites. Ask for confirmation. Do not perform the first write in the same turn as the first preview.

After confirmation, refresh the offline snapshot, reroute, fetch the selected board live, recompile, and dry-run again. If the destination, card IDs, target lists, or actions changed, show a revised preview and stop for reconfirmation.

## 6. Apply, learn, and verify

If the second dry-run is unchanged, run `apply-plan` without `--dry-run`. Re-fetch the affected cards or board and verify the actual list, checklist, comments, and new card.

Only after a verified successful write, persist a compact learning record:

```powershell
py <to-kanban-skill>/scripts/kanban_context.py learn --input <learning.json>
```

Learning input contains `title`, optional `summary`, `status`, optional `workspaceMarkers`, `boardId`, `listId`, `listName`, and optional `cardId`. This personalizes future routing without requiring the user to specify a Kanban.

Run `refresh` once more so the offline board reflects the verified write. If `apply-plan` partially fails, report `completedSteps` and `failedStep`; do not blindly replay completed operations and do not learn a failed route as successful.

## Final report

Report the inferred destination, why it was selected, cards created or updated, status changes, acceptance and execution checklist changes, dependencies, the smallest pullable set, duplicate comments skipped, the highest-priority next task, snapshot refresh result, and anything failed or unverified. Ground the report in the post-write board state.
