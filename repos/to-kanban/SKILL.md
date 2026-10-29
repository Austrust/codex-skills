---
name: to-kanban
description: Turn the current Codex conversation into coherent outcome-level Planka work items or verified task updates; infer the destination board and list from shared routing state, preview all writes, and sync through planka-kanban after confirmation. Use when the user explicitly invokes $to-kanban or asks to rewrite, organize, or send the current conversation to Kanban without naming a board.
---

# To Kanban

Treat this skill as the conversation-facing collection layer over `planka-kanban`. Infer where the work belongs, while delegating Planka authentication, reads, and writes to `planka-kanban`.

## Flow policy

The maintained Chinese work-board order is 收集箱 / 待办 / 进行中 / 等外部 / 等验收 / 已完成 / 看板规则. `等外部` maps to `blocked`, and `等验收` to `review`; old names 等待反馈 and 待审核 remain supported aliases. WIP includes 进行中, 等外部 and 等验收, using the live policy's list IDs and board-specific limit. Read [references/flow-policy.md](references/flow-policy.md) for archive-only boards and cache refresh behavior.

When creating or organizing a board, put the dedicated 看板规则 list last (rightmost), after the workflow stages. Keep its configuration card out of the task flow; follow planka-kanban's shared-WIP instructions to place and verify the list.

Read [references/flow-policy.md](references/flow-policy.md) before compiling a plan. It defines WIP configuration, dependency evidence, and completion evidence.

- Capture incomplete ideas as `inbox`; `todo` means ready to pull, with a deliverable, acceptance criteria and satisfied dependencies. Never silently map inbox to todo or create lists without authorization.
- Before proposing new starts, review existing WIP: prefer finishing, reviewing or unblocking it. Count in_progress, review and already-started blocked cards. Do not move started work to inbox/todo to free capacity.
- `intent: "propose"` is the default. Use `intent: "record"` only when the conversation supplies evidence work has already started; report capacity/dependency violations instead of hiding actual work. This is not an override for starting new work.
- No universal WIP limit is assumed. Read the board's shared `[kanban-policy:v1]` card; local boardPolicies are no longer authoritative; if absent, capture work and request the missing capacity policy before proposing a start. Recompile against fresh live state immediately before applying. Concurrent writers are not locked by the CLI.
- Completion requires evidence for every acceptance condition, including existing live conditions. A checklist checkmark or status label alone is not evidence. Scientific negative results may satisfy a criterion about producing a valid experiment or decision; never require support for a hypothesis unless that is truly the agreed deliverable.

## Shared state

On the first invocation, require the user to specify an absolute local state folder before initializing, refreshing, routing, or compiling. If the invocation already supplies a folder, use it without asking again. Otherwise ask where to store To Kanban local files and wait for the answer; do not pick the workspace or the legacy default automatically.

Remember the chosen folder with `kanban_context.py configure --path "<absolute-folder>"`. This stores only a `stateDir` path in `$CODEX_HOME/to-kanban-location.json` (or `~/.codex/to-kanban-location.json`). All task state belongs in the chosen folder. Later conversations read this pointer and reuse the folder without asking again. A missing or invalid pointer requires a folder choice; legacy `~/.codex/to-kanban/` data alone does not count as a choice.

Change the saved location only on a user's request. Configuring another folder does not migrate or delete old data; ask about migration only if it is needed. `--state-dir` is a one-command override, not persistent setup, and must not bypass the first-use folder choice. If the chosen folder is inaccessible, report the issue rather than silently falling back.

Put short-lived route inputs, summaries, live board payloads, plans and learning records under `<state-folder>/work/<unique-operation-id>/` to avoid mixing conversations. Do not create these in the research project by default.

The bundled `scripts/kanban_context.py` owns:

- `memory.json`: non-secret routing preferences and confirmed route history;
- `offline-board.json`: sanitized projects, boards, lists, cards, labels, and checklists used for routing;
- `current-route.json`: the compiler configuration for the currently inferred board;
- `current-board.json`: the matching offline board payload used by `compile_plan.py`.

Never put credentials, cookies, users, email addresses, authorization headers, or full conversation transcripts in these files. Keep only the minimum task title, summary, workspace marker, route, and outcome needed to improve future routing.

## Bootstrap and refresh

1. Locate and read the installed `planka-kanban/SKILL.md` before using its scripts.
2. Read the location pointer. If it is missing or invalid, obtain the folder from the user first and remember it:

```powershell
py <to-kanban-skill>/scripts/kanban_context.py configure --path "<absolute-folder>"
```

Then initialize shared state in the configured folder:

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

`refresh` calls `planka_cli.py`, replaces the sanitized offline snapshot atomically, and removes `current-route.json` and `current-board.json` so the next route uses the new lists and policy. It preserves routing history and workspace preferences. Refresh after board structure or policy changes even if the snapshot is younger than 15 minutes. If refresh fails but a prior snapshot exists, routing may continue from it only after clearly reporting its age. If no snapshot exists, stop before planning a write and report the Planka connection problem.

## 1. Design Kanban-quality work items

Default to one card per user-valued outcome or stage goal. First identify the goal and route to its board, read existing cards, and match the current work before rewriting titles or considering new cards. Progress, rework, additional figures and next steps for the same goal normally update the existing card by `cardId`.

1. Keep preparation, analysis, comparison, decisions, figures and reporting together when they serve one outcome. Several files, attachments, acceptance checks or internal dependencies do not by themselves justify separate cards.
2. Split only when BOTH are true: each part has independent value (it can be delivered or cancelled independently), AND there is an actual need to schedule its owner, priority, delivery date or workflow state separately. Collaboration alone is insufficient.
3. Execution steps may include intellectual work and decisions, not just mechanical actions. Track useful milestones, not every command or verification action. Keep internal ordering in the checklist; reserve card dependencies for real prerequisites between separately managed outcomes.
4. Write titles as action + outcome + scope. Preserve concrete source details in the description. Use as few outcome-based acceptance criteria as needed; one is enough for a simple task. Do not invent missing criteria.
5. Ordinary capture/closeout defaults to 0–1 new cards. Multiple independent goals may justify more. More than three new cards requires a merge review and `batchReason` explaining the batch; this is not a quota or a reason to hide requested work.

The compiler validates explicit grouping and split reasons; it cannot infer semantic independence from prose. If it rejects a split, combine the input records into one coherent card before recompiling. Do not invent different goal IDs to bypass the check or merge incompatible states/evidence mechanically.

Example: “完成三个工况的 UIV 分析并判断是否适合作为论文主图” is one card, with data preparation, plotting, comparison and the decision as steps. Data, figures and a conclusion are one deliverable package. “统一参数定义” becomes separate only if it independently serves other tasks and actually needs separate scheduling.

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
Execution steps: <optional key milestones, including analysis and decisions>
```

Use concise acceptance criteria for the agreed outcome. Review unrelated goals using the two-part split test above; multiple artifacts alone are not a split trigger. Acceptance criteria define done; execution steps describe how to get there. Do not mix them.

Order proposed cards by dependency and identify the smallest pullable set. Never move downstream cards into `in_progress` while an unresolved prerequisite blocks them.

## 2. Summarize the conversation

Choose one of two modes:

- Quick capture: update a matching existing card at its verified current state, or create one new `inbox` if no match exists. Set `primaryNextTask` to `null`.
- Closeout: group work by existing goal, update matched cards, and add only independently justified new outcomes. The next step normally stays on its parent card.

Each task record contains:

- required `title`, `status`, `summary`; `deliverable` and `acceptanceCriteria[]` are required outside inbox;
- `dependencies[]` and optional milestone `steps[]`;
- closeout evidence in `completed[]`, `artifacts[]`, and `openItems[]`;
- optional `cardId` for a verified existing-card match.

For an existing legacy card, reconstruct missing structured fields from the current conversation before preview. For every proposed new card outside inbox, `deliverable` and at least one acceptance criterion are compiler-enforced. A new `primaryNextTask` uses the same fields; use `relationship: "continuation"` for any next step within the same goal, including analysis, revision or decision-making. A `relationship: "new"` candidate is matched through the normal card identity path; if it already exists, its live state is retained without re-publishing it.

Identity and grouping fields:

- `goalId`: stable user-goal identifier, shared by records belonging to the same goal. Reuse it across conversations; do not derive a new ID from each rewritten title.
- `taskKey`: stable part identifier only when an independently justified split needs several cards under one goal. Otherwise identity uses `goalId` (legacy single records fall back to normalized title). Identity is scoped to board and the exact sorted `workspaceMarkers`; reuse these markers on retries.
- `newCardReason`: why the requested outcome is not covered by an existing card. Supply it for every proposed new card; the compiler requires it and `goalId` whenever more than one card would be created.
- `independentValue` and `splitReason`: required on every part when several records share a goal. Explain the independent value and actual separate scheduling need respectively; each part also needs a distinct `taskKey`.
- Summary-level `operationId`: a unique identifier for this logical update. Save and reuse the same input and ID on retries, including after a lost response; use a new ID for a substantive new update. If omitted, the compiler hashes the original normalized input rather than live matched IDs.
- Summary-level `batchReason`: required after a merge review when more than three new cards remain. `tasks: []` with no next task is a valid no-op when nothing needs syncing.

Use this JSON shape for a proposed card:

```json
{
  "goalId": "uiv-three-case-main-figure",
  "newCardReason": "现有卡片尚未覆盖三工况主图及选图结论",
  "title": "完成三个代表工况的 UIV 主视觉图",
  "status": "inbox",
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
- `todo`: ready to pull; deliverable and acceptance criteria are clear and prerequisites are verified.
- `inbox`: captured work that needs clarification or has unmet prerequisites; not yet started.

For a closeout, `primaryNextTask` is either `relationship: "continuation"` with `parentTaskTitle`, or `relationship: "new"`. Only one next task is promoted; keep other open items in their task comments. Never claim unverified work or include secrets.

## 3. Infer the destination

Write a short-lived UTF-8 route input:

```json
{
  "title": "任务标题",
  "summary": "一句话上下文",
  "status": "inbox",
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
2. one persisted `[kanban-item:<key>]` identity marker derived from `taskKey` or `goalId`;
3. one exact title;
4. one normalized title with an exact workspace marker.

For legacy cards without an identity marker, inspect their scope before drafting. When the goal is clearly the same despite different wording, carry its verified `cardId`; do not use fuzzy matching to mutate an uncertain card. Retain established goal IDs and workspace markers in saved operation inputs.

Multiple matches are an error. A non-matching quick capture becomes a new card.

Write the structured conversation summary as UTF-8 JSON. Prefer a file-writing tool or Python with explicit UTF-8; do not pipe Chinese JSON through PowerShell. Then run:

```powershell
py <to-kanban-skill>/scripts/compile_plan.py `
  --input <conversation-summary.json> `
  --board <fresh-board.json> `
  --output <planka-plan.json>
```

The default configuration is the inferred `current-route.json`; the default offline board is `current-board.json`. Supply a fresh live board for write plans; the compiler re-reads its shared WIP policy rather than trusting cached/local policy values. `compile_plan.py` emits operations accepted by `planka_cli.py apply-plan`, uses stable `[to-kanban:<hash>]` markers and `append-once` comments, and supports partial list mappings when only a quick `inbox` capture is needed. For a new card it writes the goal, deliverable, and dependencies into the description; writes acceptance criteria into an `验收条件` task list; and, when present, writes key execution milestones into the configured execution task list.

## 5. Preview and confirm

Run:

```powershell
py <planka-kanban-skill>/scripts/planka_cli.py apply-plan --file <planka-plan.json> --dry-run
```

Show the new/update counts and the reasons for any split, then every proposed card with its goal, deliverable, acceptance criteria, dependencies, source and target list, checklist completion/addition, comment summary, and whether it is new or matched. Also show WIP before/after, configured limit, source policy card ID/fingerprint, flow warnings, evidence references, and the proposed pull order and cards held by prerequisites. Ask for confirmation. Do not perform the first write in the same turn as the first preview.

After confirmation, refresh the offline snapshot, reroute, fetch the selected board live, recompile, and dry-run again. If the destination, card IDs, target lists, or actions changed, show a revised preview and stop for reconfirmation.

## 6. Apply, learn, and verify

If the second dry-run is unchanged, run `apply-plan` without `--dry-run`. Re-fetch the affected cards or board and verify the actual list, checklist, comments, and new card.

Only after a verified successful write, persist a compact learning record:

```powershell
py <to-kanban-skill>/scripts/kanban_context.py learn --input <learning.json>
```

Learning input contains `title`, optional `summary`, `status`, optional `workspaceMarkers`, `boardId`, `listId`, `listName`, and optional `cardId`. This personalizes future routing without requiring the user to specify a Kanban.

If a flow check fails, revise the proposal (for example retain an unready item in inbox) rather than bypassing the compiler. A prerequisite completed in this plan must be applied and verified before compiling a dependent ready/start operation.

Run `refresh` once more so the offline board reflects the verified write. A sequential retry reuses stable card identity across title/list changes; concurrent create requests are not protected by a server-side uniqueness lock. Re-read and reconcile after an uncertain outcome rather than launching parallel retries. If `apply-plan` partially fails, report `completedSteps` and `failedStep`; do not blindly replay completed operations and do not learn a failed route as successful.

## Final report

Report the inferred destination, why it was selected, cards created or updated, status changes, acceptance and execution checklist changes, dependencies, the smallest pullable set, duplicate comments skipped, the highest-priority next task, snapshot refresh result, and anything failed or unverified. Ground the report in the post-write board state.
