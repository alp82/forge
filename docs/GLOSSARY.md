# Glossary

Canonical terms for this project. Agents read this to avoid renaming the same concept three different ways across files.

## Core model

### Stage
**Definition:** A composable unit of the workflow, declared by a `stage:` block in an agent's frontmatter (`data.input/output` artifacts, `signals.subscribes/publishes` topics, optional `guard`). The router composes a route from stages.
**Avoid:** "step", "phase" (the old fixed-pipeline units, retired).

### Route
**Definition:** The ordered set of stages the deterministic router assembles for one task, recomposed as signals arrive. Order comes from artifact dependencies; membership from live signals.
**Avoid:** "pipeline" for the per-task instance (the pipeline is the whole system; a route is one task's path).

### Catalog
**Definition:** `generated/catalog.json`, compiled by `hooks/gen-catalog.py` from every agent's `stage:` frontmatter. The router's input. See `doctrine/CATALOG.md`.
**Avoid:** "registry", "manifest".

### Signal
**Definition:** A pub/sub topic. A stage `subscribes` to signals (any one triggers it, OR) and `publishes` signals (facts it emits, each with a free-form message). Bare in storage, rendered with `#`. See `doctrine/SIGNALS.md`.
**Avoid:** "event", "flag" (a signal is the topic; "triggers" is what a live one does to a stage).

### Artifact
**Definition:** A data input/output of a stage (`data.input` / `data.output`). Artifacts form the precedence DAG that orders the route. Rendered with `@`.
**Avoid:** "output", "result" (too generic).

### Size readout
**Definition:** XS / S / M / L / XL / XXL, derived from the *count* of stages in the composed route. A readout, never a driver - it does not pick stages.
**Avoid:** "complexity tier", "grade" (the old driver framing, retired). Bare "tier" collides with model tier.

### Path
**Definition:** `code`, `sketch`, `talk`, or `system` - published by `triage`, exactly one per turn, re-evaluated each turn. Shapes the route: talk parks the path (the `discuss` stage converses), sketch relaxes rigor, code runs the full composition. A bug is `code` plus a `bug` signal, not a separate path.
**Avoid:** "route type", "execution mode", "TYPE_BIAS" (retired); "diagnose" as a path (folded into code).

### Routes
**Definition:** The mandatory per-stage frontmatter list of paths (`code`/`sketch`/`talk`/`system`) a stage may run on. The router drops a triggered stage whose `routes` exclude the live path; multi-path is normal (`correctness-reviewer: [code, sketch]`).
**Avoid:** "route" singular (that is the composed per-task instance).

### Convergence
**Definition:** A route is done when the router triggers no unrun stage and every Review lens that ran is `clean`. Replaces the old backward-edge budget - there is no edge count.
**Avoid:** "completion", "budget".

### Oscillation guard
**Definition:** The only loop guard under convergence: a `scope-shift` that re-fires without resolving is surfaced to the user instead of retried silently.
**Avoid:** "retry limit", "budget".

### Scope-shift
**Definition:** A signal every stage may publish when its work breaks a premise the route was built on. The orchestrator aggregates these and recomposes.
**Avoid:** "rescope", "pivot".

### Sticky guard
**Definition:** `guard: sticky` on a safety stage (e.g. security-review): once triggered it is never auto-dropped, even if its signal goes quiet.
**Avoid:** "pinned", "locked".

### Lens
**Definition:** A review stage of the parameterized review family - same `@diff -> @findings` shape, differing only in which signal triggers it (broad lenses subscribe `code-written`; specialists subscribe a domain or `smell:<area>` signal).
**Avoid:** "broad pass", "specialist pass" (old step names), "review round".

### Gate
**Definition:** A stage whose published output is a user decision, rendered via `AskUserQuestion`. Fires only when triggered AND the answer could change the outcome.
**Avoid:** "checkpoint", "Gate 1", "XXL pushback" (retired named gates).

### Build gate
**Definition:** The finish-line check (`hooks/verify-build.py`) that runs the project's real build or type-check when Claude tries to finish, blocking on a broken build so a compile error in a file no test imports cannot slip through. Twin of the **test gate** (`hooks/verify-tests.py`). Both fire on the Stop event, run in parallel, fall back to a silent pass when their tool is absent, and cap at one retry per session.
**Avoid:** confusing with **Gate** (a workflow stage whose output is a user decision) - the build and test gates are Stop hooks, not stages.

### Triage
**Definition:** The always-on seed stage. Reads the request, publishes the path and opening signals (`ambiguous`, `bug`, risk sniffs, an advisory `est-size`); the router composes from there.
**Avoid:** "classifier" (retired), "router" (triage seeds, the router composes).

### Lock
**Definition:** A `{while, until}` signal gate on a stage. The stage is held out of the dispatch route while `while` is live and `until` is unpublished; it rejoins once `until` fires. Multiple locks AND together. The `code-implementer` carries two locks: the TDD gate `{#needs-tests -> #tests-ready}` and the plan-approval gate `{#plan-ready -> #plan-approved}`; the `system-executor` likewise pairs its safety gate `{#destructive-op -> #safety-approved}` with the same plan-approval gate. A scheduling gate, not a data input. See WORKFLOW.md > Locks.
**Avoid:** "green-light", "gate artifact".

### Trivial
**Definition:** A code change with no new logic - docs, config, version, copy, formatting, or dependency edits - that is also single-file and `est-size` S or smaller. Published by `triage` as the explicit `direct-impl` marker; routes the short path straight to the implementer, then a correctness check, skipping the planner and the test chain. Both of the implementer's locks are inactive, so it runs straight off the confirmed intent with no plan (see `WORKFLOW.md` > `## Locks`).
**Avoid:** "small", "simple".

### Needs-tests
**Definition:** The TDD axis. A code change carrying real logic - any new or changed branch, loop, or computation. Published by `triage` (and late by `correctness-reviewer`); pulls only the TDD chain (test-plan, test-gap, test-verifier) and arms the implementer's TDD lock. Independent of the review-depth axis (`significant-build`).
**Avoid:** "complex", conflating it with `significant-build` (review depth).

### Significant-build
**Definition:** The review-depth axis. A serious code build - multi-file, `est-size` L or larger, a large single-file rewrite, or a novel domain. Published by `triage` (and late by `correctness-reviewer`); pulls Scout (reuse-scanner, health-checker, prototype-identifier), the plan-challenger, and the deep Review lenses. `code`-only and independent of `needs-tests` - a build can carry logic without being big, and vice versa. The system path always confirms, so it carries none.
**Avoid:** "complex", conflating it with `needs-tests` (the TDD axis).

### Plan-approved
**Definition:** The signal that releases both implementers' plan-approval lock. Published by `plan-challenger` on Approve (the `code` path); on the system and small planned-build paths the orchestrator emits it as a hard required step - a one-tap confirm before execution, auto-released on a small planned build touching `<=1` file at `est-size <= S`. The `direct-impl` short path has no plan gate, so `plan-approved` is never owed there (see `WORKFLOW.md` > `## Locks`).
**Avoid:** "green-light", "approved" (that is the generic gate verdict).

### Self-heal
**Definition:** The `fixer`-driven repair cycle that reruns the lenses whose findings it addressed, until they come back `clean`. A signal cycle (`code-written` re-published), bounded by the oscillation guard.
**Avoid:** "auto-fix", "retry loop".

### Milestone loop / Milestone
**Definition:** A `#significant-build` decomposed into independently-verifiable slices (milestones), executed and reviewed one increment at a time rather than in a single pass. A milestone is one such slice; the milestone loop is the per-milestone execute-then-review cadence the orchestrator runs, engaged only while `#significant-build` is live.
**Avoid:** "increment", "chunk", "phase".

### milestone-scope
**Definition:** The optional `stage:` frontmatter field marking which review lenses run in the per-milestone EARLY pass: `local` (runs only on each milestone's diff slice) or `both` (runs in the EARLY pass and again in the End Review wave, e.g. `test-verifier`). Untagged is the default - the lens runs only in the End Review wave.
**Avoid:** "review-scope", "milestone-tag".

### EARLY pass
**Definition:** The per-milestone review fired at each milestone boundary (N>1 builds only): only the `milestone-scope`-tagged lenses (correctness, surface-gated security, structure, test-verifier smoke) over that milestone's diff slice. Distinct from the End Review wave - the full global lens set firing once over the whole `@diff` after the final milestone.
**Avoid:** "early review", conflating it with the End Review wave.

### #milestone-diverged
**Definition:** The signal `code-implementer` publishes mid-loop when implementing a milestone reveals the remaining breakdown is wrong. It triggers `plan-challenger` to re-split the remaining milestones (k+1..N) forward-only, never re-gating the shipped ones (1..k).
**Avoid:** "replan"; not "scope-shift" (which breaks a route premise - this re-splits remaining milestones).

### Colored milestone render
**Definition:** The milestone-status layer the render card adds during a milestone build: one line per milestone showing its state, atop the per-stage markers. See `doctrine/render-card.md` for the marker glosses.
**Avoid:** "progress bar", "status colors".

### Card grammar
**Definition:** The one shared vocabulary every render-card surface speaks - the markers, the layout rules, and the fixed phase-banner order - so a rendered list never implies an order the route does not run. See `doctrine/render-card.md`.
**Avoid:** "render format", "card layout".

### plan-arbiter
**Definition:** The read-only stage that cross-reviews N competing personality-driven plans against intent and the codebase and decides Adopt / Hybrid / Revise-first. Distinct from plan-challenger, which renders an Approve/Revise verdict on a single plan.
**Avoid:** confusing with plan-challenger (single-plan Approve/Revise verdict).

### multi-plan mode
**Definition:** The gated, orchestrator-decided fan-out that spins up N distinct personality-lens planners. Distinct from code-planner's former single-planner A/B/C APPROACHES (now removed).
**Avoid:** "A/B/C approaches" (the retired single-planner framing).

## Surfacing

### Concise Surfacing Contract
**Definition:** The rule that multi-option user choices go through `AskUserQuestion`, not free-text prompts. See WORKFLOW.md.
**Avoid:** "user prompt", "question contract".

### 4-question cap
**Definition:** At most four questions per `AskUserQuestion` turn; overflow goes to `DEFERRED_QUESTIONS`.
**Avoid:** "question limit".

### DEFERRED_QUESTIONS
**Definition:** The queue of picker-eligible items beyond the 4-question cap, threaded forward into later rounds.
**Avoid:** "backlog", "pending".

### Confidence tagging
**Definition:** The `[likely]` / `[unsure]` markers subagents append to claims they can't ground in evidence.
**Avoid:** "uncertainty markers", "hedging".

### Run-timing readout
**Definition:** The one-time card the orchestrator renders at convergence showing a run's total wall-clock time and a per-phase (and per-milestone, when the milestone loop ran) breakdown. See `doctrine/render-card.md`.
**Avoid:** "timer", "profiler", "stopwatch".

## Context injection

### Context injection slots
**Definition:** Auto-injected payloads the PreToolUse(Agent) hook (`hooks/user-context-injector.sh`) prepends to subagent prompts: `USER_CONTEXT` (slice of `MEMORY.md` plus linked files), `PROJECT_CONTEXT` (slice of `docs/` - intent, stack, glossary, ADRs), and `PSYCHOLOGY` (persona per `psychology/agent-map.json`).
**Avoid:** "context" alone (overloaded with LLM context window).

### Doctrine slice
**Definition:** A standalone markdown file under `doctrine/` holding one shared-rule section (reviewer-contract, code-doctrine, catalog, signals, ...), injected per-agent by the PreToolUse(Agent) hook into agents whose definition cites it.
**Avoid:** "include", "partial".

### DOCTRINE_MAP
**Definition:** The bash associative array in `hooks/user-context-injector.sh` mapping each agent to the doctrine slice tokens it receives. An agent appears only if its definition cites that doctrine (cite=receive).
**Avoid:** "config map".

### Psychology
**Definition:** Opt-in persona block injected via `psychology/agent-map.json` that shapes a subagent's voice.
**Avoid:** "personality", "prompt prefix".

### ADR
**Definition:** Architectural decision record produced by the `adr-drafter` stage and stored under `docs/adr/`.
**Avoid:** "decision doc", "design doc".

### Prototyper family

**Definition:** The named set code-/data-/performance-/design-/ux-prototyper, each owning a distinct pre-plan validation domain with its own trigger and outcome.

**Avoid:** _TODO:_ aliases to avoid (review and fill)

### effort

**Definition:** Official Claude Code subagent frontmatter field that sets a per-agent thinking budget independent of `model`. Values: low/medium/high/xhigh/max, with precedence env > invocation > frontmatter > parent. Model-gated (Haiku does not honor it; unsupported levels fall back silently). This repo uses medium/high/max, tuned per agent job-type, and leaves the haiku classification stages without an `effort` line.

**Avoid:** _TODO:_ aliases to avoid (review and fill)

## Self-audit and memory

### Self-audit

**Definition:** The deterministic plugin health check run by `/alp-river:audit` via `hooks/audit.py`: a pure function of repo facts (catalog stages, doctrine files, registered hooks) that scores eight fixed categories and emits a 0-100 scorecard plus a machine JSON block (a `SCORECARD_JSON ` prefixed line). Stdlib-only, fail-open, always exits 0; the same repo state always yields the same scorecard. Scoring lives entirely in the hook; the command only runs and renders it.

**Avoid:** "lint", "quality check" (overloaded); confusing with the build/test gates (Stop hooks).

### Health categories

**Definition:** The eight fixed scoring axes of the self-audit: `tool/agent coverage`, `context efficiency`, `quality gates`, `memory persistence`, `security guardrails`, `doctrine integrity`, `doctrine hygiene`, `why-anchor coverage`. Each yields an int score and a list of concrete fix actions; `top_fixes` orders worst-category-first with alphabetical tie-break.

**Avoid:** "audit sections", "metrics".

### Drift canary (doctrine-integrity check)

**Definition:** The `doctrine integrity` `/audit` category (`hooks/audit.py`, `DOCTRINE_PHRASES` + `_score_doctrine_integrity`): a presence-allowlist asserting each pinned load-bearing doctrine phrase still appears verbatim in its required file. All-or-nothing (100 or 0) and fail-open. Catches deletion of a pinned phrase, not a one-sided reword.

**Avoid:** "doctrine lint", "phrase check".

### Doctrine hygiene (audit lens)

**Definition:** The graduated `/audit` lens (`hooks/audit.py`, `_score_doctrine_hygiene`) that flags a prose instruction line duplicated verbatim across two different `agents/`/`doctrine/` files (after normalization, excluding frontmatter, fenced templates, and explicit `See doctrine/...` cross-references). Score is the fraction of checked instruction lines not duplicated; offenders name the line and both files. Fail-open - an unreadable file counts conservatively as a failing item. Enforces the CLAUDE.md doctrine-hygiene rule: one fact, one home.

**Avoid:** "dedup check", "duplicate finder".

### Why-anchor coverage (audit lens)

**Definition:** The graduated `/audit` lens (`hooks/audit.py`, `_score_why_anchor`) that scores the fraction of load-bearing directive lines (carrying an all-caps `MUST`/`NEVER`/`ALWAYS`/`REQUIRED`/`HARD` marker) in `agents/`/`doctrine/` that are anchored to a rationale - a `because`/`so that`/`to avoid`/... marker on the directive's own line or the line that continues it. Offenders name the unanchored directives (file:line + text). Fail-open.

**Avoid:** "rationale lint", "comment check".

### Memory audit (reflect step)

**Definition:** The `/alp-river:reflect` memory-audit step that runs by default as part of /reflect, reviewing MEMORY.md and linked topic files against `doctrine/MEMORY-CONVENTIONS.md`, classifying each memory Keep / Improve / Retire / Merge. Runs as a two-phase write (PROPOSAL -> per-item approval -> WRITE) executed by the main agent directly, never a capture-agent spawn. Where pending-fact expiry, over-long index lines, and overlap are reconciled operationally.

**Avoid:** "memory cleanup", "garbage collection".

### Capture (reflect step)

**Definition:** The `/alp-river:reflect` step that persists a session-surfaced pattern to memory after dedup by semantic equivalence against MEMORY.md and its topic files; surviving captures are tagged absorb-into-existing vs create-new. Two-phase write, main-agent-direct. Distinct from capture-agent, which writes `docs/` only and never memory.

**Avoid:** confusing with capture-agent (the `docs/`-only project-context harvester).

### Memory frontmatter

**Definition:** The optional per-fact keys a Claude Code memory may carry: `status: pending` (provisional, absence means durable), `expires: YYYY-MM-DD` (lapse date for a pending fact, enforced at memory-audit time, not at load - no hook reads it), `priority: high|normal|low` (retention weight under memory pressure, absence means normal).

**Avoid:** "metadata", "tags".

### One-line index entry

**Definition:** The memory convention that each line in MEMORY.md's index stays a single short line (under ~150-200 chars), with detail pushed to the linked topic file. Mirrors the native load contract: the platform loads the index eagerly and topic files on demand, so a bloated index line spends load budget owed to the topic file.

**Avoid:** "summary line", "memory entry".

## Review doctrine

### Simplicity review

**Definition:** The simplicity/YAGNI lens in `agents/simplicity-reviewer.md` that fires on planned code builds (it subscribes `#plan-ready`); the trivial short path takes correctness only. It walks the YAGNI ladder - does-it-need-to-exist -> stdlib -> native platform feature -> already-installed dependency -> one line -> the minimum that works - stopping at the first rung that holds (a rung higher than necessary is the cut). It scores each cut and ends with `net: -N lines possible` or `Lean already. Ship.` Fires once at End Review over the cumulative diff, not per milestone; milestone-scope ownership is intentionally outside its charter.

**Avoid:** "simplification pass", "dead-code scan".

### Deletion tag

**Definition:** One of `delete:` / `stdlib:` / `native:` / `yagni:` / `shrink:`, attached by simplicity-reviewer to each proposed cut, each naming the replacement. Defined in `doctrine/reviewer-contract.md`.

**Avoid:** "cut marker", "removal label".

### Floor (never simplify away)

**Definition:** The hard stop on the lean-toward bias: required trust-boundary input validation, data-loss-preventing error handling, security, accessibility, hardware calibration, and the one runnable check behind non-trivial logic are load-bearing, not bloat. A reviewer never tags these `delete:` / `yagni:` / `shrink:`. Defined in `doctrine/code-doctrine.md` and echoed in `doctrine/reviewer-contract.md`.

**Avoid:** "essential code", "non-negotiables".

## Build evidence

### Evidence receipt

**Definition:** The `EVIDENCE_RECEIPT:` block `code-implementer` appends to its output contract: one line per plan item carrying the `file:line` where that item landed plus the existing pattern it reused. `plan-adherence-reviewer` reads it from `<IMPLEMENTER_NOTES>` to trace each plan item to verifiable evidence rather than re-deriving the trace cold, falling back to the cold trace when no receipt is present.

**Avoid:** "audit trail", "change log".

## Relationships

- The catalog (stage frontmatter) feeds the router; the router composes a route from live signals; the route runs to convergence.
- Artifacts decide ORDER (precedence); signals decide MEMBERSHIP. The size readout is a side effect of the route's stage count.
- Path (from triage) shapes the route; a gate is a stage, a lens is a stage - everything composes by the same rules.

## Flagged ambiguities

- "session" - the SessionStart hook event means a Claude Code session start, but `/alp-river:reflect`'s "current session" means the current chat history.
- "tier" - now means model tier (haiku/sonnet/fable) or the size readout (XS-XXL); the old "complexity tier" driver is retired. Prefer the qualified form.
- "stage" is canonical for the workflow unit; "step" and "phase" are retired.
