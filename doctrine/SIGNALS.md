# Signal Taxonomy

The controlled vocabulary for the catalog. Stages wire together only through these
topics, so publishers and subscribers must draw from this list - that is what keeps a
composed route coherent. Topics are bare lowercase-kebab; a family takes a `:qualifier`.
`#` marks a signal in frontmatter (YAML-quoted) and in renders; storage is bare. `scope-shift` is mandatory on every stage and omitted from the tables.
New topics are added here first, then used.

## path  (published by `triage`, exactly one per turn, re-evaluated every turn)

| topic | meaning | subscribed by |
|---|---|---|
| build | make or change something (bug fixes included) | reuse-scanner, health-checker, ... |
| spike | throwaway exploration in a sandbox | spike-build (relaxed) |
| talk | discussion, build spine parked | discuss; recon stages on demand |

## request / intent

| topic | meaning | published by | subscribed by |
|---|---|---|---|
| request-received | a new turn arrived | orchestrator seed | triage |
| ambiguous | request has unresolved readings | triage, clarify | intent, clarify |
| reshape | user redirected intent | orchestrator | intent |
| intent-confirmed | outcome locked | intent | plan, classify-less downstream |
| novel-domain | unfamiliar problem area | triage | research |
| bug | a defect to diagnose before fixing - paired with `build`, never its own path | triage | investigator |

## shape / structure

| topic | meaning | published by | subscribed by |
|---|---|---|---|
| multi-file | spans several files | triage, clarify | plan |
| design-decision | a design choice to record as an ADR | /alp-river:adr command (external seed) | adr-drafter |
| new-pattern | introduces a new pattern | plan | challenge, architecture |
| new-export, new-seam | new public surface | plan, implement | architecture |
| boundary-change | module boundaries move | implement | structure |
| naming-change, pattern-change | conventions shift | implement | consistency |

## risk  (triggers safety lenses; publishers of these often pair with `guard: sticky` lenses)

| topic | meaning | published by | subscribed by |
|---|---|---|---|
| auth-surface | touches auth / identity / tokens | triage | security-review |
| secrets | secrets / credentials touched | triage | security-review |
| perms-change | permission model changes | triage | security-review |
| risk:&lt;area&gt; | generic risk in an area | triage | cost-check, gates |
| high-risk | plan is risky overall | plan | challenge |

## discovery  (pre-build steering)

| topic | meaning | published by | subscribed by |
|---|---|---|---|
| existing:&lt;symbol&gt; | reusable code exists | reuse-scan | plan |
| duplication | new code duplicates existing | reuse-scan, reuse lens | plan, fixer |
| dead-code | removable code found | health-check | cleanup |
| missing-infra:&lt;x&gt; | needed infra absent | reuse-scan | research, prototype |
| unhealthy | touched area is low-health | health-check | cleanup gate |
| novel:high | high-novelty external surface | prototype-identifier | prototype |
| alternative-shapes | competing approaches exist | prototype-identifier | plan |

## lifecycle  (the build spine)

| topic | meaning | published by | subscribed by |
|---|---|---|---|
| reuse-done, health-checked | pre-flight complete | reuse-scan, health-check | plan |
| clarified | requirements clear | clarify | plan |
| design-needed | UI / design loop required | clarify | design-loop |
| design-locked | design spec captured | design-loop | plan |
| plan-ready | approved plan exists | plan | implement, challenge |
| plan-challenged | plan survived challenge | challenge | after-plan gate |
| code-written | a diff exists | implement, fixer | lenses, test-verify |
| code-changed:&lt;area&gt; | a fix touched &lt;area&gt; | fixer | area lenses (precise re-review) |

## test  (TDD-first chain)

| topic | meaning | published by | subscribed by |
|---|---|---|---|
| test-cases-ready | cases derived from criteria | test-plan | test-author |
| tests-red | failing tests exist | test-author | test-review |
| tests-misaligned | tests don't match intent | test-review | test-author |
| tests-green | suite passes | test-verify | convergence |
| tests-missing:&lt;criterion&gt; | acceptance gap uncovered | test-gap lens | test-author |

Validated red tests are the artifact `validated-tests` (published by `test-review`);
`implement` lists it under `data.input`, so the order graph forbids code before tests.

## findings  (review lenses)

| topic | meaning | published by | subscribed by |
|---|---|---|---|
| findings:&lt;lens&gt; | a lens found issues | the lens (correctness, quality, security, perf, a11y, structure, architecture, reuse, consistency, ux, adherence, acceptance) | fixer |
| smell:&lt;area&gt; | a broad lens spotted an area to inspect | broad lens | matching specialist lens |
| clean | a lens found nothing | the lens | convergence |

## control  (gates + orchestration)

| topic | meaning | published by | subscribed by |
|---|---|---|---|
| est-size:&lt;tier&gt; | advisory upfront size estimate, read off the request shape | triage | cost gate (advisory only - never picks stages) |
| size-crossed:&lt;tier&gt; | route grew past a tier line | router | cost-check |
| approved, scope-down, abandon | user gate verdict | gate stages | orchestrator |
| cleanup-first | health gate decision | health gate | orchestrator |
| run-visual | user opted into a visual check | gate | visual-verify |

## diagnose  (investigator runs inside the `build` path via `bug`, not a separate route)

| topic | meaning | published by | subscribed by |
|---|---|---|---|
| root-cause-found | diagnosis complete | investigator | orchestrator (build continues to the fix) |
| cannot-diagnose, missing-info | blocked, needs input | investigator | orchestrator |

## Convergence

A route is **done** when no live signal triggers an unrun stage and every lens is `clean`.
There is no budget; an oscillation guard surfaces a `scope-shift` that re-fires without
ever resolving. See `doctrine/CATALOG.md` and the design note `project-river-dynamic-workflow`.
