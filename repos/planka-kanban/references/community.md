# Community 2.x adapter

Use the existing commands in `planka_cli.py` and [shared API workflows](api.md).
The baseline is Community 2.1.1; 2.2.x uses the same workflow but still requires
live discovery. Older 1.x schemas are not covered.

`capabilities` reads `/api/bootstrap`; only a 404 falls back to `/api/config`.
A 401/403 is an authentication/permission failure, not proof of Community.
Unknown edition/version stays unknown. `PLANKA_EDITION=auto|community|pro`
is an optional expectation checked against live evidence, not a way to unlock
unsupported features. Common commands remain usable when version metadata is
unavailable; inspect target records before writes.

Do not send Pro fields, call template/link/dashboard endpoints, or interpret
missing Pro routes as permission to approximate a request with another write.
Custom fields, due dates, checklists and stopwatch are not sufficient evidence
of a Pro edition: the Community baseline already has these capabilities.

Community workflow commands and Python imports remain backward compatible,
including `make_client`, `PlankaClient`, `PlankaError`, `publish_card`,
`complete_card`, `apply_plan` and `redact` in `planka_cli`.

Official baseline: [Community source and release tags](https://github.com/plankanban/planka/releases).
