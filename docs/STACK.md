# Stack

Not a dependency list. A statement of which tools the project uses at each layer, what constraints they impose, and why they were chosen. Agents read this to avoid suggesting the wrong library or pattern.

Group by layer. Each entry: tool name, the constraint it puts on the codebase, and a one-line why.

## Language and runtime

Markdown (primary) + Bash (hooks) + JSON (manifests/config); requires `jq` at consumer-side runtime.
- **Constraint:** Bash hooks use `set -euo pipefail` and depend on `jq` being on PATH; hooks must remain POSIX-friendly for cross-platform Claude Code installs; Markdown agent/command files follow the project's slot-based template conventions.
- **Why:** Plugin distribution model - Claude Code reads Markdown for agents/commands, shells out to hooks for event handling, and parses JSON for wiring.

## Plugin runtime

Claude Code plugin runtime (hooks events + Agent tool + slash command dispatch).
- **Constraint:** Hook event names must match Claude Code's spec (SessionStart, PreToolUse, PostToolUse, Stop, Notification, PermissionRequest, UserPromptSubmit); agents live in `agents/` and are invoked via Task tool; commands live in `commands/` and are dispatched as slash commands; no application framework, no web server.
- **Why:** This is a plugin, not an app - Claude Code is the host.

## State and storage

File-system only - no database.
- **Constraint:** Per-project flags stored in consumer's `.claude/settings.local.json` (e.g., `alpRiver.skipSetup`, `alpRiver.psychologyOverrides`); per-project memory lives in `~/.claude/projects/<encoded-cwd>/memory/MEMORY.md`; canonical project context lives in the consumer's `docs/{INTENT,STACK,GLOSSARY}.md`; never write to consumer source files outside the pipeline.
- **Why:** Plugin runs alongside arbitrary consumer projects - durable state belongs in Claude Code's standard locations, project context belongs in the consumer's repo.

## Testing

No internal test suite; Stop hook (`verify-tests.py`) runs the consumer project's tests after pipeline runs.
- **Constraint:** Plugin changes are validated by exercising the pipeline in a real consumer repo - no unit tests inside this repo; `verify-tests.py` must remain stdlib-Python-portable (standard library only, no third-party deps, runs on a plain `python3`) and tolerate consumer repos with no test command.
- **Why:** The plugin's behavior is mostly Markdown content and hook glue - the test-of-record is the pipeline running end-to-end against a real project.

## Plugin content conventions

Agents and commands follow tagged-slot input/output, speaking names (no cryptic codes), and the no-em-dashes rule; templates live under `templates/` and are reproduced inline in the agents that write them - both copies must stay in sync.
- **Constraint:** Tagged-slot I/O for every agent invocation; speaking-name slot identifiers; `-` not `—` everywhere; inline template copies in agents must match the source under `templates/` (per `agents/init.md` template-sync note).
- **Why:** The plugin's quality comes from the conventions in its content - codifying them here keeps drift in check.

## Tooling

No formatter, linter, or build step; manual versioning across `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`.
- **Constraint:** Patch bump only when files under `agents/`, `commands/`, `hooks/`, or `WORKFLOW.md` change; doc-only changes don't bump; minor/major are manual; CHANGELOG entry required on every bump; both `plugin.json` and `marketplace.json` versions must move together.
- **Why:** Plugin ships as Markdown + shell + JSON - no compilation, no bundling, no dependency resolution; versioning is the only quality gate that matters and it needs to stay deliberate.

## Hosting / deploy

Claude Code plugin marketplace (`/plugin marketplace add alp82/alp-river` + `/plugin install alp-river@alperortac`); GitHub mirror at github.com/alp82/alp-river.
- **Constraint:** Distribution is `git pull`-based via Claude Code's marketplace machinery - no CI/CD, no release artifacts; consumers get the current `main` branch contents when they install or update; cross-platform expectation - hooks must work on macOS, Linux, and WSL.
- **Why:** Claude Code's marketplace is the only distribution channel; no compiled artifact means no build pipeline to maintain.

## Drift observed

Items here surfaced during pipeline runs and have not been reconciled with the layers above. Triage and either update the layer or remove the bullet.

- Tooling - the Tooling layer states "No formatter, linter, or build step", but the repo now ships a deterministic self-audit health-check tool: `/alp-river:audit` over `hooks/audit.py`, a repo-fact scoring surface that is neither formatter, linter, nor build, yet is a standing quality/health gate - evidence: hooks/audit.py - sources: capture pipeline
- Tooling / security guardrails - the git-write guard posture shifted from blanket "all git writes are user-only" to "block the dangerous, allow the forward": `hooks/block-git-writes.sh` now lets plain `git add`/`commit`/`push` through (so the ship-executor tail can commit/push and open a draft PR) while still blocking history/state-destroying ops (force-push incl. `--mirror`/`--prune`/`--force-with-lease=`/`+refspec`/`:delete`, reset, rebase, merge, revert, restore, rm, mv, stash, apply, am, clean, pull, tag create/delete, branch -D/-d/-m/-M, checkout -- <path>) and hardens against global options (`-C`, `-c`, `--exec-path`, etc.) being used to evade the verb match - forward git ops are intentionally allowed for the ship flow; see WORKFLOW.md ## Shipping for the canonical doctrine - evidence: hooks/block-git-writes.sh - sources: capture pipeline
- Testing - the Testing layer states "No internal test suite; ... no unit tests inside this repo", but the repo now carries a 13-file internal pytest suite under hooks/tests/ (test_route.py, test_fable_tier_and_subagent_writes.py, ...), invoked via `uv run --no-project --with pyyaml --with pytest pytest hooks/tests/`, with its own maintenance hazards: version-pin test names stale at `_1_2_18` while asserting 1.3.5, and Group A tests pinning absolute README line numbers (73, 77, 328) - evidence: hooks/tests/test_route.py:3385, hooks/tests/test_fable_tier_and_subagent_writes.py:913 - sources: code-implementer, quality-reviewer
