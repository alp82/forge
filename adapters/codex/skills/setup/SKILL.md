---
name: setup-forge
description: Install or update forge on Codex CLI - enables hooks, installs the plugin through the native marketplace, generates the four tier agents, then live-verifies every declared capability. Run when the startup nag says the installed forge surfaces are stale, or to update forge.
---

# setup-forge — the codex install and verification

You are a codex agent session installing (or updating) forge on this machine. Follow
this document top to bottom. It is idempotent: re-running refreshes what it owns, never
duplicates — re-running IS the update mechanism. Never overwrite a surface you cannot
identify as forge's own without asking first.

The declared capabilities live in `adapters/codex/capabilities.json` (the manifest is
the single source; everything generated below is a derived artifact). Verification is
the arbiter: every declared capability is probed live, and anything this environment
refuses produces a **loud downgrade** — the user is told exactly what failed and what
the effective tier now is. Never a silent pass.

## 1. Preflight

Run `codex --version` and record the number for the report. This procedure was surveyed
against Codex CLI 0.144.5 — an older binary may predate plugins or hooks. Do not gate on
the number; the verification below is the arbiter of what this environment actually
supports.

## 2. Hooks feature gate

Codex hooks are **opt-in and carry no published stable-maturity label**. Read
`~/.codex/config.toml` and check whether `features.hooks` is enabled.

- **Enabled** — continue.
- **Not enabled** — tell the user: forge's enforcement (git-write guard, change
  tracking, the stop-gate that blocks a session ending on failing tests or unreviewed
  code) rides on codex's hooks feature, which is opt-in and not marked stable upstream.
  Ask consent to enable it (set `features.hooks` in `~/.codex/config.toml`, or have
  them do it).
- **Declined, or the flag cannot take effect** — *loud degradation branch*: report
  `effective tier: prose-only (hooks disabled)`, name each enforcement capability as
  effectively absent (`session-start-injection / tool-guard / change-tracking /
  stop-gate: ABSENT — hooks disabled`), and continue installing skills only.

## 3. Admin lockout check

Check managed/admin config for `allow_managed_hooks_only = true`. If present, user and
project hooks are ignored regardless of `features.hooks`. *Loud degradation branch*:
report `tool-guard / stop-gate / change-tracking / session-start-injection: LOCKED OUT
by admin policy — effective tier prose-only`, never pretend otherwise, and continue
installing skills only.

## 4. Install

```
codex plugin marketplace add alp82/forge
```

Then confirm the install/enable verb live — run `codex plugin --help` and use the
documented subcommand to install/enable the `forge` plugin (the marketplace-add verb is
the surveyed part; the enable verb may differ across versions). Idempotent: re-running
the marketplace add refreshes the source; re-running this setup regenerates only files
it owns.

Read the installed plugin's version from its `.codex-plugin/plugin.json` — call it
`$VERSION` below.

## 5. Tier agents

Read the `models` map from the installed plugin's `adapters/codex/capabilities.json`.
For each of the four tiers — `mini`, `standard`, `large`, `ultra` — write
`~/.codex/agents/forge-<tier>.toml`:

```toml
# forge-version: $VERSION
name = "forge-<tier>"
description = "forge stage runner, tier <tier>"
developer_instructions = "Follow the spawn prompt exactly: read the named brief and comply; your inputs are the prompt and the files it names."
model = "<the manifest's model id for this tier>"
model_reasoning_effort = "<effort for this tier — see below>"
```

Reasoning effort per tier: `mini` and `standard` use `medium`; `large` uses `high`;
`ultra` uses `xhigh`. The manifest holds model ids only — `ultra` and `large` share
`gpt-5.6-sol` and the effort line in these agent files is what distinguishes them
(there is no model above sol; codex's own "Ultra" is a reasoning mode, not a model id).

The `# forge-version:` stamp comment is load-bearing: the SessionStart hook reads it to
detect stale installs. **Ownership guard**: only overwrite files named
`forge-<tier>.toml` whose stamp identifies them as forge's own; anything else belongs
to the user — ask before replacing, never overwrite silently.

## 6. Restart gate

Whether hooks hot-load after install or need a codex restart is undocumented. Check
this session's own context for the forge banner (the "## forge" block naming the forge
skill entry rule):

- **Banner present** — hooks are live; continue to verification.
- **No banner** — hooks likely load at startup. Tell the user: restart codex and run
  `$setup-forge` again. The re-run detects current surfaces, skips the install steps,
  and lands here with the banner present.

## 7. Verify (contract § 8 — live, every declared capability)

Each probe either confirms a capability or produces a **loud downgrade or failure** —
never a silent pass.

- **(a) features.hooks + session-start injection.** The banner in this session's own
  context (step 6) is the proof. Present → verified. Absent after a restart → report
  `session-start-injection: FAILED — hooks not loading`; stop hook verification and
  report the effective tier as prose-only.
- **(b) Admin lockout.** Step 3's config read, reported as its own line:
  `user hooks: allowed | LOCKED OUT`.
- **(c) Tool-guard deny.** Create a throwaway repo and probe the guard inside it:

  ```
  PROBE_DIR="$(mktemp -d)" && cd "$PROBE_DIR" && git init -q && git commit -q --allow-empty -m probe && git reset --hard
  ```

  The `git reset --hard` must be **denied** (the shell call fails with the guard's
  "rewrites or destroys history/state" message). If it executes — harmless in this
  throwaway repo — the guard is dead: report `tool-guard: FAILED — destructive git
  command executed unblocked`. Loud failure, not a downgrade.
- **(d) Spawn isolation + fan-out.** Spawn `forge-mini` and ask it for a fact from this
  conversation that is not in its prompt (e.g. "what version did the installer read in
  step 4?"). A conforming isolated agent cannot answer — if it can, report
  `spawn.isolated: FAILED`. Then spawn two trivial agents in one dispatch for the
  parallel probe (`agents.max_threads` defaults to 6); if they visibly run serially,
  report the effective declaration as `parallel-fan-out: false` (a conforming,
  sequential-only install — not an error, but say it).
- **(e) Per-tier model resolvability.** Confirm the four agent files from step 5 exist.
  Then spawn each tier agent once with a one-token prompt ("reply: ok"). A completed
  reply proves its `model` id resolves; a spawn error names the unresolvable id — the
  spawn itself is the probe. For any unresolvable id: ask the user to pick an available
  substitute, rewrite that agent file's `model` line, and report the substitution. Loud
  effective downgrade, never silent. Note `ultra` and `large` share one id — one
  resolution covers both; still run the `ultra` spawn to exercise `xhigh`.
- **(f) Change tracking + stop-gate block.** Edit a scratch file **inside this
  session's cwd** (e.g. `./forge-probe.txt`; delete it afterwards) so the PostToolUse
  hook arms the markers. Confirm `/tmp/.codex-changed-*-<session_id>` exist —
  change-tracking verified; absent → `change-tracking: FAILED` (the likely cause is an
  edit-tool name or payload field the hook's tolerant reads still missed). Then tell
  the user: the end of this turn will be blocked once by the review gate — **that block
  message appearing is the stop-gate probe passing**. If the turn ends unblocked →
  `stop-gate: FAILED — effective tier guarded at best`, reported.

## 8. Report

One line per surface — `installed` / `refreshed` / `kept (user's own — skipped)` /
`verified` / `FAILED` / `DOWNGRADED: <what, why>`:

```
codex <version> — forge $VERSION
features.hooks           <enabled | DECLINED — prose-only>
user hooks               <allowed | LOCKED OUT>
plugin (marketplace)     <installed | refreshed>
agents/forge-*           <status, one line per substitution if any>
session-start-injection  <verified | FAILED>
tool-guard               <verified | FAILED>
spawn floor              <verified | FAILED>
parallel-fan-out         <true | false (effective)>
change-tracking          <verified | FAILED>
stop-gate                <armed — the end-of-turn block is the pass signal | FAILED>
```

Close by stating the tier actually achieved — **gated** when the stop-gate verified,
recomputed from what the probes found, never assumed — and the getting-started lines:

- Invoke the **forge** skill (`$forge`) for every code-modifying request — it triages,
  plans, challenges, implements test-first, and reviews.
- Invoke the **crossfire** skill (`$crossfire`) for a standalone review wave over any
  diff.
- Re-run this install any time via `$setup-forge`; the startup nag will tell you when
  the installed surfaces are stale.
