# Glossary

Canonical terms for this project. Agents read this to avoid renaming the same concept three different ways across files.

## Terms

For each domain term, give the definition and the aliases to avoid. Aliases should be the names that have crept in elsewhere or that are tempting but wrong here.

### Complexity tier

**Definition:** The classifier's verdict on a request's size, one of S / M / L / XL / XXL. Controls how many phases of the pipeline run - S short-circuits to the main agent, XXL pushes back and asks for decomposition. Appears in code and agent files as the slot code `EFFECTIVE_TIER`; the human-readable name "complexity tier" is canonical for prose and docs.

**Avoid:** "complexity" alone, "size", "grade", bare "tier" (collides with model tier - haiku/sonnet/opus).

### Execution mode

**Definition:** The work-type axis with values `build` and `diagnose`. Selects which phases and reviewers apply - diagnose skips Design and runs investigator-first. Appears in code and agent files as the slot code `TYPE_BIAS`; the human-readable name "execution mode" is canonical for prose and docs.

**Avoid:** "type", "mode" alone (model tier also uses "mode"), "bias" alone (overloaded with LLM bias).

### Iteration

**Definition:** A re-entry from a later pipeline step back to an earlier one (e.g. implementer back to planner). Capped at 2 cumulative per request via the Backward-Edge Budget. Internal term in source: "backward edge".

**Avoid:** "loop" (in-step loops are free and distinct from iterations), "retry".

### Pushback

**Definition:** The specific iteration from implementer to planner when implementation reveals the plan is wrong. A pushback consumes one unit of the Backward-Edge Budget. Internal term in source: "kickback".

**Avoid:** "rejection", "bounce-back".

### Self-heal

**Definition:** Step 9's fixer-driven repair cycle that reruns failing reviewers after fixes are applied. Has its own separate budget of 2 self-heal rounds, distinct from the Backward-Edge Budget that caps iterations.

**Avoid:** "auto-fix", "retry loop".

### Pipeline output markers

**Definition:** Speaking-name slot identifiers that flow between pipeline steps. Most are subagent-emitted: `CONFIRMED_INTENT`, `CLASSIFICATION`, `CLARIFY_OUTPUT`, `APPROVED_PLAN`, `DISCOVERIES`. A few are not - `AGGREGATED_DISCOVERIES` is built by the main agent concatenating per-agent `DISCOVERIES` blocks at Step 10; `LOCKED_DESIGN_SPEC` is the verbatim paste-back from the design picker, captured by the main agent.

**Avoid:** "output", "result", "response" (all too generic); "tag" (suggests metadata, not payload).

### Phase

**Definition:** One of the seven coarse pipeline groupings: Understand, Prepare, Design, Build, Verify, Capture, Follow-up. Phases are labels; the executable unit is the Step.

**Avoid:** "stage" (drifts in - README.md uses "stage"; "phase" is canonical).

### Step

**Definition:** A numbered unit within a phase (Step 0 through Step 12). The Step is the unit the orchestrator actually executes; the Phase is just the grouping label above it.

**Avoid:** "stage", and avoid using "phase" for the unit (phase is the grouping, step is the unit).

### Broad pass

**Definition:** Step 7's parallel fan-out of reviewer subagents that always runs at M and above.

**Avoid:** "review round", "first review".

### Specialist pass

**Definition:** Step 8's conditional reviewer set that fires only when triggered by Broad-pass output.

**Avoid:** "deep review", "second review".

### Pre-flight

**Definition:** Step 2's fan-out of reconnaissance subagents that gathers context before clarification.

**Avoid:** "prep", "research phase".

### Gate 1

**Definition:** The L/XL pause before pre-flight where the user confirms cost before the pipeline spends fan-out tokens.

**Avoid:** "confirmation", "checkpoint".

### XXL pushback

**Definition:** Step 1's response when the classifier returns XXL - a 3-option picker (Split / Treat as XL / Abandon) that surfaces the suggested decomposition before any other gate fires. Split cycles are bounded (capped at 2 scope-downs). Distinct from the term "Pushback" above - XXL pushback is a request-level decision, Pushback is a step-to-step iteration.

**Avoid:** "rejection", "refusal".

### Setup nudge

**Definition:** Reminder pointing the user at `/alp-river:setup` when `docs/INTENT.md` is missing. Fires from two places: the SessionStart hook (every session boundary, before any classification) and Step 1 in-pipeline (first-fire on M/L/XL/XXL when the session-boundary nudge wasn't acted on).

**Avoid:** "warning", "notice".

### Design loop

**Definition:** Step 3.5's UI parameter picker that iterates with the user to produce a `LOCKED_DESIGN_SPEC` before planning starts.

**Avoid:** "design phase" (loop is more specific - it iterates with the user).

### Capture-agent two-phase

**Definition:** Step 10's pattern where phase 1 proposes glossary/stack/intent updates and phase 2 writes them after user approval.

**Avoid:** "capture step".

### Context injection slots

**Definition:** Auto-injected payloads that the PreToolUse(Agent) hook (`hooks/user-context-injector.sh`) prepends to subagent prompts. Three blocks: `USER_CONTEXT` (slice of `MEMORY.md` plus linked files), `PROJECT_CONTEXT` (slice of `docs/` - intent, stack, glossary, ADRs), and `PSYCHOLOGY` (persona block resolved per-agent via `psychology/agent-map.json`). The per-agent doc-token routing dictionary inside the hook (`READ_MAP`) is config, not a payload.

**Avoid:** "context" alone (overloaded with LLM context window).

### ADR

**Definition:** Architectural decision record produced by the adr-drafter subagent and stored under `docs/adr/`.

**Avoid:** "decision doc", "design doc".

### Psychology

**Definition:** Opt-in persona block injected via `psychology/agent-map.json` that shapes a subagent's voice and disposition.

**Avoid:** "personality", "prompt prefix".

### Confidence tagging

**Definition:** The `[likely]` / `[unsure]` markers subagents append to claims they can't ground in evidence.

**Avoid:** "uncertainty markers", "hedging".

### Concise Surfacing Contract

**Definition:** The rule that multi-option user choices go through Claude Code's AskUserQuestion tool, not free-text prompts.

**Avoid:** "user prompt", "question contract".

### 4-question cap

**Definition:** Hard rule that the main agent can ask at most four questions per turn; overflow goes to `DEFERRED_QUESTIONS`.

**Avoid:** "question limit" (the cap is specifically four).

### DEFERRED_QUESTIONS

**Definition:** The queue of questions clarifier/interviewer agents would have asked beyond the 4-question cap, surfaced later in the pipeline.

**Avoid:** "backlog", "pending".

### After-plan stop

**Definition:** Pipeline pause at L/XL once a plan has been approved, giving the user a chance to review before implementation begins.

**Avoid:** "checkpoint" (too generic).

### After-diagnose stop

**Definition:** Pipeline pause in bug-framing once the investigator returns its diagnosis, giving the user a continue-or-stop choice before implementation begins.

**Avoid:** "checkpoint" (too generic).

### Doctrine slice

**Definition:** A standalone markdown file under `doctrine/` holding one shared-rule section (reviewer-contract, code-doctrine, confidence-tagging, or discoveries), lifted verbatim from WORKFLOW.md and injected per-agent by the PreToolUse(Agent) hook into agents whose definition cites it. Introduces "doctrine" as a named injection axis delivered to subagents, distinct from the three existing Context injection slots (USER_CONTEXT, PROJECT_CONTEXT, PSYCHOLOGY).

**Avoid:** _TODO:_ aliases to avoid (review and fill)

### DOCTRINE_MAP

**Definition:** The bash associative array in `hooks/user-context-injector.sh` mapping each agent to the doctrine slice tokens it receives, paralleling READ_MAP. An agent appears in the map only if its definition cites that doctrine (cite=receive). New routing structure future agent additions must update.

**Avoid:** _TODO:_ aliases to avoid (review and fill)

## Relationships

- Complexity tier controls HOW MANY phases run (S short-circuits, XXL pushes back via XXL pushback).
- Execution mode controls WHICH phases run (diagnose skips Design).
- Phase contains many Step; Step is the executable unit, Phase is the grouping label.
- Broad pass always runs at M+; Specialist pass runs only when Broad-pass output triggers it.
- DISCOVERIES (per-agent) flow into AGGREGATED_DISCOVERIES (Step 10 input) and then into capture-agent's two-phase write.

## Flagged ambiguities

- "session" - the SessionStart hook event means a Claude Code session start, but `/alp-river:reflect`'s "current session" means the current chat history. Mark which usage applies in each file.
- "tier" - has at least four meanings: complexity tier (S/M/L/XL/XXL), model tier (haiku/sonnet/opus), kickback tier (plan-patch/replan/reinterview escalation in `agents/implementer.md`), and finding priority tier (1-5 in reviewer outputs). `WORKFLOW.md § Model Tiering` covers the first two. Prefer the qualified form ("complexity tier", "model tier", etc.) in new prose; reserve bare "tier" for cases where context makes the meaning obvious.
