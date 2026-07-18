# forge — opencode install and verification

You are an opencode agent session installing (or updating) forge on this machine. Follow
this document top to bottom. It is idempotent: re-running refreshes current copies, never
duplicates — re-running IS the update mechanism. Never overwrite a surface you cannot
identify as forge's own without asking first.

## 1. Preflight

Run `opencode --version` and record the number for the report. This procedure was
surveyed against v1.18.3 — an older binary may predate the skill tool or plugin hooks.
Do not gate on the number; the verification below is the arbiter of what this
environment actually supports.

## 2. Fetch

Clone once, shallow, into a freshly-created temp dir — never a fixed, guessable path
(a predictable clone target under `/tmp` is poisonable on a shared host, and this clone
feeds an auto-loaded plugin):

```
CLONE_DIR="$(mktemp -d)"
git clone --depth 1 https://github.com/alp82/forge "$CLONE_DIR"
```

One fetch feeds every copy below, so the two version stamps written in step 3 always
agree at install time. Read the version now from
`$CLONE_DIR/.claude-plugin/plugin.json` (the `version` field) — call it
`$VERSION` below.

## 3. Install (idempotent, ownership-guarded)

For every target below: if the target already exists and is recognizably forge's own —
it carries a `.forge-version` stamp, or it is content you can identify as forge's from
the clone — refresh it in place. If it exists and is NOT recognizably forge's, it
belongs to the user: **ask before replacing, never overwrite silently**.

1. **Skills.** Copy `skills/forge/` and `skills/crossfire/` from the clone to
   `~/.config/opencode/skills/forge/` and `~/.config/opencode/skills/crossfire/`
   (each directory whole, including the stage briefs beside each SKILL.md).
2. **Setup skill.** Copy `adapters/opencode/skills/setup/` from the clone to
   `~/.config/opencode/skills/setup-forge/` — opencode requires the directory name to
   equal the skill's frontmatter `name`, which is `setup-forge`.
3. **Plugin.** Copy `adapters/opencode/hooks/forge.js` to
   `~/.config/opencode/plugins/forge.js`.
4. **Version stamp.** Write `$VERSION` into
   `~/.config/opencode/skills/forge/.forge-version`. The plugin carries its own baked
   `FORGE_VERSION`; at startup it compares the two stamps and nags on drift — that nag
   is the update signal.
5. **Tier agents.** Read the `models` map from the clone's
   `adapters/opencode/capabilities.json` (the manifest is the single source; these
   agent files are derived artifacts). For each of the four tiers — `mini`,
   `standard`, `large`, `ultra` — write `~/.config/opencode/agents/forge-<tier>.md`:

   ```markdown
   ---
   description: forge stage runner, tier <tier>
   mode: subagent
   model: <the manifest's model id for this tier>
   hidden: true
   ---

   Follow the spawn prompt exactly: read the named brief and comply; your inputs are
   the prompt and the files it names.
   ```

## 4. Restart gate

Plugins load at opencode startup only. Check this session's own context for the forge
banner (the "## forge" block naming the forge skill entry rule):

- **Banner present** — the plugin is live; continue to verification.
- **No banner** — the plugin just landed but is not loaded. Tell the user: restart
  opencode and paste the same install line again. The re-run will detect current copies,
  skip the copying, and land here with the banner present.

## 5. Verify (contract § 8 — live, every declared capability)

Each probe either confirms a capability or produces a **loud downgrade**: tell the user
exactly what failed and what the effective declaration now is. Never report a silent
pass.

- **(a) Session-start injection.** The banner in this session's context (step 4) is the
  proof. Present → verified. Absent after a restart → report
  `session-start-injection: FAILED — plugin not loading`, and stop verification.
- **(b) Tool guard.** Create a throwaway repo and probe the guard inside it:

  ```
  mkdir -p "$CLONE_DIR/guard-probe" && cd "$CLONE_DIR/guard-probe" && git init -q && git commit -q --allow-empty -m probe && git reset --hard
  ```

  The `git reset --hard` must be **blocked** by the plugin (the bash call fails with the
  guard's "rewrites or destroys history/state" message). If it executes — harmless in
  this throwaway repo — the guard is dead: report `tool-guard: FAILED — destructive git
  command executed unblocked`. Loud failure, not a downgrade.
- **(c) Spawn floor and fan-out.** Task-spawn one tier agent (say `forge-mini`) and ask
  it for a fact from this conversation that is not in its prompt (e.g. "what version
  string did the installer read in step 2?"). A conforming isolated agent cannot answer
  — if it can, report `spawn.isolated: FAILED`. Then task-spawn two trivial agents in
  one message for the parallel probe; if they visibly run serially, report the effective
  declaration as `parallel-fan-out: false` (a conforming, sequential-only install — not
  an error, but say it).
- **(d) Model resolvability.** Confirm the four agent files from step 3.5 exist. Then
  task-spawn each tier agent once with a one-token prompt ("reply: ok"). A completed
  reply proves its `model` id resolves against this user's configured providers; a spawn
  error names the unresolvable id — the spawn itself is the probe, no eyeballing of
  provider lists. For any unresolvable id: ask the user to pick an available substitute
  (`/models` lists them), rewrite that agent file's `model:` line, and report the
  substitution. Loud effective downgrade, never silent.
- **(e) Change tracking + stop-gate (degraded).** Use the edit or write tool to touch a
  scratch file under `$CLONE_DIR/` — that arms this session's change marker.
  Then tell the user: the forge review reminder should appear when this session next
  idles; if it never does, the stop-gate is absent, not merely degraded — report it.
  Be plain about the ceiling either way: opencode cannot block a session from ending;
  this nudge is after-the-fact by construction.

## 6. Report

One line per surface — `copied` / `refreshed` / `kept (user's own — skipped)` /
`verified` / `DOWNGRADED: <what, why>`:

```
opencode <version> — forge $VERSION
skills/forge          <status>
skills/crossfire      <status>
skills/setup-forge    <status>
plugins/forge.js      <status>
agents/forge-*        <status, one line per substitution if any>
session-start-injection  <verified | FAILED>
tool-guard               <verified | FAILED>
spawn floor              <verified | FAILED>
parallel-fan-out         <true | false (effective)>
change-tracking + nudge  <armed — watch for the idle reminder>
```

Close by stating the tier actually achieved — **guarded** when the tool guard verified
(there is no stop-gate on opencode; the idle nudge is its degraded stand-in) — and the
getting-started lines:

- Invoke the **forge** skill for every code-modifying request — it triages, plans,
  challenges, implements test-first, and reviews.
- Invoke the **crossfire** skill for a standalone review wave over any diff.
- Re-run this install any time via the **setup-forge** skill (or re-paste the README
  line); the startup nag will tell you when the copies are stale.

Finally, remove the temp clone: propose `rm -rf "$CLONE_DIR"` to the user (the
guard does not block it, but deleting is theirs to confirm).
