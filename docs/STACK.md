# Stack

Not a dependency list. A statement of which tools the project uses at each layer, what constraints they impose, and why they were chosen. Agents read this to avoid suggesting the wrong library or pattern.

Group by layer. Each entry: tool name, the constraint it puts on the codebase, and a one-line why.

## Language and runtime

Markdown (primary) + Bash (hooks) + JSON (manifests/config); uses `jq` at consumer-side runtime, degrading gracefully when absent.
- **Constraint:** Bash hooks use `set -euo pipefail`; `jq` is a soft dependency - hooks fail open when it is missing (the git-write guard warns to stderr and allows; user-context-injector exits silently; auto-format aborts on its jq call and, being async-registered, surfaces nothing), and the git-write guard stays fail-closed only when jq is present but the hook payload is unparseable; hooks must remain POSIX-friendly for cross-platform Claude Code installs; Markdown agent/command files follow the project's slot-based template conventions.
- **Why:** Plugin distribution model - Claude Code reads Markdown for agents/commands, shells out to hooks for event handling, and parses JSON for wiring.

## Plugin runtime

Claude Code plugin runtime (hooks events + Agent tool + slash command dispatch).
- **Constraint:** Hook event names must match Claude Code's spec (SessionStart, PreToolUse, PostToolUse, Stop, Notification, PermissionRequest, UserPromptSubmit); agents live in `agents/` and are invoked via Task tool; commands live in `commands/` and are dispatched as slash commands; no application framework, no web server.
- **Why:** This is a plugin, not an app - Claude Code is the host.

## State and storage

File-system only - no database.
- **Constraint:** Per-project flags stored in consumer's `.claude/settings.local.json` (e.g., `alpRiver.skipSetup`); per-project memory lives in `~/.claude/projects/<encoded-cwd>/memory/MEMORY.md`; canonical project context lives in the consumer's `docs/{INTENT,STACK,GLOSSARY}.md`; never write to consumer source files outside the pipeline.
- **Why:** Plugin runs alongside arbitrary consumer projects - durable state belongs in Claude Code's standard locations, project context belongs in the consumer's repo.

## Testing

Internal pytest suite under `hooks/tests/` (730 tests), run via `uv run --no-project --with pyyaml --with pytest pytest hooks/tests/`; the Stop hook (`verify-tests.py`) additionally runs the consumer project's tests after pipeline runs.
- **Constraint:** `verify-tests.py` must remain stdlib-Python-portable (standard library only, no third-party deps, runs on a plain `python3`) and tolerate consumer repos with no test command; README-fact tests anchor by content (named table rows, verbatim phrases), not absolute line numbers - keep new ones content-anchored. Every version bump touches README.md by design: a gate test pins the Latest-updates topmost entry to plugin.json's version, so the window rolls each release.
- **Why:** The plugin's behavior is mostly Markdown content and hook glue - the internal suite guards the hook glue, and the test-of-record is still the pipeline running end-to-end against a real project.

## Plugin content conventions

Agents and commands follow tagged-slot input/output, speaking names (no cryptic codes), and the no-em-dashes rule; templates live under `templates/` and are reproduced inline in the agents that write them - both copies must stay in sync.
- **Constraint:** Tagged-slot I/O for every agent invocation; speaking-name slot identifiers; `-` not `—` everywhere; inline template copies in agents must match the source under `templates/` (per `agents/init.md` template-sync note).
- **Why:** The plugin's quality comes from the conventions in its content - codifying them here keeps drift in check.

## Tooling

No formatter, linter, or build step; a deterministic self-audit (`/alp-river:audit` over `hooks/audit.py`, a repo-fact scoring surface) is the standing quality gate; manual versioning across `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`.
- **Constraint:** Patch bump only when files under `agents/`, `commands/`, `hooks/`, or `WORKFLOW.md` change; doc-only changes don't bump; minor/major are manual; CHANGELOG entry required on every bump; both `plugin.json` and `marketplace.json` versions must move together, and the release-version gate test (`hooks/tests/test_release_version.py`, `EXPECTED_VERSION`) must be carried forward in the same bump or the suite fails. The git-write guard (`hooks/block-git-writes.sh`) blocks history/state-destroying git ops (incl. force-push variants, reset, rebase, merge, revert, restore, rm, mv, stash except list/show, apply, am, clean, pull, cherry-pick, filter-branch, ref surgery, tag create/delete, branch -D/-d/-m/-M, destructive checkout forms; non-exhaustive - the script's patterns are authoritative) while allowing forward ops (add/commit/push) for the ship tail; it matches at command position (first token per pipeline segment, with env-assignment and shell-reserved-word stripping) rather than substring-anywhere, is hardened against global-option evasion, and fails open with a warning when jq is missing (jq posture: see Language and runtime; canonical doctrine: WORKFLOW.md ## Shipping).
- **Why:** Plugin ships as Markdown + shell + JSON - no compilation, no bundling, no dependency resolution; the self-audit and deliberate versioning are the quality gates that matter.

## Hosting / deploy

Claude Code plugin marketplace (`/plugin marketplace add alp82/alp-river` + `/plugin install alp-river@alperortac`); GitHub mirror at github.com/alp82/alp-river.
- **Constraint:** Distribution is `git pull`-based via Claude Code's marketplace machinery - no CI/CD, no release artifacts; consumers get the current `main` branch contents when they install or update; cross-platform expectation - hooks must work on macOS, Linux, and WSL.
- **Why:** Claude Code's marketplace is the only distribution channel; no compiled artifact means no build pipeline to maintain.

## Drift observed

Items here surfaced during pipeline runs and have not been reconciled with the layers above. Triage and either update the layer or remove the bullet.

Nothing currently unreconciled.
