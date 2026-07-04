# Project Context Templates

These templates feed the alp-river plugin's `## PROJECT_CONTEXT` block. Subagents that work on your project pick up the matching docs automatically - no per-spawn prep, no copy-paste.

## How to use

1. Copy any of the four templates into your project's `docs/` folder, keeping the UPPERCASE filenames.
2. Fill in the `_TODO:_` markers with real content.
3. Delete sections that don't apply.
4. The hook injects whatever exists. Missing files skip silently.

Or run `/alp-river:setup` to do the first three steps interactively for INTENT/STACK/GLOSSARY.

**Maintainer note**: if you edit `INTENT.md`, `STACK.md`, or `GLOSSARY.md`, also update the inlined copies in `agents/setup-agent.md` to keep them in sync.

## Layout

```
your-project/
└── docs/
    ├── INTENT.md       <- product intent (purpose, users, success, out of scope)
    ├── STACK.md        <- chosen stack and constraints, by layer
    ├── GLOSSARY.md     <- canonical terms, avoid-aliases, ambiguities
    └── adr/            <- architecture decision records
        ├── 0000-template.md   <- copy this for each new decision
        ├── 0001-some-decision.md
        └── ...
```

## What gets injected

| File | Goes to | How it appears |
|------|---------|----------------|
| `INTENT.md` | agents that judge fit (clarifier, planner, acceptance, ux, ...) | full body under `### INTENT.md` |
| `STACK.md` | agents that touch tech choice (researcher, implementer, security, perf, ...) | full body under `### STACK.md` |
| `GLOSSARY.md` | every judgment-call agent | full body under `### GLOSSARY.md` |
| `adr/*.md` | agents that reason about prior decisions (planner, implementer, fixer, ...) | one bullet per ADR with status, title, summary, path |

ADRs collapse to a summary list, not full bodies, to keep prompts lean. The full text stays in your repo for humans to read.

## ADR conventions

- File name: `NNNN-kebab-title.md` (zero-padded four-digit number, kebab title).
- Frontmatter: YAML with `status` (`accepted` / `proposed` / `deprecated` / `superseded`) and `date` (ISO).
- Body: numbered title (`# NNNN. Title`) followed by 1-3 sentence summary, then optional sections.
- The plugin skips ADRs whose status is `deprecated` or `superseded`, files matching `0000-*.md`, and any ADR whose summary still contains a `_TODO:_` marker.

## Why these four

- **INTENT** anchors what success looks like - keeps planners and reviewers from drifting.
- **STACK** keeps language/framework/tooling choices consistent across spawns - no agent reaches for the wrong library.
- **GLOSSARY** kills ambiguous terms before they multiply - agents stop renaming the same concept three different ways.
- **ADR** records the why behind irreversible calls - new work doesn't relitigate settled questions.
