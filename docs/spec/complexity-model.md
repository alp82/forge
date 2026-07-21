# The complexity-based decision model

**Status:** locked spec, handed off for build. This document is the authoritative reference for forge's redesigned routing model - the one that replaces the `trivial | standard` binary with a two-axis grid that proportions pipeline depth to a request's size and risk.

**Scope:** this spec fixes the *model* and the *cutover shape*. Carrying the edits into `TRIAGE.md` / `SKILL.md` / `IMPLEMENTER.md` is a downstream forge build, out of scope here (see §5). The validation table in §4 is that build's acceptance gate.

**Provenance.** Every ruling below is the resolution of a locked decision ticket on the [complexity-model map](https://github.com/alp82/forge/issues/67): axis model [#69](https://github.com/alp82/forge/issues/69), routing table [#70](https://github.com/alp82/forge/issues/70), signal source [#71](https://github.com/alp82/forge/issues/71), lens scaling [#72](https://github.com/alp82/forge/issues/72), escalation policy [#73](https://github.com/alp82/forge/issues/73), validation / migration / claims [#74](https://github.com/alp82/forge/issues/74). Prior-art survey: [`docs/research/complexity-routing-prior-art.md`](../research/complexity-routing-prior-art.md).

---

## 1. The model

### 1.1 Why two axes

forge routes process depth for a *change*, and that is exactly the domain where size and risk dissociate: a one-line auth change is tiny-but-dangerous; a 400-line mechanical rename is big-but-safe. A single scalar cannot name that cell - collapsing both into one number is the "the middle gets the full pipeline" cliff this model exists to remove. Two candidate third axes are folded away rather than added: **reversibility** is a component of risk (part of "how bad if wrong"), and **uncertainty / likelihood** stays in the existing detour flags (`unknowns`, `unproven-external`, `missing-knowledge`), which are already condition-scaled and out of this model's scope.

The result is a symmetric **3×3 grid**, size band × risk band, in the shape of an ISTQB likelihood×impact risk matrix. The dials are read independently and the route is the pair - see §2.

### 1.2 SIZE axis - "how much work and new logic"

**Gates:** plan + tests. **Estimated ex ante** by triage from the request, not measured from a diff, then re-scored authoritatively by the planner (§2.4).

- **Definition:** logic load is primary (a new or changed branch, loop, or computation); surface breadth is a secondary amplifier. Logic load gates tests (no new logic → existing tests hold); breadth still gates a light plan even when logic is flat (a broad rename is easy to miss a call site on).
- **Bands:**
  - **minimal** - one seam, no new logic. Docs, config, copy, version bumps, a localized edit. Like today's `trivial`, but keyed to one *seam*, not one *file*.
  - **moderate** - new logic in a bounded area, OR a broad mechanical change across many files with flat logic. The middle that currently has no home.
  - **substantial** - significant new logic AND/OR broad new surface: multiple interacting pieces, new modules or endpoints, cross-cutting reasoning.

### 1.3 RISK axis - "how bad if wrong" (impact only)

**Gates:** challenge + review-wave depth. **Impact only, not likelihood** - likelihood is uncertainty, owned by the detour flags. Kept conservative: **default-to-deep on impact**, so a rare-but-catastrophic path earns depth regardless of how likely it is to break. Reads primarily from **PATH**, CODEOWNERS-style.

- **Signals, in order:** sensitive surface (auth / secrets / permissions, payments, data migrations, infra & deploy, public API / contracts); reversibility (destructive or irreversible ops); blast radius (a widely-consumed shared contract vs. a leaf). Triage's existing `security` / `performance` / `ui` sniffs feed straight in as surface hits.
- **Bands:**
  - **routine** - no sensitive surface: leaf files, internal helpers, docs, self-contained features.
  - **elevated** - user-facing (`ui`), perf-hot (`performance`), or a moderately-shared contract. Wrong is annoying, not dangerous.
  - **critical** - sensitive or irreversible: `security` surfaces, payments, migrations, infra / deploy, destructive ops, breaking public-API changes. Default-to-deep.

### 1.4 The grid

Nine cells collapse many-to-one onto the pipeline depths defined in §2. The two corners reproduce today's two paths (the continuity anchor); the seven interior cells are the proportionate middle that the binary had no home for.

| size ↓ / risk → | routine | elevated | critical |
|---|---|---|---|
| **minimal** | short path | light plan (floored) | light plan (floored) |
| **moderate** | light plan | light plan | light plan |
| **substantial** | full plan | full plan | full plan |

The cell names only the *plan* depth (the one place the axes cross, §2.3); tests overlay by logic-load, challenge and review depth overlay by risk band. The machine contract is two tokens (`SIZE`, `RISK`); nicknames are for prose only.

---

## 2. The routing table - separable dials

The route is composed from **two independent lookups**, not a 9-cell case table. Triage (then the planner, authoritatively) emits two tokens replacing `trivial | standard`:

- `SIZE: minimal | moderate | substantial`
- `RISK: routine | elevated | critical`

One deliberate coupling crosses the dials (§2.3); everything else is independent.

### 2.1 Size dial → plan + tests

**Plan:**

| SIZE | plan |
|---|---|
| minimal | **skip** |
| moderate | **light** - a small, concise artifact; still challenged when risk calls for it ("light" means small, not challenge-exempt) |
| substantial | **full** - today's PLANNER.md pass |

**Tests** fire on the **logic-load sub-signal** (= today's `needs-tests`: a new or changed branch, loop, or computation), NOT the band label:

- A moderate-*by-breadth* change (e.g. a 40-file flat rename) skips tests but still earns the light plan.
- A moderate-*by-logic* change gets tests.
- When tests fire, the stage is **uniform** - TEST-AUTHOR + TEST-REVIEW, TEST-REVIEW always-on ("code never starts against unvalidated tests"). No test-depth tiers.
- **Risk never gates tests.** A critical one-line cookie flip has no new logic → no tests.

### 2.2 Risk dial → challenge + review depth

**Challenge** scales the machinery *and* the human's attention (the scarce resource is attention, not the spawn):

| RISK | challenge |
|---|---|
| routine | **none** |
| elevated | **challenger only** (no worker), **autonomous** planner↔challenger ping-pong to convergence, **capped at 2 revise rounds**; converged → proceed; still-blocked after 2 → **escalate to HITL** (surface the standing blocker with Approve / Revise / Reshape). The human is not otherwise involved. |
| critical | **challenger + worker** (cross-vendor second opinion), **HITL** Approve / Revise / Reshape gate with both verdicts. |

**Review-wave depth** is **risk × size**, not risk-only (§2.5). Risk's sole review-wave lever is the **worker** lens at critical; size governs the structural lenses.

### 2.3 The one coupling - challenge implies a plan

The challenger challenges a *plan*, so whatever risk band first fires the challenger (**elevated**) floors the plan at **light**, even when size says skip. The effective plan depth is the **deeper of** (size-plan, risk-floor). This is the only place the dials cross, and it falls out of "you don't challenge thin air," not a special case.

### 2.4 Signal source - provisional triage, authoritative planner re-score

Triage emits **provisional** `SIZE` + `RISK`: a gate-opener whose only job is to decide whether a plan fires. The **planner re-scores both axes authoritatively** on successful completion - the plan is the one point where true logic-load / surface-breadth (SIZE) and true path / impact (RISK) become known. The re-score lands *after planning and before challenge / tests*, so the challenge runs on the correct RISK band and tests re-gate on the correct SIZE.

- **Distinct from a KICKBACK.** The re-score is a *success-path* recalibration the planner emits as normal output; a KICKBACK is the *implementer* bouncing an unexecutable plan. Different stage, different trigger.
- **One asymmetry.** The `minimal + routine` corner skips the plan, so it has no re-score - triage's provisional call stands there until an implementer KICKBACK bites. Cheapest cell, bounded cost.

### 2.5 Review-wave lens membership

Standing lenses, keyed by dial:

| Lens | Keyed on | Fires when |
|---|---|---|
| CORRECTNESS | - | always (floor) |
| ACCEPTANCE | - | always (floor); stands down only when there is no confirmed intent |
| CONVENTIONS | size | `moderate`+ |
| SIMPLICITY | size | `moderate`+ |
| SHAPE | size | `substantial` only |
| worker | risk | `critical` only |

- **Floor = CORRECTNESS + ACCEPTANCE**, every cell: "is it right, and is it what was asked." ACCEPTANCE is the only spec gate in the `minimal + routine` skip-plan corner, so it earns always-on; it keeps its existing stand-down when there is genuinely no confirmed intent (a standalone `/crossfire`).
- **Size adds the structural lenses, staggered:** `moderate` adds CONVENTIONS + SIMPLICITY (is this nontrivial new code clean and in-style?); `substantial` adds SHAPE (the deep architecture lens - depth, seams, deletion test - that only earns its keep on a genuinely large new surface). Splitting SIMPLICITY from SHAPE turns their premature-abstraction overlap into graceful escalation rather than a redundant top-tier double-fire.
- **Risk's only review-wave lever is the worker, at `critical`.** No per-risk tier-bump on the always-on lenses - risk's teeth live on the challenge stage. So `elevated` adds nothing to the review wave; risk's review lever is binary while size's is ternary, coherent under separable dials.
- **Conditionals** (UI / SECURITY / PERFORMANCE) stay **surface-triggered**, fire orthogonally to both dials, and layer on top of whatever standing set the cell selects. No low band suppresses a trigger - that is what keeps a tiny-but-dangerous change from slipping past its security review. Because surface is what sets the risk band, SECURITY naturally co-fires with critical and UI / PERFORMANCE with elevated.

### 2.6 Uncertainty handling - routing, not rounding

"When uncertain, round up" is replaced by **uncertain → route**, scoped by *where* the uncertainty lives:

- **Request-level uncertainty** (the ask is fuzzy or has more than one serious reading, e.g. "make the export faster") → **HITL clarify**. This is the existing `unknowns` detour flag: triage does not silently guess a band, it surfaces.
- **Band-level uncertainty on a clear ask** (intent is crisp but the band is a genuine post-plan fact, e.g. "rate-limit the login endpoint, 5/min per IP" - moderate or substantial depends on whether middleware already exists) → **no interrupt**. It rides triage's provisional call and the planner re-score corrects it. Pinging the human for a band the planner sets authoritatively minutes later is the needless question without the payoff.

### 2.7 Worked interior cell - the tiny-but-dangerous case

*"Flip the session cookie to `SameSite=Strict`"* → **minimal × critical**: light plan (floored so the challenger has an artifact), no tests (no new logic), challenger + worker + human gate, minimal-size review wave + the worker lens (+ SECURITY by surface trigger). The dangerous one-liner earns a concise plan you approve and cross-model scrutiny, without paying for tests it has nothing to assert or structural lenses it has no surface for.

---

## 3. Escalation policy

Mid-run escalation is **escalation-only** and reuses the rails that already exist (implementer `KICKBACK: replan`, planner `DETOUR`). No new machinery.

### 3.1 Single writer

Only the **planner re-score** writes SIZE / RISK. Every other stage that needs the band raised does so by kicking back *into* a planner re-spawn - so a raised band always re-gates its dependents (tests, challenge, review depth) by construction, and "who may raise which axis" collapses to one rule instead of a per-stage grant matrix.

### 3.2 Escalation table

| Stage | Band action | Axis | How far |
|---|---|---|---|
| Triage | emits *provisional* | SIZE + RISK | initial gate-opener |
| **Planner re-score** | **writes** (authoritative) | both | jump to evidence-supported band |
| Challenger | none | - | existing `revise` / `reject` kickback to planner |
| Implementer | raises via `KICKBACK: replan` (supplies evidence; planner re-scores) | both | jump to evidence |
| Test stages | consume | - | - |
| Review wave | consume → **FIXER** | - | *one seam:* KICKBACK-to-planner on a suspected critical under-call (§3.4) |
| FIXER | consume | - | - |

### 3.3 Forward-only

The forward loop **raises** the band; the review tail **consumes** it. By the time the review wave runs, the band's gates are all behind it, so a reviewer's normal output is a finding → FIXER, never a replan. Escalation deepens every stage still *ahead* (review depth, ship HITL gate) but never rewinds to re-fire a gate that already passed.

- **How far up:** the re-score is authoritative, not incremental, so a raise jumps straight to the band the evidence supports (no one-band-per-raise throttle).
- **Loop safety** comes from **never-down** (the band is a ratchet) plus the existing **two-strike KICKBACK stop** ("same blocker twice → surface to the user"), not from rate-limiting the jump.
- **Honest cost, named.** A badly under-called RISK means the plan itself never got adversarially challenged - only its output got deep-reviewed. The deepened review wave is the backstop for everything except the one carve-out below.

### 3.4 Rewind exception - bounded, one trigger

Forward-only stays the rule. A single carve-out overrides the normal implementer behavior (`KICKBACK: replan` re-runs the implementer with **no** re-gate through the challenge):

- **Trigger:** RISK re-scores to `critical` **AND** the challenge was gated `none` (never ran) → the re-plan **re-fires the challenge** (challenger + worker + HITL gate). This is the *zero-adversary → critical* gap.
- **Why it clears asymmetric rigor:** (1) the challenge is a *design-time* adversary on the plan - reviewing finished code is not a substitute; (2) at critical the challenge tier carries the **HITL sign-off**, which the review wave never restores. Shipping a genuinely critical change that was never challenged is the costly-to-skip-wrongly case.
- **Not triggered** when the challenge already ran at challenger-only (`elevated → critical`): the plan already faced an adversary, and the deepened review wave + worker lens covers the increment.
- **Loop guard:** once per run - the re-fired challenge is thereafter a passed gate and cannot be rewound again. Combined with never-down and the two-strike KICKBACK guard, no loop.
- **Reachable from both** the implementer `KICKBACK: replan` and the review-wave seam; both funnel through the planner re-score, so single-writer holds.

---

## 4. Validation - by-hand dry-run table

The model is proved by running representative past requests through the dials by hand and confirming the stage-set that fires matches what each request deserves. There is **no shipped conformance tool** - a design validated once by its author earns a checklist, not tooling. This same table is the **downstream build's acceptance gate**: the doctrine edit is not done until the table still holds against the edited `TRIAGE.md` / `SKILL.md`. It is a one-time *design* test, never a per-request runtime step; at runtime triage still emits one classification, same cost as today.

**Anchor (the one falsifiable check):** `minimal + routine` fires exactly today's `trivial` short path, and `substantial + critical` fires exactly today's full pipeline. The seven interior cells are new, so they are judged sensible, not reproduced.

Stage-set legend: **Plan** {skip / light / full} · **Tests** {yes / no} · **Challenge** {none / challenger / challenger+worker+HITL} · **Wave** = standing lenses that fire (CORRECTNESS+ACCEPTANCE floor, + CONVENTIONS+SIMPLICITY at moderate+, + SHAPE at substantial, + worker at critical) plus any surface conditional.

| # | Past request (real forge work) | SIZE | RISK | Cell | Plan | Tests | Challenge | Wave | Note |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Add complexity/risk routing prior-art survey (`846aaa2`) | minimal | routine | min×rou | skip | no | none | CORRECTNESS + ACCEPTANCE | **Anchor:** reproduces today's trivial short path |
| 2 | Flip a user-facing README hero line / copy tweak | minimal | elevated | min×ele | light (floor) | no | challenger | floor + UI(trigger) | Concise plan so the challenger has an artifact |
| 3 | Flip the session cookie to `SameSite=Strict` (§2.7) | minimal | critical | min×cri | light (floor) | no | challenger+worker+HITL | floor + worker + SECURITY(trigger) | Tiny-but-dangerous; no tests, no structural lenses |
| 4 | Harden opencode install: config dir + skill shadow (`dd86deb`) | moderate | routine | mod×rou | light | yes | none | floor + CONVENTIONS + SIMPLICITY | Bounded install-script logic, reversible |
| 5 | Fix opencode plugin load + banner on ≥1.18 (`7f8da91`) | moderate | elevated | mod×ele | light | yes | challenger | floor + CONVENTIONS + SIMPLICITY | Enforcement-plugin bug; wrong is degraded, not dangerous |
| 6 | Fix codex enforcement hooks don't load (`2f7ab1c` / #61) | moderate | critical | mod×cri | light | yes | challenger+worker+HITL | floor + CONVENTIONS + SIMPLICITY + worker | Silent-enforcement-failure class earns the second opinion + gate |
| 7 | Merge the two test stages into one tests stage (`3a2f90e`) | moderate | routine | mod×rou | light | no | none | floor + CONVENTIONS + SIMPLICITY | Doctrine restructure, flat logic, internal |
| 8 | Restructure the repo into the decided shape (`c39ed6f` / #42) | substantial | routine | **sub×rou** | full | yes | none | floor + CONVENTIONS + SIMPLICITY + **SHAPE** | **The motivating gap:** big low-risk change now gets structural review |
| 9 | Make the worker second opinion vendor-relative (`c569fdb` / #65) | substantial | elevated | sub×ele | full | yes | challenger | floor + CONVENTIONS + SIMPLICITY + SHAPE | Multi-file contract change, no sensitive surface |
| 10 | Build the codex adapter (`2f7ab1c` / #45) | substantial | critical | sub×cri | full | yes | challenger+worker+HITL | floor + CONVENTIONS + SIMPLICITY + SHAPE + worker | **Anchor:** reproduces today's full pipeline (git-guard + Stop-gate = critical surface) |

**Coverage:** all three SIZE bands × all three RISK bands are hit (rows 1-10 touch 8 distinct cells including both anchors and the `substantial × routine` motivating gap). Rows 2 and 3 exercise the plan-floor coupling (§2.3); row 6 is the class the rewind exception (§3.4) protects when a request *arrives* looking routine and re-scores to critical.

**One documented refinement to the anchor.** Today's `trivial` short path runs CORRECTNESS + any triggered conditional. The new `minimal + routine` floor adds **ACCEPTANCE** (per §2.5, always-on wherever confirmed intent exists - and triage always writes `intent.md`). So the reproduction is *exact on pipeline shape* (skip plan, no challenge, no tests, minimal wave) and a deliberate **superset by one always-on spec-check lens**. This is intended: "is it what was asked" should not have been skippable on the short path. The build's acceptance gate treats this one-lens addition as expected, not as a reproduction failure.

---

## 5. Migration runbook

The spec hands off the cutover **shape**; carrying the edits is a downstream forge build.

### 5.1 The band mapping

- `trivial` → the corner `minimal + routine` (the reproduction anchor).
- `standard` → **nothing single.** The "not-trivial ⇒ fire everything" blob dissolves into active grid placement. Triage now scores SIZE + RISK instead of defaulting everything-not-trivial to the full path.

### 5.2 What breaks - three contained edit sites

1. **`skills/forge/TRIAGE.md`** - the return block: `SIZE: trivial | standard` → `SIZE: minimal | moderate | substantial` **plus a new `RISK: routine | elevated | critical` line**, and the sizing prose gains the RISK-signal reading (§1.3). `NEEDS-TESTS` survives almost unchanged - tests fire on the logic-load sub-signal, risk-independent.
2. **`skills/forge/SKILL.md`** - the gating: the "Trivial short path" block and the implicit `standard` = full-pipeline become the **separable dials** of §2 (size → plan + tests; risk → challenge + review depth; the §2.3 plan-floor coupling; the §2.5 size-keyed review-wave membership; the §2.4 planner re-score; the §3 escalation policy including the §3.4 rewind exception as a documented override of the "KICKBACK replan does not re-gate the challenge" line).
3. **`skills/forge/IMPLEMENTER.md`** - one clause: "On the trivial short path there is no plan" → "when no plan ran" (the skip-plan corner is now `minimal + routine`, not `trivial`).

### 5.3 Ordering and fallback

- **Atomic swap** of `TRIAGE.md` + `SKILL.md` together - they are coupled: triage cannot emit new bands while the skill still switches on `trivial | standard`. `IMPLEMENTER.md`'s one-clause edit rides the same change.
- **No compatibility shim.** House style bars backwards-compat scaffolding, and forge has zero external consumers.
- **The §4 dry-run table runs as the pre-merge gate.**
- **Safe-fallback semantics shift.** The blunt "when uncertain ⇒ `standard`" net is replaced by provisional placement + planner re-score, with a thumb on the scale for **RISK only**: doubt rounds RISK up (asymmetric rigor - a skipped challenge or gate costs the task), while SIZE rides the provisional call for the planner to re-score (an extra plan pass is cheap).

---

## 6. Public claims

**README does not move** as part of this spec. Public framing is already owned by the harness-agnostic claims work ([#47](https://github.com/alp82/forge/issues/47)).

- **"It can't skip the review"** survives intact: the wave scales, but CORRECTNESS + ACCEPTANCE are the always-on floor in every cell (§2.5), so review is never fully skipped and the enforcement promise stays literally true.
- **"challenge - a second agent tries to break the plan"** becomes conditional (none at `minimal + routine`), but the README stage table describes behavior-when-run, not universality - nothing becomes false, so it is left as-is.
- **Optional follow-up (out of this spec's scope):** advertising "process proportional to the change" as a *feature* is a separate post-implementation README edit, not a claim this spec forces.

---

## Appendix - the token contract

What triage emits, net (shape unchanged from today apart from the SIZE band values and the new RISK line):

```
INTENT: <one line>
SIZE: minimal | moderate | substantial
RISK: routine | elevated | critical
NEEDS-TESTS: yes | no
FLAGS:
- <flag> — <why>
(or "none")
```

Both bands are **provisional**; the authoritative call is the planner re-score (§2.4). Request-level uncertainty routes via the `unknowns` flag → clarify (§2.6), not a silent band bump.
