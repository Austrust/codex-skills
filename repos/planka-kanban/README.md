# Planka Kanban

Codex skill for inspecting and editing PLANKA kanban boards through the REST API.

## What It Includes

- `SKILL.md`: Codex skill instructions and safety rules.
- `scripts/planka_cli.py`: Dependency-free PLANKA API helper; reuses cards by ID or stable work-item key on retries.
- `scripts/planka_transport.py`: Shared HTTP/authentication and redacted output.
- `scripts/planka_editions.py`: Live edition/version discovery and CLI routing.
- `scripts/planka_pro.py`: Isolated Pro 2.5.0 operations with preview and read-back verification.
- [Community compatibility](references/community.md) and [Pro operations](references/pro-2.5.md): active edition-specific contracts, examples and verification limits.
- `scripts/test_publish_identity.py`: Offline regression coverage for card identity, retry recovery and checklist/comment deduplication.
- `references/api.md`: Practical PLANKA REST API notes.
- [Shared WIP policy](references/shared-wip.md): maintained workflow stages, board-owned capacity, archive exemption and cache synchronization.
- `agents/openai.yaml`: Codex skill interface metadata.

## Authentication

Set environment variables before running the CLI:

```bash
export PLANKA_BASE_URL="https://your-planka.example"
export PLANKA_API_KEY="<redacted>"
```

or:

```bash
export PLANKA_BASE_URL="https://your-planka.example"
export PLANKA_USERNAME="username"
export PLANKA_PASSWORD="<redacted>"
```

## Examples

```bash
python scripts/planka_cli.py whoami
python scripts/planka_cli.py capabilities
python scripts/planka_cli.py projects
python scripts/planka_cli.py board --board-id <boardId>
```

Create or update a card from a UTF-8 JSON spec:

```bash
python scripts/planka_cli.py publish-card --file draft.json --dry-run
python scripts/planka_cli.py publish-card --file draft.json
```

Complete existing cards or run ordered compound edits from UTF-8 JSON specs:

```bash
python scripts/planka_cli.py complete-card --file complete.json --dry-run
python scripts/planka_cli.py apply-plan --file plan.json --dry-run
```

Keep credentials in environment variables or stdin. Do not commit API keys, tokens, passwords, cookies, or long-lived credential files.
