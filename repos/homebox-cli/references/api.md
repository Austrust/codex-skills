# HomeBox API notes (v0.27.x)

Base path: `<instance>/api/v1`. The interactive spec is at `/swagger/doc.json`
and `/swagger/`.

## Authentication and tenancy

- Static API keys: create under Profile -> API Keys, or
  `POST /users/self/api-keys` with `{"name": "...", "expiresAt": "<RFC3339>"}`.
  The response contains the raw token once. Server default TTL is 30 days.
- Every request sends `Authorization: Bearer <raw-api-key>`.
  A session token from `POST /users/login` is returned *with* the literal
  `Bearer ` prefix inside the `token` field, so a session token must be sent as
  `Authorization: <token>`; API keys are sent as `Authorization: Bearer <key>`.
- Collections ("groups" / tenants) are selected with `X-Tenant: <group-uuid>`.
  Without the header the server uses the user's default collection.
- `GET /groups/all` works without a tenant header. Users that have not been
  invited to a collection get `403` on tenant routes (this deployment's custom
  image also blocks creating collections unless the user is a superuser).

## Entities (items + locations)

An "entity" is either an item or a location; the distinction is
`entityType.isLocation`. Fetch `/entity-types` per collection — IDs differ per
collection. `POST /entities` with no `entityTypeId` resolves the default "Item"
type; creating a location requires the collection's location type ID.

Common query parameters for `GET /entities`:

| Param | Meaning |
|---|---|
| `q` | free text across names, descriptions, serial/model, manufacturer, notes, tags, custom fields; `#000-001` looks up an asset ID |
| `page`, `pageSize` | pagination; `page` defaults to all (`-1`) |
| `isLocation` | `true` only locations, `false` only items; **absent means items only** |
| `parentIds` | one or more parent UUIDs |
| `entityTypeIds` | filter by entity type |
| `tags` + `matchAllTags` | tag UUIDs |
| `includeArchived` | include archived entities |
| `orderBy` (name, createdAt, updatedAt, assetId), `orderDirection` | sorting |

Response: `{"page": ..., "pageSize": ..., "total": ..., "items": [EntitySummary],
"totalPrice": ...}`. Entity summary carries `id`, `assetId`, `name`,
`description`, `quantity`, `parent` (summary or null), `entityType`, `tags`,
`imageId`/`thumbnailId`, plus purchase/sale dates.

`GET /entities/{id}` returns the full `EntityOut`: adds `serialNumber`,
`modelNumber`, `manufacturer`, `notes`, purchase/warranty fields, `attachments`,
`fields` (custom fields), and `children` for locations.

### Create

`POST /entities` (`EntityCreate`) accepts: `name` (required), `description`,
`quantity`, `entityTypeId`, `parentId`, `locationId`, `modelNumber`,
`manufacturer`, `tagIds`. It does **not** accept custom fields.

`parentId` semantics:

- item in a location: `parentId` = the location UUID.
- item in a container item: `parentId` = the container item, and `locationId`
  = the physical location when it differs from the container's location.
- sub-location: `parentId` = parent location UUID and the location entity type.

### Update

`PUT /entities/{id}` (`EntityUpdate`) is a **full replacement**, not a patch:
omitted scalar fields reset to zero/empty. Always GET the entity first, merge,
then PUT. `name` is required. Fields: `name`, `description`, `quantity`,
`serialNumber`, `modelNumber`, `manufacturer`, `notes`, `assetId`,
`purchaseDate`, `purchaseFrom`, `purchasePrice`, `warrantyExpires`,
`warrantyDetails`, `soldDate`, `soldTo`, `soldPrice`, `soldNotes`, `insured`,
`archived`, `lifetimeWarranty`, `syncChildEntityLocations`, `tagIds`, `fields`,
`parentId`, `locationId`, `entityTypeId`. The CLI merges for you.

`PATCH /entities/{id}` exists for quantity/parent/tags/type only.

Other entity routes: `GET /entities/{id}/path` (root -> entity), `GET
/entities/tree?withItems=`, `GET /assets/{assetId}`, `POST
/entities/{id}/duplicate`, `DELETE /entities/{id}` (204, cascades children),
`GET /entities/export` (CSV), `POST /entities/import` (multipart CSV).

## Tags

`GET/POST /tags`, `GET/PUT/DELETE /tags/{id}`. TagCreate: `name`, `description`,
`color`, `icon`, `parentId`. Tags are per collection and hierarchical (max
depth 5). Items reference tags through `tagIds`.

## Attachments

`POST /entities/{id}/attachments` is `multipart/form-data` with fields:

- `file` (required)
- `name` (required; filename including extension)
- `type` (optional: `photo`, `attachment`, `manual`, `receipt`, `warranty`;
  inferred from the extension when omitted)
- `primary` (`true`/`false`, only meaningful for photos)

The response is the updated entity. `GET .../attachments/{attachment_id}`
downloads one file; `POST .../attachments/external` links an external URL.
`PUT .../attachments/{attachment_id}` updates title/type/primary, `DELETE`
removes it. Maximum upload size is server-configured.

## Maintenance

- `GET /entities/{id}/maintenance`
- `POST /entities/{id}/maintenance` with `name` (required), `description`,
  `completedDate`, `scheduledDate`, `cost`.
- Dates are `YYYY-MM-DD` (JSON string, empty string = none). `cost` is declared
  with Go's `,string` option, so send it as a JSON **string** (`"12.5"`).
- At least one of completed/scheduled must be set.
- `GET /maintenance`, `PUT/DELETE /maintenance/{id}` operate on entries by ID.

## Dates, IDs, numbers

- Dates marshal as `"YYYY-MM-DD"`; any time component sent is stripped.
- `assetId` marshals as `"000-001"`; the server assigns the next ID.
- `quantity` is a float.
- Custom fields (`fields`) use `{name, type, textValue, numberValue,
  booleanValue}`; write them through `PUT /entities/{id}`.

## Collections, stats, keys, QR

- `GET /groups/all` — collections visible to the user.
- `GET /groups/statistics` — `totalItems`, `totalLocations`, `totalTags`,
  `totalUsers`, `totalItemPrice`, `totalWithWarranty`.
- `/groups/statistics/locations` and `/groups/statistics/tags` may return
  `null` when empty.
- `GET/POST /users/self/api-keys`, `DELETE /users/self/api-keys/{id}`.
- `GET /qrcode?data=<text>` returns a 900x900 JPEG QR code (logo included).
- Label printing is disabled on this deployment's instance (`labelPrinting:
  false` in `/status`); use the QR endpoint or the browser for labels.

## Known limits in v0.27.1

- The UI cannot change a location's parent after creation; the API can
  (`parentId` in `PUT`), which is what `homebox move` uses.
- No stock quantity in/out, purchase orders, BOM, loans, depreciation or work
  orders — HomeBox is an equipment/thing register. Use InvenTree/Snipe-IT for
  those.
- `PUT` replaces the tag set and custom-field list, so always merge from a
  fresh GET (the CLI does).
- OIDC users created on demand have no collection until they accept an invite;
  API calls return 403 for them.
