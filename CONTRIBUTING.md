# Contributing to forge

How the plugin works inside, how the repo is laid out, and how to run it locally. For the tour aimed at adopters, start with the [README](README.md).

## 💻 Local development

Clone the repo and pass `--plugin-dir`:

```bash
git clone https://github.com/alp82/forge.git
claude --plugin-dir ./forge
```

## 🗂️ Structure

```
forge/
├── .claude-plugin/         <- plugin.json (version), marketplace.json
├── skills/
│   ├── forge/              <- SKILL.md (pipeline router) + stage briefs, primitive briefs, WORKER.md
│   ├── crossfire/          <- SKILL.md (review wave) + 8 lens briefs
│   └── setup/              <- SKILL.md (/setup-forge: skill install + tracker doc)
├── hooks/                  <- 6 deterministic hooks + hooks.json + tests/
└── .claude/skills/         <- repo-internal skills (/audit, /reflect), not shipped
```

## 🔧 Under the hood

**Skills all the way down.** There are no agent definitions and no deterministic router. `skills/forge/SKILL.md` is a prose flow: triage with detection detours (interview, prototype, research, diagnose), then plan → challenge → implement test-first → review wave → fix. Every stage runs as a generic spawned subagent with one contract — *"Read `<brief path>` and follow it"* — so each stage's judgment lives in its sibling brief file, plain markdown a contributor can edit directly.

**File-carried artifacts.** Every stage output a later stage consumes is a markdown file in the gitignored run dir `.forge/<slug>/` (`plan.md`, `challenge.md`, `findings-<lens>.md`, …). Spawn prompts pass paths, never pasted content, so runs survive compaction and a fresh respawn needs only paths.

**Independence where it pays.** The challenger and a different-model worker probe the plan in parallel, neither seeing the other's verdict; the review wave fires every applicable lens the same way. Worker failure is visible and non-blocking.

**Deterministic floor.** The hooks are the only code: test/build verification on edits, a git-write guard, a code-change stamp, and a Stop gate that blocks a session which changed code but never ran tests or review. The flow persuades; the hooks enforce.

**Word budgets as law.** Each SKILL.md and brief fits one read — ~865-word target, 2,000-word hard ceiling. The repo-internal `/audit` skill checks the budgets, cross-file duplication, version mirrors, and the hook test suite.

## 🏷️ Versioning and changelog

The plugin version lives in `.claude-plugin/plugin.json` and is mirrored in `.claude-plugin/marketplace.json` and the README version badge - bump all three together.

### Changelog style

CHANGELOG.md entries are a user-facing summary, not implementation notes.

- **Shape by release type:** patch (X.Y.Z, Z > 0) - bullets only, no intro; minor (X.Y.0) - one intro paragraph framing the release theme, then bullets; major or initial release (X.0.0, or 0.1.0) - several intro paragraphs giving the wider arc, then bullets.
- **Per-bullet rules:** one line per bullet - no multi-sentence run-ons; outcome only - what changes for the person using this, not how it works inside; no internal terms (step numbers, agent names, axis names, flag names - if a stranger wouldn't recognize the word, drop it); no clever framing (no rhetorical asides, no "but"/"also"/"instead" - state the change and stop); bullets cap at four per release.
