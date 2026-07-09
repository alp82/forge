## Multi-plan adjudication

On a wide-design-space code build the orchestrator may run **several plans in parallel** - each
planner under a different lens - then have each plan challenged, then have `plan-arbiter` pick or
graft a winner. This doctrine is the detail home for that mode; `WORKFLOW.md` carries only the
cross-references.

## Arming rule

The orchestrator arms multi-plan if and only if `#significant-build` is live AND it judges the
design space wide - several materially different architectural approaches exist, not stylistic
variants. This is the same `#significant-build` gate the milestone loop arms on (`WORKFLOW.md`
## Milestone loop, Arming); multi-plan is a second, orthogonal choice the orchestrator makes off
that same live signal. A narrow design space runs the single-plan path - one planner, one
challenger in terminal mode - exactly as today. Multi-plan is never the default; wide design
space is the positive signal that arms it.

## Lens starter set

Each parallel planner runs under one lens - a named bias that shapes which trade-offs it favors
while every requirement stays intact. The starter set:

- **smallest-shippable** - the least code that fully satisfies the intent
- **risk-first** - the approach that minimizes blast radius and maximizes rollback safety
- **dead-simple** - the most obvious, lowest-abstraction structure
- **reuse-first** - the approach that leans hardest on proven existing code

The orchestrator picks **2-3 lenses** typically (more plans cost more without sharpening the
choice) and which lenses fit the task - a refactor leans reuse-first + dead-simple; a risky
migration leans risk-first + smallest-shippable.

## The lens injection mechanism

A lens rides in as a `<PLANNING_LENS>` slot in the planner's input (an optional `?planning-lens`
on `code-planner`). The orchestrator fills it per spawn, so each of the N parallel `code-planner`
spawns gets a different lens.

## Critique-only versus terminal challenger

`plan-challenger` runs in one of two modes, selected by an optional `?critique-only` input:

- **terminal mode** (single-plan path, no `<CRITIQUE_ONLY>`): the challenger emits its full
  output including the CHALLENGE_QUESTIONS picker, and Approve publishes `#plan-approved`. This is
  today's behavior, unchanged.
- **critique-only mode** (multi-plan path, `<CRITIQUE_ONLY>` set): the challenger emits
  BLOCKERS/CONCERNS/STRENGTHS but OMITS the picker and NEVER publishes `#plan-approved`. The
  arbiter owns approval, so no challenger preempts it. One critique-only challenger runs per competing plan.

### Construction invariant

On an armed multi-plan run, `plan-arbiter` MUST be the SOLE source of `#plan-approved` - otherwise
two publishers could race the gate - and the
orchestrator's fan-out step is the **named guarantor**: it spawns EVERY `plan-challenger` instance
WITH `<CRITIQUE_ONLY>` set. Because every challenger on that run is critique-only, no
terminal-mode challenger exists to publish `#plan-approved` - so the arbiter is the only publisher
that can fire it.

This invariant is **CONVENTION-enforced, not statically checkable**. In the catalog,
`plan-challenger` publishes `#plan-approved` unconditionally - critique-only mode and terminal mode
are the SAME catalog stage, distinguished only by the runtime `<CRITIQUE_ONLY>` input flag. No
static analysis (check_catalog, the router) can tell the two modes apart at catalog-read time, so
nothing in the toolchain enforces this invariant automatically. The orchestrator's fan-out
discipline is the SOLE guarantor: the agent's prose (## Critique-only mode) states the behavior,
and the orchestrator MUST honor it by setting `<CRITIQUE_ONLY>` on every multi-plan challenger
spawn, since no static check catches a missed flag. This differs from the `WORKFLOW.md` ## Milestone loop "Construction invariant", where the
dead state (double `#milestones-complete`) IS statically checkable via signal subscriptions in the
catalog - that parallel does not hold here.

### Atomic co-publish contract

The orchestrator publishes `#critiques-ready` AND seeds `@competing-plans` + `@plan-critiques`
into `available` in ONE atomic recompose - it is **HARD REQUIRED** (same emphasis as the milestone
loop's "MUST add `@diff` to available") that the trigger never fires before its batch is
available, because the arbiter subscribes `#critiques-ready` and requires both artifacts -
emitting the trigger early would compose it with no inputs and immediately drop it as
unsatisfiable. So the three values - `critiques-ready`, `competing-plans`, and
`plan-critiques` - co-occur in one recompose, never split across turns. This recompose happens
after the per-plan critique phase completes: every critique-only challenger has returned before
the arbiter is triggered.

## Seed rationale

`#critiques-ready`, `@competing-plans`, and `@plan-critiques` are entered into `check_catalog`'s
seed sets (SEED_SIGNALS / SEED_ARTIFACTS) on the EXISTING grounds the seed model already names:
**values that enter a route from outside any stage; the orchestrator seeds these** - the same
basis as `request-received` and `reshape`. The arbiter declares them as required inputs and
subscribes the trigger, but no in-catalog stage produces them - the orchestrator does, in the
atomic co-publish above. The orchestrator seeds these rather than declaring a phantom producer
stage because they are an orchestration act (fan out planners, fan out critique-only challengers,
gather the batch), not a single agent's output. Modeling a fake producer stage would put a stage
in the catalog that never runs as a normal route member; seeding matches how every other
orchestrator-sourced value enters (the request seed, the gate decisions).

This arbiter is the FIRST stage to declare **orchestrator-sourced** values as seeds. It is a new
precedent: until now the seeds were the request seed, user/gate decisions, and the `/alp-river:adr`
command. It is NOT modeled on `#milestones-complete` - that orchestrator-emitted signal is in
neither seed list (no stage subscribes it as a required trigger or requires it as input, so it
never needed a seed entry). The arbiter's inputs do need seed entries because the arbiter
subscribes and requires them, and the seed grounds are the orchestrator-source basis, stated above.

## Selector, not critic

The arbiter is a **selector**, not a second critic. The critiques already ran in the per-plan
critique-only phase; the arbiter weighs them, it does not redo them. It adds no new requirements
and does not re-plan - it steelmans each plan, finds complementary strengths, and picks or grafts.
This keeps the adjudication cheap and bounded: one read-and-decide pass over work already done,
not a fresh review wave.

## Verdicts and tie-break ordering

The arbiter emits one of three verdicts: **Adopt** publishes `#plan-approved` and ships the
selected plan to the implementer. **Hybrid** and **Revise-first** are backward edges via the
Revision Contract (`WORKFLOW.md` ## Revision Contract) - neither publishes `#plan-approved`
directly; the revised or grafted plan must re-earn approval through its gate.

For the full tie-break ordering and the complete per-verdict output contract, see
`agents/plan-arbiter.md` ## Tie-break ordering and ## Output (strict).
