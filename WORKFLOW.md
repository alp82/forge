# Global Development Rules

## Principles
- Never guess, never assume, never improvise unagreed solutions.
- Extracting actual intent is more important than moving fast.
- Research before asking. Subagents exhaust filesystem, tools, and web first; questions only surface what those sources don't already answer.
- Clarify in loops, not single passes. Intent and clarification stages re-run with prior rounds folded in until the latest exchange surfaces no new aspects. Loops within one step are free and do not count as backward edges.
- Leave touched code better than you found it. Unrelated changes get their own task.
- No TODOs, placeholders, or incomplete implementations.
- No backwards compatibility. Obsolete code gets deleted, not preserved.
- No unnecessary comments, docstrings, or type annotations on unchanged code.
- Always use the editor's dedicated file operation tools. When an edit fails, fix the edit - never fall back to shell commands (sed, awk, python scripts) for file manipulation.

## Tone
- No corporate phrasing or fake contrast framing ("While X is important, Y...").
- No sycophancy. If an idea is weak, say so and explain why.
- Wit and sarcasm welcome when they land. Don't force it.
- Be direct. Say what you mean.

## Formatting
- No preamble or postamble. Start with the answer, end when the answer ends. No "I'll now...", "Let me...", "Here's what I found:", "Hope this helps."
- Status updates between tool calls: one sentence, fragments OK. "Reading the config." not "Let me take a look at the configuration file."
- Don't restate the user's question before answering.
- Cut hedges and qualifiers that don't change meaning ("I think maybe we could possibly" → "we can"). Keep hedges only when the uncertainty is real and load-bearing.
- Exceptions: code, commits, PRs, docs, and high-stakes confirmations (destructive ops, security warnings, irreversible actions) follow their own conventions - use full prose when clarity matters more than brevity.

## Context Discipline
- Always prefer subagents. The main agent orchestrates and talks to the user - it does NOT read entire codebases, do deep analysis, or implement large changes itself.
- Subagents return structured verdicts (VERDICT/FINDINGS/ACTION_NEEDED), not raw dumps.
- Spawn dynamic subagents when the situation calls for it. Pick the cheapest model that can handle the job (fast/small for classification, mid-tier for analysis/implementation, top-tier only when truly needed).

## Subagent Context Inheritance

MEMORY.md + linked files don't transfer to subagents automatically - they inherit nothing. Neither do project-level docs.

The alp-river plugin's **PreToolUse(Agent) hook** (`user-context-injector`) handles both. It prepends up to two blocks to the Agent prompt:

- `## USER_CONTEXT` - MEMORY.md + linked files (durable user preferences and feedback).
- `## PROJECT_CONTEXT` - matching slices of the project's `docs/` folder (intent, stack, glossary, ADRs).

The two axes are independent. User-aware status does not determine project-aware status, and vice versa.

**User-aware** means the agent receives `## USER_CONTEXT`. The hook's case statement is the allowlist. When a user preference conflicts with a default behavior, the preference wins unless it creates a correctness issue.

**Project-aware** means the agent receives `## PROJECT_CONTEXT`. The hook's `READ_MAP` is the allowlist. Each entry lists which doc tokens the agent needs (`intent`, `stack`, `glossary`, `adrs`).

For the authoritative per-agent wiring, read `hooks/user-context-injector.sh` - the case statement (user-aware allowlist) and `READ_MAP` (project-aware tokens per agent) are the single source of truth. Agent files do not carry a `reads:` field; what runs is what's in the hook.

If no MEMORY.md exists for the current project, the hook skips the USER_CONTEXT block silently. A missing `docs/` folder omits the whole PROJECT_CONTEXT block. Per-doc silent skip: a missing token target (e.g. no `INTENT.md`) just omits that slice. No errors, no scaffolding prompts.

### Project Context docs

Project intent, stack choices, glossary, and prior architectural decisions live in your repo's `docs/` folder.

Four file types feed it. Token names are lowercase; resolved filenames are UPPERCASE to match README/CHANGELOG/LICENSE convention. ADRs live in `docs/adr/` per the standard ADR convention.

| Token | Resolves to | How it appears |
|-------|-------------|----------------|
| `intent` | `docs/INTENT.md` | full body under `### INTENT.md` |
| `stack` | `docs/STACK.md` | full body under `### STACK.md` |
| `glossary` | `docs/GLOSSARY.md` | full body under `### GLOSSARY.md` |
| `adrs` | `docs/adr/*.md` | summary list - one bullet per ADR with status, title, summary, path |

ADRs collapse to a list, not full bodies, to keep prompts lean. The hook drops ADRs with status `deprecated` or `superseded`, files matching `0000-*.md` (catches the unfilled template), and ADRs whose summary still contains a `_TODO:_` marker.

Templates ship in the plugin's `templates/` folder; copy them into your project's `docs/` and fill in the `_TODO:_` markers. Run `/alp-river:setup` to populate INTENT/STACK/GLOSSARY interactively. Run `/alp-river:adr` to record a decision deliberately - it drafts via the `adr-drafter` agent (read-only, opus) and rejects duplicates of active ADRs before any file lands.

## Confidence Tagging

Every finding carries a tag: `[likely]` (evidence-based - code you read, official docs, observed behavior) or `[unsure]` (judgment, single-source, stale, or inferred). Both hedge - `[likely]` means "probably true, read carefully," not "certain."

- **Pre-flight agents**: report both tiers; `[unsure]` guides where to verify before planning. Consumers verify load-bearing `[unsure]` items before acting on them.
- **Post-impl reviewers**: `[likely]` unconditionally; `[unsure]` only at high impact (correctness, security, data risk).
- **Web-sourced** (plan-challenger, security-reviewer, researcher): `[likely]` = official advisory/CVE/maintainer page; `[unsure]` = blog/undated thread. Include source URL.

## Pipeline

Every implementation task runs through a staged pipeline. Depth scales with complexity; confirming intent is always mandatory.

Phases: Understand (0-1) → Prepare (2-3) → Design (3.5-5) → Build (6) → Verify (7-9) → Capture (10-11) → Follow-up (12).

### Axes

The pipeline tracks two internal axes (both set during the run, neither set by entry):

| Axis | Values | What it controls |
|------|--------|------------------|
| `EFFECTIVE_TIER` | `S` / `M` / `L` / `XL` / `XXL` | Sizes the internal gates (which steps fire, fan-out depth, model overrides). Set by Step 1 classifier (or, on `TYPE_BIAS=diagnose`, by the investigator's COMPLEXITY for the diagnose stop). |
| `TYPE_BIAS` | `build` / `diagnose` | Detected at Step 0 Level 1 from the user's request. Picks the Step 0 framing variant and the Step 2 agent set. |

Stops fire at natural seams in the pipeline, not via a pre-set point:
- `after-diagnose` fires after Step 2 when `TYPE_BIAS: diagnose`. Picker chooses Continue (rolls into build or plan-only based on tier) or Stop.
- `after-plan` fires after Step 5 on L/XL whenever a plan was produced. Picker chooses Continue-build (default) or Stop.

### Type Bias

`TYPE_BIAS` is determined at Step 0 Level 1 by the main agent reading the user's request:

- **`build`** (default): the request reads as feature/refactor/doc work. Use the outcome-restate variant of Step 0 Level 1.
- **`diagnose`**: the request reads as a bug report (signals: "why", "broken", "failing", "error", "fix", "doesn't work", a stack trace, a symptom description). Use the bug-framing variant of Step 0 Level 1 (observed vs expected vs environment) and wait for user confirmation OR missing info before proceeding.

If detection is ambiguous, default to `build`. The user reshapes at Level 1 if the framing is wrong - one round of Step 0, no cost beyond that.

`TYPE_BIAS` shapes two things downstream:
- **Step 0 framing**: as above.
- **Step 2 agent set**: `build` fans out across the four pre-flight agents (reuse-scanner, health-checker, prototype-identifier, researcher). `diagnose` launches the investigator alone - same step semantically (gather information before designing).

On Continue from the after-diagnose stop, `TYPE_BIAS` is replaced with `build` (the user is now in fix-or-implement mode). The user restates intent in their own words and the pipeline runs Step 1 onward on that restatement.

### Step 0: Intent

Before classification, confirm direction - a misread request misclassifies every gate downstream. **Level 1 runs on every task at every tier, including S follow-ups in main-agent mode.** No "this is small, I'll just do it" path.

- **Level 1 (always, every tier)**: Main agent restates the **outcome** the user wants - what needs to be true when this is done, in user-observable terms. Keep it concise; clarity wins over brevity, so use a couple of sentences, a small ASCII diagram, or a brief example if that lands the point better than prose. **No file paths, schema fields, function names, API routes, or component names** - those are implementation details that belong in the plan, not the intent. If you can't restate without naming specifics, you've over-interpreted; pull back to the goal. **Main agent stays text-only - no codebase reads, no web lookups.** Wait for the user's reply.
  - **Affirmation -> proceed**: short positive reply (`y`, `yes`, `correct`, `proceed`, `looks right`, `go`, similar). Move to Step 1.
  - **Anything else -> reshape**: free-text additions, corrections, the user restating in their own words, or any reply that's not a bare affirmation. Treat the reply as the new `<RAW_REQUEST>` and escalate to Level 2 with it.
- **Level 2 (on reshape OR when the request has multiple readings OR when restating would require recon)**: enter the **interview loop**. Launch `interviewer` (opus) to research the target area (filesystem + web when relevant), then probe scope, users, success criteria, and priority trade-offs. Each round, present QUESTIONS to the user, capture answers, append to `<PRIOR_ROUNDS>`, re-launch. Exit when `VERDICT: confirmed` AND `NEW_ASPECTS_FOUND: no`. Cap at 5 rounds - at the cap, present the latest direction and ask the user to confirm or reshape. Rendering follows the Concise Surfacing Contract.

Emit `<CONFIRMED_INTENT>` - every downstream agent reads it.

### Step 1: Classify

Launch `complexity-classifier` (opus) with `<CONFIRMED_INTENT>`. Output `<CLASSIFICATION>` with COMPLEXITY (S|M|L|XL|XXL) + REASON, plus `SUGGESTED_SPLIT` on XXL. The classifier's COMPLEXITY sets `<EFFECTIVE_TIER>` and gates which downstream steps fire:

- **S**: lighter path. Skip Gate 1 (no L/XL cost prompt). Run a single `reuse-scanner` at Step 2. Skip Step 3 unless ambiguity is glaring. Skip Step 3.5. Main agent implements at Step 6. Skip Steps 7-10 entirely - the Stop hook runs the project's test suite automatically; jump to Step 11 with a brief summary.
- **M**: run the full Step 2 fan-out. Step 3 clarify runs only when pre-flight leaves ambiguity. Step 3.5 design loop fires only when the clarifier flags it. Main agent implements at Step 6. Step 7 includes test-verifier + correctness + quality + acceptance (no plan-adherence-reviewer on M).
- **L/XL**: full pipeline. **Fire the canonical Gate 1 block below** before Step 2.
- **XXL**: **Fire the XXL pushback block first**, then Gate 1 (skipped if user chose `Treat as XL`).

Capture as `<CLASSIFICATION>` and `<EFFECTIVE_TIER>`. The remainder of the pipeline reads `<EFFECTIVE_TIER>` for every per-tier gate.

On `TYPE_BIAS: diagnose` (detected at Step 0 Level 1), Step 1 is skipped on entry. The investigator's COMPLEXITY sets `EFFECTIVE_TIER` for the diagnose phase only. On Continue from the diagnose stop, the user restates intent (Step 0 Level 1 style), and the Step 1 classifier runs on that restatement to size downstream gates.

#### Setup nudge (L/XL/XXL, first-fire)

On first L/XL/XXL classification in this run, before XXL pushback or Gate 1's prompt:

1. Check whether `docs/INTENT.md` exists.
2. Read `.claude/settings.local.json` if present and look up `alpRiver.skipSetup`. Treat a missing file or missing key as `false`.
3. If `docs/INTENT.md` exists OR `alpRiver.skipSetup: true`, skip the nudge.
4. Otherwise, emit one advisory line immediately above Gate 1's prompt:

   > Project context missing: no `docs/INTENT.md`. Consider `/alp-river:setup` first so planning and review run with your intent, stack, and glossary loaded. Dismiss permanently with `"alpRiver": {"skipSetup": true}` in `.claude/settings.local.json`.

Advisory only - does not block, does not add an interaction step, does not re-fire on re-classify, does not count against the backward-edge budget.

#### XXL pushback (XXL only, fires before Gate 1)

When the classifier (first pass or re-classify upgrade) returns COMPLEXITY: XXL, fire this block **before** Gate 1.

Initialize on first fire (if not already initialized by Gate 1): `<SCOPE_DOWN_COUNT> = 0`. Threaded through subsequent gate fires and shared with Gate 1's counter.

Surface the SUGGESTED_SPLIT inline above the picker:

```
This classifies as XXL: <REASON>.

Spans more than fits cleanly into one task. Suggested decomposition:
<SUGGESTED_SPLIT, one bullet per line, verbatim from classifier output>
```

**If `<SCOPE_DOWN_COUNT> < 2`**, invoke `AskUserQuestion`:

- `question`: ``Worth it? (split cycles used: <SCOPE_DOWN_COUNT>/2)``
- `header`: `XXL split`
- `multiSelect`: `false`
- `options`:
  - `Split` - "Pick one slice from the suggested decomposition (or describe a different reduction) and run with it. Re-enters Step 0 with the chosen slice."
  - `Treat as XL` - "Keep the work as one task. Continue at XL gates for all downstream stages. Counts as cost confirmation - Gate 1 does not fire."
  - `Abandon` - "Stop the command."

Interpret the user's selection:
- `Split` -> ask the user (free-text follow-up):
  > Which slice do you want to tackle now? Pick one from the suggested decomposition by number, or describe a different scope reduction in your own words.

  Take the reply, increment `<SCOPE_DOWN_COUNT>`, feed the reply as the new `<RAW_REQUEST>` into Step 0 Level 1 restatement, and run the normal intent loop. After re-classify, this block (or Gate 1) fires again per the resulting tier.
- `Treat as XL` -> continue as XL for all downstream gates and record `EFFECTIVE_TIER: XL` for plan/challenge/implement/review stages. This path counts as if Gate 1 fired and the user picked `Continue` - **Gate 1 does not re-fire this run**.
- `Abandon` -> stop the pipeline; emit no `<!-- pipeline-complete -->`.

**If `<SCOPE_DOWN_COUNT> >= 2` (cap reached)**, invoke `AskUserQuestion` with the locked options:

- `question`: ``Split cycles used. Classified XXL: <REASON>. Worth it?``
- `header`: `XXL split`
- `multiSelect`: `false`
- `options`:
  - `Treat as XL` - "Keep the work as one task. Continue at XL gates."
  - `Abandon` - "Stop the command."

(No `Split` option at the cap.)

XXL pushback cycles are **free** - they do not count toward the backward-edge budget.

#### Gate 1: Pre-plan cost check (L/XL)

Skip Gate 1 if XXL pushback fired this run and the user chose `Treat as XL` (cost confirmation already given via the pushback).

After the classifier (or re-classifier) lands at L or XL **for the first time in this run**, pause before continuing to pre-flight (or, on re-classify, to Step 4).

Initialize on first fire: `<SCOPE_DOWN_COUNT> = 0`. Threaded through subsequent gate fires in this run.

**If `<SCOPE_DOWN_COUNT> < 2`**, invoke `AskUserQuestion`:

- `question`: ``This classifies as <tier>: <REASON>. Worth it? (scope-down cycles used: <SCOPE_DOWN_COUNT>/2)``
- `header`: `Cost check`
- `multiSelect`: `false`
- `options`:
  - `Continue` - "Proceed to pre-flight at `<tier>` gates."
  - `Scope down` - "Narrow the scope. You'll be asked what to drop; the reduced request feeds back through Step 0 and re-classifies."
  - `Abandon` - "Stop the command."

Interpret the user's selection:
- `Continue` -> proceed.
- `Scope down` -> ask the user (free-text follow-up):
  > Ok, restating with narrower scope. What part of the work do you want to drop or postpone?

  Take the reply, increment `<SCOPE_DOWN_COUNT>`, feed the reply as the new `<RAW_REQUEST>` into Step 0 Level 1 restatement, and run the normal intent loop. After re-classify, this gate fires again with the updated counter.
- `Abandon` -> stop the pipeline; emit no `<!-- pipeline-complete -->`.

**If `<SCOPE_DOWN_COUNT> >= 2` (cap reached)**, invoke `AskUserQuestion` with the locked options:

- `question`: ``Scope-down limit reached. Classified <tier>: <REASON>. Worth it?``
- `header`: `Cost check`
- `multiSelect`: `false`
- `options`:
  - `Continue` - "Proceed to pre-flight at `<tier>` gates."
  - `Abandon` - "Stop the command."

(No `Scope down` option at the cap.)

Gate 1 cycles are **free** - they do not count toward the backward-edge budget.

### Step 2: Pre-flight

Bias-conditional. Same step semantically: gather information before designing.

- **`TYPE_BIAS: build` or `plan-only`** (M/L/XL): parallel fan-out on the confirmed scope:
  - `reuse-scanner` - reusable code + quick-win refactors
  - `health-checker` - code health + cleanup targets
  - `prototype-identifier` - external APIs / SDK novelty
  - `researcher` - library/framework/domain knowledge (skip if interviewer flagged no external deps)

  On `EFFECTIVE_TIER: S`, run `reuse-scanner` alone. The other three skip.

- **`TYPE_BIAS: diagnose`**: launch `investigator` (see commands/investigate.md Step 2 for full spec). On `VERDICT: cannot-diagnose` with non-empty `MISSING_INFO`, run the wait-on-user free loop (request missing detail, re-invoke investigator).

Step 2's depth varies by tier (S = 1 agent, M+ = 4 agents) and its agent set varies by bias (diagnose = investigator alone).

**Health gate** (build / plan-only only): cleanup-first → wait user; proceed-with-cleanup → carry targets forward; proceed → continue.
**Prototype gate** (build / plan-only only): launch `prototyper` (sonnet) if flagged, writing to `.prototypes/`. prototype-identifier tags each target with NOVELTY (low/med/high); on `high`, it also emits `ALTERNATIVE_SHAPES` and the prototyper builds **two** differently-shaped tracers for that target (Design It Twice at the prototype layer) and reports a `COMPARISON` so the planner picks on evidence rather than intuition.

### Step 3: Clarify (L/XL; M when ambiguity remains after pre-flight)
Enter the **clarify loop**. Launch `requirements-clarifier` (opus) with intent + pre-flight outputs. Each round, apply the Concise Surfacing Contract 4-cap priority queue across QUESTIONS + [unsure] criteria + [unsure] assumptions; invoke `AskUserQuestion` with the resulting items. Thread DEFERRED_QUESTIONS forward. Append answers to `<PRIOR_ROUNDS>`, re-launch. Exit when `CLARITY: clear` AND `NEW_ASPECTS_FOUND: no`. Cap at 5 rounds - at the cap, present the latest state and ask the user to confirm or reshape. Emit `<CLARIFY_OUTPUT>`.

The clarifier also emits `WRITES_PROPOSED` (glossary terms) on exit when the round settled canonical names. The clarifier itself never writes - on `STOP_POINT: none` runs the main agent merges these into Step 10's aggregated discoveries; on `STOP_POINT: after-plan` they surface as info only.

**Re-classify (backward edge)**: before exiting Step 3, if clarify answers (or earlier interviewer output) materially shifted scope, rerun `complexity-classifier` on intent + clarify. Scope up → add gates for the new tier going forward. Scope down → keep current gates (no retroactive downgrade). **Counts toward backward-edge budget.**

### Step 3.5: Design Loop (when clarifier flagged DESIGN_LOOP_NEEDED: yes)

Fires only when `<CLARIFY_OUTPUT>` carried `DESIGN_LOOP_NEEDED: yes`. Skipped otherwise.

1. **Confirm parameters**: Launch `design-explorer` (opus) with intent, classification, clarify output, pre-flight findings, and `<USER_PARAM_PICKS>: none`. Output is `PHASE: confirm-params` with `PARAMS_TO_CONFIRM`. Apply the Concise Surfacing Contract 4-cap priority queue and invoke `AskUserQuestion` with the items. Capture user selections as `<USER_PARAM_PICKS>`.
2. **Build the picker page**: Re-launch `design-explorer` with the same inputs plus `<USER_PARAM_PICKS>`. Output is `PHASE: built` with `HOST_DECISION` (sandbox vs real-page), `PAGE_FILE`, `PAGE_URL`, `CONTROLS_EXPOSED`, `COPY_SPEC_FORMAT`, `USER_INSTRUCTIONS`, and `CLEANUP_NEEDED`. Surface `USER_INSTRUCTIONS` and the page reference inline.
3. **Wait for paste-back**: The user opens the page, flips through controls, clicks Copy on the chosen combination, pastes the labeled key-value spec back into chat. The next user message is the spec - capture it verbatim as `<LOCKED_DESIGN_SPEC>`.
4. **Re-explore on request**: If the pasted reply asks for more options on a parameter, treat it as a refined `<USER_PARAM_PICKS>` and re-invoke the build phase. Otherwise hand `<LOCKED_DESIGN_SPEC>` (and `CLEANUP_NEEDED` when `HOST_DECISION: real-page`) to Step 4.

The design loop is **free** - it does not count toward the backward-edge budget. The planner reads `<LOCKED_DESIGN_SPEC>` as input and (when real-page) folds `CLEANUP_NEEDED` into the plan's implementation steps so the picker artifacts never ship.

### Step 4: Plan (L/XL)
Launch `planner` (opus) with intent, classification, clarify, pre-flight findings, plus `<LOCKED_DESIGN_SPEC>` and `<DESIGN_CLEANUP>` from Step 3.5 (or "none" when the design loop didn't run). XL presents 2-3 APPROACHES with ASCII diagrams + RECOMMENDATION. Approved output emits `<APPROVED_PLAN version="N">`. When the design spec is bound, the planner builds to it verbatim; when cleanup is needed (real-page host), the planner folds those steps into the implementation.

The plan's `## Acceptance` section attaches a `VALIDATION` type (`test`, `manual`, or `observable`) to each acceptance criterion pulled from `<CLARIFY_OUTPUT>`. The declared validation is part of the contract - acceptance-reviewer checks both the implementation AND that the named validation actually happened (test exists, observable is present at the named location, or manual is flagged for the user).

### Step 5: Challenge (L/XL)
Launch `plan-challenger` (opus). XL challenges **all** approaches (not just the recommendation). Verdict:
- `approve` → present to user
- `revise` → planner rerun with BLOCKERS (**backward edge**)
- `reject` → reinterview (**backward edge**)

Surface BLOCKERS + SCOPE_MISMATCH inline; render CHALLENGE_QUESTIONS via AskUserQuestion (Concise Surfacing Contract).

Optional `SCOPE_MISMATCH` slot - one-liner "drop X to land Y" when the plan reaches farther than the intent's primary outcome needs. Heuristic, advisory; does not change VERDICT. Shown alongside plan to the user for an informed call.

### Step 6: Implement
- **S/M**: main agent implements directly (M draws on pre-flight + clarify).
- **L/XL**: delegate to `implementer` (opus) with `<APPROVED_PLAN>` + reuse + intent.

Implementer VERDICT:
- `complete` | `partial` → Step 7.
- `blocked` → **kickback tier** (counts toward backward-edge budget):
  - `plan-patch` - narrow-scope planner rerun on one step
  - `replan` - full planner rerun with new constraint
  - `reinterview` - scope wrong, back to Step 0

### Step 7: Broad pass (M/L/XL, fail-fast)
Parallel:
- `test-verifier` - fails fast; if red, skip Step 8 and jump to self-heal
- `correctness-reviewer` - correctness, type holes, dead code (opus on L/XL, sonnet on M)
- `quality-reviewer` - engineering judgment: hacky shortcuts, bloat, wrong tool, unelegant (opus across)
- `acceptance-reviewer` - intent fulfillment + acceptance criteria
- `plan-adherence-reviewer` - file list, function signatures, step order (L/XL only)

### Step 8: Specialist pass (conditional)
Gate each specialist on broad-pass finding OR touched files matching its domain:

| Specialist | Trigger |
|------------|---------|
| `structure-reviewer` | broad pass flagged structure / boundaries |
| `architecture-reviewer` (opus) | touched files introduce new exports / wrappers / seams; broad pass flagged shallow abstraction |
| `reuse-reviewer` | broad pass flagged duplication |
| `consistency-reviewer` | touched files affect patterns / naming |
| `security-reviewer` (opus) | touched files include auth / permissions |
| `performance-reviewer` | touched files include db / queries |
| `accessibility-reviewer` | touched files include UI |
| `design-consistency-reviewer` | touched files include UI |
| `ux-reviewer` | touched files include UI |
| `visual-verifier` | UI touched - inline offer (default-Y on XL, default-N on M/L); dev server at URL from project CLAUDE.md |

Nothing flagged and no domain match → skip Step 8.

### Step 9: Self-heal
Launch `fixer` (opus on L/XL, sonnet on M) with aggregated findings. Fixer addresses every reported finding; anything that can't be fixed in scope goes into REMAINING.

**Post-fix RE-RUN set** = gates that flagged anything the fixer addressed + gates whose domain the fixer's edits touched.

- Round 1: fix + rerun
- Round 2: present to user → directed fix + rerun
- Round 3+: stop, surface

Summary in Step 11 cites post-fix gate results only.

### Step 10: Capture (M/L/XL)

Before summarizing, harvest novel project-context items surfaced by upstream agents during this run. Aggregate every non-empty `DISCOVERIES` block from design-explorer, implementer, fixer, investigator, and the reviewers (correctness, quality, architecture, structure, consistency, security, performance) into `<AGGREGATED_DISCOVERIES>`. Also fold in any non-empty `WRITES_PROPOSED` block from `<CLARIFY_OUTPUT>` (glossary terms the clarifier surfaced on exit) - same dedup + approval flow applies.

Launch `capture-agent` (opus) with `<PHASE>: 1` and `<AGGREGATED_DISCOVERIES>`. The agent dedups against the loaded PROJECT_CONTEXT (intent, stack, glossary) and emits one of:

- `PHASE_RESULT: complete-empty` - nothing novel; skip to Step 11.
- `PHASE_RESULT: complete-no-docs-dir` - target `docs/` does not exist; recommend `/alp-river:setup` to the user, skip to Step 11.
- `PHASE_RESULT: proposal-ready` - a `PROPOSAL` block listing dedup-survived candidates per bucket.

On `proposal-ready`, present the proposal to the user and capture per-item approvals:
- `glossary`: `accept | edit: <text> | reject`.
- `stack_drift` and `intent_drift`: `accept-as-drift | edit: <text> | reject`.

Re-launch `capture-agent` with `<PHASE>: 2` and `<APPROVALS>`; it appends approved glossary terms and drift sections. Capture-agent never creates `docs/`.

Skip Step 10 entirely on S tasks - no upstream emitters run.

### Step 11: Summarize
- What was built (2-3 sentences)
- Files created / modified
- Post-fix gate results
- Captures recorded (glossary/drift counts, or "none")
- Backward edges used: N/2
- REMAINING items for user triage

Emit `<!-- pipeline-complete -->` at the end.

### Stop Points

The pipeline has two natural stops. Both fire automatically when reached; the user picks Continue or Stop.

- **`after-plan`** fires after Step 5 (Challenge) on L/XL whenever a plan was produced. Invoke `AskUserQuestion`:
  - `question`: ``Plan approved. Continue building, or stop here?``
  - `header`: `After plan`
  - `multiSelect`: `false`
  - `options`:
    - `Continue-build (Recommended)` - "Run the implementation, review, and self-heal stages now."
    - `Stop` - "Stop the run. The plan is on screen for you to act on later."

  On `Continue-build` → proceed to Step 6. On `Stop` → emit `<!-- pipeline-complete -->`. Bare Enter accepts Continue-build.

- **`after-diagnose`** fires after Step 2 on `TYPE_BIAS: diagnose`. The picker options depend on the investigator's `COMPLEXITY` to avoid mis-routing - a small fix shouldn't pretend a plan helped, and a large fix shouldn't bypass planning.
  - **`COMPLEXITY: S` or `M`**:
    - `Continue-fix` - "Continue here at S/M gates. You'll restate the outcome in your own words, then the main agent implements directly."
    - `Stop` - "Stop after the diagnosis report."
  - **`COMPLEXITY: L`, `XL`, or `XXL`**:
    - `Continue-plan` - "Continue here. You'll restate the outcome in your own words, then run pre-flight + clarify + plan + challenge. The after-plan picker fires next."
    - `Stop` - "Stop after the diagnosis report."

  On Continue (either variant), set `TYPE_BIAS: build` and prompt the user verbatim:

  > Restate the outcome you want in your own words (avoid file paths or function names - those go in the plan).

  Capture the reply as `<CONFIRMED_INTENT>`. Run Step 1 classifier on it. Fire XXL pushback / Gate 1 per tier. Skip Step 2 (investigator already ran - findings carry forward as `<PREFLIGHT>` material for the planner). Proceed to Step 3 (clarify if needed) → 3.5 → 4 → 5. The after-plan picker fires on L/XL after Step 5 as usual. Continue through Step 11 otherwise.

  On `Stop` → emit `<!-- pipeline-complete -->`.

The user's restate at Continue is verbatim - no mechanical synthesis from investigator output, no auto-filled RECOMMENDED FIX. The investigator's report stays surfaced as a report, never silently consumed as intent.

### Step 12: Follow-up Requests
Every subsequent request is a new task. Re-enter Step 0 and run **Level 1 restate-and-wait** before any work - the gate is mandatory for follow-ups too, including S. Level 2 stays optional: skip it when the user's affirmation reads as a clean continuation; spawn the interviewer on any reshape reply per the Step 0 affirmation rule.

The main agent runs the pipeline directly from this file. `TYPE_BIAS` is auto-detected at Step 0 Level 1 from the user's text (see `### Type Bias` above). The single slash entry `/alp-river:go` exists for users who want a discoverable trigger; free-text chat follows the same pipeline without any command dispatch.

## Model Tiering

| Tier | Agents |
|------|--------|
| **opus** | classifier, interviewer, clarifier, planner, plan-challenger, implementer, design-explorer, acceptance-reviewer, security-reviewer, investigator, quality-reviewer, architecture-reviewer, capture-agent, adr-drafter; fixer + correctness-reviewer on L/XL |
| **sonnet** | reuse-scanner, structure-reviewer, consistency-reviewer, reuse-reviewer, test-verifier, visual-verifier, a11y-reviewer, design-consistency-reviewer, ux-reviewer, plan-adherence-reviewer, prototyper; fixer + correctness-reviewer on M |
| **haiku** | health-checker, prototype-identifier, researcher |

Commands override the model at spawn time (`Agent` tool's `model` parameter) when the tier depends on complexity.

## Clarification Loops

Step 0 Level 2 (interviewer) and Step 3 (clarifier) run as loops, not single passes. Depth scales with the unknowns still lurking - keep going until the user is satisfied and no new aspects emerge.

**Exit criteria** - exit when ALL hold:
1. Agent's VERDICT is `confirmed` (interviewer) or `clear` (clarifier).
2. Agent's `NEW_ASPECTS_FOUND: no`.
3. User has no further additions.

**Cap**: 5 rounds per stage. At the cap, present the latest state and ask the user to confirm explicitly or reshape the request. Do not loop silently.

**Round inputs**: re-invocations carry `<PRIOR_ROUNDS>` - a compressed log of prior questions and the user's answers (one line per Q&A, no reasoning). The agent uses it to detect whether the latest answer raised new aspects vs. reaffirmed prior ones, and to avoid re-asking what's already settled.

**Research first**: before formulating questions in any round, the agent exhausts filesystem (Glob/Grep/Read), prior pre-flight findings, and web sources when the request mentions external surface. It reports what it checked in `LOOKUPS_PERFORMED`. If the codebase or research already answers a candidate question, drop it.

**Loops are free**: clarification loops refine intent within a step. They do NOT count toward the backward-edge budget.

## Concise Surfacing Contract

**Purpose**: Inline prose stays only for decisions. Multi-option choices render through `AskUserQuestion` so reasoning lives in `description`/`preview` instead of inline prose. Recon notes and round-over-round restatements still exist in the subagent output - the user opens them on demand by scrolling the transcript.

**In scope**: Step 0 Level 2 (interviewer), Step 1 cost gates (Gate 1 + XXL pushback), Step 3 (clarifier), Step 3.5 (design-explorer's `PARAMS_TO_CONFIRM` phase), Step 5 (plan-challenger), after-plan stop (Continue-build / Stop), after-diagnose stop (Continue-fix or Continue-plan, by COMPLEXITY / Stop), specialist-pass visual-verifier offer (when UI touched), capture-agent per-item approvals.

**Out of scope** (each excluded for a reason):
- **Step 0 Level 1**: stays plain text. Single-sentence restate; affirm-or-reshape where reshape is free-text. A picker would add ceremony for what's essentially confirm/correct.
- **Step 4**: emits `<APPROVED_PLAN>` as a text readback only - no picker. The user decides once at Step 5.
- **Pre-flight agents**: unchanged. Not user-facing.
- **Post-impl reviewers**: unchanged.

**MUST-render rule**: when the workflow reaches any In-scope decision point, the main agent MUST invoke `AskUserQuestion` instead of rendering options as prose. When all picker-eligible items are empty AND the agent's exit criteria hold, the main agent proceeds without prompting. Single-question single-select auto-submits per `AskUserQuestion` CLI behavior - that is expected.

**Picker-eligible items by source**:
- `interviewer`: non-empty `QUESTIONS`, still-open `DEFERRED_QUESTIONS`.
- `requirements-clarifier`: non-empty `QUESTIONS`, still-open `DEFERRED_QUESTIONS`, promoted `[unsure]` criteria or assumptions.
- `design-explorer`: non-empty `PARAMS_TO_CONFIRM` or `DEFERRED_PARAMS`.
- `plan-challenger`: non-empty `CHALLENGE_QUESTIONS`.
- **Main-agent direct prompts** (no subagent emitter): Gate 1, XXL pushback, after-plan stop, after-diagnose stop, visual-verifier offer, capture-agent per-item approvals. Canonical blocks live here in WORKFLOW.md (Step 1 for Gate 1 + XXL pushback + Setup nudge; Stop Points for after-plan + after-diagnose). The main agent renders the picker directly per those specs.

**Question schema** (carried by interviewer/clarifier `QUESTIONS` items and challenger `CHALLENGE_QUESTIONS` items):
- `question` (text)
- `header` (max 12 chars)
- `multiSelect` (true | false)
- `options` (2-4 entries; each has `label`, `description`, optional `preview`)

**Description vs. preview**: `description` carries the essence - what choosing this means and its consequence. It is load-bearing; the user can decide from it alone. `preview` is enrichment, best-effort; the host CLI may strip it when `toolConfig.askUserQuestion.previewFormat` is unset. Never put load-bearing content in `preview`.

**No agent-side "Other"**: the CLI surfaces an "Other" free-text escape automatically. Agents MUST NOT synthesize their own "Other" option.

**4-question cap + DEFERRED priority queue**: `AskUserQuestion` accepts 1-4 questions per call. When upstream output produces more than 4 picker-eligible items, the main agent fills the 4 slots in this priority order and rolls the rest into `DEFERRED_QUESTIONS`:
1. Genuine open `QUESTIONS` in the order the agent emitted them (clarifier orders by plan-change impact; interviewer orders by direction impact).
2. `[unsure]` items from `ACCEPTANCE_CRITERIA_PROPOSED`, in their original list order (each becomes a Confirm/Replace shape).
3. `[unsure]` items from `ASSUMPTIONS_TO_CONFIRM`, in their original list order (each becomes Confirm/Replace).

Walk this priority queue top-to-bottom; remainder goes to `DEFERRED_QUESTIONS` preserving the same order. Deterministic and re-runnable. On rounds where `QUESTIONS` already fills all 4 slots, `[unsure]` items defer entirely - acceptable trade-off; the loop will surface them on a later round.

**DEFERRED_QUESTIONS round-trip**:
- **Clarifier**: `DEFERRED_QUESTIONS` lives **inside** `<CLARIFY_OUTPUT>` so the SessionStart re-injector preserves it across compaction.
- **Interviewer**: `DEFERRED_QUESTIONS` is a top-level sibling of `QUESTIONS` (interviewer output has no wrapper today; adding one is out of scope). Compaction during the intent loop will lose interviewer `DEFERRED_QUESTIONS`. Accepted trade-off - Step 0 L2 rounds are short; the agent re-asks anyway.
- The main agent threads still-open `DEFERRED_QUESTIONS` items into the next round's `<PRIOR_ROUNDS>` so the subagent can resurface them.

**HEADER_GUIDANCE**: each covered subagent file carries its own `HEADER_GUIDANCE` worked examples (max 12 chars per header). The agent must produce a header that fits the cap; truncated headers signal a too-broad question.

**SCOPE_MISMATCH surfacing**: the plan-challenger's `SCOPE_MISMATCH` field is preserved. Surfaced inline as a single-line advisory alongside `BLOCKERS` at Step 5. Also folded into the Reshape option's `preview` in `CHALLENGE_QUESTIONS` so the user sees the "drop X to land Y" framing in context.

**Reshape == challenger `reject` for backward-edge accounting**: Step 4 has no picker. Reshape exists only at Step 5 in `CHALLENGE_QUESTIONS`. Selecting Reshape IS the `reject` path - reinterview to Step 0, counts as one backward edge per the Backward-Edge Budget section below. No new source of backward edges.

**Mapping Approve/Revise/Reshape to existing branches**:
- **Approve** -> proceed to Step 6.
- **Revise** -> rerun planner with `<REPLAN_REASON>` = `BLOCKERS`; one backward edge.
- **Reshape** -> reinterview from Step 0; one backward edge (equivalent to challenger `reject`).

## Backward-Edge Budget

Cap: **2 cumulative backward edges per task.** Backward edges revisit a prior step; they're distinct from in-step loops.

Counts toward the budget:
- `plan-challenger` verdict `revise` → planner rerun
- `plan-challenger` verdict `reject` → reinterview
- implementer kickback (`plan-patch` | `replan` | `reinterview`)
- re-classify after clarify when scope moves

Does **not** count (separate budget of 2):
- fixer self-heal rounds
- reviewer reruns during self-heal

Does **not** count (free, no cap beyond per-stage limits):
- intent loop (Step 0 Level 2 re-runs)
- clarify loop (Step 3 re-runs)
- investigator MISSING_INFO loop (Step 2 on bias=diagnose, re-launch with refreshed framing)

At the cap, stop and surface state to the user - don't loop silently.

## Input Template Contract

Every agent receives inputs via a tagged-slot template defined in its own definition file. The main agent fills slots verbatim from predecessor output - no paraphrase.

Every template:
- names each required slot with an XML-style tag (e.g. `<CONFIRMED_INTENT>`, `<PREFLIGHT>`, `<APPROVED_PLAN>`)
- states the source agent and the expected content for each slot
- the agent's first step parses required slots; on a missing required slot it emits `INPUT_ERROR: missing <slot>` and stops

Output wrapping: agents emit structured blocks named with XML-style tags that successors reference (e.g. `<APPROVED_PLAN version="N">`, `<CLARIFY_OUTPUT>`). This makes relay mechanical and enables re-injection after compaction.

## Compaction

After compaction, a `SessionStart` hook reads the transcript for the highest-version `<APPROVED_PLAN>`, `<CONFIRMED_INTENT>`, `<CLARIFY_OUTPUT>`, `<CLASSIFICATION>`, and re-injects them into the post-compact session.

What still needs manual preservation in the conversation: current workflow step, gate results so far, unresolved self-heal findings, backward-edge count. Canonical state (intent / plan / classify / clarify) re-injects itself.

Discard: raw exploration output, full file contents already acted on, superseded plans.

## Code Quality
- Use the project's formatter.
- Failing tests → fix the code, keeping assertions and coverage intact.
- Delete dead code: unused functions, stale imports, obsolete files.
- Search for existing patterns before writing new ones. Reuse beats reinvention.
- Improve the area you're touching: dead code, stale abstractions, obvious simplifications.

## Changelog Style

The CHANGELOG.md entries and the README's "Latest updates" section follow the same rules. They are a user-facing summary, not implementation notes.

**Shape by release type:**
- **Patch** (X.Y.Z, Z > 0): bullets only. No intro.
- **Minor** (X.Y.0): one intro paragraph framing the release theme, then bullets.
- **Major or initial release** (X.0.0, or 0.1.0): several intro paragraphs giving the wider arc, then bullets.

**Per-bullet rules:**
- **One line per bullet.** No multi-sentence run-ons, no parentheticals stacking up. If it doesn't fit on one line, the bullet is too long.
- **Outcome only.** What changes for the person using this. Not how it works inside.
- **No internal terms.** No step numbers, no agent names, no axis names, no flag names. If a stranger wouldn't recognize the word, drop it.
- **No clever framing.** No "Misread X? Reshape Y." rhetorical asides. No "but", "also", "instead". State the change and stop.
- **Bullets cap at four per release.** If you have more, you have too many.

README's "Latest updates" mirrors the CHANGELOG entry verbatim - same wording, same bullet count.

## Reviewer Contract

Shared rules for every specialized reviewer (correctness, quality, architecture, security, performance, accessibility, design-consistency, ux, consistency, structure, reuse). Each reviewer's own file carries only its Criteria list and any specialization - the rest lives here.

### Confidence tagging (reviewer reporting threshold)

Tag each finding `[likely]` or `[unsure]` per the "Confidence Tagging" rules above.

**Reporting threshold:** report `[likely]` findings unconditionally. Report `[unsure]` only when impact is high - correctness, security, or data risk (correctness-reviewer priority tiers 1-2). Skip speculative low-impact findings.

### Standard inputs

Every reviewer receives inputs via a tagged-slot template defined in its own file. Every template defines at minimum:

```
<TOUCHED_FILES>{file paths the implementer modified or created - sourced from implementer's FILES_MODIFIED + FILES_CREATED, or from main-agent session edits on S/M tasks}</TOUCHED_FILES>
```

Reviewers Read those files directly to inspect current state. Reviewers that need more declare the additional slots in their template (acceptance-reviewer: `<CONFIRMED_INTENT>` + `<APPROVED_PLAN>`; structure/consistency/reuse-reviewer: `<APPROVED_PLAN>` for scope judgment; plan-adherence-reviewer: `<APPROVED_PLAN>`).

**First step for every reviewer**: parse required slots. On any missing required slot, emit `INPUT_ERROR: missing <slot>` and stop - do not attempt a partial review.

Main agent fills slots verbatim from predecessor output. No paraphrase.

### Base output format

```
VERDICT: [pass | fail | warn]
FINDINGS:
- [likely|unsure] [file_path:line] - [issue and why it matters]
(empty if pass, max 5 issues, [likely] findings first)
ACTION_NEEDED: [specific fixes, or "none"]
```

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

### Discoveries

Every reviewer (and implementer, fixer, investigator, design-explorer) appends a `DISCOVERIES` block as the last section of its output. This is the channel for novel project-context items the agent noticed in passing while doing its primary job - terms that should be canonical, drift from the declared stack or intent. Step 10 (Capture) aggregates these and offers them to the user.

**Exception - non-emitters:** accessibility-reviewer, ux-reviewer, and design-consistency-reviewer do not emit DISCOVERIES - their scope is WCAG/visual/UX checks, not domain content. test-verifier, plan-adherence-reviewer, reuse-reviewer, and acceptance-reviewer also do not emit DISCOVERIES (mechanical/blueprint-fidelity/duplication-check/intent-fulfillment respectively, not domain-novelty surfaces).

Three buckets, each terminated with `(none)` when empty:

```
DISCOVERIES:
  glossary:
    - [term] - [one-sentence definition] - [why novel]
    (or "(none)")
  stack_drift:
    - [layer] - [deviation] - [evidence file:line]
    (or "(none)")
  intent_drift:
    - [aspect] - [deviation] - [evidence file:line]
    (or "(none)")
```

**Novelty bar:** the item must NOT already be covered by the loaded `PROJECT_CONTEXT`. Skip anything you can find in `GLOSSARY.md`, `STACK.md`, or `INTENT.md`. When in doubt, skip - capture-agent does the final dedup, but you don't need to dump candidates the agent will only have to filter out.

The block is mandatory even when every bucket is empty. Emit all three bucket headings with `(none)` so the parser sees a structured block.

### Example output (consistency-reviewer)

```
VERDICT: warn
EXAMPLES_COMPARED: src/features/reports/controller.ts, src/features/users/controller.ts
FINDINGS:
- [likely] src/features/items/controller.ts:22 - returns `{ data, meta }` but every other controller returns the bare array. Align with reports/users.
- [likely] src/features/items/service.ts:8 - `get_item` (snake_case) diverges from camelCase used elsewhere in the module.
ACTION_NEEDED: Change return shape to bare array; rename `get_item` to `getItem`.
DISCOVERIES:
  glossary:
    (none)
  stack_drift:
    (none)
  intent_drift:
    (none)
```
