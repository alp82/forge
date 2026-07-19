# forge adapter — gemini

Everything harness-specific about running forge under
[Google Gemini CLI](https://github.com/google-gemini/gemini-cli): the six enforcement
hooks, the setup skill, and the capability declaration. The contract this adapter
implements is [`docs/spec/adapter-contract.md`](../../docs/spec/adapter-contract.md). This
is the second non-Claude adapter at the gated tier — and gemini is the strongest non-Claude
target surveyed.

## Enforcement tier: gated (derived)

This tier is a **derivative snapshot**, not an independent claim — the source is
[`capabilities.json`](capabilities.json), and verification (the install-time probes in
[`skills/setup/SKILL.md`](skills/setup/SKILL.md)) recomputes the tier from the manifest
and compares it against this line. Derivation per contract § 5:

```
enforcement["stop-gate"].level == "full"  ⇒  gated
```

`capabilities.json` declares `stop-gate` `full` (gemini's `AfterAgent` hook returns
`decision: "block"`, which "triggers an automatic retry turn" — the agent must address the
reason before its answer stands), so the first rule fires and the tier is **gated**.
Unlike codex, gemini's hooks need no opt-in feature flag; the load-bearing precondition is
instead the **spawn floor** (`experimental.enableAgents`, on by default), which install
verifies.

## Capabilities and mechanisms

Declared in [`capabilities.json`](capabilities.json); mechanisms per capability:

| Capability | Level | Mechanism |
|---|---|---|
| `session-start-injection` | full | `BeforeAgent` hook `additionalContext` injects the forge banner (fires every turn including the first) |
| `tool-guard` | full | `BeforeTool(shell)` hook, exit 2 denies |
| `change-tracking` | full | `AfterTool(edit tools)` hook arms session markers |
| `stop-gate` | full | `AfterAgent` hook, `decision:"block"` triggers an automatic retry turn |

Spawn floor: isolated, model-selectable spawns via gemini's native subagents (markdown +
YAML agent files with per-agent `model` frontmatter). `parallel-fan-out` is declared
**`false`** — gemini subagents are single-threaded per instance, so review waves run their
lenses sequentially. This is a conforming, full-fledged forge target (contract § 3):
independence, not wall-clock parallelism, carries the guarantees. Role tiers resolve to
`gemini-2.5-flash` / `gemini-3-flash-preview` / `gemini-3-pro-preview` /
`gemini-3-pro-preview` — see the ultra note under known limitations.

## Install and update

Via gemini's native Git extension channel (the only carrier that ships `hooks/`):

```
gemini extensions install https://github.com/alp82/forge
```

then run the `setup-forge` skill inside a gemini session. Setup gates on the spawn floor
(`experimental.enableAgents`), wires the six hooks (extension autoload where gemini
supports it, else `~/.gemini/settings.json`), generates the four tier agents
(`~/.gemini/agents/forge-<tier>.md`), and live-verifies every declared capability — first
install ends with "reload gemini and re-run `setup-forge`" when hooks and agents only load
at startup.

If gemini does not surface the `setup-forge` skill after the extension install (its
adapter-dir location may sit outside gemini's skill discovery), bootstrap it the way the
opencode adapter does — paste into a gemini session:

```
Fetch https://raw.githubusercontent.com/alp82/forge/main/adapters/gemini/skills/setup/SKILL.md and follow it.
```

**Update = `gemini extensions update --all` (or `--auto-update`) and re-run
`setup-forge`.** Setup is idempotent — re-running refreshes what it owns, never
duplicates, and § 8 re-verification happens by construction. Staleness is self-detected:
setup stamps the forge version into each tier-agent file; the BeforeAgent hook compares
those stamps against the extension version and nags on drift.

## Verification behavior

What setup ([`skills/setup/SKILL.md`](skills/setup/SKILL.md)) probes, and what loud
failure looks like:

- **Spawn floor** — `experimental.enableAgents` disabled is a hard stop (a harness that
  cannot spawn is not a forge target), not a prose-only downgrade; setup asks consent to
  enable it and does not proceed until spawn is available.
- **BeforeAgent injection** — the forge banner in the installing session's own context is
  the proof; absent after a reload is `session-start-injection: FAILED`.
- **Hook activation path** — reported as `hooks: extension-autoloaded |
  settings.json-wired | FAILED (settings.json not writable)`, never silently assumed.
- **Tool guard** — a throwaway `git init` repo and a `git reset --hard` inside it; the
  command executing (harmlessly, there) instead of being denied is a loud failure.
- **Spawn isolation** — a spawned agent must not know conversation facts outside its
  prompt. No parallel probe runs: `parallel-fan-out` is `false` by declaration.
- **Model resolvability** — each tier agent is spawned once with a one-token prompt; a
  spawn error names the unresolvable model id, and the user picks a substitute which is
  written into the agent file and reported (loud effective downgrade, never silent).
- **Change tracking + stop-gate** — an edit-tool touch of a scratch file in the session's
  cwd, then the marker files are checked and the end-of-turn AfterAgent block is announced
  in advance: the block (an automatic retry turn) appearing IS the stop-gate pass signal;
  an unblocked turn end is `stop-gate: FAILED`.

## Known limitations and divergences

The gemini hook protocol is documented at survey level but under-specified in places;
every assumption below is deliberately conservative and arbitrated by the live install
probes, never silently resolved:

- **Ultra equals large, with no effort knob.** Gemini exposes no model above
  `gemini-3-pro-preview`, and its agent frontmatter carries no reasoning-effort field
  (unlike codex's `model_reasoning_effort`). So `models.ultra == models.large ==
  "gemini-3-pro-preview"` and the two tiers are genuinely identical agents — equality is
  allowed by the capability ordinal.
- **Timeout unit is unspecified.** The survey gives the `timeout` field but not its unit.
  hooks.json uses millisecond values (5000 / 130000 / 190000) that are safe under both
  readings — correct as ms, harmlessly over-long as seconds; the inner subprocess timeout
  in `verify_shared.py` is the real execution guard either way (RISK-9).
- **Extension hook autoload path is assumed.** Gemini loads hooks from an extension's
  `hooks/hooks.json`; forge keeps them under `adapters/gemini/hooks/` to keep the adapter
  dir whole (contract § 7). Setup probes autoload live and falls back to wiring
  `~/.gemini/settings.json` with absolute command paths (RISK-8); the § 7 (a)/(c) probes
  arbitrate.
- **BeforeAgent, not SessionStart, carries injection.** Gemini's SessionStart is
  advisory-only with no documented context-injection channel; injection rides BeforeAgent
  `additionalContext`, which fires before every turn including the first. The banner
  reinjects each turn (RISK-1).
- **Hook stdin field names are assumed Claude/codex-shaped** (`tool_name`, `tool_input`,
  `session_id`, `cwd`); the survey documents the output channels (`additionalContext`,
  `decision`) but not the input schema field-by-field. The guard, marker, and gate hooks
  read tolerantly; probes (c) and (f) arbitrate.
- **Tool names are matched broadly.** Only `run_shell_command` (shell) and `write_file` /
  `replace` (edits) are documented; the matchers add the plausible cross-harness spellings
  (`apply_patch`, `edit`, `write`, `str_replace`, `create_file`, `Edit`, `Write`), and the
  AfterTool matcher is kept in sync with the hook's internal `EDIT_TOOLS` set by a
  regression test (RISK-4). Probes (c)/(f) arbitrate.
- **`stop_hook_active` has no documented gemini equivalent.** The gates read it tolerantly
  (absent → proceed); the max-1-retry marker cap makes an infinite AfterAgent loop
  structurally impossible either way.
- **hooks.json top-level schema is assumed** (flat entries under event keys carrying
  `type`/`command`/`timeout`/`matcher`); the survey gives the entry fields but not the
  file shape (RISK-6). The setup skill reads this file as the canonical hook spec and
  translates it to whatever gemini's live config wants.
- **Subagents cannot nest, and are experimental.** `experimental.enableAgents` gates the
  whole surface, and "subagents cannot call other subagents"; forge's flat
  orchestrator-plus-workers shape fits the no-nesting rule, and the flag is verified at
  install.
- **Subagent markers can miss the rendezvous.** A gemini subagent's AfterTool firing under
  its own session id arms the wrong marker — the same accepted caveat as Claude Code;
  review-owed's disk-mtime settling is session-agnostic and mitigates the review gate's
  share.

## Survey source

Declaration surveyed 2026-07-17 against Gemini CLI 0.51.0:
[`docs/research/gemini-cli-survey.md`](https://github.com/alp82/forge/blob/research/gemini-cli-survey/docs/research/gemini-cli-survey.md)
(branch `research/gemini-cli-survey`), primary-sourced from the official
[google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli) `docs/` tree.
