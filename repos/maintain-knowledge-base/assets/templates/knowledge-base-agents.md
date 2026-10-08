# Knowledge-base instructions

## Authority

- Treat this repository as the durable source of truth.
- Read `README.md`, `catalog/vocabulary.md`, and the relevant `PROJECT.md` before changing knowledge.
- Use `catalog/entities.csv` for identity and current lifecycle state, `catalog/projects.csv` for project-specific fields, and `catalog/relations.csv` for cross-entity relationships.
- Do not infer inventory counts from folders or project mentions.

## Write workflow

1. Search names, aliases, IDs, model numbers, and serial numbers before adding anything.
2. Classify the input as fact, entity, relationship, project context, reusable knowledge, decision, source, or inbox material.
3. Update the single canonical owner of each field.
4. Record sources, verification dates, and meaningful uncertainty.
5. Add qualified relationships and update navigation.
6. Run the knowledge-base audit after structural changes.

## Safety

- Never fabricate missing facts or silently resolve conflicts.
- Archive rather than delete; never reuse IDs.
- Preserve project evidence when promoting reusable knowledge.
- Do not store passwords, tokens, private keys, or unnecessary sensitive personal data.
- Ask before bulk moves, destructive cleanup, or schema changes that affect many records.
