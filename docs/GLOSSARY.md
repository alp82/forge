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
**Definition:** `build`, `spike`, or `talk` - published by `triage`, exactly one per turn, re-evaluated each turn. Shapes the route: talk parks the spine (the `discuss` stage converses), spike relaxes rigor, build runs the full composition. A bug is `build` plus a `bug` signal, not a separate path.
**Avoid:** "route type", "execution mode", "TYPE_BIAS" (retired); "diagnose" as a path (folded into build).

### Routes
**Definition:** The mandatory per-stage frontmatter list of paths (`build`/`spike`/`talk`) a stage may run on. The router drops a triggered stage whose `routes` exclude the live path; multi-path is normal (`correctness-reviewer: [build, spike]`).
**Avoid:** "route" singular (that is the composed per-task instance).

### Convergence
**Definition:** A route is done when the router triggers no unrun stage and every review lens that ran is `clean`. Replaces the old backward-edge budget - there is no edge count.
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

### Triage
**Definition:** The always-on seed stage. Reads the request, publishes the path and opening signals (`ambiguous`, `bug`, risk sniffs, an advisory `est-size`); the router composes from there.
**Avoid:** "classifier" (retired), "router" (triage seeds, the router composes).

### Self-heal
**Definition:** The `fixer`-driven repair cycle that reruns the lenses whose findings it addressed, until they come back `clean`. A signal cycle (`code-written` re-published), bounded by the oscillation guard.
**Avoid:** "auto-fix", "retry loop".

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

## Relationships

- The catalog (stage frontmatter) feeds the router; the router composes a route from live signals; the route runs to convergence.
- Artifacts decide ORDER (precedence); signals decide MEMBERSHIP. The size readout is a side effect of the route's stage count.
- Path (from triage) shapes the route; a gate is a stage, a lens is a stage - everything composes by the same rules.

## Flagged ambiguities

- "session" - the SessionStart hook event means a Claude Code session start, but `/alp-river:reflect`'s "current session" means the current chat history.
- "tier" - now means model tier (haiku/sonnet/opus) or the size readout (XS-XXL); the old "complexity tier" driver is retired. Prefer the qualified form.
- "stage" is canonical for the workflow unit; "step" and "phase" are retired.
