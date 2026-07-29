# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root, or
- **`CONTEXT-MAP.md`** at the repo root if it exists—read each mapped context relevant to the work.
- **`docs/adr/`**—read ADRs touching the area being changed.

If these files do not exist, proceed silently. The domain-modeling workflow creates them lazily when terminology or architectural decisions are resolved.

## File structure

This is a single-context repository:

```
/
├── CONTEXT.md
├── docs/adr/
└── skills/
```

## Use the glossary's vocabulary

Use terms as defined in `CONTEXT.md`. Do not drift to synonyms the glossary explicitly avoids.

If a needed concept is missing, reconsider whether the term belongs or note the gap for domain modeling.

## Flag ADR conflicts

Surface any contradiction with an existing ADR explicitly rather than silently overriding it.
