# forge adapter — opencode

Everything harness-specific about running forge under [opencode](https://opencode.ai):
the enforcement plugin, the install procedure, the setup skill, and the capability
declaration. The contract this adapter implements is
[`docs/spec/adapter-contract.md`](../../docs/spec/adapter-contract.md).

## Enforcement tier: guarded (derived)

This tier is a **derivative snapshot**, not an independent claim — the source is
[`capabilities.json`](capabilities.json), and verification (the standing test in
[`hooks/tests/capabilities.test.mjs`](hooks/tests/capabilities.test.mjs) plus the
install-time probes below) recomputes the tier from the manifest and compares it against
this line. Derivation per contract § 5:

```
enforcement["stop-gate"].level != "full"
enforcement["tool-guard"].level != "absent"  ⇒  guarded
```

`capabilities.json` declares `stop-gate` `degraded` (a reactive idle nudge, not a gate)
and `tool-guard` `full`, so the second rule fires and the tier is **guarded**. opencode
has no way to block the end of a session — a full stop-gate is impossible there, so
gated is out of reach by construction.

## Capabilities and mechanisms

Declared in [`capabilities.json`](capabilities.json); mechanisms per capability:

| Capability | Level | Mechanism |
|---|---|---|
| `session-start-injection` | full | `chat.message` hook appends the forge banner part to a main session's first message |
| `tool-guard` | full | `tool.execute.before(bash)` hook, throw blocks the tool call |
| `change-tracking` | full | `tool.execute.after(edit\|write\|apply_patch)` hook arms per-session change markers |
| `stop-gate` | degraded | `session.idle` event + `client.session.prompt` reactive nudge — post-hoc, cannot block the session from ending |

Spawn floor: isolated, model-selectable spawns via opencode's task tool and the four
generated tier agents (`forge-mini` / `forge-standard` / `forge-large` / `forge-ultra`,
derived from the manifest's `models` map at install time). `parallel-fan-out` declared
`true` — undocumented upstream, so install probes it live and downgrades loudly if
fan-out runs serially.

## Install and update

opencode has no plugin marketplace; forge installs through a bootstrap paste. Inside an
opencode session, paste:

```
Fetch https://raw.githubusercontent.com/alp82/forge/main/adapters/opencode/INSTALL.md and follow it.
```

The session clones `main` once, copies the skills, the enforcement plugin, and the setup
skill into `~/.config/opencode/`, generates the four tier agents, then verifies every
declared capability live (contract § 8). Plugins load at startup, so the first install
ends with "restart opencode and re-paste" — the re-run detects current copies, skips the
copying, and lands in verification.

**Update = re-run the same paste.** [`INSTALL.md`](INSTALL.md) is idempotent —
re-following it refreshes, never duplicates, and § 8 re-verification happens by
construction. After first install, the in-session `setup-forge` skill re-runs the same
procedure. Staleness is self-detected: the install stamps the forge version into both
copied surfaces (plugin file + skills copy); at startup the plugin compares the two
stamps and nags on drift.

## Verification behavior

What [`INSTALL.md`](INSTALL.md) probes, and what loud failure looks like:

- **Session-start injection** — the forge banner in the installing session's own context
  is the proof; no banner means the plugin is not live (restart gate).
- **Tool guard** — a throwaway `git init` repo and a `git reset --hard` inside it; the
  command executing (harmlessly, there) instead of being blocked is a loud failure.
- **Spawn floor + fan-out** — an isolation probe (a spawned agent must not know
  conversation facts outside its prompt), and a two-agent parallel probe; serial
  execution downgrades the effective declaration to `parallel-fan-out: false`, reported.
- **Model resolvability** — each tier agent is spawned once with a one-token prompt; a
  spawn error names the unresolvable model id, and the user picks a substitute which is
  written into the agent file and reported (loud effective downgrade, never silent).
- **Change tracking + stop-gate (degraded)** — an edit-tool touch of a scratch file,
  then the idle nudge is watched for; no nudge means the stop-gate is absent: reported.

## Known limitations

- **No stop-gate is possible.** The survey found no session-lifecycle hook that can veto
  anything; `session.idle` is fire-and-forget. The idle nudge is post-hoc — the model
  has already stopped — and burns a fresh turn. Nothing can refuse to let the agent
  stop; this adapter says so plainly rather than pretending otherwise.
- **Plugin activation needs an opencode restart.** Plugins load at startup only;
  INSTALL.md's restart gate handles the first run.
- **Session state is in-memory.** An opencode restart resets the plugin's per-session
  sets: a resumed session sees the banner once more, and a changed-but-unnudged session
  loses its change marker and its nudge. Acceptable degradation at the guarded tier.
- **No harness hook-config file exists.** Contract § 7's "harness hook-config" slot is
  the plugin file itself — file placement in `~/.config/opencode/plugins/` is the
  registration.
- **`read-only` spawn markers map to brief discipline.** No native read-only agent kind
  is generated; per contract § 2 an ordinary isolated agent conforms.
- **Claude-compat shadowing.** opencode also reads `~/.claude/skills/`; a forge install
  for Claude Code on the same machine may surface the same skill names there. Benign at
  equal versions; the drift nag covers staleness of this adapter's own copies.

## Survey source

Declaration surveyed 2026-07-17 against opencode v1.18.3:
[`docs/research/opencode-survey.md`](https://github.com/alp82/forge/blob/research/opencode-survey/docs/research/opencode-survey.md)
(branch `research/opencode-survey`), primary-sourced from
[opencode.ai/docs](https://opencode.ai/docs/) and the
[sst/opencode](https://github.com/sst/opencode) TypeScript source on `dev`. Built-in
tool ids (`bash`, `edit`, `write`, `apply_patch`) re-verified against the source tool
registry on 2026-07-18.
