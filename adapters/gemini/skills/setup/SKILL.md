---
name: setup-forge
description: Install or update forge on Gemini CLI - installs the extension through the native Git channel, wires the six hooks, generates the four tier agents, then live-verifies every declared capability. Run when the startup nag says the installed forge surfaces are stale, or to update forge.
---

# setup-forge — the gemini install and verification

You are a Gemini CLI agent session installing (or updating) forge on this machine. Follow
this document top to bottom. It is idempotent: re-running refreshes what it owns, never
duplicates — re-running IS the update mechanism. Never overwrite a surface you cannot
identify as forge's own without asking first.

The declared capabilities live in `adapters/gemini/capabilities.json` (the manifest is
the single source; everything generated below is a derived artifact). Verification is
the arbiter: every declared capability is probed live, and anything this environment
refuses produces a **loud downgrade** — the user is told exactly what failed and what
the effective tier now is. Never a silent pass.

Two structural facts distinguish gemini from the codex adapter:

- **Hooks are first-class** — there is no `features.hooks` opt-in to enable; the gate
  below is instead the **spawn floor** (`experimental.enableAgents`), which gemini needs
  for subagents.
- **No parallel fan-out** — gemini subagents are single-threaded (`parallel-fan-out:
  false` in the manifest). This is a conforming, sequential-only install, not a defect.

## 1. Preflight

Run `gemini --version` and record the number for the report. This procedure was surveyed
against Gemini CLI 0.51.0 — an older binary may predate hooks, the Agent Skills standard,
or subagents. Do not gate on the number; the verification below is the arbiter of what
this environment actually supports.

## 2. Spawn-floor gate (`experimental.enableAgents`)

forge's whole dispatch model rests on isolated, model-selectable subagents (contract
§ 2 — the floor, no fallback). Gemini's subagent surface sits behind
`experimental.enableAgents`, which is **on by default** but can be turned off.

Read `~/.gemini/settings.json` and check `experimental.enableAgents`.

- **Enabled (or absent → default on)** — continue.
- **Explicitly disabled** — forge cannot run: a harness that cannot spawn isolated agents
  is not a forge target (contract § 2). Tell the user, ask consent to set
  `experimental.enableAgents: true` in `~/.gemini/settings.json`, and do not proceed with
  hook wiring until spawn is available. This is a **hard stop**, not a prose-only
  degradation — enforcement tiers below the floor, but the floor is non-negotiable.

Hooks themselves need no feature flag on gemini. The only environmental precondition is a
writable `~/.gemini/settings.json` (checked in § 4).

## 3. Install (native Git extension channel)

```
gemini extensions install https://github.com/alp82/forge
```

This is the canonical install: only the native channel carries `hooks/` (contract § 11).
Gemini reads the repo-root `skills/` (the harness-neutral pipeline) natively via the
Agent Skills standard, so the forge and crossfire skills work with zero copying. Update
later with `gemini extensions update --all` (or install with `--auto-update`).

Read `$VERSION` from the installed extension's `gemini-extension.json` (repo root of the
extension checkout) — you stamp it into the tier agents below.

## 4. Wire the hooks

The six forge hooks are declared in `adapters/gemini/hooks/hooks.json` (BeforeAgent
injection, BeforeTool git-guard, AfterTool change-tracking, three AfterAgent stop-gates).

RISK-8 — **extension hook autoload is under-specified**: gemini documents hooks shipped
at an extension's `hooks/hooks.json`, but forge keeps them under `adapters/gemini/hooks/`
so the adapter dir stays whole (contract § 7). Resolve it live, do not assume:

1. **Probe autoload** — check whether the extension install already activated the hooks
   (the § 7 (a) banner and § 7 (c) guard probes are the ground truth). If both fire, the
   extension autoloaded them; skip to § 5.
2. **Else wire via settings.json** (the documented alternative — "Hooks are configured
   under a `hooks` object in `settings.json`"). Merge the `adapters/gemini/hooks/hooks.json`
   entries into `~/.gemini/settings.json`, rewriting each `command` to the **absolute**
   path of the installed hook script (relative and `${extensionPath}` paths may not
   resolve for a settings.json-wired command). If `~/.gemini/settings.json` is not
   writable, that is a **loud failure**: report `hooks: FAILED — settings.json not
   writable, effective tier prose-only` and continue installing skills only.

Idempotent: re-merging replaces forge's own hook entries (match on the
`adapters/gemini/hooks/` command path), never appends a duplicate. Leave every non-forge
hook entry untouched.

## 5. Tier agents

Read the `models` map from the installed extension's `adapters/gemini/capabilities.json`.
For each of the four tiers — `mini`, `standard`, `large`, `ultra` — write
`~/.gemini/agents/forge-<tier>.md` (gemini subagents are markdown + YAML frontmatter, not
TOML):

```markdown
---
name: forge-<tier>
description: forge stage runner, tier <tier>
model: <the manifest's model id for this tier>
---
<!-- forge-version: $VERSION -->

Follow the spawn prompt exactly: read the named brief and comply; your inputs are the
prompt and the files it names.
```

Gemini's agent frontmatter carries **no reasoning-effort field** (unlike codex), so
`ultra` and `large` — which share the model id `gemini-3-pro-preview` — are genuinely
identical agents. That is allowed: the role tiers are a capability ordinal (each at least
as capable as the one before), and equality is permitted at the top where gemini exposes
no model above pro.

The `<!-- forge-version: -->` stamp comment is load-bearing: the BeforeAgent hook reads
it to detect stale installs. **Ownership guard**: only overwrite files named
`forge-<tier>.md` whose stamp identifies them as forge's own; anything else belongs to the
user — ask before replacing, never overwrite silently.

## 6. Reload gate

Whether gemini hot-loads new hooks and agents or needs a `/reload` (or a restart) is
version-dependent. Check this session's own context for the forge banner (the "## forge"
block naming the forge skill entry rule):

- **Banner present** — hooks are live; continue to verification.
- **No banner** — reload gemini (or restart) and run `setup-forge` again. The re-run
  detects current surfaces, skips the install steps, and lands here with the banner
  present.

## 7. Verify (contract § 8 — live, every declared capability)

Each probe either confirms a capability or produces a **loud downgrade or failure** —
never a silent pass.

- **(a) BeforeAgent injection.** The forge banner in this session's own context (step 6)
  is the proof. Present → verified. Absent after a reload → report
  `session-start-injection: FAILED — BeforeAgent not injecting`; the hooks are not live,
  so report the effective tier as prose-only.
- **(b) Hook activation path.** Report which of the two § 4 routes carried the hooks:
  `hooks: extension-autoloaded | settings.json-wired | FAILED (settings.json not
  writable)`.
- **(c) Tool-guard deny.** Create a throwaway repo and probe the guard inside it:

  ```
  PROBE_DIR="$(mktemp -d)" && cd "$PROBE_DIR" && git init -q && git commit -q --allow-empty -m probe && git reset --hard
  ```

  The `git reset --hard` must be **denied** (the shell call fails with the guard's
  "rewrites or destroys history/state" message). If it executes — harmless in this
  throwaway repo — the guard is dead: report `tool-guard: FAILED — destructive git
  command executed unblocked`. Loud failure, not a downgrade.
- **(d) Spawn isolation (sequential).** Spawn `forge-mini` and ask it for a fact from this
  conversation that is not in its prompt (e.g. "what version did the installer read in
  step 3?"). A conforming isolated agent cannot answer — if it can, report
  `spawn.isolated: FAILED`. Gemini is **sequential-only** (`parallel-fan-out: false`): do
  not probe for parallel dispatch; a review wave running its lenses one after another is
  the expected, conforming behavior.
- **(e) Per-tier model resolvability.** Confirm the four agent files from step 5 exist.
  Then spawn each tier agent once with a one-token prompt ("reply: ok"). A completed reply
  proves its `model` id resolves; a spawn error names the unresolvable id — the spawn
  itself is the probe. For any unresolvable id (the survey's model list can age): ask the
  user to pick an available substitute, rewrite that agent file's `model` line, and report
  the substitution. Loud effective downgrade, never silent. Note `ultra` and `large` share
  `gemini-3-pro-preview` — one resolution covers both.
- **(f) Change tracking + stop-gate block.** Edit a scratch file **inside this session's
  cwd** (e.g. `./forge-probe.txt`; delete it afterwards) so the AfterTool hook arms the
  markers. Confirm `/tmp/.gemini-changed-*-<session_id>` exist — change-tracking verified;
  absent → `change-tracking: FAILED` (the likely cause is an edit-tool name or payload
  field the hook's tolerant reads still missed). Then tell the user: the end of this turn
  will be blocked once by the review gate — **that AfterAgent block (an automatic retry
  turn) appearing is the stop-gate probe passing**. If the turn ends unblocked →
  `stop-gate: FAILED — effective tier guarded at best`, reported.

## 8. Report

One line per surface — `installed` / `refreshed` / `kept (user's own — skipped)` /
`verified` / `FAILED` / `DOWNGRADED: <what, why>`:

```
gemini <version> — forge $VERSION
experimental.enableAgents  <enabled | ENABLED with consent | DISABLED — spawn floor down>
extension (git channel)    <installed | refreshed>
hooks                      <extension-autoloaded | settings.json-wired | FAILED>
agents/forge-*             <status, one line per substitution if any>
session-start-injection    <verified | FAILED>
tool-guard                 <verified | FAILED>
spawn floor                <verified | FAILED>
parallel-fan-out           false (gemini subagents are single-threaded — conforming)
change-tracking            <verified | FAILED>
stop-gate                  <armed — the end-of-turn AfterAgent block is the pass signal | FAILED>
```

Close by stating the tier actually achieved — **gated** when the stop-gate verified,
recomputed from what the probes found, never assumed — and the getting-started lines:

- Invoke the **forge** skill for every code-modifying request — it triages, plans,
  challenges, implements test-first, and reviews.
- Invoke the **crossfire** skill for a standalone review wave over any diff.
- Re-run this install any time via the `setup-forge` skill; the startup nag will tell you
  when the installed surfaces are stale.
