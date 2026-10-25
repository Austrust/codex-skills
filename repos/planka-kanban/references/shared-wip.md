# Shared WIP policy

## Work stages and archive-only boards

For the maintained seven-column layout, use 收集箱 / 待办 / 进行中 / 等外部 / 等验收 / 已完成 / 看板规则. WIP covers 进行中, 等外部 and 等验收; read the actual limit and list IDs from each board. Legacy names 等待反馈 and 待审核 are still accepted by the routing layer. Adding or renaming stages does not authorize moving tasks or changing capacity.

An explicitly designated archive-only board does not need a machine WIP policy. Within an authorized repair, replace its invalid rule card with a plain-language note such as 存档说明（不参与 WIP）, removing both the `[kanban-policy:v1]` prefix and the `kanban-policy` block. Preserve the card and its history. Empty `wipListIds` remains invalid for work boards. The reader returns `policySource.kind: missing` for the archive note, not an unlimited capacity; do not use that result to start work. Restore work through an active board with a valid policy.

After structural or policy changes, re-fetch the board and verify list order, policy coverage and unchanged task locations, then run the installed `to-kanban/scripts/kanban_context.py refresh`. That rebuilds the local snapshot and clears stale current-route/current-board files while retaining learned preferences. Keep cache files and actual board exports out of Git.

## Policy representation

The source of truth is one card whose name starts with `[kanban-policy:v1]`, normally `[kanban-policy:v1] WIP 规则`, in a visible 看板规则 list. Its description contains one `kanban-policy` fenced JSON block with exactly `schemaVersion: 1`, positive integer `wipLimit`, and non-empty `wipListIds` of actual board list IDs. Include all started-but-unfinished stages, including waiting/review. List IDs survive renaming. The card itself is excluded from WIP.

Place 看板规则 last (the rightmost named list), after all workflow stages. Create workflow lists first, then append the rules list at the maximum current named-list position plus 65536. If publishing a policy card bootstraps the board and rules list first, move that list to the end after creating the workflow stages. When organizing an existing board, preserve the relative order of its work lists and change only the rules list's position. Read a fresh board snapshot, write `{"position": <maximum + 65536>}` to a UTF-8 file, and use `planka_cli.py raw --method PATCH --path /api/lists/<rules-list-id> --file <file>`; re-fetch and verify the rules list is last. Skip the write if it is already last. Keep the policy card in this dedicated list, outside the task flow.

Read:

```powershell
python scripts/planka_cli.py policy-read --board-id <boardId>
```

Create/update using a UTF-8 JSON file:

```json
{"boardId":"board-id","listId":"existing-rules-list-id","policy":{"schemaVersion":1,"wipLimit":2,"wipListIds":["doing-id","waiting-id"]}}
```

```powershell
python scripts/planka_cli.py policy-set --file policy.json --dry-run
python scripts/planka_cli.py policy-set --file policy.json
```

Choose limits and target boards from user intent or existing agreed rules. Two is not a default. A new card requires an existing listId; create a rules list with the normal create-list command only within the authorized board scope. Updating reuses the unique card and preserves prose outside the block. Duplicate cards or malformed rules stop the operation. No local fallback is used by to-kanban, and no automatic migration publishes old local settings.

Recompile if policy or live WIP changes after preview. `apply-plan` checks this for compiled plans carrying policySource metadata; raw move/publish operations remain storage APIs. The check does not provide atomic multi-client locking. Updating rules does not move any work items. All computers need the updated skill scripts, credentials and server URL; policy data itself is read from PLANKA.
