# forge adapter — Claude Code

The reference adapter (adapter #1, first-built — no structural privilege). Everything
harness-specific about running forge under Claude Code lives here: the six hooks, the
setup skill, and the capability declaration. The contract this adapter implements is
[`docs/spec/adapter-contract.md`](../../docs/spec/adapter-contract.md).

## Enforcement tier: gated (derived)

This tier is a **derivative snapshot**, not an independent claim — the source is
[`capabilities.json`](capabilities.json), and adapter verification
([#44](https://github.com/alp82/forge/issues/44)) recomputes the tier from the manifest
and compares it against this line. Derivation per contract § 5:

```
enforcement["stop-gate"].level == "full"  ⇒  gated
```

`capabilities.json` declares `stop-gate` `full` (Stop hook, blocking exit re-engages the
agent), so the first rule fires and the tier is **gated**.

## Capabilities and mechanisms

Declared in [`capabilities.json`](capabilities.json); mechanisms per capability:

| Capability | Level | Mechanism |
|---|---|---|
| `session-start-injection` | full | `SessionStart` hook (startup/resume/clear/compact) |
| `tool-guard` | full | `PreToolUse(Bash)` hook, exit 2 blocks |
| `change-tracking` | full | `PostToolUse(Edit\|Write)` hook arms session markers |
| `stop-gate` | full | `Stop` hook, blocking exit re-engages the agent |

Spawn floor: isolated, model-selectable spawns via the Task tool; `parallel-fan-out`
declared `true`. Role tiers resolve to `haiku` / `sonnet` / `opus` / `fable`.

## Install and update

Via the native plugin channel, inside a Claude Code session:

```
/plugin marketplace add alp82/forge
/plugin install forge@alperortac
/forge:setup-forge
```

Setup runs once, plugin-prefixed; it installs the bare command names (`/forge`,
`/crossfire`, `/setup-forge`). Plugin updates propagate through the marketplace on their
own — no re-run needed unless the session-start nag says so.

## Verification behavior

What setup ([`skills/setup/SKILL.md`](skills/setup/SKILL.md)) probes, and what loud
failure looks like:

- **Symlink-first install** into the stable marketplace-clone root — never the versioned
  plugin cache. Where a symlink fails, a copy is made and stamped with the plugin
  version in `.forge-version`; an unresolvable stable root falls back the same way.
- **Ownership guard**: an existing `~/.claude/skills/<name>` that is not forge's own is
  never overwritten silently — setup asks first.
- **Stale-install detection**: the `SessionStart` hook
  ([`hooks/session-start.sh`](hooks/session-start.sh)) nags loudly — "re-run
  /setup-forge" — on a dangling symlink, a cache-pointing symlink (dangles on next
  update), or a copy whose version stamp differs from the plugin's.

## Known limitations

- The capability declaration is the contract § 6 worked example — a hypothesis until
  install-time verification ([#44](https://github.com/alp82/forge/issues/44)) confirms
  each declared capability live at build time.
- The skills.sh channel carries root `skills/` only — no hooks ship, so that channel
  installs prose-only by construction (contract § 11); the native plugin channel above
  is canonical.

## Survey source

Declaration surveyed 2026-07-18 against the Claude Code plugin surface: hooks reference
(`SessionStart` / `PreToolUse` / `PostToolUse` / `Stop`) and the plugin manifest schema
(custom `skills` and `hooks` path fields), per
[code.claude.com/docs/en/plugins-reference](https://code.claude.com/docs/en/plugins-reference).
