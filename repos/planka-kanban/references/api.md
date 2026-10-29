# PLANKA REST API Reference

## Official References

- API reference entry point: https://docs.planka.cloud/docs/category/api-reference/
- Swagger UI: https://docs.planka.cloud/docs/api-reference/swagger-ui/
- Postman docs: https://docs.planka.cloud/docs/api-reference/postman/
- Python SDK: https://docs.planka.cloud/docs/api-reference/python/
- Source route map: https://raw.githubusercontent.com/plankanban/planka/master/server/config/routes.js

## Authentication

Login:

```http
POST /api/access-tokens
Content-Type: application/json

{
  "emailOrUsername": "username-or-email",
  "password": "<redacted>",
  "withHttpOnlyToken": false
}
```

Use the returned token:

```http
Authorization: Bearer <redacted>
```

API keys can be used as bearer tokens. The Python SDK documents both `login(username=..., password=...)` and `login(api_key=...)`.

If login returns `403` with `step: "accept-terms"`, fetch `GET /api/terms` to inspect the terms signature, but only call `POST /api/access-tokens/accept-terms` after the user authorizes accepting terms for that account.

## Response Shape

Most endpoints return:

```json
{
  "item": {},
  "included": {}
}
```

or:

```json
{
  "items": [],
  "included": {}
}
```

`GET /api/boards/{id}` is the most useful board snapshot. It includes board memberships, labels, lists, cards, card memberships, card labels, task lists, tasks, custom fields, custom field values, users, projects, and attachments.

## Publishing Script

Use `scripts/planka_cli.py publish-card` for routine note-to-card publishing. Do not pass Chinese or multiline content through shell arguments or PowerShell stdin; write a UTF-8 JSON file and pass `--file`.

Supported publish spec fields:

```json
{
  "project": "optional project name",
  "projectId": "optional project id",
  "board": "optional board name",
  "boardId": "optional board id",
  "createBoardIfMissing": false,
  "list": "target list name, created if missing",
  "listId": "optional target list id",
  "title": "required card title",
  "cardId": "optional verified existing card id",
  "workItemKey": "optional stable logical task key, reused on retries",
  "description": "optional markdown description",
  "type": "project",
  "taskList": "task list title",
  "tasks": ["optional checklist item"],
  "dueDate": "optional ISO date-time",
  "isDueCompleted": false
}
```

Behavior:

- Resolves project, board, and list by exact name or id.
- Creates a missing board only when `createBoardIfMissing` is true. Board creation uses `POST /api/projects/{projectId}/boards` and requires project-manager permission.
- Creates the target list if it does not exist.
- Uses `type: "project"` by default, because `story` cards do not render task lists.
- Resolves an explicit `cardId`, then the persisted `[kanban-item:<workItemKey>]` description marker, then a unique exact title across the board. Missing explicit IDs and ambiguous or conflicting identities fail instead of creating a replacement. Existing names are retained when targeting by ID/key.
- Writes the identity marker with card creation and preserves it on description edits, so sequential retries can reuse a renamed card after a lost response. This is not a concurrent-create uniqueness lock.
- A match in another list requires `moveExistingToTargetList: true`; otherwise publishing stops before card updates instead of creating a duplicate.
- Creates one task list by name and adds only missing checklist items by exact text.
- Re-fetches the card after publishing and verifies the requested checklist items are present.
- Supports `--dry-run` to show planned writes without modifying Planka.

## Reliable Edit Scripts

Use `complete-card` for the common "finish or advance an old card" path. This prevents partial ad hoc chains where a card is moved but checklist or comments are missed.

Supported complete-card spec fields:

```json
{
  "cardId": "optional card id",
  "project": "optional project name",
  "projectId": "optional project id",
  "board": "optional board name",
  "boardId": "optional board id",
  "title": "required when cardId is omitted",
  "sourceList": "optional source list name for title lookup",
  "sourceListId": "optional source list id for title lookup",
  "moveToList": "optional target list name",
  "moveToListId": "optional target list id",
  "completeTasks": ["Verified criterion"],
  "evidence": {"Verified criterion": "Checked output and result"},
  "taskNames": ["optional exact task name"],
  "comment": "optional comment text",
  "commentMode": "append-once"
}
```

Behavior:

- Resolves the card by `cardId`, or by exact `title` inside a resolved board.
- `sourceList` narrows title lookup and avoids ambiguous same-title cards.
- Moves the card only when `moveToList` or `moveToListId` is present.
- Completes only exact names selected by `completeTasks` or `taskNames`, each backed by an `evidence` entry. Blanket completion and ambiguous names are rejected. Evidence is recorded in a comment; checklist updates precede the card move.
- Appends comments once by default; use `commentMode: "always"` only when duplicate comments are intentional.
- Re-fetches the card and verifies the requested move, task completion, and comment.
- Supports `--dry-run` to show planned writes without modifying PLANKA.

Use `apply-plan` for compound operations that must run in order:

```json
{
  "operations": [
    {
      "action": "complete-card",
      "boardId": "example-board-id",
      "title": "Old card",
      "moveToList": "已完成",
      "completeTasks": ["Verified criterion"],
      "evidence": {"Verified criterion": "Checked output and result"},
      "comment": "Finished."
    },
    {
      "action": "publish-card",
      "boardId": "example-board-id",
      "list": "进行中",
      "title": "Next task",
      "type": "project",
      "tasks": ["First step"]
    }
  ]
}
```

Supported operation actions are `publish-card`, `complete-card`, and `comment`. `apply-plan` stops at the first failed operation and returns `completedSteps` plus `failedStep`, making retries auditable.

For comments with Chinese or multiline text, prefer a JSON spec:

```json
{
  "cardId": "1784666124357469306",
  "comment": "Multiline or Chinese comment.",
  "commentMode": "append-once"
}
```

## Write Operations: Memberships, Attachments, and Recovery

These operational notes were reported from use of a deployed instance. Check its response shape and supported routes when a different version behaves differently; do not infer that a failed request made no changes.

### Card memberships

- Add with `POST /api/cards/{cardId}/card-memberships` and a `userId`. The user must already belong to the destination board; otherwise the observed response is `404 User not found`.
- If board access is missing, establish the necessary board membership first through `POST /api/boards/{boardId}/board-memberships`. An `editor` membership worked in the reported workflow; do not elevate an existing role or grant temporary access without authorization. Record the original membership and role. Revoke only access introduced for the operation when that cleanup is authorized, and then verify that required card assignments still exist.
- Remove with `DELETE /api/cards/{cardId}/card-memberships/userId:{userId}`: use exactly one literal colon. The observed double-colon form returns `400 Invalid userId`; `/api/card-memberships/{membershipId}` returns 404 on that instance.
- No per-card bulk membership removal endpoint was available in the reported instance. Enumerate the verified `(cardId, userId)` pairs and delete individually.

### File attachments

Upload with `POST /api/cards/{cardId}/attachments`, using multipart form data with all three fields:

| Field | Value |
|---|---|
| `file` | Binary file content |
| `type` | `file` |
| `name` | Filename |

Missing fields returned `400 E_MISSING_OR_INVALID_PARAMS`. Use Bearer authentication, not HTTP Basic (which returned 401). For password login, send the authentication payload above to `POST /api/access-tokens`, take the token from the returned `item`, and use it in the Authorization header without logging it. An existing valid Bearer credential does not need another login. The download path `/attachments/{id}/download/{name}` also requires authenticated access; it is not a public attachment link.

### Batch writes and partial failure

Before bulk edits, save the original affected state locally: card IDs, board/list/position, membership `(cardId, userId)` pairs, and exact description text as relevant. These recovery files may contain private data; keep them outside published skill source and routing caches. Preview supported operations with `--dry-run`, execute the authorized changes, and re-fetch to verify. Where the CLI has no dry-run support, prepare a read-only operation preview rather than inventing a flag. After partial failure, reconcile live state and retry only failed or unapplied operations; never replay the whole batch blindly.

## Observed Response Shapes and State Semantics

- Card membership is a separate relation in `included.cardMemberships`; join it to cards by `cardId`. Do not expect a `memberships` property on each card.
- The requested board may be absent from `included.boards`. Resolve its name from the top-level `item` of `GET /api/boards/{id}` or fetch that board separately. A project discovery response may have empty `included.projects`; use `GET /api/projects` and its `items` for the project list.
- List `name` can be null or invisible in the UI. Resolve and operate by verified list IDs rather than guessing a name.
- `isClosed` means archived, not completed. A normal card in a completed list can still have `isClosed: false`. Determine workflow status from the board's mapped list IDs; determine today's work from those states plus the relevant date rules, not from `isClosed` alone.
- `[kanban-policy:v1]` policy cards appear in the ordinary cards collection. Exclude the dedicated policy list and policy cards from task totals; WIP uses the configured active/waiting/review list IDs and excludes configuration cards.
- `dueDate` is stored in UTC. Convert from the user's actual timezone when writing and back when reading. For UTC+08:00, local 21:00 is 13:00Z on the same day; other times and offsets can cross a date boundary. Do not hard-code an eight-hour offset for all users.
- Description newlines are preserved by the server in the reported workflow, while terminal rendering may visually fold them. Compare decoded text (including newline count or visible `\n` markers), not terminal appearance. Length alone cannot establish exact equality.

## User And Project Manager Script

Use `scripts/planka_cli.py ensure-project-managers` to create/reuse users and add them to a project as managers. It requires an admin token/account for user creation. PLANKA requires a project manager user to have global role `admin` or `projectOwner`; the script creates users as `projectOwner` by default and patches existing users to that role when needed.

Input shape:

```json
{
  "project": "Project name",
  "users": [
    {
      "username": "username",
      "email": "username@example.invalid",
      "password": "<redacted>",
      "name": "Display Name",
      "role": "projectOwner",
      "preserveRole": false,
      "language": "zh-CN"
    }
  ]
}
```

Prefer stdin for specs containing passwords so credentials are not left on disk.
Set `preserveRole: true` for an existing user when the requested operation should only add project-manager membership and must not alter the user's global role.

## Permission Model

- A global `boardUser` can access boards where it has membership.
- Board membership role `viewer` can read; viewers may comment if `canComment` is true.
- Board membership role `editor` can create and update lists/cards/tasks/labels/comments and perform normal board edits.
- User, config, webhook, and project-management endpoints may require admin or project-manager rights.
- PLANKA sometimes returns `404` instead of `403` for forbidden board/list/card access to avoid leaking object existence.

## Endpoint Map

Public/bootstrap:

```text
GET    /api/bootstrap
GET    /api/terms
GET    /swagger.json
```

Authentication:

```text
POST   /api/access-tokens
POST   /api/access-tokens/accept-terms
POST   /api/access-tokens/revoke-pending-token
DELETE /api/access-tokens/me
```

Users:

```text
GET    /api/users
POST   /api/users
GET    /api/users/{id}
PATCH  /api/users/{id}
PATCH  /api/users/{id}/email
PATCH  /api/users/{id}/password
PATCH  /api/users/{id}/username
POST   /api/users/{id}/avatar
POST   /api/users/{id}/api-key
DELETE /api/users/{id}
```

Projects and managers:

```text
GET    /api/projects
POST   /api/projects
GET    /api/projects/{id}
PATCH  /api/projects/{id}
DELETE /api/projects/{id}
POST   /api/projects/{projectId}/project-managers
DELETE /api/project-managers/{id}
POST   /api/projects/{projectId}/background-images
DELETE /api/background-images/{id}
```

Boards:

```text
POST   /api/projects/{projectId}/boards
GET    /api/boards/{id}
PATCH  /api/boards/{id}
DELETE /api/boards/{id}
POST   /api/boards/{boardId}/board-memberships
PATCH  /api/board-memberships/{id}
DELETE /api/board-memberships/{id}
```

Labels:

```text
POST   /api/boards/{boardId}/labels
PATCH  /api/labels/{id}
DELETE /api/labels/{id}
```

Lists:

```text
POST   /api/boards/{boardId}/lists
GET    /api/lists/{id}
PATCH  /api/lists/{id}
POST   /api/lists/{id}/sort
POST   /api/lists/{id}/move-cards
POST   /api/lists/{id}/clear
DELETE /api/lists/{id}
```

List create payload:

```json
{
  "type": "active",
  "position": 65536,
  "name": "To Do"
}
```

Cards:

```text
GET    /api/lists/{listId}/cards
POST   /api/lists/{listId}/cards
GET    /api/cards/{id}
PATCH  /api/cards/{id}
POST   /api/cards/{id}/duplicate
POST   /api/cards/{id}/read-notifications
DELETE /api/cards/{id}
POST   /api/cards/{cardId}/card-memberships
DELETE /api/cards/{cardId}/card-memberships/userId:{userId}
POST   /api/cards/{cardId}/card-labels
DELETE /api/cards/{cardId}/card-labels/labelId::{labelId}
```

Card create payload:

```json
{
  "type": "project",
  "position": 65536,
  "name": "Implement API workflow",
  "description": "Markdown is supported.",
  "dueDate": "2026-05-27T10:00:00.000Z",
  "isDueCompleted": false
}
```

Use `"type": "project"` for ordinary actionable cards and any card that needs task lists/checklists. Although the API accepts `"story"`, PLANKA's `StoryContent` modal does not render `TaskLists`; `ProjectContent` does.

Card update/move payload:

```json
{
  "boardId": "target-board-id",
  "listId": "target-list-id",
  "position": 65536,
  "name": "New title",
  "description": "New description",
  "dueDate": null,
  "isDueCompleted": false,
  "isSubscribed": true
}
```

For moves, send the destination `boardId`, `listId`, and `position` together; missing position can return `422 Position must be present`. Ordinary field edits do not require move fields. Cross-board moves can silently clear card memberships: capture them first and verify/reapply authorized assignments on the destination board. Board editors can update all card fields; viewers can only subscribe/unsubscribe.

Tasks:

```text
POST   /api/cards/{cardId}/task-lists
GET    /api/task-lists/{id}
PATCH  /api/task-lists/{id}
DELETE /api/task-lists/{id}
POST   /api/task-lists/{taskListId}/tasks
PATCH  /api/tasks/{id}
DELETE /api/tasks/{id}
```

Attachments:

```text
POST   /api/cards/{cardId}/attachments
PATCH  /api/attachments/{id}
DELETE /api/attachments/{id}
GET    /attachments/{id}/download/{filename}
```

Comments and actions:

```text
GET    /api/cards/{cardId}/comments
POST   /api/cards/{cardId}/comments
PATCH  /api/comments/{id}
DELETE /api/comments/{id}
GET    /api/boards/{boardId}/actions
GET    /api/cards/{cardId}/actions
```

Custom fields:

```text
POST   /api/projects/{projectId}/base-custom-field-groups
PATCH  /api/base-custom-field-groups/{id}
DELETE /api/base-custom-field-groups/{id}
POST   /api/boards/{boardId}/custom-field-groups
POST   /api/cards/{cardId}/custom-field-groups
GET    /api/custom-field-groups/{id}
PATCH  /api/custom-field-groups/{id}
DELETE /api/custom-field-groups/{id}
POST   /api/base-custom-field-groups/{baseCustomFieldGroupId}/custom-fields
POST   /api/custom-field-groups/{customFieldGroupId}/custom-fields
PATCH  /api/custom-fields/{id}
DELETE /api/custom-fields/{id}
PATCH  /api/cards/{cardId}/custom-field-values/customFieldGroupId::{groupId}[:]customFieldId::{fieldId}
DELETE /api/cards/{cardId}/custom-field-values/customFieldGroupId::{groupId}[:]customFieldId::{fieldId}
```

Notifications and services:

```text
GET    /api/notifications
GET    /api/notifications/{id}
PATCH  /api/notifications/{id}
POST   /api/notifications/read-all
POST   /api/users/{userId}/notification-services
POST   /api/boards/{boardId}/notification-services
PATCH  /api/notification-services/{id}
POST   /api/notification-services/{id}/test
DELETE /api/notification-services/{id}
```

Admin/config/webhooks:

```text
GET    /api/config
PATCH  /api/config
POST   /api/config/test-smtp
GET    /api/webhooks
POST   /api/webhooks
PATCH  /api/webhooks/{id}
DELETE /api/webhooks/{id}
PATCH  /api/_internal/config
```

## Practical Position Values

PLANKA accepts numeric positions. Use `65536` for first item in an empty list. When inserting between known positions, use their midpoint. When appending, use max position plus `65536`.

## Common Troubleshooting

- `401 E_UNAUTHORIZED`: token missing, invalid, or expired; login again.
- `403 termsAcceptanceRequired`: terms must be accepted before token issuance.
- `403 Not enough rights`: current user lacks editor/admin/project-manager rights.
- `404 E_NOT_FOUND`: object does not exist or access is hidden by permission checks.
- `422 positionMustBePresent`: include `position` when creating/moving cards or lists as required.
