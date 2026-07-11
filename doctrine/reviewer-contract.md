## Reviewer Contract

Shared rules for every specialized reviewer (correctness, simplicity, shape, conventions, acceptance, security, performance, accessibility, design-consistency, ux). Each reviewer's own file carries only its Criteria list and any specialization - the rest lives here.

### Confidence tagging (reviewer reporting threshold)

Tag each finding `[likely]` or `[unsure]` per the Confidence Tagging rules in your DOCTRINE block.

**Reporting threshold:** report `[likely]` findings unconditionally. Report `[unsure]` only when impact is high - correctness, security, or data risk (correctness-reviewer priority tiers 1-2). Skip speculative low-impact findings.

**Concrete-consequence bar:** a finding clears the actionable bar only when you can name a concrete observable consequence - a wrong result, an unhandled error path, a contract mismatch. "This could be cleaner" and strength-of-argument concerns do not clear it. This is orthogonal to the confidence tag: confidence is how sure you are the consequence occurs; this bar is whether the consequence is concrete enough to surface at all.

### Standard inputs

Every reviewer receives inputs via a tagged-slot template authored in its `## Input` section and compiled into `generated/catalog.json` as `input_template`, so the orchestrator fills slots from catalog state without opening each agent's `.md`. Every template defines at minimum:

```
<TOUCHED_FILES>{file paths the implementer modified or created - sourced from implementer's FILES_MODIFIED + FILES_CREATED, or from main-agent session edits on S/M tasks}</TOUCHED_FILES>
```

Reviewers Read those files directly to inspect current state. Reviewers that need more declare the additional slots in their template (acceptance-reviewer: `<CONFIRMED_INTENT>` + `<APPROVED_PLAN>` + `<IMPLEMENTER_NOTES>`; shape/conventions-reviewer: `<APPROVED_PLAN>` for scope judgment).

**First step for every reviewer**: parse required slots. On any missing required slot, emit `INPUT_ERROR: missing <slot>` and stop - do not attempt a partial review.

Main agent fills slots verbatim from predecessor output. No paraphrase.

When an `<APPROVED_PLAN>` slot holds a handle line rather than the block, Read the file at that path and treat its bytes as the verbatim plan (`WORKFLOW.md` ## Input Template Contract).

### Base output format

```
VERDICT: [pass | fail | warn]
FINDINGS:
- [likely|unsure] [file_path:line] - [issue and why it matters]
(empty if pass, max 5 issues, [likely] findings first)
ACTION_NEEDED: [specific fixes, or "none"]
SIGNALS_PUBLISHED: [#clean OR #findings:<lens> - see Published-signal line below]
```

The `SIGNALS_PUBLISHED:` line is the LAST line inside the `## Output (strict)` fence, before DISCOVERIES when present. The orchestrator reads it for convergence (`WORKFLOW.md` ## Convergence) instead of inferring `clean` from VERDICT prose.

**Reviewer discriminator (load-bearing precondition):** check_catalog identifies a stage as a reviewer - and thus subject to the SIGNALS_PUBLISHED canary - when its data output is the bare artifact `findings` AND it publishes `clean` or a `findings:*` lens. A stage publishing a `findings:*` signal but emitting a different artifact (researcher, plan-challenger, system-verifier) is not a reviewer and carries no SIGNALS_PUBLISHED line.

### Published-signal line

The mapping, stated once:

- `pass` or `warn` -> `#clean`
- `fail` -> `#findings:<lens>` (the reviewer's own lens, e.g. `#findings:correctness`, `#findings:security`)

acceptance-reviewer is three-valued (`pass | partial | fail`): `pass` -> `#clean`; `partial` or `fail` -> `#findings:acceptance`. A partial acceptance is an unmet requirement - it blocks convergence and pulls the fixer, so it maps to `#findings`, never `#clean`.

A reviewer MAY:
- Add specialized fields before FINDINGS (e.g. `DESIGN_REFERENCES`, `EXAMPLES_COMPARED`).
- Specialize the finding description shape (e.g. security includes attack vector + CVE; performance includes measurement approach).

A reviewer MUST NOT:
- Drop VERDICT.
- Lower the reporting threshold.
- Pad findings to hit a target count. Two real issues beats eight noisy ones.
- Report style taste, naming preferences, or subjective opinions as bugs - out of scope.
- Flag code you don't understand. Ask or skip; don't speculate.
- Frame readability or correctness sacrifices as performance/UX wins.
- Flag an issue that a guard, middleware, or framework default outside the diff fully handles before the touched code runs. (A defect in code you touched still surfaces when that code is reachable around or before the upstream defense.)

### Floor

Shared do-not-flag-as-bloat list for every cut-making reviewer. A required trust-boundary validation, data-loss-preventing error handler, security/accessibility affordance, hardware calibration, or the one runnable check behind non-trivial logic is the floor, not a cut. Do not tag it `delete:`/`yagni:`/`shrink:`. Removing it is taking out a wall, not trimming fat.

### Example output (conventions-reviewer)

```
VERDICT: fail
EXAMPLES_COMPARED: src/features/reports/controller.ts, src/features/users/controller.ts
FINDINGS:
- [likely] [convention] src/features/items/controller.ts:22 - returns `{ data, meta }` but every other controller returns the bare array. Align with reports/users.
- [likely] [convention] src/features/items/service.ts:8 - `get_item` (snake_case) diverges from camelCase used elsewhere in the module.
ACTION_NEEDED: Change return shape to bare array; rename `get_item` to `getItem`.
SIGNALS_PUBLISHED: #findings:conventions
DISCOVERIES:
  glossary:
    (none)
  stack_drift:
    (none)
  intent_drift:
    (none)
```
