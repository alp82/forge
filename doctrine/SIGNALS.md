# Signal Taxonomy

The controlled vocabulary for the catalog. Stages wire together only through these
topics, so publishers and subscribers must draw from this list - that is what keeps a
composed route coherent. Topics are bare lowercase-kebab; a family takes a `:qualifier`.
`#` marks a signal in frontmatter (YAML-quoted) and in renders; storage is bare. `scope-shift` is mandatory on every stage and omitted from the tables.
New topics are added here first, then used.

## path  (published by `triage`, exactly one per turn, re-evaluated every turn)

| topic | meaning | subscribed by |
|---|---|---|
| talk | discussion, path parked; the main agent answers inline | discuss; recon on confirm |
| sketch | throwaway exploration in a sandbox - code tracer-bullets, diagrams, mockups, idea sketches | sketch-build; recon |
| code | make or change code (bug fixes included) | (path filter) |
| system | OS-level work: configs, troubleshooting, CLI tooling | system path |

## request / intent

| topic | meaning | published by | subscribed by |
|---|---|---|---|
| request-received | a new turn arrived | orchestrator seed | triage |
| ambiguous | request has unresolved readings | triage, clarify | clarify |
| reshape | user redirected intent | orchestrator | clarify |
| needs-interview | the ask is non-trivial (est-size above S, or absent) - interview before planning; a clear ask exits in one round with zero questions | triage | clarify |
| intent-confirmed | outcome locked, route through planning - on a clear `code` ask triage publishes this OR `direct-impl`, never both | triage, clarify | planner |
| direct-impl | trivial `code` change (single-file, `est-size <= S`, no new logic) - skip the plan, go straight to the implementer | triage | code-implementer |
| novel-domain | unfamiliar problem area | triage | research |
| bug | a defect to diagnose before fixing - pairs with `code` or `system`, never its own path | triage | code-investigator, system-investigator |
| needs-tests | a code change carrying real logic (`code` path only) - the TDD axis | triage, correctness-reviewer | test-plan, test-gap, test-verifier, the implementer's TDD lock (test-author joins via `#test-cases-ready`) |
| significant-build | a serious `code` build - full Review depth plus Scout (`code` path only) - the review-depth axis | triage, correctness-reviewer | reuse-scanner, health-checker, prototype-identifier, plan-challenger, the deep Review lenses (acceptance, shape, conventions) |

## shape / structure

| topic | meaning | published by | subscribed by |
|---|---|---|---|
| new-pattern | introduces a new pattern | plan | challenge, shape |
| new-export, new-seam | new public surface | plan, implement | shape |
| boundary-change | module boundaries move | implement | shape |
| naming-change, pattern-change | conventions shift | implement | conventions |
| ui-touched | the produced diff touches UI files | implement, fixer | accessibility, design-consistency, ux |
| perf-surface | the produced diff touches a perf-relevant surface - data access, loops over collections, queries, or payload assembly | implement, fixer | performance-reviewer |

## risk  (triggers safety lenses; publishers of these often pair with `guard: sticky` lenses)

| topic | meaning | published by | subscribed by |
|---|---|---|---|
| auth-surface | touches auth / identity / tokens | triage | security-review |
| secrets | secrets / credentials touched | triage | security-review |
| perms-change | permission model changes | triage | security-review |
| risk:&lt;area&gt; | generic risk in an area | triage | gates |
| high-risk | plan is risky overall | plan | challenge |
| destructive-op | a system action that is destructive or hard to reverse (`rm -rf`, package removal, `systemctl mask`, `dd`, partition ops) | triage, system-planner | safety-gate |
| irreversible | a system action with no clean rollback | triage, system-planner | safety-gate |

## discovery  (pre-code steering)

| topic | meaning | published by | subscribed by |
|---|---|---|---|
| existing:&lt;symbol&gt; | reusable code exists | reuse-scan | plan |
| duplication | new code duplicates existing | reuse-scan, conventions lens | plan, fixer |
| dead-code | removable code found | health-check | cleanup |
| missing-infra:&lt;x&gt; | needed infra absent | reuse-scan | research, prototype |
| unhealthy | touched area is low-health | health-check | orchestrator (cleanup-first recommendation) |
| domain:integration | a prototyping target is an external API / SDK / integration | prototype-identifier | code-prototyper |
| domain:data | a prototyping target is a schema / data model / transformation | prototype-identifier | data-prototyper |
| domain:performance | a prototyping target is timing / scale-critical | prototype-identifier | performance-prototyper |

## lifecycle  (the code path)

| topic | meaning | published by | subscribed by |
|---|---|---|---|
| reuse-done, health-checked | Scout complete | reuse-scan, health-check | plan |
| clarified | requirements clear | clarify | plan |
| design-needed | UI / design loop required | clarify | design-prototyper |
| design-locked | design spec captured | design-prototyper | plan |
| user-flow-needed | user-flow / state-sequence exploration required | clarify | ux-prototyper |
| ux-flow-locked | user-flow spec captured | ux-prototyper | plan |
| plan-ready | a plan artifact exists and is awaiting approval - arms the plan-gate lock on both implementers | code-planner, system-planner | code-implementer's plan-gate lock (while), system-executor's plan-gate lock (while) |
| plan-challenged | plan survived challenge | challenge | orchestrator |
| critiques-ready | every competing plan has been critiqued; the arbiter may now adjudicate (multi-plan code build only) | orchestrator | plan-arbiter |
| code-written | a diff exists | implement, fixer, system-executor | correctness-reviewer |
| milestone-diverged | the remaining milestone breakdown is wrong; re-split forward | code-implementer | plan-challenger |
| milestones-complete | the final milestone shipped; the orchestrator releases @diff and #code-written for the End Review wave | orchestrator | orchestrator |
| config-changed | a system change touched a tracked config file | system-executor | system-verifier |
| verified | the system reached its desired state | system-verifier | convergence |

## test  (TDD-first chain)

| topic | meaning | published by | subscribed by |
|---|---|---|---|
| test-cases-ready | cases derived from criteria | test-plan | test-author |
| tests-red | failing tests exist | test-author | test-review |
| tests-misaligned | tests don't match intent | test-review | test-author |
| tests-green | suite passes | test-verify | convergence |
| tests-missing:&lt;criterion&gt; | acceptance gap uncovered | test-gap lens | test-author |
| tests-ready | implementer lock released | test-review | implementer's lock |

The implementer carries two locks that AND together (see `WORKFLOW.md` > `## Locks`): the TDD
lock `{while:#needs-tests, until:#tests-ready}` and the plan-gate lock
`{while:#plan-ready, until:#plan-approved}`. On a logic code change `test-review` publishes
`#tests-ready` after validating the red tests, releasing the TDD lock - code cannot start
against unvalidated tests. On a planned build the plan-gate lock holds the implementer until
`#plan-approved` fires, so code never starts against an unapproved plan. On the `#direct-impl`
short path BOTH locks are inactive: a trivial change carries no `#needs-tests` (TDD lock
inactive) and no `#plan-ready` is ever live (plan-gate lock inactive by silence), so the
implementer runs straight off `@confirmed-intent` with no plan.

## findings  (Review)

| topic | meaning | published by | subscribed by |
|---|---|---|---|
| findings:&lt;lens&gt; | a lens found issues | the lens (correctness, simplicity, shape, conventions, acceptance, security, perf, a11y, ux, consistency - the last is design-consistency-reviewer's) | fixer |
| smell:&lt;area&gt; | a broad lens spotted an area to inspect | broad lens | matching specialist lens |
| findings:system | system verification found drift from the desired state | system-verifier | fixer, system-executor |
| clean | a lens found nothing | the lens | convergence |

## control  (gates + orchestration)

| topic | meaning | published by | subscribed by |
|---|---|---|---|
| est-size:&lt;tier&gt; | advisory upfront size estimate, read off the request shape | triage | orchestrator - small-planned-build auto-release only (WORKFLOW.md ## Locks, Release policy) |
| approved, scope-down, abandon | user gate verdict | gate stages | orchestrator |
| safety-approved | user cleared a destructive/irreversible system action | safety-gate | system-executor's lock |
| plan-approved | the plan cleared its approval gate, releasing both implementers' plan-gate lock | plan-challenger (code path, single-plan terminal gate); plan-arbiter (code path, multi-plan adjudication); orchestrator (system / small planned build, where no in-route stage publishes it) - never owed on the `#direct-impl` short path, which carries no plan gate | code-implementer's lock, system-executor's lock |

On a multi-plan code build the per-plan critique-only challengers do NOT publish `#plan-approved` - the arbiter does, on its Adopt verdict (see `doctrine/multi-plan.md`). `critiques-ready`, `competing-plans`, and `plan-critiques` are orchestrator-sourced (seeded into the route, see `doctrine/multi-plan.md` ## Seed rationale), so `plan-challenger` does NOT publish `critiques-ready`.

## diagnose  (investigator runs inside the `code` or `system` path via `bug`, not a separate route)

| topic | meaning | published by | subscribed by |
|---|---|---|---|
| root-cause-found | diagnosis complete | code-investigator, system-investigator | orchestrator (the fix continues) |
| cannot-diagnose, missing-info | blocked, needs input | code-investigator, system-investigator | orchestrator |

## Convergence

A route is **done** per `WORKFLOW.md` `## Convergence`: empty route, empty `held`, every lens `clean`.
There is no budget; an oscillation guard surfaces a `scope-shift` that re-fires without
ever resolving. See `doctrine/CATALOG.md` and the design note `project-river-dynamic-workflow`.
