# forge adapter — codex

Everything harness-specific about running forge under
[OpenAI Codex CLI](https://developers.openai.com/codex): the enforcement hooks, the
installer that writes them into codex's own hooks file, the setup skill, and the
capability declaration. The contract this adapter implements is
[`docs/spec/adapter-contract.md`](../../docs/spec/adapter-contract.md). This is the
first non-Claude adapter at the gated tier.

## Enforcement tier: gated (derived)

This tier is a **derivative snapshot**, not an independent claim — the source is
[`capabilities.json`](capabilities.json), and verification (the install-time probes in
[`skills/setup/SKILL.md`](skills/setup/SKILL.md)) recomputes the tier from the manifest
and compares it against this line. Derivation per contract § 5:

```
enforcement["stop-gate"].level == "full"  ⇒  gated
```

`capabilities.json` declares `stop-gate` `full` (codex's `Stop` hook returns
`decision: "block"`, forcing an additional processing pass), so the first rule fires and
the tier is **gated**. The load-bearing caveat: the enforcement hooks live in codex's
own `$CODEX_HOME/hooks.json` and must be **trusted** before they run — install writes
them and drives the trust step, degrading loudly to prose-only if hooks are unavailable
or locked out.

## How the hooks are installed — and why not via the plugin

Codex does **not** load hooks carried by a plugin. `plugin_hooks` is a *removed* feature
(`codex features list` reports `plugin_hooks  removed`), so a `hooks` pointer in
`.codex-plugin/plugin.json` is inert — which is why this adapter's plugin manifest has
no `hooks` field. Codex loads hooks only from **`$CODEX_HOME/hooks.json`** (default
`~/.codex/hooks.json`) under a per-hook trust mechanism.

So the marketplace install lands only the **skills**. The enforcement layer is written
into codex's own hooks file by [`hooks/install-forge-hooks.py`](hooks/install-forge-hooks.py),
which the setup skill runs: it reads the shipped nested-schema template
[`hooks/hooks.json`](hooks/hooks.json), resolves every command to an absolute path (codex
substitutes no plugin-root variable), and **merges** forge's four events into
`$CODEX_HOME/hooks.json` — owning only its own entries (ownership keyed by hook-script
basename), never touching a user's or Orca's hooks. Idempotent: re-running replaces
forge's entries and leaves everything else byte-for-byte.

The `hooks.json` schema codex requires (verified live on 0.143.0) is nested and
Claude-shaped:

```
{ "hooks": { "<Event>": [ { "matcher"?: "<regex>",
  "hooks": [ { "type": "command", "command": "<abs>", "timeout": N, "statusMessage"? } ] } ] } }
```

Event keys are CamelCase (`SessionStart` / `PreToolUse` / `PostToolUse` / `Stop`).

## Capabilities and mechanisms

Declared in [`capabilities.json`](capabilities.json); mechanisms per capability:

| Capability | Level | Mechanism |
|---|---|---|
| `session-start-injection` | full | `SessionStart` hook injects the forge banner |
| `tool-guard` | full | `PreToolUse(shell)` hook, exit 2 + stderr denies |
| `change-tracking` | full | `PostToolUse(edit tools)` hook arms session markers |
| `stop-gate` | full | `Stop` hook, `decision:"block"` re-engages the agent |

Spawn floor: isolated, model-selectable spawns via codex's native subagents (TOML agent
files with per-agent `model` and `model_reasoning_effort` override). `parallel-fan-out`
is declared **false** — codex's `enable_fanout` is under-development and off, so only
sequential `multi_agent` is available; independence (not wall-clock parallelism) carries
the guarantees, so sequential-only is a conforming proof. Role tiers resolve to
`gpt-5.4-mini` / `gpt-5.4` / `gpt-5.5` / `gpt-5.5` (mini / standard / large / ultra) —
see the ultra note under known limitations.

## Install and update

Add the marketplace and install the plugin (this lands the **skills**):

```
codex plugin marketplace add alp82/forge
codex plugin add forge@alperortac
```

(`codex plugin add <plugin>@<marketplace>` is the install verb; codex reuses
`.claude-plugin/marketplace.json` for discovery — the marketplace name is `alperortac`.)
Then run the `$setup-forge` skill. Setup writes forge's hooks into `$CODEX_HOME/hooks.json`
via the installer, drives the trust step, generates the four tier agents
(`~/.codex/agents/forge-<tier>.toml`), and live-verifies every declared capability —
first install ends with "restart codex, trust forge's hooks, and re-run `$setup-forge`"
because hooks load at startup and must be trusted.

**Update = re-run `$setup-forge`.** Setup is idempotent — re-running refreshes what it
owns (skills via the marketplace, hooks via the installer's merge), never duplicates, and
§ 8 re-verification happens by construction. Staleness is self-detected: setup stamps the
forge version into each tier-agent file; the SessionStart hook compares those stamps
against the plugin version and nags on drift.

## Verification behavior

What setup ([`skills/setup/SKILL.md`](skills/setup/SKILL.md)) probes, and what loud
failure looks like:

- **hooks availability + admin lockout** — codex's `hooks` feature is stable and on by
  default; an `allow_managed_hooks_only` admin policy (or a build that disables hooks)
  produces a loud `effective tier: prose-only` report, never a silent skills-only install.
- **Session-start injection** — the forge banner in the installing session's own
  context is the proof; absent after a restart-and-trust is `session-start-injection: FAILED`.
- **Tool guard** — a throwaway `git init` repo and a `git reset --hard` inside it; the
  command executing (harmlessly, there) instead of codex reporting `Command blocked by
  PreToolUse hook` is a loud failure.
- **Spawn floor + fan-out** — an isolation probe (a spawned agent must not know
  conversation facts outside its prompt); fan-out is declared false, so the sequential
  result is reported, not treated as a downgrade.
- **Model resolvability** — each tier agent is spawned once with a one-token prompt; a
  spawn error names the unresolvable model id, cross-checked against `codex debug models`,
  and the user picks a substitute which is written into the agent file and reported.
- **Change tracking + stop-gate** — an edit-tool touch of a scratch file in the
  session's cwd, then the marker files are checked and the end-of-turn review block is
  announced in advance: the block appearing IS the stop-gate pass signal; an unblocked
  turn end is `stop-gate: FAILED`.

## Verified live (Codex CLI 0.143.0)

Confirmed by direct probing during the #61 fix, headless `codex exec` against a sandboxed
`CODEX_HOME`:

- **`$CODEX_HOME/hooks.json` nested schema loads** — the wrong (flat, or event-map-at-top)
  shape is rejected loudly at startup (`failed to parse hooks config … unknown field`),
  so a schema regression cannot pass silently.
- **`SessionStart` fires** — the banner hook runs and receives a JSON stdin payload
  (`session_id`, `cwd`, `hook_event_name`, `model`, …).
- **`PreToolUse` tool-guard denies** — a `git reset --hard` is blocked (`hook: PreToolUse
  Blocked`, command does not run) via **exit 2 + stderr**. The payload is Claude-shaped:
  `tool_name` (the shell tool reports as `Bash`) and `tool_input.command`.
- **`PostToolUse` change-tracking arms markers** — an edit-tool file write arms all three
  `/tmp/.codex-changed-*-<session_id>` markers.
- **`Stop` gate blocks** — with code changed and no review, review-owed's
  `decision:"block"` is honored (`hook: Stop Blocked`); the agent re-engages, runs the
  review, and the next `Stop` passes — the max-1-retry cap breaks the loop cleanly. This
  is the defining gated-tier capability, end-to-end.
- **Model catalog** — `gpt-5.5` / `gpt-5.4` / `gpt-5.4-mini` all exist and support
  `low`/`medium`/`high`/`xhigh` reasoning efforts (`codex debug models`).
- **`enable_fanout` is under-development/off** and `plugin_hooks` is removed
  (`codex features list`); `hooks` is stable/on.
- **Trust** — automation runs hooks with `--dangerously-bypass-hook-trust`; interactive
  sessions prompt to trust newly written hooks.

## Known limitations and divergences

- **Hooks must be trusted, and are locked out under admin policy.** A newly written
  `$CODEX_HOME/hooks.json` entry does not run until trusted (interactive prompt, or
  `--dangerously-bypass-hook-trust` for automation); admin `allow_managed_hooks_only` can
  lock user hooks out entirely. Both produce a loud prose-only degradation at install.
- **Ultra is `gpt-5.5` at `xhigh`, a manifest limitation.** There is no model above
  `gpt-5.5`; codex's "Ultra" is a reasoning mode, not a model id. The contract § 6
  manifest holds model-id strings only, so `models.ultra == models.large == "gpt-5.5"`
  (equality is allowed by the capability ordinal) and the ultra/large distinction lives
  in the generated agent files' `model_reasoning_effort` (`xhigh` vs `high`).
- **Edit-tool names matched broadly.** The `PostToolUse` marker hook matches
  `apply_patch|edit|write|str_replace|create_file|Edit|Write` with tolerant payload reads
  (string or argv-array commands; `file_path`/`path`/patch-body paths) and fail-toward-arm
  on a matched edit tool with no derivable path. Probe (f) arbitrates the live edit-tool
  name. (The shell tool is confirmed `Bash`; the guard's matcher covers it.)
- **`stop_hook_active` has no documented codex equivalent.** The gates read it tolerantly
  (absent → proceed); the max-1-retry marker cap makes an infinite Stop loop structurally
  impossible either way.
- **Subagent markers can miss the rendezvous.** A codex subagent's PostToolUse firing
  under its own `session_id` arms the wrong marker — the same accepted caveat as Claude
  Code; review-owed's disk-mtime settling is session-agnostic and mitigates the review
  gate's share.
- **`agents.max_depth` defaults to 1** — subagents do not spawn subagents. Forge's flat
  orchestrator-plus-workers shape fits the default; nothing here raises it.

## Survey source

Originally surveyed 2026-07-17 against Codex CLI 0.144.5
([`docs/research/codex-cli-survey.md`](https://github.com/alp82/forge/blob/research/codex-cli-survey/docs/research/codex-cli-survey.md),
branch `research/codex-cli-survey`); the capability declaration was re-grounded by live
probing against Codex CLI 0.143.0 during the #61 fix (see "Verified live" above), which
corrected the hooks-install mechanism, the `hooks.json` schema, the model ids, and the
fan-out declaration.
