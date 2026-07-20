---
name: forge
description: Run a code-modifying request end to end - triage with detection detours, plan, challenge, implement test-first, review wave, fix. Every code-modifying request enters here.
disable-model-invocation: true
argument-hint: the request, or a tracker ticket reference
---

# forge — the pipeline router

You are the orchestrator of one forge run. Every stage runs as a spawned subagent reading a sibling brief file; you spawn, gate, and relay — you never do a stage's work inline. The conversation carries only gists and terse status lines (`<stage> done ▶ <next>`); full sentences are reserved for findings, errors, and points where the user must decide.

**Enforcement self-check.** Once, before triage, look for any evidence of the adapter's enforcement layer — the cheapest signal the harness offers: injected session context (a forge banner or equivalent) or the adapter's hooks registered in the harness. Any single piece of evidence suffices; say nothing when one is found. Only when there is none, tell the user plainly: this run is prose-only, every rule in this brief binds regardless, and the adapter's README/setup restores the native install.

**Spawn contract.** One shape for every stage: spawn a fresh isolated agent (`read-only` where marked) with the tier the step names, and the prompt: *"Read `<brief path>` and follow it. Run dir: `<run dir>`. Inputs: `<paths>`."* A tier resolves to a concrete model through the adapter's `models` manifest; absent a manifest, map the four tiers — `mini`, `standard`, `large`, `ultra` — onto the harness's available models in ascending capability. Paths, never pasted content — every artifact a later stage consumes is a file in the run dir, so a fresh respawn needs only paths. Brief paths are relative to this skill's base directory; crossfire lens briefs sit beside it at `../crossfire/`. The worker forwarder (`WORKER.md`) alone takes one extra prompt field — `host-vendor: <vendor>`, read verbatim from the session-start banner's host-vendor line — so it can exclude same-vendor second opinions; if no banner carries that line, forward nothing and the worker fails loud to single-model judgment (its brief owns that rule).

## Open the run

1. Ensure `.forge/` is in the repo's `.gitignore`; append it if missing.
2. Create the run dir `.forge/<slug>/` — a short kebab-case reduction of the request subject (≤40 chars).
3. **Ticket contract.** When the request is or names a tracker ticket, read it per `docs/agents/issue-tracker.md` — the ticket body is the request. At close, post a resolution comment (verdict gist, pointer to the change's durable home — commit or PR, explicit deviations) and close the ticket. No tracker configured → the contract lies dormant.

## Triage

Spawn TRIAGE.md (`read-only`, tier `mini`) → writes `intent.md`, returns size and flags. Take each detour whose flag fired — conditions, not stages; skip silently otherwise:

- **unknowns** → follow INTERVIEW.md yourself, inline — it questions the user, and a subagent can't. Never answer its questions on the user's behalf.
- **unproven external** → PROTOTYPE.md (build spawned, reaction with the user) → `prototype.md`.
- **missing knowledge** → spawn RESEARCH.md (tier `standard`) → `research.md`.
- **bug** → spawn DIAGNOSE.md (`read-only`, tier `large`) → `diagnosis.md`. A bug is a code build with a diagnosis first, never its own route.
- **multi-session** — the ask spans sessions with open decisions → recommend charting a map with a mapping skill such as `/wayfinder`; with none available, the interview carves the largest one-session slice and names the remainder.

**Trivial short path.** SIZE `trivial` (single file, no new logic): skip plan, challenge, and tests — spawn IMPLEMENTER.md (tier `ultra`) straight off `intent.md`, then run the wave with CORRECTNESS plus any triggered conditional lens.

## Plan

Spawn PLANNER.md (tier `ultra`) → `plan.md`. A `DETOUR: prototype` return means a load-bearing external couldn't be verified from sources — take the prototype detour, then re-spawn.

## Challenge

Spawn in parallel, neither seeing the other's verdict before both are written:

- CHALLENGER.md (tier `ultra`) → `challenge.md`
- the worker forwarder WORKER.md (tier `standard`) → `challenge-worker.md` — a different-model second opinion; on failure it records `WORKER FAILED`, visible and non-blocking.

Read both, then put a structured choice to the user: **Approve** (proceed; open concerns become known risks) / **Revise** (re-spawn PLANNER.md with the blockers as corrections; the revised plan re-earns approval through this gate) / **Reshape** (back to the interview — the plan answers the wrong question). The plan's Summary and both challenge verdicts are the evidence shown.

## Tests

One stage, two hands — like the challenge, it pairs a doer with an independent check. When the change carries real logic (triage's NEEDS-TESTS, or the plan reveals it):

1. Spawn TEST-AUTHOR.md (tier `standard`) → red tests in the repo's test tree + `tests.md`.
2. Spawn TEST-REVIEW.md (`read-only`, tier `large`) to validate the red tests against intent and plan. `misaligned` → re-spawn TEST-AUTHOR.md with the report; loop until `ready`. Code never starts against unvalidated tests.

## Implement

Spawn IMPLEMENTER.md (tier `ultra`) → the change with tests green + `receipt.md`. A KICKBACK return (its brief names the kickback levels) → re-spawn PLANNER.md with the reason as corrections, then re-run the implementer — a forward correction, no re-gate through the challenge. Two kickbacks on the same blocker → stop and surface to the user.

## Review wave

Spawn every applicable lens in parallel, each reading `receipt.md` + `plan.md` + `intent.md`, each writing `findings-<lens>.md`:

- **Standing, every build:** `../crossfire/CORRECTNESS.md` (tier `large`), `ACCEPTANCE.md` (`large`), `SIMPLICITY.md` (`standard`), `SHAPE.md` (`standard`), `CONVENTIONS.md` (`standard`).
- **Conditional:** `UI.md` (`standard`) when the diff touches user-facing UI; `SECURITY.md` (`large`) when it touches auth, secrets, permissions, or untrusted input; `PERFORMANCE.md` (`large`) when it touches a hot path or data-volume-sensitive code.
- **Worker:** the WORKER.md forwarder over the diff → `findings-worker.md` — one more lens, same visible-failure rule.

## Fix

Any lens failed → spawn FIXER.md (tier `standard`; `ultra` when the fix set is large or structural) with the findings paths. It fixes and returns a re-run set: re-spawn exactly those lenses (CORRECTNESS always rides along) over the new diff. Loop until every lens is clean. Findings the fixer can't own (plan-level, missing context) surface to the user — never silently dropped.

## Close

Terse summary: what changed and where, review outcome, deviations from the plan. Post the ticket resolution when one is open. Run artifacts are process debris — they die with the run; reasoning worth keeping goes to a repo-native home (docs, ADR, commit message) and gets pointed at. Stamped code changes owe tests and review before the session ends; the adapter's stop-gate, where present, enforces that floor.

## Standing stances

- **Confirm before remote.** No push, publish, or PR creation without an explicit user confirm; the adapter's tool guard, where present, backs this deterministically.
- **Confirm before destruction.** Destructive or irreversible commands are proposed to the user, never run unconfirmed.
