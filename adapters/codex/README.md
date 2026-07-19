# forge adapter — codex

Everything harness-specific about running forge under
[OpenAI Codex CLI](https://developers.openai.com/codex): the six enforcement hooks, the
setup skill, and the capability declaration. The contract this adapter implements is
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
the tier is **gated**. The load-bearing caveat: codex hooks are opt-in
(`features.hooks`) and carry no published stable-maturity label — install verifies the
flag and degrades loudly to prose-only when hooks are off or locked out.

## Capabilities and mechanisms

Declared in [`capabilities.json`](capabilities.json); mechanisms per capability:

| Capability | Level | Mechanism |
|---|---|---|
| `session-start-injection` | full | `SessionStart` hook injects the forge banner |
| `tool-guard` | full | `PreToolUse(shell)` hook, exit 2 denies |
| `change-tracking` | full | `PostToolUse(edit tools)` hook arms session markers |
| `stop-gate` | full | `Stop` hook, `decision:"block"` re-engages the agent |

Spawn floor: isolated, model-selectable spawns via codex's native subagents (TOML agent
files with per-agent `model` and `model_reasoning_effort` override); `parallel-fan-out`
declared `true` (`agents.max_threads` defaults to 6). Role tiers resolve to
`gpt-5.6-luna` / `gpt-5.6-terra` / `gpt-5.6-sol` / `gpt-5.6-sol` — see the ultra note
under known limitations.

## Install and update

Via codex's native plugin marketplace (self-serve git channel, no OpenAI review):

```
codex plugin marketplace add alp82/forge
```

then install/enable the `forge` plugin (`codex plugin --help` names the exact verb on
your version) and run the `$setup-forge` skill. Setup enables `features.hooks` (with
consent), generates the four tier agents (`~/.codex/agents/forge-<tier>.toml`), and
live-verifies every declared capability — first install ends with "restart codex and
re-run `$setup-forge`" when hooks only load at startup.

**Update = re-add the marketplace source and re-run `$setup-forge`.** Setup is
idempotent — re-running refreshes what it owns, never duplicates, and § 8
re-verification happens by construction. Staleness is self-detected: setup stamps the
forge version into each tier-agent file; the SessionStart hook compares those stamps
against the plugin version and nags on drift.

## Verification behavior

What setup ([`skills/setup/SKILL.md`](skills/setup/SKILL.md)) probes, and what loud
failure looks like:

- **features.hooks + admin lockout** — a disabled flag or `allow_managed_hooks_only`
  admin policy produces a loud `effective tier: prose-only` report, never a silent
  skills-only install.
- **Session-start injection** — the forge banner in the installing session's own
  context is the proof; absent after a restart is `session-start-injection: FAILED`.
- **Tool guard** — a throwaway `git init` repo and a `git reset --hard` inside it; the
  command executing (harmlessly, there) instead of being denied is a loud failure.
- **Spawn floor + fan-out** — an isolation probe (a spawned agent must not know
  conversation facts outside its prompt), and a two-agent parallel probe; serial
  execution downgrades the effective declaration to `parallel-fan-out: false`, reported.
- **Model resolvability** — each tier agent is spawned once with a one-token prompt; a
  spawn error names the unresolvable model id, and the user picks a substitute which is
  written into the agent file and reported (loud effective downgrade, never silent).
- **Change tracking + stop-gate** — an edit-tool touch of a scratch file in the
  session's cwd, then the marker files are checked and the end-of-turn review block is
  announced in advance: the block appearing IS the stop-gate pass signal; an unblocked
  turn end is `stop-gate: FAILED`.

## Known limitations and divergences

The codex hook protocol is documented at survey level but under-specified in places;
every assumption below is deliberately conservative and arbitrated by the live install
probes, never silently resolved:

- **Hooks are opt-in and unlabeled-maturity.** `features.hooks` must be enabled, and no
  published maturity label marks the hook system stable; admin
  `allow_managed_hooks_only` can lock user hooks out entirely. Both produce a loud
  prose-only degradation at install.
- **Ultra is sol at `xhigh`, a manifest limitation.** There is no model above
  `gpt-5.6-sol`; codex's "Ultra" is a reasoning mode, not a model id. The contract § 6
  manifest holds model-id strings only, so `models.ultra == models.large ==
  "gpt-5.6-sol"` (equality is allowed by the capability ordinal) and the ultra/large
  distinction lives in the generated agent files' `model_reasoning_effort` (`xhigh` vs
  `high`). The manifest stays the source for the id; the agent files carry the effort.
- **SessionStart output schema is assumed Claude-shaped** (`hookSpecificOutput.
  additionalContext`, plain-stdout fallback); the survey never specifies it. Probe (a)
  arbitrates.
- **Tool names are assumed, matched broadly.** Neither the shell tool nor the edit
  tools are named in the survey; the guard matches
  `shell|local_shell|bash|Bash|exec_command`, the marker hook matches
  `apply_patch|edit|write|str_replace|create_file|Edit|Write` with tolerant payload
  reads (string or argv-array commands; `file_path`/`path`/patch-body paths) and
  fail-toward-arm on a matched edit tool with no derivable path. Probes (c) and (f)
  arbitrate.
- **`stop_hook_active` has no documented codex equivalent.** The gates read it
  tolerantly (absent → proceed); the max-1-retry marker cap makes an infinite Stop loop
  structurally impossible either way.
- **hooks.json top-level schema and hook command-path resolution are assumed** (flat
  entries under event keys; plugin-root-relative command paths — no documented
  plugin-root variable exists). The scripts self-locate internally, so only invocation
  resolution is at risk; probes (a)/(b) catch a wrong assumption immediately.
- **plugin.json pointer fields are assumed Claude-shaped** (`skills` / `hooks` keys in
  `.codex-plugin/plugin.json`); the first live `codex plugin marketplace add` verifies,
  and the setup restart gate catches a consumer-side miss.
- **The plugin install/enable verb beyond `marketplace add` is undocumented** — setup
  consults `codex plugin --help` live. Whether hooks hot-load after install or need a
  codex restart is also undocumented — the restart gate handles both.
- **Subagent markers can miss the rendezvous.** A codex subagent's PostToolUse firing
  under its own `session_id` arms the wrong marker — the same accepted caveat as Claude
  Code; review-owed's disk-mtime settling is session-agnostic and mitigates the review
  gate's share.
- **`agents.max_depth` defaults to 1** — subagents do not spawn subagents. Forge's flat
  orchestrator-plus-workers shape fits the default; nothing here raises it.

## Survey source

Declaration surveyed 2026-07-17 against Codex CLI 0.144.5:
[`docs/research/codex-cli-survey.md`](https://github.com/alp82/forge/blob/research/codex-cli-survey/docs/research/codex-cli-survey.md)
(branch `research/codex-cli-survey`), primary-sourced from the official Codex docs
(developers.openai.com/codex → learn.chatgpt.com), the
[openai/codex](https://github.com/openai/codex) repo, and agentskills.io.
