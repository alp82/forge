---
name: setup-forge
description: Install forge's bare skill names into ~/.claude/skills - symlink, version-stamped copy where symlinks fail - and write this repo's tracker conventions if absent. Run once after plugin install; re-run when the stale-skills nag says so.
disable-model-invocation: true
---

# setup-forge — install and per-repo config

You run forge's two setup jobs: **once per machine**, put the bare skill names (`/forge`, `/crossfire`, `/setup-forge`) into `~/.claude/skills`; **once per repo**, write the tracker conventions the ticket contract reads. Both are idempotent — re-running refreshes, never duplicates. Per-repo facts only, never doctrine.

Bootstrap wrinkle, accepted and documented: the first invocation is necessarily plugin-prefixed (`/forge:setup-forge`) — the bare names exist only after this skill runs once.

## Locate the plugin — and the stable root

The plugin root is `${CLAUDE_PLUGIN_ROOT}` when set; otherwise four directories up from this file. Read the plugin version from `.claude-plugin/plugin.json` — the copy stamp below needs it.

The plugin root is **not** the symlink target. An installed plugin's root sits in the version-stamped cache (`~/.claude/plugins/cache/<marketplace>/forge/<version>/`), which moves on every update — a symlink into it dangles the moment a new version lands. The symlink target is the **stable root**: the marketplace clone, updated in place at a path that never moves. Resolve it from `installLocation` in `~/.claude/plugins/known_marketplaces.json` for the marketplace named in the plugin root's cache path; forge's plugin source is `./`, so the clone root holds `skills/` directly. A plugin root that is not under `plugins/cache/` (a dev tree) is its own stable root. No stable root resolvable → skip straight to the copy fallback.

## Install the bare skill names

For each `skills/*/` and `adapters/claude-code/skills/*/` directory under the plugin root that holds a `SKILL.md`, the bare name is its frontmatter `name:` (directory basename as fallback) and the target is `~/.claude/skills/<name>` (create `~/.claude/skills` if missing).

1. **Symlink first.** `ln -sfn <stable root skill dir> <target>` — the skill's own directory under the stable root, at the same plugin-root-relative path — never into the versioned cache. A symlink into the stable root survives updates — plugin updates propagate with zero re-run.
2. **Ownership guard.** A target that already exists and is not forge's own — neither a symlink into an installed plugin's skill tree nor a copy carrying a `.forge-version` stamp — belongs to the user. Ask before replacing it; never overwrite silently.
3. **Copy fallback.** Where no stable root resolves or symlink creation fails (filesystem or platform refuses), copy the skill directory instead and write the plugin version into `<target>/.forge-version`. The stamp convention is canonical in `adapters/claude-code/hooks/session-start.sh`: the SessionStart hook compares stamp to plugin version and prints the one-line "re-run /setup-forge" nag when they differ. On re-run, retry the symlink before refreshing a copy — the machine may allow it now.

## Tracker conventions — per repo, only if absent

`docs/agents/issue-tracker.md` is the one file every toolkit reads for tracker operations. **If it exists, leave it untouched** — it is the repo's own record; report "tracker doc present" and move on.

If absent, ask the user one question — which tracker this repo uses:

- **GitHub issues** (the reference case) → write the doc with `gh` commands.
- **Local markdown** → a file-per-issue convention under `docs/issues/`.
- **Something else** → interview for the four operations below and write what the user gives.
- **No tracker** → write nothing; the ticket contract lies dormant and forge runs standalone.

The doc states, one concrete command each: how to **read** a ticket (body + comments), **comment** on it, **close** it, and **list** open ones. That is the whole surface forge consumes — `/forge <ticket>` reads the ticket as the request and posts the resolution back before closing. Other toolkits (a mapping skill such as wayfinder) read the same doc and may append their own sections; write only forge's.

## Optional override — offer, never write unasked

`docs/agents/worker.md` controls worker dispatch: `worker: none` stands detection down; a custom command template replaces the known-workers table for a CLI it doesn't know (the table lives in `skills/forge/WORKER.md`). Mention that it exists; write it only when the user asks.

## Getting started

Relay this once setup succeeds — it is the whole onboarding:

- **`/forge <request>`** — every code-modifying request enters here; it triages, plans, challenges, implements test-first, and reviews. Pass a ticket reference and the ticket body is the request.
- **`/crossfire [files | range]`** — the standalone review wave over any diff.
- A request too big for one session gets a recommendation to chart a map first, with a mapping skill such as `/wayfinder`.

## Report

Terse lines, one per action: skill → `linked` / `copied (symlink failed: <reason>)` / `kept (user's own — skipped)`; tracker doc → `written (<tracker>)` / `present (untouched)` / `skipped (no tracker)`. Close with the getting-started block above.
