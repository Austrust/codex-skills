# Planka Kanban

Codex skill for inspecting and editing PLANKA kanban boards through the REST API.

## What It Includes

- `SKILL.md`: Codex skill instructions and safety rules.
- `scripts/planka_cli.py`: Dependency-free PLANKA API helper.
- `references/api.md`: Practical PLANKA REST API notes.
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
