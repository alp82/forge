---
name: setup-forge
description: Install or update forge on Codex CLI - installs the plugin through the native marketplace, writes forge's enforcement hooks into codex's own hooks file, generates the four tier agents, then live-verifies every declared capability. Run when the startup nag says the installed forge surfaces are stale, or to update forge.
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

**Why the hooks are installed by hand, not carried by the plugin.** Codex does not load
hooks that a plugin ships (`plugin_hooks` is a *removed* feature — `codex features list`
confirms it). Real codex hooks live in `$CODEX_HOME/hooks.json` (default `~/.codex/
hooks.json`) under a per-hook trust mechanism. So the marketplace install lands only the
skills; the enforcement layer is written into codex's own hooks file by the installer
script below. The `hooks` field is intentionally absent from `.codex-plugin/plugin.json`.

## 1. Preflight

Run `codex --version` and record the number for the report. This procedure was verified
live against Codex CLI 0.143.0. Do not gate on the number; the verification below is the
arbiter of what this environment actually supports.

## 2. Hooks availability

Codex's `hooks` feature is **stable and on by default** — no opt-in flag. Confirm it with
`codex features list | grep '^hooks '` (expect `stable  true`). If a build ever reports it
otherwise, or an admin has disabled it, treat that as the *loud degradation branch*:
report `session-start-injection / tool-guard / change-tracking / stop-gate: ABSENT — hooks
unavailable`, and continue installing skills only.

## 3. Admin lockout check

Check managed/admin config for `allow_managed_hooks_only = true`. If present, user and
project hooks are ignored regardless of the feature flag. *Loud degradation branch*:
report `tool-guard / stop-gate / change-tracking / session-start-injection: LOCKED OUT
by admin policy — effective tier prose-only`, never pretend otherwise, and continue
installing skills only.

## 4. Install

Add the marketplace, then install the plugin (this lands the **skills**):

```
codex plugin marketplace add alp82/forge
codex plugin add forge@alperortac
```

`codex plugin add <plugin>@<marketplace>` is the install verb; the marketplace name is
`alperortac` (from `.claude-plugin/marketplace.json`, which codex reuses for discovery —
no codex-specific marketplace manifest exists). Confirm live with `codex plugin list`.
Idempotent: re-running the marketplace add refreshes the source; re-running this setup
regenerates only files it owns.

Read the installed plugin's version from its `.codex-plugin/plugin.json` — call it
`$VERSION` below — and note the installed plugin's root directory `$PLUGIN_ROOT` (from
`codex plugin list`, or wherever the marketplace cached it); the hook scripts live under
`$PLUGIN_ROOT/adapters/codex/hooks/`.

### 4a. Write the enforcement hooks

Run the installer that ships beside the hooks — it resolves absolute script paths and
merges forge's entries into `$CODEX_HOME/hooks.json`, owning only its own and never
touching a user's or Orca's hooks:

```
python3 "$PLUGIN_ROOT/adapters/codex/hooks/install-forge-hooks.py"
```

It writes the four events (`SessionStart` / `PreToolUse` / `PostToolUse` / `Stop`) with
absolute command paths and prints where it wrote and which events it owns. A non-zero
exit is a **loud failure** — report it and do not claim the enforcement tier.

### 4b. Trust the hooks

Codex will not run a newly written hook until it is trusted. On the next interactive
codex start you are prompted to trust forge's hooks — approve them. For headless
automation, the run passes `--dangerously-bypass-hook-trust` (only where the hook source
is already vetted — it is forge's own install). Until the hooks are trusted, the
verification probes below will show the enforcement layer absent.

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
`ultra` uses `xhigh`. The manifest holds model ids only — `ultra` and `large` share the
same model (`gpt-5.5`), and the effort line in these agent files is what distinguishes
them (there is no model above `gpt-5.5`; codex's own "Ultra" is a reasoning mode, not a
model id). All four ids resolve against `codex debug models`; probe (e) confirms it live.

The `# forge-version:` stamp comment is load-bearing: the SessionStart hook reads it to
detect stale installs. **Ownership guard**: only overwrite files named
`forge-<tier>.toml` whose stamp identifies them as forge's own; anything else belongs
to the user — ask before replacing, never overwrite silently.

## 6. Restart / trust gate

Hooks written in step 4a are loaded at codex startup and must be trusted (step 4b), so
they are not live in the session that wrote them. Check this session's own context for
the forge banner (the "## forge" block naming the forge skill entry rule):

- **Banner present** — hooks are live and trusted; continue to verification.
- **No banner** — restart codex, trust forge's hooks when prompted, and run
  `$setup-forge` again. The re-run detects current surfaces, skips the install steps,
  and lands here with the banner present.

## 7. Verify (contract § 8 — live, every declared capability)

Each probe either confirms a capability or produces a **loud downgrade or failure** —
never a silent pass.

- **(a) session-start injection.** The banner in this session's own context (step 6) is
  the proof. Present → verified. Absent after a restart-and-trust → report
  `session-start-injection: FAILED — hooks not loading or not trusted`; stop hook
  verification and report the effective tier as prose-only.
- **(b) Admin lockout.** Step 3's config read, reported as its own line:
  `user hooks: allowed | LOCKED OUT`.
- **(c) Tool-guard deny.** Create a throwaway repo and probe the guard inside it:

  ```
  PROBE_DIR="$(mktemp -d)" && cd "$PROBE_DIR" && git init -q && git commit -q --allow-empty -m probe && git reset --hard
  ```

  The `git reset --hard` must be **denied** — codex reports `Command blocked by PreToolUse
  hook` and the command does not run. If it executes — harmless in this throwaway repo —
  the guard is dead: report `tool-guard: FAILED — destructive git command executed
  unblocked`. Loud failure, not a downgrade. (Codex's shell tool reports as `Bash`; the
  guard's matcher covers it.)
- **(d) Spawn isolation + fan-out.** Spawn `forge-mini` and ask it for a fact from this
  conversation that is not in its prompt (e.g. "what version did the installer read in
  step 4?"). A conforming isolated agent cannot answer — if it can, report
  `spawn.isolated: FAILED`. Fan-out is declared **false** (codex `enable_fanout` is
  under-development/off; only sequential `multi_agent` is stable) — report
  `parallel-fan-out: false (sequential-only — conforming, not an error)`.
- **(e) Per-tier model resolvability.** Confirm the four agent files from step 5 exist.
  Then spawn each tier agent once with a one-token prompt ("reply: ok"). A completed
  reply proves its `model` id resolves; a spawn error names the unresolvable id — the
  spawn itself is the probe. For any unresolvable id: cross-check `codex debug models`,
  ask the user to pick an available substitute, rewrite that agent file's `model` line,
  and report the substitution. Loud effective downgrade, never silent. Note `ultra` and
  `large` share one id — one resolution covers both; still run the `ultra` spawn to
  exercise `xhigh`.
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
hooks feature           <stable/on | UNAVAILABLE — prose-only>
user hooks              <allowed | LOCKED OUT>
plugin (marketplace)    <installed | refreshed>
hooks ($CODEX_HOME)     <written | refreshed | FAILED>
agents/forge-*          <status, one line per substitution if any>
session-start-injection <verified | FAILED>
tool-guard              <verified | FAILED>
spawn floor             <verified | FAILED>
parallel-fan-out        <false (sequential-only)>
change-tracking         <verified | FAILED>
stop-gate               <armed — the end-of-turn block is the pass signal | FAILED>
```

Close by stating the tier actually achieved — **gated** when the stop-gate verified,
recomputed from what the probes found, never assumed — and the getting-started lines:

- Invoke the **forge** skill (`$forge`) for every code-modifying request — it triages,
  plans, challenges, implements test-first, and reviews.
- Invoke the **crossfire** skill (`$crossfire`) for a standalone review wave over any
  diff.
- Re-run this install any time via `$setup-forge`; the startup nag will tell you when
  the installed surfaces are stale.
