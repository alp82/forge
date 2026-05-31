# Global Development Rules

## Principles
- Never guess, never assume, never improvise unagreed solutions.
- Extracting actual intent is more important than moving fast.
- Research before asking. Subagents exhaust filesystem, tools, and web first; questions only surface what those sources don't already answer.
- Clarify in loops, not single passes. Intent and clarification steps re-run with prior rounds folded in until the latest exchange surfaces no new aspects. Loops within one step are free and do not count as backward edges.
- Leave touched code better than you found it. Unrelated changes get their own task.
- No TODOs, placeholders, or incomplete implementations.
- No backwards compatibility. Obsolete code gets deleted, not preserved.
- No unnecessary comments, docstrings, or type annotations on unchanged code.
- Always use the editor's dedicated file operation tools. When an edit fails, fix the edit - never fall back to shell commands (sed, awk, python scripts) for file manipulation.
- Searching, portably: use whatever the environment offers - the Grep/Glob tools, or `rg`/`grep`/`find` via Bash - and let the search tool expand patterns, not the shell. Always quote globs (`rg -g "*.md"`, `find . -name "*.md"`) so the same command works in bash, zsh, or fish.

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
- Subagents return structured verdicts (VERDICT/FINDINGS/ACTION_NEEDED), not raw dumps. A return is the agent's *conclusion*, not its transcript: the wrapped output block its definition specifies, nothing more. No narration of what it read, no step-by-step of how it searched, no restating the inputs back. The orchestrator relays only what the next stage or the user needs; everything else stays in the subagent and is recovered by re-reading its output only if a later stage calls for it. A verbose return is a defect - it burns the main context the orchestrator exists to protect.
- Spawn dynamic subagents when the situation calls for it. Pick the cheapest model that can handle the job (fast/small for classification, mid-tier for analysis/implementation, top-tier only when truly needed).

## Subagent Context Inheritance

MEMORY.md + linked files don't transfer to subagents automatically - they inherit nothing. Neither do project-level docs.

The alp-river plugin's **PreToolUse(Agent) hook** (`user-context-injector`) handles all three. It prepends up to three blocks to the Agent prompt:

- `## USER_CONTEXT` - MEMORY.md + linked files (durable user preferences and feedback).
- `## PROJECT_CONTEXT` - matching slices of the project's `docs/` folder (intent, stack, glossary, ADRs).
- `## PSYCHOLOGY` - the persona block resolved per-agent via `psychology/agent-map.json` (opt-in voice and disposition shaping).

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

See `doctrine/confidence-tagging.md` - injected into citing agents by the PreToolUse(Agent) hook.

## Pipeline

Every code-modifying request runs through a **composed route**. The deterministic router (`hooks/route.py`) assembles the exact stages a task needs from the catalog (`generated/catalog.json`, compiled from `agents/*.md` frontmatter - see `doctrine/CATALOG.md` and `doctrine/SIGNALS.md`) and grows or shrinks it as the task reveals itself. There is no per-tier step list; size (XS-XXL) is a *readout* of the assembled route, not a driver.

**No exception for prompts that feel small** - a trivial ask just produces a tiny route (often one stage). Code-modifying requests enter the loop regardless of perceived size.

### The loop

The main agent is a thin orchestrator. It holds four pieces of run state and turns the crank:

- `live` - signal topics currently emitted (seeded with `request-received`).
- `available` - artifacts that exist (seeded with `request`).
- `ran` - stages already executed.
- `premises` - the assumptions the current route was built on; each stage is handed these and reports breaks.

Each turn:

1. **Route.** Call the router **once** on the current state; it returns the ordered route + size + `triggered_by` (which signal pulled each stage in). This single call is also the recompose - step 4 updated the state at the end of the previous turn, so a freshly published signal grows the route here, a `scope-shift` reshapes it, and sticky stages persist (never auto-dropped). One router call per turn, not two. JSON in, JSON out:
   ```
   echo '{"live":[...],"available":[...],"already_run":[...]}' | python3 hooks/route.py
   ```
   The router rejects an unrecognized top-level key (a typo like `liv` for `live`): it writes the offending key to stderr and exits nonzero rather than silently dropping it and returning an empty route, so a malformed call is never mistaken for convergence.
2. **Render.** Show the route as inline markdown - emit it directly from state, no script, no Bash. Render **every turn** so progress is never invisible: the full route on the first turn and at any gate (legibility A), the delta on a plain recompose (legibility B). This is a status surface, not a question - it never interrupts; asking the user is what a gate stage does when it runs (step 3, see `## Gates`). Formats:
   - **Full (A)** - a header `path · size · N stages`, then one line per stage `• name ← #signal-that-pulled-it-in`, marking the running stage (`▶`), done stages (`✓`), held stages (`🔒 name (held until #until-signal)`), and `[sticky]` guards. The render composes `route` + `held` so a gated stage stays visible. Example:
     ```
     build · M · 5 stages
       ✓ triage
       ▶ reuse-scanner ← #needs-tests
       • planner ← #clarified
       🔒 implementer (held until #tests-ready)
       • correctness-reviewer ← #code-written
     ```
   - **Delta (B)** - lead with the why (the new signal's message), then `+added / -removed (now size/N)`. Example: `+security-reviewer ← #auth-surface (now L/6)`.
3. **Run** the next not-yet-run stage in route order. Held stages are NOT in `route` - a lock keeps a held stage out of the dispatch list until its `until` signal fires (see `## Locks`). Spawn the running stage's agent (the `model` lives in the agent's frontmatter); hand it the artifacts its `input` names, plus the `premises`. Pass each input as the **verbatim output** of the stage that produced it, never paraphrased, stubbed, or hand-written (Input Template Contract); if an `input` does not exist yet its producer has not run, so run the producer - **never fabricate a predecessor's artifact** to start a dependent stage early, which only forces the downstream stage to redo the missing work and degrades its output. Stages that share inputs but feed none of each other - the review fan-out over `@diff` is the canonical case - may run in one parallel batch; a stage whose `input` is another stage's `output` waits for that producer to return. Parallelism is for independent stages only; the `input`/`output` precedence graph is the one rule never bent (`doctrine/CATALOG.md`). Spawn each stage at the cheapest model its frontmatter allows, and expect a **structured return, not a transcript** (Context Discipline) - the agent's wrapped output block is the artifact; its reasoning and reads stay behind it. Do not paste a subagent's full output into the conversation; surface only the line(s) the render, the next stage, or a gate actually needs.
4. **Update.** Add the stage's `output` to `available`, its published signals to `live` (each carries a one-line message = the why), and record it in `ran`. A published `scope-shift` logs a broken premise. These updates are the state the next turn's step 1 recomposes from.

Repeat until **convergence**: the router returns an empty route (no live signal triggers an unrun stage) and every review lens that ran came back `clean`.

### Seed and path

The route is rooted by the always-on `triage` stage. It reads the request and publishes exactly one **path** - `build`, `spike`, or `talk` - plus early signals (`ambiguous`, `novel-domain`, a bug-framing `bug`, risk sniffs) and one advisory `est-size:<tier>`. The router composes from there. The path is sticky but re-evaluated every turn: `talk` flips to `build` on "do it"; a `spike` graduates to `build` on the kept code.

- **`build`** - the full composed route. A bug is a build: `triage` pairs `build` with a `bug` signal, the `investigator` diagnoses inside the route, and the build spine fixes the cause. There is no separate `diagnose` path. The implementer carries a `{while:#needs-tests, until:#tests-ready}` lock (the TDD gate, see `## Locks`): on a logic change `triage` publishes `#needs-tests`, so the implementer holds until `test-review` publishes `#tests-ready` after validating the red tests; a trivial change carries no `#needs-tests`, so the lock is inactive and the implementer runs straight off the plan.
- **`talk`** - the spine is parked; the `discuss` stage converses - options with worked examples, honest tradeoffs, one sharp question, never code. Recon stages (research, investigator, reuse-scan, design-explorer) stay summonable on demand, but nothing produces a `diff` and nothing is reviewed or captured.
- **`spike`** - sandboxed throwaway (`.prototypes/`). `spike-build` runs relaxed; the build-only ceremony band (challenge, capture, plan-adherence, the quality/architecture/consistency lenses) is filtered off the path by each stage's `routes`. Correctness and security still apply. Graduating flips to `build`.

`est-size` is advisory only: it feeds the cost gate's upfront estimate and never picks stages. The real size stays the final route count.

### Worked routes

Four `echo STATE | python3 hooks/route.py` traces:

- **build** - `{"live":["build","needs-tests","code-written","ui-touched","run-visual","auth-surface"],"available":["confirmed-intent","diff"]}` composes `reuse-scanner` + `health-checker`, the full review fan-out (correctness, quality, architecture, structure, consistency, performance, reuse, acceptance, plan-adherence, test-gap, test-verifier, ux, accessibility, design-consistency, visual), `security-reviewer` pulled in by `auth-surface`, and `capture-agent`. `ui-touched` (emitted because the diff touches UI) pulls the UI lenses; `run-visual` opts into `visual-verifier`. Size XXL.
- **trivial build** - `{"live":["build"],"available":["request","triage-read","confirmed-intent"]}` composes `planner`, then `implementer` (its TDD lock inactive - no `#needs-tests` is live) + `correctness-reviewer` once a diff exists. Size S. None of the deep lenses, pre-flight, clarify, test-chain, challenge, or capture join - they wait on `#needs-tests`.
- **spike** - `{"live":["spike","code-written"],"available":["confirmed-intent","diff"]}` composes just `spike-build` then `correctness-reviewer`; the 15 build-only lenses are dropped `off-path` by the `routes` filter. Size S.
- **talk** - `{"live":["talk","ambiguous"],"available":["request","triage-read"]}` composes `interviewer` (pulled by `ambiguous`) then `discuss`, ordered after it because `discuss` optionally consumes the interviewer's `confirmed-intent`. No diff, nothing reviewed.

### Intent

`triage` settles framing. When the request is clear, **state the one-line interpretation and proceed** - no confirmation gate; the user corrects in their next message if it is wrong. `triage` mints `@confirmed-intent` on a clear build, so its pre-flight is satisfied without the interviewer. When `triage` publishes `ambiguous` (any genuine doubt - low bar), the `interviewer` stage joins and loops until intent is confirmed. Intent is always *stated*, never silently assumed (see Principles), but a clear ask is not stopped.

### Gates

A gate is a stage whose output is a **user decision**, rendered via `AskUserQuestion` (Concise Surfacing Contract). It fires only when its triggering signal is live AND the answer could change what happens next - a 95%-Continue checkpoint is narrated, not asked. The user's choice publishes a signal (`approved` / `scope-down` / `abandon` / ...) that feeds the next recompose. A size-threshold crossing (`size-crossed:L`) is itself a signal a cost gate can subscribe to.

### Asymmetric rigor

Skipping a stage needs a positive signal; adding one needs only doubt. Safety and clarify stages carry `guard: sticky` or fire on any risk sniff - in by default, dropped only on strong signal. A needless question costs mild annoyance; a wrong assumption costs the task.

## Model Tiering

Each stage declares its own `model` in agent frontmatter - `opus` for planning and
judgment, `sonnet` for analysis and implementation, `haiku` for classification and
lookups. The router spawns each stage at its declared model; there is no per-tier override
table. Swap a specific agent's voice under `alpRiver.psychologyOverrides`, or change its
`model` in frontmatter.

## Clarification Loops

The `interviewer` and `requirements-clarifier` stages run as loops, not single passes -
depth scales with the unknowns still lurking. Each loops *internally* (the route sees one
stage) until its exit criteria hold:
1. VERDICT is `confirmed` (interviewer) or `clear` (clarifier).
2. `NEW_ASPECTS_FOUND: no`.
3. The user has no further additions.

**Cap**: 5 rounds per stage; at the cap, present the latest state and ask the user to
confirm or reshape - never loop silently. Re-invocations carry `<PRIOR_ROUNDS>` (a
compressed Q&A log) so the agent tells new aspects from reaffirmations and never re-asks
what is settled. Before asking, the agent exhausts filesystem and web sources and reports
`LOOKUPS_PERFORMED`; if research already answers a question, it drops it. Internal loops
are free - convergence, not a budget, governs the route.

## Concise Surfacing Contract

**Purpose**: inline prose stays only for decisions. Multi-option choices render through
`AskUserQuestion` so the reasoning lives in `description`/`preview`, not inline. Recon
notes and round-over-round restatements stay in subagent output - the user opens them by
scrolling.

**MUST-render rule**: when a gate stage is triggered (its signal is live) AND the answer
could change the outcome, the orchestrator MUST invoke `AskUserQuestion` rather than render
options as prose. When no picker-eligible item is open and the stage's exit criteria hold,
proceed without prompting. A single-question single-select auto-submits - expected.
`triage`'s one-line intent restatement is plain text, not a picker; confirm/correct needs
no ceremony.

**Picker-eligible sources**: `interviewer` and `requirements-clarifier` (`QUESTIONS`, open
`DEFERRED_QUESTIONS`, promoted `[unsure]` criteria or assumptions); `design-explorer`
(`PARAMS_TO_CONFIRM`); `plan-challenger` (`CHALLENGE_QUESTIONS`); and any gate stage whose
output is a user decision (the cost check on `size-crossed:<tier>`, continue/stop after a
diagnosis or a plan, the visual-verify offer, capture's per-item approvals).

**Question schema**: `question` (text), `header` (max 12 chars), `multiSelect`, `options`
(2-4; each `label`, `description`, optional `preview`).

**Description vs. preview**: `description` carries the essence plus, for any non-trivial
decision (one that sets a value, data shape, behavior, or UI result), one concrete example
of what the choice produces (e.g. `wrapped -> {users:[...]}` vs `bare -> [...]`). The
example is load-bearing - lead with it, cut hedges to make room. Bare yes/no and fixed
process gates (Continue/Stop, Approve/Revise/Reshape) are exempt. `preview` is best-effort
enrichment; never put load-bearing content there. The CLI supplies the "Other" escape -
agents MUST NOT synthesize their own.

**4-question cap + DEFERRED priority queue**: `AskUserQuestion` takes 1-4 questions. With
more than 4 eligible items, fill the slots in order - open `QUESTIONS`, then `[unsure]`
criteria, then `[unsure]` assumptions - and roll the rest into `DEFERRED_QUESTIONS`,
preserving order. Deterministic and re-runnable. `DEFERRED_QUESTIONS` rides inside
`<CLARIFY_OUTPUT>` so it survives compaction; the orchestrator threads still-open items into
the next round's `<PRIOR_ROUNDS>`.

**Challenger reshape**: `plan-challenger`'s `CHALLENGE_QUESTIONS` carry Approve (proceed) /
Revise (rerun planner with `BLOCKERS`) / Reshape (back to intent). `SCOPE_MISMATCH` surfaces
inline alongside `BLOCKERS` and in the Reshape option's `preview`.

## Convergence

There is no edge budget. A route runs until it converges: the router returns no triggered
unrun stage and every lens that ran is `clean`. The only loop guard is oscillation - a
`scope-shift` that re-fires without resolving is surfaced to the user, not retried
silently. See `## Pipeline` > The loop.

A *missing* output block is not convergence: when a spawned stage returns no wrapped output, the orchestrator treats it as a failure - re-dispatch the stage or surface the gap to the user, never wait silently for an artifact that is not coming.

A `#needs-tests` published late - e.g. by `correctness-reviewer` on a cheap-path build -
does NOT re-hold the already-run implementer (the loop skips `already_run`). It escalates
review depth: the late signal pulls the test chain and the deep lenses in to retroactively
test and scrutinize the existing diff.

## Locks

A stage may declare a scheduling gate in frontmatter:

```yaml
lock:
  - while: '#needs-tests'
    until: '#tests-ready'
```

A lock has three states:

- **Inactive** - `while` is not live. The lock does nothing and the stage runs normally.
  This is the cheap path.
- **Held** - `while` is live and `until` is not yet published. The stage is kept OUT of
  `route` (the dispatch list) and reported in a separate `held` map keyed by the unmet
  `until` signals. A held stage produces no output, so any downstream consumer left without
  a producer is dropped too.
- **Released** - `until` goes live. The lock clears and the stage rejoins the route.

Multiple locks **AND** together (every one must be inactive or released for the stage to
run). `while` and `until` match on family prefix, like every other signal. A lock is a
**scheduling gate, not a data input** - it gates *when* a stage may run, never *what* it
reads.

The implementer's `{while:#needs-tests, until:#tests-ready}` lock is the **TDD gate**. On a
logic build `triage` publishes `#needs-tests`, so the implementer is held until `test-review`
publishes `#tests-ready` after validating the red tests - code cannot start against
unvalidated tests. A trivial change carries no `#needs-tests`, so the lock is inactive and
the implementer runs straight off the plan.

## Input Template Contract

Every agent receives inputs via a tagged-slot template defined in its own definition file. The main agent fills slots verbatim from predecessor output - no paraphrase.

Every template:
- names each required slot with an XML-style tag (e.g. `<CONFIRMED_INTENT>`, `<PREFLIGHT>`, `<APPROVED_PLAN>`)
- states the source agent and the expected content for each slot
- the agent's first step parses required slots; on a missing required slot it emits `INPUT_ERROR: missing <slot>` and stops

Output wrapping: agents emit structured blocks named with XML-style tags that successors reference (e.g. `<APPROVED_PLAN version="N">`, `<CLARIFY_OUTPUT>`). This makes relay mechanical and enables re-injection after compaction.

## Compaction

After compaction, `hooks/reinject-canonical-state.sh` re-anchors the workflow pointer plus
the canonical run state: the current `<ROUTE>`, `<LIVE_SIGNALS>`, `<AVAILABLE_ARTIFACTS>`,
and `<PREMISES>`. The router recomputes the route from those, so resumption is
deterministic. Preserve manually only what is not in those blocks: the stage currently
mid-run and any gate awaiting the user.

## Code Doctrine

See `doctrine/code-doctrine.md` - injected into planner, implementer, and plan-challenger by the PreToolUse(Agent) hook.

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

See `doctrine/reviewer-contract.md` (and `doctrine/discoveries.md` for the Discoveries channel) - injected into reviewers and the DISCOVERIES-emitting agents by the PreToolUse(Agent) hook.
