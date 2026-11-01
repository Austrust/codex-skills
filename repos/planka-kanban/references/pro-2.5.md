# Pro 2.5.0 adapter

Run `python scripts/planka_cli.py capabilities`, then use common commands for
ordinary cards and `pro --file operation.json [--dry-run]` for the operations
below. Pro commands require live bootstrap evidence: a license object and version
`2.5.0`. A newer version requires contract review; an environment override cannot
substitute for that evidence. Discovery does not modify or validate licenses.

## Supported operation specs

| action | Additional fields | Behavior |
|---|---|---|
| `search` | `query` (1–128 characters) | Global search |
| `dashboard` | `panel` optional, default `due-cards` | Read one dashboard panel |
| `teams` | none | Read teams and included relations |
| `board-templates` | none | Read global board templates |
| `card-templates` | none | Read card template catalog |
| `personal-card-templates` | none | Read personal card templates |
| `template-destinations` | none | Read template destinations |
| `board-template-config` | `boardId` | Read board template configuration |
| `link-access` | `cardId` | Inspect linked-card access |
| `custom-field-entries` | `cardId` | Read repeated custom-field group entries |
| `link-card` | `cardId`, `listId`, `position` | Create a link to the source card; reuse a single existing link in that list |
| `apply-template` | template `cardId`, `listId`, `position`, `createNew: true`, optional `name` | Create a new card from a template |
| `update-card` | `cardId`, `fields` | Patch `startDate`, `dueDate`, `isDueCompleted`, `locationName`, `isDraft` |

Dashboard panels: `recently-touched-by-me`, `member-cards-with-activity`,
`due-cards`, `recent-contributors`, `collaborators`, `pulse`, `forgotten`, `config`.
IDs are strings, never JSON numbers. Dates use ISO date-time strings or null;
the server validates formats. Use UTF-8 files for Chinese text.

```json
{"action":"link-card","cardId":"123","listId":"456","position":65536}
```

```json
{"action":"apply-template","cardId":"123","listId":"456","position":65536,"createNew":true,"name":"New outcome"}
```

```json
{"action":"update-card","cardId":"123","fields":{"startDate":"2026-11-02T01:00:00.000Z","isDraft":false}}
```

Writes read the source and (for creation) destination first. `--dry-run` only
reads, then returns method/path/body. Actual writes re-fetch the resulting card
and compare requested fields or destination/source relation. Template application
creates a new card on each execution; it is not idempotent. After a lost response,
inspect the destination and reconcile before retrying. Link reuse protects
sequential retries only; it does not lock concurrent writers. Existing links are
reused without repositioning them.

## Semantics and boundaries

- `linkedCardId` identifies the canonical source. Board payloads can include
  source cards from other boards. Filter by actual `boardId`/`listId` before title
  resolution or WIP counting. A linked card is a placement, not an independent
  deliverable. Do not pass linked cards into common publish/complete flows;
  inspect source and destination, clarify intended scope when needed, and use
  the canonical source for content changes. Pro writes reject a linked source.
- Pro can return `teams`, `teamMemberships`, `boardTeams`, `cardTeams`,
  `labelGroups`, and repeated custom-field entries. Preserve these relations;
  do not equate a team assignment with a direct card membership.
- Common start/done evidence and WIP rules also apply to link/template writes.
  The Pro adapter validates API mechanics, not task readiness or acceptance.
- Public boards, public share links, team grants and permission changes need
  explicit user intent. No operation above turns them on implicitly.
- Recurrence, access changes, team writes, template configuration writes,
  description-editing locks, and exports are not implemented by the typed Pro
  adapter. Inspect the deployed version's contract before an authorized raw call;
  do not guess JSON schemas or imply complete Pro feature coverage.
- `apply-plan` continues to accept common actions only. Run Pro operations
  separately; never silently translate them into common actions.

## Evidence and verification

2026-11-01: routes and input contracts inspected from the deployed 2.5.0 image
(`config/routes.js`, relevant controllers). Only derived contracts are included;
no commercial source, credentials or live exports are distributed with this skill.
Live read-only verification passed for discovery, search, dashboard, teams,
global/personal template reads and destinations, plus `update-card` dry-run.
Write behavior is covered offline; no production mutation was used for testing.

The deployment's `/swagger.json` returned 404 even though a route exists in the
image. Do not assume public Swagger represents this Pro build.
Official context: [Pro 2.5.0 announcement](https://planka.app/blog/planka-pro-v2-5-0)
and [API documentation](https://docs.planka.cloud/docs/category/api-reference/).
