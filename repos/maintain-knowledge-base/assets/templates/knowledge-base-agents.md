# Knowledge-base instructions

## Authority

- This repository is the durable source of truth for its own records.
- Identity and lifecycle state: `catalog/entities.csv`; project-specific fields: `catalog/projects.csv`; cross-entity relationships: `catalog/relations.csv`.
- Reading, searching, writing, aliases, path resolution, and audit timing belong to the `maintain-knowledge-base` skill; this file records only conventions specific to this knowledge base.
- Default instruction document for agents reading this library: the workspace root `AGENTS.md`.
- Do not infer inventory counts from folders or project mentions.

## Local conventions

- （记录本库特有的布局、命名或访问约定；没有就删除本节。）
- Navigation follows `research-readme-index`; do not duplicate record status, dates, or counts in README files.

## Safety

- Never fabricate missing facts or silently resolve conflicts.
- Archive rather than delete; never reuse IDs.
- Preserve project evidence when promoting reusable knowledge.
- Do not store passwords, tokens, private keys, or unnecessary sensitive personal data; record only where credentials are securely stored.
- Ask before bulk moves, destructive cleanup, or schema changes that affect many records.
