# forge — adapter contract

The one page a harness implementer reads to port forge. An **adapter** is everything
harness-specific about a forge install for one agent CLI — hook implementations, the
setup/install skill, and the capability declaration. The core (the pipeline briefs under
root `skills/`) is harness-neutral and identical under every adapter.

## 1. Preamble

Two standing rules govern this document:

- **Spec § 10 is the canonical decision index.** Each section below opens by citing the
  spec entry it executes ("Normative source: …") and adds implementer detail only —
  definitions, conformance tests, schema, checklists. Where the two disagree, the spec is
  right and this file has a bug; a spec amendment that is not mirrored here is a bug in
  this file, not an ambiguity.
- **Claude Code holds no structural privilege** (spec § 10, #38 pt 5). It is adapter #1
  only in the sense of first-built reference implementation, sitting at
  `adapters/claude-code/` and bound by every rule here. Capability and event names in
  this contract are harness-neutral; Claude Code mechanisms appear only as the reference
  example.

Status: the restructuring ([#42](https://github.com/alp82/forge/issues/42)) has landed —
§ 7's anatomy is the repo's current shape.

## 2. The spawn floor (required)

Normative source: spec § 10, #36 pts 1–3.

To run forge at all, a harness MUST provide all three of the following. There is no
single-context fallback — a harness that cannot spawn isolated agents is not a forge
target.

1. **Isolated spawn.** An agent runs in a fresh context that does not inherit the
   orchestrator's conversation. Its inputs arrive only through two doors: the spawn
   prompt, and files in the run directory named by that prompt. Its output returns only
   through two doors: a run-dir file, or the spawn's return value. *Conformance test:*
   spawn an agent and ask it about any fact from the orchestrator's conversation that is
   not in its prompt or named input files — a conforming isolated agent must be unable to
   answer.
2. **Model-selectable spawn.** The orchestrator chooses the model per spawn — every stage
   brief names a role tier (§ 6 `models`), which the adapter's manifest resolves to a
   concrete model, so an adapter that cannot honor a per-spawn model choice cannot run
   the briefs as written.
3. **Sequential-execution discipline.** An adapter that runs an independent pair of
   agents serially MUST NOT feed the first agent's output into the second. Independence,
   not wall-clock parallelism, carries the guarantees.

Briefs mark some spawns `read-only`. An adapter maps the marker to a native read-only
agent kind where one exists; absent one, an ordinary isolated agent conforms — the
brief's own read-only discipline carries the constraint.

## 3. Optional capabilities

Normative source: spec § 10, #36 pt 2.

**Parallel fan-out** is the one optional spawn capability, adapter-declared as
`parallel-fan-out` in the manifest (§ 6). Briefs say "spawn independently — in parallel
where the adapter supports it," so a sequential-only harness is a full-fledged forge
target: gemini's subagents are single-threaded per instance today
([docs/core/subagents.md](https://github.com/google-gemini/gemini-cli/blob/main/docs/core/subagents.md))
and gemini is one of the first three proofs.

## 4. The four enforcement capabilities

Normative source: spec § 10, #37 pts 1 and 3.

None of these joins the § 2 floor: an adapter may declare all four `absent` and still
conform — spawn is the requirement, enforcement only tiers the guarantee (spec § 10,
#37 pt 1). Each capability is declared `full / degraded / absent`. The spec mandates a named mechanism for any
`degraded` claim; this contract tightens that operationally: the manifest (§ 6) names the
mechanism for `full` claims too, because the manifest is what install-time verification
(§ 8) probes against. `absent` carries `null`.

Each capability, defined by the failure class it prevents, with example mechanisms:

- **Session-start injection** (`session-start-injection`) — prevents: a session begins
  without the forge entry rule loaded, and stale or dangling installs go unnoticed.
  Examples: Claude Code's `SessionStart` hook; gemini's `BeforeAgent`
  `additionalContext`, which injects text before every turn including the first
  ([docs/hooks/writing-hooks.md](https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/writing-hooks.md)).
- **Tool guard** (`tool-guard`) — prevents: a destructive command executes instead of
  being intercepted. Examples: Claude Code's `PreToolUse` hook; codex's `PreToolUse`
  with `permissionDecision: "deny"` ([codex hooks](https://learn.chatgpt.com/codex/hooks));
  opencode's `tool.execute.before`, which may throw to abort a tool call
  ([opencode plugins](https://opencode.ai/docs/plugins/)).
- **Change tracking** (`change-tracking`) — prevents: stop-gates cannot tell code
  sessions from chat-only ones (which must stop freely). Example: Claude Code's
  `PostToolUse` on file edits, arming per-session change markers the gates read.
- **Stop-gate** (`stop-gate`) — prevents: the turn ends with failing tests, a broken
  build, or unreviewed changes. Examples: Claude Code's `Stop` hook; codex's `Stop` hook
  returning `decision: "block"` — gated behind the `features.hooks` config flag
  ([codex hooks](https://learn.chatgpt.com/codex/hooks),
  [config reference](https://learn.chatgpt.com/codex/config-file/config-reference));
  gemini's `AfterAgent` `"decision": "block"`, which triggers an automatic retry turn
  ([docs/hooks/reference.md](https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/reference.md)).
  opencode has no equivalent — `session.idle` is fire-and-forget
  ([opencode plugins](https://opencode.ai/docs/plugins/)), so its stop-gate is at best
  `degraded` (a reactive idle nudge).

In-repo provenance for these mechanism claims — the harness surveys, cited by
branch-qualified URL because they are unmerged:
[codex](https://github.com/alp82/forge/blob/research/codex-cli-survey/docs/research/codex-cli-survey.md),
[gemini](https://github.com/alp82/forge/blob/research/gemini-cli-survey/docs/research/gemini-cli-survey.md),
[opencode](https://github.com/alp82/forge/blob/research/opencode-survey/docs/research/opencode-survey.md).

## 5. Enforcement tiers and derivation

Normative source: spec § 10, #37 pts 2, 3, and 5.

Three enforcement tiers: **gated / guarded / prose-only**. Operationally, from the manifest:

```
enforcement["stop-gate"].level == "full"                                  ⇒ gated
else enforcement["tool-guard"].level != "absent"
     OR enforcement["stop-gate"].level == "degraded"                      ⇒ guarded   (a full guard, a degraded gate)
else                                                                      ⇒ prose-only
```

`session-start-injection` and `change-tracking` never trigger `guarded` on their own:
neither is a mechanical block — injection is informational, and change-tracking (§ 9)
"arms the per-session markers the three stop-gates read" but blocks nothing itself if
every gate/guard is `absent`.

The tier is never stored as an independent claim. It is derived from `capabilities.json`
at read time by the install skill; anywhere it is displayed — an adapter README, a
listing — is a derivative snapshot that verification recomputes from the manifest and
compares (§ 10). This is #37 pt 3's shorthand rule made mechanical: the manifest is the
claim, the tier only a reading of it.

Prose is tier-invariant (spec § 10, #37 pt 5): every tier ships the same brief text
carrying the same full discipline; hooks only enforce what the prose already states; a
tier change alone never edits brief text.

## 6. The capability manifest

The decision this contract owns (deferred by #37/#38 to
[#40](https://github.com/alp82/forge/issues/40)): the capability checklist lives in a
machine-readable manifest, `adapters/<harness>/capabilities.json`, not a prose section —
install-time verification (§ 8; decided in spec § 10, #37 pt 4) is a mechanical reader,
as would be any future conformance check (prospective; no ticket owns one) — and a
second, prose-form home for the same checklist would drift from the first. This section
defines the schema once.

Shape:

```json
{
  "harness": "<string>",
  "vendor": "<string>",
  "surveyed": "<ISO-8601 date string>",
  "spawn": {
    "isolated": true,
    "model-selectable": true,
    "parallel-fan-out": "<boolean>"
  },
  "models": {
    "mini": "<harness-native model identifier>",
    "standard": "<harness-native model identifier>",
    "large": "<harness-native model identifier>",
    "ultra": "<harness-native model identifier>"
  },
  "enforcement": {
    "session-start-injection": { "level": "full|degraded|absent", "mechanism": "<string or null>" },
    "tool-guard":              { "level": "full|degraded|absent", "mechanism": "<string or null>" },
    "change-tracking":         { "level": "full|degraded|absent", "mechanism": "<string or null>" },
    "stop-gate":               { "level": "full|degraded|absent", "mechanism": "<string or null>" }
  }
}
```

Rules:

- `spawn.isolated` and `spawn.model-selectable` are booleans that MUST be `true` — they
  are the floor (§ 2); declaring them anyway keeps install-time verification a one-file
  read. `parallel-fan-out` declares the § 3 option.
- `vendor` names the host harness's **model vendor** as a bare token (`anthropic`,
  `openai`, `google`, …) — never a `provider/model` path. The neutral worker forwarder
  (`skills/forge/WORKER.md`) reads it to exclude same-vendor second opinions: the
  challenge/crossfire worker earns its keep only when another *model* judges, so a worker
  sharing the host's vendor collapses into one model agreeing with itself. Required. The
  adapter surfaces it to the dispatcher through the session-start banner (§ 4); where no
  banner carries it, the worker degrades loudly to single-model judgment rather than
  guessing — this manifest is the one home for the value, the banner only relays it.
- `models` maps the four **role tiers** the briefs spawn with — `mini` / `standard` /
  `large` / `ultra`, a capability-ordinal register (each tier at least as capable as the
  one before) — to harness-native model identifiers; all four keys required; briefs say
  "tier `<name>`" and never name a model.
- The four enforcement keys are exactly the kebab-case identifiers above — the manifest
  exists for mechanical readers, so JSON keys carry no spaces; § 4 binds each identifier
  to its prose name.
- `mechanism` is a non-null string naming the harness surface for any `full` or
  `degraded` level (§ 4), and `null` for `absent`.
- `surveyed` records the date of the harness survey the declaration rests on.

Worked example — Claude Code's expected landing, a hypothesis until adapter verification
([#44](https://github.com/alp82/forge/issues/44)) confirms it at build time:

```json
{
  "harness": "claude-code",
  "vendor": "anthropic",
  "surveyed": "2026-07-18",
  "spawn": { "isolated": true, "model-selectable": true, "parallel-fan-out": true },
  "models": { "mini": "haiku", "standard": "sonnet", "large": "opus", "ultra": "fable" },
  "enforcement": {
    "session-start-injection": { "level": "full", "mechanism": "SessionStart hook (startup/resume/clear/compact)" },
    "tool-guard":              { "level": "full", "mechanism": "PreToolUse(Bash) hook, exit 2 blocks" },
    "change-tracking":         { "level": "full", "mechanism": "PostToolUse(Edit|Write) hook arms session markers" },
    "stop-gate":               { "level": "full", "mechanism": "Stop hook, blocking exit re-engages the agent" }
  }
}
```

Derived tier (per § 5): gated.

## 7. Adapter directory anatomy

Normative source: spec § 10, #38 pts 3–5. The internal anatomy is the other decision this
contract owns — the spec fixed only the slot.

`adapters/<harness>/` contains:

- `capabilities.json` — required. The § 6 manifest.
- `README.md` — required. Contents per § 10.
- `hooks/` — required whenever any enforcement capability is non-`absent`: the hook
  scripts plus the harness's own hook-config file (e.g. `hooks.json`). A prose-only
  adapter has none.
- `skills/setup/SKILL.md` — required. The harness's install/setup skill (§ 8).

The channel manifests (`.claude-plugin/`, `.codex-plugin/`, `gemini-extension.json`) are
not part of the adapter dir: each install channel requires its manifest at repo root, so
they live there as thin pointers into `adapters/<harness>/` (spec § 10, #38 pt 3). One
version repo-wide, stamped into every channel manifest — the bump mechanism belongs to
[#43](https://github.com/alp82/forge/issues/43); this contract only states the
invariant.

## 8. Install and update expectations

Normative source: spec § 10, #37 pt 4. Operational detail generalized from the existing
setup-skill precedent (`adapters/claude-code/skills/setup/SKILL.md`).

Install MUST:

- **Verify every declared capability live** against the actual environment — a probe or a
  harness-config check. Example: a codex install checks that `features.hooks` is enabled
  and that admin `allow_managed_hooks_only` does not lock user hooks out
  ([config reference](https://learn.chatgpt.com/codex/config-file/config-reference)).
- **Degrade loudly, never silently.** A refused capability gets a loud failure or a
  downgrade of the *effective* declaration to what the environment supports — with the
  user told which of the two outcomes occurred.
- **Be idempotent.** Re-running refreshes, never duplicates — the pattern
  `adapters/claude-code/skills/setup/SKILL.md` already sets (symlink-first, ownership
  guard, stamped copy fallback).

Update MUST re-verify capabilities, and MUST NOT silently change tier. Stale-install
detection — the `session-start.sh` version-stamp nag, comparing installed stamp to
current version at session start — is the reference mechanism where the harness supports
it.

## 9. Hook porting rules

Normative source: spec § 10, #37 and the tier-necessity survey
([#49](https://github.com/alp82/forge/issues/49)).

**The six-hook surface is a ceiling, not a floor.** An adapter ports at most these six
behaviors and adds none — they are the survivors of a cull from 14 registrations. A hook
that cannot name its failure class is a candidate for deletion, not porting.

| Hook (reference impl) | Capability | Failure class prevented | Measured catch rate |
|---|---|---|---|
| `session-start.sh` | session-start-injection | session begins without the forge entry rule; stale installs unnoticed | fires every session by construction |
| `block-git-writes.sh` | tool-guard | destructive git command executes (`reset --hard`, `push --force`, `checkout --`) | none measurable — value rests on severity × nonzero incidence |
| `mark-code-change.py` | change-tracking | none itself — arms the per-session markers the three stop-gates read | n/a |
| `verify-tests.py` | stop-gate | turn ends with a failing suite | up to 73 block events in plugin-repo transcripts, up to 117 across seven repos; median 2.3 s per check |
| `verify-build.py` | stop-gate | turn ends with a broken build/typecheck | counted with the above; median 23 ms |
| `review-owed.py` | stop-gate | code changed, no review wave ran | newest hook; no transcript corpus yet |

The catch-rate numbers are documented upper bounds, not asserted precision — per
[`pipeline-audit.md`](../research/pipeline-audit.md) § "Known limitations", the 73/117
Stop-hook counts include doctrine text quoting the trigger strings. Sources: the audit
(on main, above) and the enforcement-layer case § 1
([branch](https://github.com/alp82/forge/blob/research/enforcement-layer-case/docs/research/enforcement-layer-case.md))
— cited, never re-derived.

## 10. What an adapter must document

Its `README.md` states:

- **The derived tier, with its derivation shown** from `capabilities.json`, explicitly
  marked derivative — the manifest is the source, and adapter verification (#44–#46's
  checklists) recomputes the tier from the manifest and compares it against this
  snapshot.
- **Each capability's mechanism** and any degradation from `full`.
- **Exact install and update commands** via the harness's native channel.
- **Verification behavior**: what install probes, and what loud failure or downgrade
  looks like to the user.
- **Known limitations and divergences** from this contract.
- **Survey source and date** backing the declaration.

## 11. Distribution note

Normative source: spec § 10, #39 — indexed there, not restated here. The native channel
is canonical because it is the only carrier that ships `hooks/`; skills.sh carries root
`skills/` only, so it installs prose-only by construction — the loud hookless self-check
lives in forge skill prose (core, [#41](https://github.com/alp82/forge/issues/41)'s
text), not in any adapter.

## 12. Conformance — proving a port runs forge

Normative source: spec § 10, #51.

A port proves it actually runs forge with the checklist below, run **once, by hand, by the
port author**. It is not a shipped or maintained tool: the runner is one person doing a
one-time port, so the anti-drift argument that earns the pipeline its hooks (§ 9) does not
apply. The check is deliberately narrow — it proves the two things install-time
verification (§ 8) cannot:

- **The § 2 spawn floor holds** on the real harness.
- **The pipeline drives end-to-end** and leaves its artifacts.

Enforcement-capability presence is *not* re-proven here — that is § 8's job, run at every
install. Conformance is behavioral (the stages actually executed and chained through the
run dir), never a golden-output diff: model and harness variance make exact output
unstable, so the check asserts artifact *presence and non-emptiness*, not content.

### Checklist

1. **Isolation** (§ 2 pt 1). Spawn an agent and ask it a fact from the orchestrator's
   conversation that is not in its prompt or named input files. *Pass:* it cannot answer.
2. **Model resolution** (§ 2 pt 2, § 6). Confirm all four `models` tiers in
   `capabilities.json` — `mini` / `standard` / `large` / `ultra` — resolve to a model the
   harness accepts at spawn time. *Pass:* one spawn per tier, each starts.
3. **Sequential discipline** (§ 2 pt 3). Only when the manifest declares
   `parallel-fan-out: false`: confirm an independent pair runs into separate contexts with
   the first agent's output never fed to the second. *Pass:* the second agent's prompt
   carries no trace of the first's result.
4. **End-to-end drive.** In a throwaway fixture repo, drive one **trivial** forge task
   (single file, no new logic — e.g. add a one-line helper) through `/forge`. The trivial
   short path runs TRIAGE → IMPLEMENTER → the review wave without the plan/challenge/test
   gates, so it drives end-to-end with minimal human sitting. *Pass:* the run reaches its
   terminal summary without the orchestrator stalling.
5. **Artifacts present.** Inspect the run dir `.forge/<slug>/` at the summary — run
   artifacts are process debris that die with the run, so read them before cleanup.
   Confirm the files the driven path emits exist and are non-empty: `intent.md`,
   `receipt.md`, and at least one `findings-<lens>.md` (`findings-correctness.md` always
   rides the wave). *Pass:* every expected file exists with content — presence and
   non-emptiness only, never a content diff.

### Recording

A passing run is a derivative snapshot, recorded as one line in the adapter `README.md` —
`Conformance: passed <date> (<harness> <version>)` — the same derivative pattern § 10's
tier line uses: the manifest and this checklist are the source, the README line a reading
of them. The three first-adapter live validations
([#53](https://github.com/alp82/forge/issues/53) opencode,
[#55](https://github.com/alp82/forge/issues/55) codex,
[#57](https://github.com/alp82/forge/issues/57) gemini) are this checklist's inaugural
instances.
