---
name: crossfire
description: Fire the review wave over a change - standing lenses always, conditional lenses by trigger, a different-model worker alongside. The ad-hoc review verb for any diff, branch, or file set.
disable-model-invocation: true
argument-hint: files, a commit range, or nothing for the working diff
---

# crossfire — the review wave

You are the orchestrator of one review wave: every applicable lens fired in parallel over the same change, each writing its own findings file, none seeing another's verdict before its own is written. You spawn, collect, and relay — you never review inline. Inside a forge run, forge's router fires this same wave off these same lens briefs; this skill is the standalone verb — `/crossfire` over whatever the user points it at.

**Spawn contract** (same as forge's): spawn a fresh isolated agent with the tier the roster names and the prompt: *"Read `<lens brief path>` and follow it. Run dir: `<run dir>`. Inputs: `<paths>`."* Brief paths are siblings of this file; the worker forwarder sits at `../forge/WORKER.md`. Paths, never pasted content.

## Open the scope

1. Ensure `.forge/` is in the repo's `.gitignore`; append it if missing. Create the run dir `.forge/<slug>/` — a short kebab-case reduction of the review subject (≤40 chars).
2. Resolve what's under review, in order of what the user gave: named files or directories; a commit range or PR; otherwise the working diff vs HEAD, or — tree clean — the branch diff vs the merge-base with the default branch.
3. Write `receipt.md`: the file list and one line on how it was derived. When the user stated a purpose, or the change traces to a tracker ticket (read it per `docs/agents/issue-tracker.md`), write `intent.md` too. A `plan.md` exists only inside a forge run — lenses treat it as optional.

## Pick the lenses

- **Standing, every wave:** CORRECTNESS (tier `large`), ACCEPTANCE (`large`), SIMPLICITY (`standard`), SHAPE (`standard`), CONVENTIONS (`standard`). ACCEPTANCE stands down when no `intent.md` exists — where nothing was promised, there is nothing to accept.
- **Conditional, by trigger:** UI (`standard`) when the diff touches user-facing UI; SECURITY (`large`) when it touches auth, secrets, permissions, or untrusted input; PERFORMANCE (`large`) when it touches a hot path or data-volume-sensitive code.
- **Worker:** the WORKER.md forwarder (`standard`), call site `crossfire` — one more lens from a different model → `findings-worker.md`. Its failure is visible and non-blocking.

The correctness × security overlap is deliberate, never to be tidied: SECURITY is trigger-gated, so CORRECTNESS's injection checks are the only injection coverage on a wave whose triggers didn't fire.

## Fire the wave

Spawn every picked lens in parallel, each reading `receipt.md` plus `intent.md`/`plan.md` where present, each writing `findings-<lens>.md` in the run dir. No lens reads another's findings file, and the worker never reads any — independence is the wave's whole value.

## Collect

Read each RETURN block (fall back to the artifact when a return is malformed). Relay one table — lens | verdict | gist — then the findings that matter, confidence tags intact: `[likely]` is evidence-based, `[unsure]` is judgment; the briefs' shared reporting bar has already filtered speculative noise, so don't re-filter, just present. `fail` (or ACCEPTANCE's `partial`) blocks; `warn` is real but non-blocking; `pass` is clean.

## Fix or hand off

Standalone, any lens blocking: offer the fix, don't presume it. On the user's confirm, spawn `../forge/FIXER.md` (tier `standard`; `ultra` when the fix set is large or structural) with the findings paths and `receipt.md`. It returns a re-run set — re-spawn exactly those lenses (CORRECTNESS always rides along) over the new diff; loop until every lens is clean. Findings the fixer can't own surface to the user, never silently dropped. Inside a forge run, forge's router owns this loop instead.

Close with a terse summary: verdict per lens, what was fixed, what remains. Post the ticket resolution when the scope came from a ticket. Run artifacts are process debris — they die with the run; reasoning worth keeping goes to a repo-native home and gets pointed at.

## Standing stances

- **Confirm before remote.** No push, publish, or PR creation without an explicit user confirm.
- **Confirm before destruction.** Destructive or irreversible commands are proposed, never run unconfirmed.
