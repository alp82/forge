# Global Development Rules

## Principles
- Never guess, never assume, never improvise unagreed solutions.
- Name the unknowns. When the filesystem, tools, and web don't yield a fact you need, list what you couldn't determine rather than leaving the gap implicit.
- Say when you don't know. "I couldn't confirm X" is a complete answer; silent confidence on an unverified point is the failure to avoid.
- Extracting actual intent is more important than moving fast.
- Research before asking. Subagents exhaust filesystem, tools, and web first; questions only surface what those sources don't already answer.
- Clarify in loops, not single passes. Intent and clarification steps re-run with prior rounds folded in until the latest exchange surfaces no new aspects. Loops within one step are free and do not count as backward edges. This is a convergence loop, distinct from a correction revision - see `## Revision Contract` for the mechanism behind both.
- Leave touched code better than you found it. Unrelated changes get their own task.
- No TODOs, placeholders, or incomplete implementations.
- No backwards compatibility. Obsolete code gets deleted, not preserved.
- No unnecessary comments, docstrings, or type annotations on unchanged code.
- Always use the editor's dedicated file operation tools. When an edit fails, fix the edit - never fall back to shell commands (sed, awk, python scripts) for file manipulation.
- Searching, portably: prefer the Grep and Glob tools whenever they are granted - they never shell-parse the path or pattern, so filenames and patterns with shell-special characters just work. Let the search tool expand patterns, not the shell. Fall back to `rg`/`grep`/`find` via Bash only when those tools are not available (the orchestrator in some sessions) or when you genuinely need a pipe. When you do use Bash, quote globs (`rg -g "*.md"`, `find . -name "*.md"`) so the same command works in bash, zsh, or fish.

## Tone
- No corporate phrasing or fake contrast framing ("While X is important, Y...").
- No sycophancy. If an idea is weak, say so and explain why.
- Wit and sarcasm welcome when they land. Don't force it.
- Be direct. Say what you mean.

## Formatting
- No preamble or postamble. Start with the answer, end when the answer ends. No "I'll now...", "Let me...", "Here's what I found:", "Hope this helps."
- Status updates between tool calls: one sentence, fragments OK - reserved for user-facing decision points and surfaced results, not for narrating mechanism. "Reading the config." not "Let me take a look at the configuration file." The pipeline loop is card-only: the render card is the status surface for route/recompose, so the orchestrator does not narrate route/render/read-contract/spawn/recompose mechanics inline.
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

Each turn (the loop is **card-only**: the render card carries the why, mechanism reasoning stays in the thinking block, and the orchestrator narrates none of the route/render/read-contract/spawn/recompose mechanics inline - the reserved inline-prose bucket is `triage`'s one-line restatement, gate questions, and surfaced findings, errors, stalls, and scope-shifts the loop must not swallow):

1. **Route.** Silently call the router **once** on the current state; it returns the ordered route + size + `triggered_by` (which signal pulled each stage in). This single call is also the recompose - step 4 updated the state at the end of the previous turn, so a freshly published signal grows the route here, a `scope-shift` reshapes it, and sticky stages persist (never auto-dropped). One router call per turn, not two. JSON in, JSON out:
   ```
   echo '{"live":[...],"available":[...],"already_run":[...]}' | python3 hooks/route.py
   ```
   The router rejects an unrecognized top-level key (a typo like `liv` for `live`): it writes the offending key to stderr and exits nonzero rather than silently dropping it and returning an empty route, so a malformed call is never mistaken for convergence.
2. **Render.** Show the route as **native markdown** - emit it directly from state, rendered (not fenced), no script, no Bash. The card is **never wrapped in a ``` code fence**: a fence would trap the emoji markers and the Plan Breakdown as raw monospace and is exactly the bug this format avoids. The render card IS the narration for the route/recompose; there is no separate inline play-by-play. Render **every turn** so progress is never invisible: the full route on the first turn and at any gate (legibility A), the delta on a plain recompose (legibility B). This is a status surface, not a question - it never interrupts; asking the user is what a gate stage does when it runs (step 3, see `## Gates`). Formats:
   - **Full (A)** - a header `path · size · N stages`, then one line per stage `• name ← #signal-that-pulled-it-in`, marking running stages (`▶`), done stages (`✓`), held stages (`🔒 name (held until #until-signal)`), and `[sticky]` guards. The markers always render natively. The router returns `waves` (the topo levels); stages in one wave share no precedence edge and dispatch as a single parallel batch, each marked `▶`. The render composes `route` + `held` so a gated stage stays visible. At a plan-approval gate the card also carries the producer's Plan Breakdown as a short **Plan breakdown** section beneath the stage lines. Example, emitted exactly as this native markdown (no fence) - a caption, then a real markdown list, then a bold label and the breakdown as plain prose:

     *code · M · 5 stages*

     - ✓ triage
     - ▶ reuse-scanner ← #significant-build
     - • code-planner ← #clarified
     - 🔒 code-implementer (held until #tests-ready, #plan-approved)
     - • correctness-reviewer ← #code-written

     **Plan breakdown** - Adds a per-user rate limit so one client can't flood the API: each request checks a small counter and is waved through or held. request -> [counter < 100?] -> allow / 429.
   - **Milestone layer** - during a milestone-loop build the card adds a colored milestone-status layer atop the existing stage markers, also native markdown: a `milestone k of N` header and the milestone list marked `🟩` (verified) / `🟨` (building) / `🟥` (pending). These markers are **always included and render natively**. The stage lines keep their own `▶ ✓ 🔒 •` markers underneath. See `## Milestone loop` for when the loop engages and what each milestone reviews.
   - **Delta (B)** - lead with the why (the new signal's message), then `+added / -removed (now size/N)`, emitted as a native-markdown line (no fence). Example, the line as emitted: `+security-reviewer ← #auth-surface (now L/6)`.
   - **Timing readout (C)** - rendered **once, at convergence** (see `## Convergence` > Run-timing readout for the trigger and how durations are measured). Native markdown, no fence, same as every other card. Layout: a header line `Run complete - <total> total`, then one indented line per banner group that ran `<emoji> <Group>  <time>`, using the **existing 7-group banner vocabulary and its stage groupings from README's "Stages" > "Code" section** (🔎 Intent / 🧭 Scout / 📐 Blueprint / 🧪 Tests / 🔨 Build / 🔬 Review / 📓 Document) - do not restate the per-stage mapping here, it is owned there.
     - **Total (always shown)** = wall-clock from the first stage's dispatch to convergence.
     - **Per-group breakdown (shown when useful)** = sum of the `duration_ms` of the stages that fall in each group; list only groups that actually ran. "Useful" = more than one group ran (a one-stage route shows only the total - there is nothing to break down).
     - **Per-milestone (only when the milestone loop ran)** = above the group breakdown, one line per milestone `milestone k of N - <time>`, summing the `duration_ms` of the stages dispatched within that milestone. Omit this block entirely on a single-pass build.
     - Format durations human-readable: `<m>m <ss>s` at/above a minute, `<s>s` below (e.g. `4m 12s`, `41s`).
3. **Run** the next not-yet-run stage in route order. Held stages are NOT in `route` - a lock keeps a held stage out of the dispatch list until its `until` signal fires (see `## Locks`). Silently spawn the running stage's agent (the `model` lives in the agent's frontmatter) and silently read its input contract; hand it the artifacts its `input` names, plus the `premises`. Pass each input as the **verbatim output** of the stage that produced it, never paraphrased, stubbed, or hand-written (Input Template Contract); if an `input` does not exist yet its producer has not run, so run the producer - **never fabricate a predecessor's artifact** to start a dependent stage early, which only forces the downstream stage to redo the missing work and degrades its output. When several stages each produce the same artifact (the three domain prototypers all emit `@prototypes`), concatenate each firing producer's verbatim output into that one SCOUT `<prototypes>` slot - never pick one and drop the rest. Stages that share inputs but feed none of each other - the Review wave over `@diff` is the canonical case - may run in one parallel batch; a stage whose `input` is another stage's `output` waits for that producer to return. Parallelism is for independent stages only; the `input`/`output` precedence graph is the one rule never bent (`doctrine/CATALOG.md`). Spawn each stage at the cheapest model its frontmatter allows, and expect a **structured return, not a transcript** (Context Discipline) - the agent's wrapped output block is the artifact; its reasoning and reads stay behind it. Do not paste a subagent's full output into the conversation; surface only the line(s) the render, the next stage, or a gate actually needs. **Hang-prone stages run in the background.** Stages that do network I/O or hold a tool budget - the researcher, the investigators, web-using reviewers like security-reviewer, and every parallel review wave (one hung member otherwise freezes the batch) - are hang-prone, and so are the side-effecting stages (`code-implementer`, `fixer`, `test-author`, `system-executor`): a stage that edits the tree can stall mid-write, and backgrounding it is safe because the working tree it leaves behind is exactly the durable record `## Recovery` reconciles from. The orchestrator dispatches each with background Agent dispatch (`Agent(run_in_background: true)`), keeps its task handle, and watches it two ways: a completion push (the task's own finish notification) is the normal end, and a watchdog catches the stage that never pushes - it `stat`s the agent's transcript for an mtime freeze (no size or mtime change for ~120s; it never reads the transcript content, only its file metadata) and also holds an absolute wall-clock deadline as the hard ceiling. Whichever fires first, it stops the task (`TaskStop(task_id)`) and treats it as a missing output. Cheap deterministic stages (triage, the router call) run in the foreground as before. **This is the one case where a stage spans turns:** a backgrounded stage does not complete in the turn it is dispatched. The orchestrator dispatches it, keeps cranking the loop - render and recompose per steps 1-2 - while it runs, and reaps it when its completion notification lands or its deadline fires; the watchdog reap *is* that deadline check. Reconcile with "run the next not-yet-run stage" above: a backgrounded stage is dispatched-and-awaited across turns, not run-to-return inside one turn. On a breach - mtime freeze or absolute deadline - `TaskStop` it and treat it exactly as a missing output, recovered per `## Recovery`: a read-only stage re-dispatches (bounded one retry, then surface), and a side-effecting stage reconciles from the working tree it left behind rather than re-running blind. That read-only re-dispatch is the same stage re-run, not a scope-shift, so it is not a backward edge and is bounded like the oscillation guard - one retry, then surface. A background stage in flight must also survive compaction or be recoverable: `hooks/reinject-canonical-state.sh` does not persist a live task handle, so a handle lost to compaction is a missing output - recovered by the same `## Recovery` branch for the mid-run stage (`## Compaction` already flags the mid-run stage for manual preservation). Where a runtime lacks background Agent dispatch, run the stage in the foreground and lean on the agent's OWN tool budget as the sole cap - the partial-return rule each web-using hang-prone agent carries. A synchronous foreground subagent holds the orchestrator until it returns, so the cap lives inside the agent and the missing-output rule catches an empty or explicitly-partial RETURN. Foreground is the degraded fallback: the cap rides inside the agent rather than in a mid-run watchdog.
4. **Update.** Silently add the stage's `output` artifacts to `available`, its published `#signals` to `live` (each carries a one-line message = the why), and record it in `ran`. The two are different keys, never conflated: `triage`'s artifact `@confirmed-intent` lands in `available`, while its signal `#intent-confirmed` lands in `live`. A published `scope-shift` logs a broken premise. For a reviewer, the published signal is read from the explicit `SIGNALS_PUBLISHED:` token inside its output (see `doctrine/reviewer-contract.md` ### Published-signal line), not inferred from VERDICT prose. These updates are the state the next turn's step 1 recomposes from.

Repeat until **convergence**: the router returns an empty route AND an empty `held` map (no live signal triggers an unrun stage, no stage is waiting on an unmet `until`) and every Review lens that ran came back `clean`. A lens "came back `clean`" is read from its explicit `SIGNALS_PUBLISHED:` token (`doctrine/reviewer-contract.md` ### Published-signal line), NOT inferred from VERDICT prose. A non-empty `held` map is never convergence - it is either a pending plan-approval the orchestrator owes (emit/surface it, see `## Convergence` > Stall guard) or, on `#abandon`, a dropped stage.

### Seed and path

The route is rooted by the always-on `triage` stage. It reads the request and publishes exactly one **path** - `talk`, `sketch`, `code`, or `system` - plus early signals (`ambiguous`, `novel-domain`, a bug-framing `bug`, risk sniffs) and one advisory `est-size:<tier>`. The router composes from there. The path is sticky but re-evaluated every turn: `talk` flips to `code`/`system` on "do it"; a `sketch` graduates to `code`/`system` on the kept work.

A path is defined by **what it leaves behind**: `talk` leaves nothing, `sketch` leaves a throwaway artifact in a sandbox, `code` leaves a reviewed change in the codebase, `system` leaves a verified change to the machine.

- **`talk`** - inline-first. The main agent answers directly and reads freely (reads never prompt); the path is parked. The only moves that ask first are the expensive ones - spawning a recon subagent (`discuss`, `researcher`, an investigator, `design-prototyper`) or producing a diagram/visual - each a one-tap confirm. Nothing produces a `diff`, nothing is reviewed or documented.
- **`sketch`** - sandboxed throwaway (`.prototypes/`) in any medium: a code tracer-bullet (`sketch-build`), a diagram, a UI mockup, an idea sketch. Runs relaxed; the code-only ceremony band (challenge, Document, plan-adherence, the quality/architecture/consistency lenses) is filtered off the path by each stage's `routes`. Correctness and security still apply. Graduating flips to `code`/`system`.
- **`code`** - the full composed route. A bug is a code build: `triage` pairs `code` with a `bug` signal, the `code-investigator` diagnoses inside the route, and the code path fixes the cause. There is no separate `diagnose` path. Two independent axes shape a code build: `#needs-tests` (the TDD axis - a change carrying real logic) and `#significant-build` (the review-depth axis - a serious build that pulls Scout and the deep lenses). The `code-implementer` carries two locks (see `## Locks`): the TDD gate `{while:#needs-tests, until:#tests-ready}` - on a logic change held until `test-review` publishes `#tests-ready`, inactive on a trivial change - and the unconditional plan gate `{while:#plan-ready, until:#plan-approved}`, which holds it on every code build until the plan is approved.
- **`system`** - OS-level work: configs, troubleshooting, CLI tooling. The system path is `system-planner` (ordered steps, each with backup / dry-run / rollback) -> `system-executor` (runs them) -> `system-verifier` (confirms the desired state actually holds). A bug here pairs `system` with `bug`: the `system-investigator` diagnoses from service state, logs, and configs. No TDD chain and no code-convention lenses; instead the executor carries two locks (see `## Locks`): the `{while:#destructive-op, until:#safety-approved}` safety gate - on a destructive or irreversible step the `safety-gate` holds it until the user clears the action - and the unconditional `{while:#plan-ready, until:#plan-approved}` plan gate, which the orchestrator clears with a one-tap confirm before execution (the system path always confirms, so it carries no `#significant-build`). Security still applies.

`est-size` is advisory only: it feeds the cost gate's upfront estimate and never picks stages. The real size stays the final route count.

### Worked routes

Five `echo STATE | python3 hooks/route.py` traces:

- **code** - `{"live":["code","needs-tests","significant-build","code-written","ui-touched","auth-surface"],"available":["confirmed-intent","diff"]}` composes `reuse-scanner` + `health-checker` + `prototype-identifier` (Scout, pulled by `#significant-build`), the full Review wave (correctness and simplicity via `#code-written` (always-on); quality, architecture, structure, consistency, performance, reuse, acceptance, plan-adherence, assumptions, naming-clarity via `#significant-build`; test-gap, test-verifier via `#needs-tests`; ux, accessibility, design-consistency via `#ui-touched`), `security-reviewer` pulled in by `auth-surface`, and `capture-agent`. The two axes are independent: `#needs-tests` pulls only the TDD chain, `#significant-build` pulls Scout and the deep lenses. The lenses share `@diff`, so they land in one parallel wave. Size XXL.
- **trivial code** - `{"live":["code","intent-confirmed"],"available":["request","triage-read","confirmed-intent"]}` composes only `code-planner` (size XS) - this single router call is just the planner. Once the planner publishes `#plan-ready`, the next recompose puts `code-implementer` in `held` keyed on `#plan-approved` (its TDD lock is inactive - no `#needs-tests` - but the plan-gate lock holds it): `{"live":["code","intent-confirmed","plan-ready"],...}` returns `held: {"code-implementer": ["plan-approved"]}`. The orchestrator emits `#plan-approved` (auto on this trivial plan, or a one-tap confirm), releasing the implementer; `correctness-reviewer` and `simplicity-reviewer` then join once `#code-written` makes `@diff` available. None of the deep lenses, Scout, clarify, test-chain, challenge, or Document join - they wait on `#significant-build` (and the TDD chain on `#needs-tests`).
- **sketch** - `{"live":["sketch","code-written"],"available":["confirmed-intent","diff"]}` composes just `sketch-build` then `correctness-reviewer`; the code-only lenses are dropped `off-path` by the `routes` filter. Size S.
- **system** - `{"live":["system","plan-ready","destructive-op"],"available":["confirmed-intent","system-plan"]}` composes `safety-gate` (armed by `destructive-op`) and holds `system-executor` in `held` keyed on BOTH unmet untils - `held: {"system-executor": ["safety-approved", "plan-approved"]}`. The `safety-gate` clears `#safety-approved` in-route; the orchestrator emits `#plan-approved` via the one-tap pre-execution confirm. Once both fire the executor runs and `system-verifier` follows. Without a `#destructive-op` the safety lock is inactive, but the plan gate still holds the executor on `#plan-approved` alone. No TDD chain, no code lenses.
- **talk** - `{"live":["talk","ambiguous"],"available":["request","triage-read"]}` composes `interviewer` (pulled by `ambiguous`) then `discuss`, ordered after it because `discuss` optionally consumes the interviewer's `confirmed-intent`. No diff, nothing reviewed.

### Intent

`triage` settles framing. When the request is clear, **state the one-line interpretation and proceed** - no confirmation gate; the user corrects in their next message if it is wrong. `triage` mints `@confirmed-intent` on a clear code or system ask, so its Scout step is satisfied without the interviewer. When `triage` publishes `ambiguous` (any genuine doubt - low bar), the `interviewer` stage joins and loops until intent is confirmed. Intent is always *stated*, never silently assumed (see Principles), but a clear ask is not stopped.

### Gates

A gate is a stage whose output is a **user decision**, rendered via `AskUserQuestion` (Concise Surfacing Contract). It fires only when its triggering signal is live AND the answer could change what happens next - a 95%-Continue checkpoint is narrated, not asked. The user's choice publishes a signal (`approved` / `scope-down` / `abandon` / ...) that feeds the next recompose. A size-threshold crossing (`size-crossed:L`) is itself a signal a cost gate can subscribe to.

An `abandon` outcome is a **run-terminal**, not just another signal: the orchestrator stops the route, drops any stage still held behind the abandoned gate (its `until` signal will never fire), and surfaces what ran and what did not. This is what makes a `safety-gate` Abort terminate cleanly - the held `system-executor` is dropped and never run, rather than waiting forever for a `#safety-approved` that is not coming.

The **plan-approval gate** holds both implementers behind `#plan-approved` (see `## Locks`). On the `code` path with `#significant-build` live, `plan-challenger` runs in-route and its Approve publishes `#plan-approved`; on a multi-plan run (`doctrine/multi-plan.md`) the per-plan challengers run critique-only and `plan-arbiter` is the in-route publisher instead, on its Adopt verdict. On the system and trivial-code paths there is no in-route publisher, so the orchestrator emits `#plan-approved` itself: a one-tap confirm before execution (system: always; trivial code: only when the plan touches `>1` file or `est-size > S`, else auto-published). The system confirm asks "Run this system change?" with header `Run change` and options Proceed / Abort; the trivial-code confirm asks "Proceed with this change?" with header `Proceed` and options Proceed / Hold, where the Hold option's description carries the escalation - declining escalates to the full challenge. Each one-tap confirm renders the planner's Plan Breakdown in its card, and the gate's concrete example rides in that card breakdown, not in the option descriptions (which stay fixed-process example-exempt). (The auto/confirm threshold stated here - `>1 file or est-size > S` - is the De Morgan dual of the `## Locks` release policy - `<=1 file AND est-size <= S` - see that section for the absent-est-size default.)

### Asymmetric rigor

Skipping a stage needs a positive signal; adding one needs only doubt. Safety and clarify stages carry `guard: sticky` or fire on any risk sniff - in by default, dropped only on strong signal. A needless question costs mild annoyance; a wrong assumption costs the task.

## Model Tiering

Each stage declares its own `model` in agent frontmatter - `opus` for the planning,
judgment, and intent work (the planners, the challenger, the deep reviewers, and the
intent stages), `sonnet` for analysis and implementation, `haiku` for classification
and lookups. The router spawns each stage at its declared model; there is no per-tier
override table. Swap a specific agent's voice under `alpRiver.psychologyOverrides`, or
change its `model` in frontmatter.

Alongside `model`, each stage declares an `effort` level - `medium`, `high`, or `max` -
matched to the job rather than the model: mechanical stages that execute an upstream
decision sit at `medium`; analysis, the review lenses, and the intent loops at `high`; and
only the generative planners (`code-planner`, `system-planner`) and the adversarial
`plan-challenger` at `max`. Effort sets a stage's thinking budget independent of its model and is read by the
harness at spawn, never by the router or catalog. It is model-gated: `haiku` does not honor
effort, so the haiku classification stages (`triage`, `prototype-identifier`,
`health-checker`) carry no `effort` line.

## Instruction-to-hook

Promote a repeated agent instruction to a deterministic hook when the check is
mechanical, has a single correct answer, and recurs across runs - reproducible work that
belongs off the per-agent prompt budget. Keep it an agent instruction when it needs
judgment or run-specific context. Example: "the build and tests must be green at finish" is
mechanical and recurs every run, so it lives in the `verify-build` / `verify-tests` Stop
hooks rather than in each implementer's prompt.

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
`DEFERRED_QUESTIONS`, promoted `[unsure]` criteria or assumptions); `design-prototyper`
(`PARAMS_TO_CONFIRM`); `ux-prototyper` (`FLOW_TO_CONFIRM`); `plan-challenger`
(`CHALLENGE_QUESTIONS`); and any gate stage whose
output is a user decision (the cost check on `size-crossed:<tier>`, continue/stop after a
diagnosis or a plan, Document's per-item approvals).

**Question schema**: `question` (text), `header` (max 12 chars), `multiSelect`, `options`
(2-4; each `label`, `description`, optional `preview`).

**Description vs. preview**: `description` carries the essence plus, for any non-trivial
decision (one that sets a value, data shape, behavior, or UI result), one concrete example
of what the choice produces (e.g. `wrapped -> {users:[...]}` vs `bare -> [...]`). This is
the DEFAULT shape for every surfaced explanation at a decision point: plain words first,
then a concrete before->after (or input->output) example, jargon cut. The
example is load-bearing - lead with it, cut hedges to make room. Bare yes/no and fixed
process gates (Continue/Stop, Approve/Revise/Reshape) are exempt. `preview` is best-effort
enrichment; never put load-bearing content there. The CLI supplies the "Other" escape -
agents MUST NOT synthesize their own.

**Plan breakdown**: at every plan-approval gate where the user is asked - the challenge
gate, the system one-tap confirm, the trivial-code one-tap confirm - the orchestrator
renders the producer's Plan Breakdown verbatim inside the Full (A) render card shown at
that gate, as native-markdown prose within the card (rendered, not fenced). It is a render-card surface, not inline prose and not `preview`: it carries the
load-bearing plain-language summary that the card-only rule and the non-load-bearing
`preview` rule both keep out of the wrong place. It is short and flows naturally - a plain
summary with a concrete example and a small visual woven in, where that example is the same
before->after / input->output shape in plain words (the default above) - and is authored plain by the
producer; the orchestrator relays it, it does not synthesize. This reconciles the exemption
above: the fixed-process gates (Continue/Stop, Approve/Revise/Reshape) stay example-exempt
in their option descriptions because the gate's required concrete example lives in the
breakdown woven into the card, so the exemption and the show-an-example intent stay
consistent. A silent auto-approve renders no breakdown - there is no prompt.

**4-question cap + DEFERRED priority queue**: `AskUserQuestion` takes 1-4 questions. With
more than 4 eligible items, fill the slots in order - open `QUESTIONS`, then `[unsure]`
criteria, then `[unsure]` assumptions - and roll the rest into `DEFERRED_QUESTIONS`,
preserving order. Deterministic and re-runnable. `DEFERRED_QUESTIONS` rides inside
`<CLARIFY_OUTPUT>` so it survives compaction; the orchestrator threads still-open items into
the next round's `<PRIOR_ROUNDS>`.

**Challenger reshape**: `plan-challenger`'s `CHALLENGE_QUESTIONS` carry Approve (proceed) /
Revise (rerun planner with `BLOCKERS`) / Reshape (back to intent). `SCOPE_MISMATCH` surfaces
inline alongside `BLOCKERS` and in the Reshape option's `preview`.

**Brief escalation (render-only)**: this is the canonical home for the matched label pair and the
coexistence mechanic. Four dense pickers (plan-challenger, plan-arbiter, interviewer intent-confirm,
requirements-clarifier direction/confirm) carry ONE escape option, `See it in plain words` - an
inline plain re-render that rides the picker as a single option (the question budget stays 4).
Picking it makes the orchestrator re-render the SAME decision inline in plain before->after form (the
Description-vs-preview default above) AND re-emit the SAME picker, so the gate STAYS at the picker -
read off the pick, NOT a routing signal (cross-ref `## Locks`, Brief escalation, handled inline). The
final line of that plain re-render offers the deeper `See it as an interactive doc` (the render-only
`.briefs/` HTML page) via the EXISTING per-surface paste-back token - no new token, no second option slot.
A pulled brief closed without a paste-back leaves the gate PENDING: the picker stays the open gate until a
verdict token arrives, so the gate never leaves the picker. Escape-bearing stages reference this block.
See `doctrine/briefs.md` for the three surfaces, the per-surface tokens, and the lazy-build rule.

## Convergence

There is no edge budget. A route runs until it converges: the router returns no triggered
unrun stage and every lens that ran is `clean`. The only loop guard is oscillation - a
`scope-shift` that re-fires without resolving is surfaced to the user, not retried
silently. A correction revision (a challenger `revise`, an implementer kickback) re-spawns
its producer per `## Revision Contract`, so the oscillation guard stays the only loop limit.
See `## Pipeline` > The loop.

A *missing* output block is not convergence: when a spawned stage returns no wrapped output - including the harness `[Tool result missing due to internal error]` - the orchestrator treats it as a failure and recovers per `## Recovery`, never an open-ended wait for an artifact that is not coming. This is what a background stage's deadline breach (`## Pipeline` > The loop, step 3) and a task handle lost to compaction both collapse to: a read-only stage re-dispatches once then surfaces, a side-effecting stage reconciles from the working tree and surfaces only on the AMBIGUOUS outcome.

**Run-timing readout.** At convergence the orchestrator renders one final timing card (the Timing readout (C) format, `## Pipeline` > The loop, step 2). It needs no new instrumentation: every background stage's completion notification already carries a `usage` block with `duration_ms` (alongside tokens and tool_uses), which the orchestrator reaps as it runs the loop. As each notification lands it **accumulates** that stage's `duration_ms` keyed by stage; a stage that ran more than once - a re-dispatched read-only stage (`## Recovery`), a `fixer` loop iteration, a re-run TDD chain across milestone boundaries - **adds** each run's duration, so the readout reflects total time spent including retries. It then rolls those per-stage totals up into the 7 banner groups (mapping per README's Stages section) and, when the milestone loop ran, per milestone (the orchestrator owns the loop, so it knows each milestone's stage set). The **total** is wall-clock to convergence, not the per-stage sum - parallel waves and backgrounded stages overlap, so the sum overcounts elapsed time and is reserved for the per-group/per-milestone cost breakdown. A foreground stage with no notification (triage, the router call) contributes negligibly and is folded into wall-clock either way.

**Stale-approval retraction.** On a **pre-implementation** re-plan (a challenger `revise`, a planner kickback, a reshape that re-derives the plan before the implementer or executor ran), the orchestrator performs a **live-set removal** of `#plan-approved`: it is removed from `live` so the revised plan must re-earn it through its gate. This live-set removal is the explicit retraction primitive - the counterpart to dropping a stage from `already_run` (e.g. `system-verifier` after a drift fix). This does NOT apply once the implementer/executor has run - a late re-plan after code exists is a forward correction, not a re-gate, and the already-run stage is skipped (`already_run`). Inside a milestone loop this clause reads per-milestone: a mid-loop tier-growth re-gate retracts `#plan-approved` BEFORE the next milestone's implementer run, so it stays pre-implementation for that milestone (the Stale-approval retraction (`## Convergence`); see `## Milestone loop`, Per-milestone retraction reconciliation).

**Milestone HARD withhold and convergence.** During a milestone loop the orchestrator withholds `@diff` from `available` and `#code-written` until `#milestones-complete` (`## Milestone loop`). While `@diff` is absent the global End Review lenses have no required input, so the router drops them as unsatisfiable - dropped, not deferred - which keeps convergence reachable per milestone (a held stage with no in-route producer is dropped too, see `## Locks`). They re-enter and fire once when `@diff` becomes available at loop end.

**Late escalation, never a re-gate.** A signal published late by `correctness-reviewer` on a cheap-path build escalates review depth without re-holding the already-run implementer (the loop skips `already_run`): a late `#needs-tests` pulls the TDD chain in to retroactively test the diff, and a late `#significant-build` pulls the deep lenses (plus the `fixer`) in to scrutinize it. Neither ever re-gates through `plan-challenger` - the plan gate is strictly pre-implementation, and `already_run` keeps the implementer from being re-held.

**Multi-plan adjudication.** On an armed multi-plan code run (`doctrine/multi-plan.md`) the orchestrator publishes `#critiques-ready` AND seeds `@competing-plans` + `@plan-critiques` into `available` in ONE atomic recompose, after the per-plan critique phase - the trigger never fires before its batch is available. The arbiter's Adopt publishes `#plan-approved`; Revise-first and Hybrid both re-spawn the planner via `## Revision Contract` and neither publishes `#plan-approved` directly, so the revised plan re-earns approval through its gate.

**Stall guard.** A stage held on `#plan-approved` with no in-route producer AND no plan-approval confirm pending is a stall, not convergence - surface it to the user, never wait forever. (The no-in-route-producer clause is always true on the system path, so the operative test is "no plan-approval confirm pending": if the orchestrator owes a `#plan-approved` emit and has not surfaced the confirm, that is the stall to catch.) On a multi-plan code run the arbiter IS an in-route `#plan-approved` producer, so the no-in-route-producer clause is false there - "arbiter in-route but not yet returned" is a non-stall held state (the implementer waits on an in-route producer that will fire), distinct from the system-path stall where the orchestrator owes the emit. However, "arbiter in-route" requires that the atomic co-publish landed: the orchestrator emitted `#critiques-ready` AND seeded `@competing-plans` + `@plan-critiques` together. If the orchestrator emitted `#critiques-ready` but never seeded those artifacts, the arbiter is dropped as unsatisfiable-input and nobody owes the `#plan-approved` emit - that state IS a stall and MUST be surfaced, not treated as a non-stall held state.

`system-verifier` works the loop in reverse: when it finds drift it publishes `findings:system`,
which re-runs the `system-executor` to re-fix; the orchestrator then drops `system-verifier`
from `already_run` so it re-verifies the corrected state - the system analog of a review lens
re-running after the `fixer`.

## Recovery

When a stage's output is lost - a deadline breach (`## Pipeline` > The loop, step 3), a task handle dropped to compaction, or a harness `[Tool result missing due to internal error]` - the orchestrator reconstructs what happened from the durable record and continues on its own, never an open-ended wait. The branch is decided by what the lost stage *does*:

- **Re-runnable stage** (researcher, the investigators, every review lens - all read-only). Re-dispatch it. Re-running is idempotent because it touches nothing, so the recovery is a single bounded retry; if that retry also breaches, surface the stall to the user. This is the read-only branch the deadline-breach and lost-handle paths above feed into.
- **Side-effecting stage** for code and tests (`code-implementer`, `fixer`, `test-author`). The working tree IS the durable record, so reconcile from it rather than re-run blind: `git diff` the tree against the approved plan's expected file set, then run the project gate (build / type-check / the test suite). Four outcomes: **COMPLETE** (expected files present, gate green - publish the stage's normal output and proceed), **PARTIAL** (some expected files present - resume the remainder; the idempotent read-modify-write each implementer/fixer leans toward, `doctrine/code-doctrine.md`, lets a re-dispatched remainder no-op the work already on disk), **NOTHING-LANDED** (no expected file changed - re-dispatch the stage as if it had not run), **AMBIGUOUS** (the tree diverges from the plan in a way none of the three explain - surface to the user; this is the only branch that pulls the user in).
- **Side-effecting stage** for system (`system-executor`). Reconcile through the existing `system-verifier` reverse-loop above: run it against the desired state, and its drift finding re-runs the executor exactly as a verifier-detected drift would. No separate mechanism.

This is coherent because the two branches are complementary and exhaustive: every stage is either read-only or side-effecting, and each lands in its own branch. Detection only has to *eventually* fire - reconcile-from-trace carries the correctness, the timer just decides when to look - so a coarse mtime-freeze window costs latency, never a wrong recovery.

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

The `system-executor` carries a `{while:#destructive-op, until:#safety-approved}` lock (the **safety gate**): on a destructive or irreversible system step, `system-planner` (or `triage`) publishes `#destructive-op`, so the executor is held until the `safety-gate` stage carries the action to the user and `#safety-approved` fires - no destructive command runs unconfirmed.

The `ship-executor` carries a single `{while:#ship-ready, until:#ship-approved}` lock (the **ship gate**): the orchestrator emits `#ship-ready` at convergence on a ship request (see `## Shipping`), so the executor is held until the `ship-gate` stage - a real `routes:[code]` stage that publishes `#ship-approved` in-route - carries the forward git/gh commands to the user and `#ship-approved` fires. No commit, push, or PR runs unconfirmed.

The `code-implementer`'s `{while:#needs-tests, until:#tests-ready}` lock is the **TDD gate**. On a
logic build `triage` publishes `#needs-tests`, so the implementer is held until `test-review`
publishes `#tests-ready` after validating the red tests - code cannot start against
unvalidated tests. A trivial change carries no `#needs-tests`, so the lock is inactive and
the implementer runs straight off the plan.

Both implementers also carry a second, **unconditional** `{while:#plan-ready, until:#plan-approved}` lock - the **plan-approval gate**. `#plan-ready` fires the moment a plan exists, so this lock is always armed on a code or system build; the implementer/executor is held until `#plan-approved` clears it. No code or system change ever starts against an unapproved plan.

**Release policy.** Unlike the safety gate - a real `routes:[system,code]` stage (`safety-gate`) that publishes `#safety-approved` in-route - `#plan-approved` has **no in-route publisher** on the system or trivial-code path: `plan-challenger` is `routes:[code]` and only runs on a `#significant-build`. So on those paths the orchestrator emits `#plan-approved` as a **HARD REQUIRED step**. The cue is a stage sitting in `held` keyed on `#plan-approved` with no in-route producer. (The threshold below is the De Morgan dual of the `## Gates` plan-approval paragraph - `>1 file or est-size > S` - kept in sync by this cross-reference.)
- **System** - always a one-tap confirm before execution (the system path uses always-confirm; there is no `plan-challenger` band to fall back on, which is why the orchestrator-emit must be hard and backstopped, not best-effort). The confirm asks "Run this system change?", header `Run change`, options Proceed / Abort.
- **Trivial code** - auto-publish `#plan-approved` iff the plan touches `<=1` file AND `est-size <= S`; otherwise a one-tap confirm asking "Proceed with this change?", header `Proceed`, options Proceed / Hold (the Hold description states that declining escalates to the full challenge). When `#est-size` is not live (triage may omit it on some paths), treat the plan as NOT trivial - apply a one-tap confirm, never auto-publish. Declining the one-tap escalates into the full `plan-challenger` band (publish `#significant-build`, run the challenger, which then owns the `#plan-approved` release). `est-size` stays advisory for stage selection but is **load-bearing** for this auto-release decision only - when absent, the safe default is confirm.

Each one-tap confirm renders the planner's Plan Breakdown in its card, and the gate's concrete example rides in that card breakdown, not in the option descriptions (which stay fixed-process example-exempt).

**Brief escalation, handled inline.**
- **Option, not a signal.** Both `See it in plain words` (the inline plain re-render that rides the picker on the four dense pickers) and `See it as an interactive doc` (the `.briefs/` HTML page, pulled from inside that plain re-render) are handled the same orchestrator-inline way as the trivial-code Hold: read off the pick, never a routing signal (same pattern as the trivial-code Hold escalation above).
- **Orchestrator writes, then waits.** On reading the pick, the ORCHESTRATOR performs the Write INLINE - before awaiting the paste-back - calling its own Write tool to produce `.briefs/<touchpoint>-<slug>.html`, then waits for the paste-back token. Surfacing agents stay read-only.

See `doctrine/briefs.md` for the artifact list, the gate-stays-at-the-picker rule, the `safety-gate` special case, and the slug reduction rule.

On the `code` path proper (`#significant-build` live), `plan-challenger` runs in-route and publishes `#plan-approved` on Approve, so the orchestrator does not emit it there. On a multi-plan code run the per-plan challengers are critique-only and `plan-arbiter` is the sole in-route publisher of `#plan-approved` (its Adopt verdict); Hybrid and Revise-first re-spawn the planner and publish nothing (`doctrine/multi-plan.md`).

## Milestone loop

A `#significant-build` decomposes into milestones reviewed one increment at a time. The planner's `## Plan Breakdown` always carries an ordered, **advisory** milestone list (`agents/code-planner.md`); the orchestrator owns the loop/no-loop choice.

**Arming (orchestrator rule).** The orchestrator ENGAGES the milestone loop - per-milestone execution, the EARLY pass, and the divergence re-split - if and only if `#significant-build` is live (it already tracks `live`; precedent: the orchestrator already keys behavior off `#significant-build`). Otherwise it runs the plan as a single pass - today's behavior. The milestone breakdown is advisory input to this choice, never the gate itself.

A second, orthogonal choice the orchestrator makes off that same `#significant-build` signal is whether to run **multiple plans in parallel** under different lenses, each critiqued, then adjudicated by `plan-arbiter` - armed when `#significant-build` is live AND the design space is wide. See `doctrine/multi-plan.md` for the arming rule, the lens set, the critique-only construction invariant, and the atomic co-publish contract.

**EARLY pass (per milestone, N>1 only).** At each milestone the orchestrator runs ONLY the milestone-scoped lenses over that milestone's diff slice: `correctness-reviewer` + `security-reviewer` (surface-gated, fires only when the milestone slice trips its surface) + `structure-reviewer` + `test-verifier` (smoke), each `milestone-scope`-tagged (`local`, or `both` for `test-verifier`). The full End Review wave is NOT part of the loop - it fires once at the end (see HARD withhold below).

**Construction invariant.** The implementer publishes `#milestone-diverged` only during loop execution; loop execution only happens when `#significant-build` is live; therefore `plan-challenger` (which subscribes `#significant-build`) is always live when a divergence re-split composes. The dead-subscriber state - a `#milestone-diverged` with no live re-splitter - is unreachable by construction.

**Milestone-boundary spec.** At each boundary the orchestrator (a) live-set removes `#tests-ready` / `#tests-red` / `#test-cases-ready` from `live`; (b) KEEPS `#needs-tests` / `#significant-build` live so the implementer's locks go HELD (not inactive); (c) drops `{test-plan, test-author, test-review}` from `already_run` so the TDD chain re-runs for the next milestone. This is symmetric to the `system-verifier` drop-from-`already_run` (`## Convergence`). Retracting `#tests-ready` alone is only half the move - without (c) the re-held implementer would stall with no in-route producer for its `until` signal.

**Forward-only re-split.** `#milestone-diverged` re-splits the REMAINING milestones k+1..N only; the shipped milestones 1..k are never re-gated (mirrors the late-escalation forward-correction in `## Convergence`, "Late escalation, never a re-gate").

**HARD withhold (HARD REQUIRED, same emphasis as the `#plan-approved` orchestrator-emit).** Until `#milestones-complete`, the orchestrator MUST NOT add `@diff` to `available` and MUST NOT publish `#code-written`. This keeps the End Review wave (the global lenses over the whole `@diff`) from firing per milestone; it fires exactly once, after the final milestone, when `@diff` becomes available and `#code-written` publishes. `#milestones-complete` is orchestrator-emitted, like the other orchestrator-sourced control signals. No git commits happen between milestones - the working tree accumulates across all milestones and only the final cumulative diff is the artifact the End Review wave sees (consistent with `## Recovery`'s reconcile-from-tree).

**Tier-growth re-gate.** This is an orchestrator observation, not a signal: when a re-split grows the remaining work past its `est-size` tier, the orchestrator retracts `#plan-approved` via the existing live-set-removal primitive (`## Convergence`, Stale-approval retraction) and re-gates - one-tap - the REMAINING milestones only.

**Per-milestone retraction reconciliation.** A mid-loop tier-growth re-gate retracts `#plan-approved` BEFORE the next milestone's implementer run, so it is pre-implementation FOR THAT MILESTONE; the Stale-approval retraction "once the implementer has run" clause reads per-milestone inside the loop, consistent with the per-milestone re-hold at the boundary.

**N=1 / cheap path.** Below a significant build (no `#significant-build` live), the loop does not engage - a single pass, byte-AND-cost-identical to today, with no early pass.

**Colored render.** During a milestone build the render card shows the milestone list with `🟩` (verified) / `🟨` (building) / `🟥` (pending) plus a `milestone k of N` header, all native markdown that renders inline; the stage lines keep their existing `▶ ✓ 🔒 •` markers (`## Pipeline` > The loop, step 2).

## Shipping

The shipping tail is **opt-in and in-session only**: it ships the work built THIS run as one commit, one pushed branch, and one draft PR. It engages only when the request explicitly asks to ship, release, or open a PR - `triage` then publishes `#ship-requested` (a marker, alongside `code`, never its own path; see `agents/triage.md`). With no such request the tail never composes and the run converges normally.

The ship gate is **surfaced only at convergence**, so it is a deliberate appendix after the build is done, not a stage woven into the route. The trigger is a HARD REQUIRED orchestrator emit, the same shape as the `#plan-approved` orchestrator-emit (`## Locks`, Release policy): when the router returns an empty `route` AND an empty `held` map AND every lens that ran is `clean` (the convergence definition, `## Convergence`) AND `#ship-requested` is live AND `#ship-ready` is not already live, the orchestrator emits `#ship-ready`. That emit re-populates the route (`ship-gate`, which subscribes `#ship-ready`) and `held` (`ship-executor`, held on its `{while:#ship-ready, until:#ship-approved}` lock, `## Locks`). The `ship-gate` carries the forward git/gh commands to the user; its Proceed publishes `#ship-approved` in-route, releasing the executor. True final convergence is reached only after the executor publishes `#shipped` and the route empties again.

- **Seed.** `#ship-ready` is in `SEED_SIGNALS` (`hooks/check_catalog.py`) because it is orchestrator-emitted at convergence, not published by any stage - the same basis as `#request-received` and `#critiques-ready`. It is reliably emitted (the convergence trigger above), unlike the unsatisfiable `#milestones-complete` case. The generic seed cost applies: a future stage that subscribes `#ship-ready` on a path where the orchestrator does NOT emit it would not be caught as an orphan, because the seed exempts the topic from the publisher check.

## Input Template Contract

Every agent receives inputs via a tagged-slot template authored under the agent's `## Input` heading and compiled into `generated/catalog.json` as `input_template`, so the orchestrator fills slots from catalog state without opening each agent's `.md`. The main agent fills slots verbatim from predecessor output - no paraphrase.

Every template:
- names each required slot with an XML-style tag (e.g. `<CONFIRMED_INTENT>`, `<SCOUT>`, `<APPROVED_PLAN>`)
- states the source agent and the expected content for each slot
- the agent's first step parses required slots; on a missing required slot it emits `INPUT_ERROR: missing <slot>` and stops

Output wrapping: agents emit structured blocks named with XML-style tags that successors reference (e.g. `<APPROVED_PLAN version="N">`, `<CLARIFY_OUTPUT>`). This makes relay mechanical and enables re-injection after compaction.

## Revision Contract

This harness has no live follow-up to a running subagent. Every re-production of a prior output is a fresh spawn, and its input must be self-contained: the orchestrator assembles the package, not the agent (Context Discipline). A continuation handle to a *completed* subagent may exist in the runtime, but a revision re-spawns fresh with the prior artifact folded in by design - the package has to be self-contained, deterministic, and compaction-survivable, which a live handle is not. Re-spawn fresh and present it as the normal move - assemble the package and proceed. A revision package fills three roles.

1. **Prior version** - the complete prior artifact. Folded into the prompt verbatim when the artifact lives only in the conversation (the plan), or re-read from disk when the artifact is a file the agent wrote (the tests).
2. **Corrections** - the exact directive driving the change (challenger `BLOCKERS`, implementer kickback `REASON`, test-review misalignment report).
3. **Guard** - the literal instruction to reproduce the prior version exactly except where a correction applies, emit a minimal diff rather than a from-scratch re-derivation, and bump the version where the artifact is versioned.

Each agent fills these three roles with its own speaking-named slots; there is no shared generic tag.

**Correction revision.** Re-emits the agent's OWN artifact with targeted fixes, keeping a stable tag and bumping the version. The guard applies. Instances:
- `code-planner` - prior version `<PRIOR_PLAN>`, corrections `<REPLAN_REASON>`; emits `<APPROVED_PLAN version="N+1">`.
- `test-author` - prior version is the on-disk tests it wrote (re-read, not folded in), corrections `<TEST_CORRECTIONS>`; amends the suite in place.

**Non-revision boundary.** An agent that makes forward edits to a shared mutable artifact from OTHERS' findings is not revising. `fixer` is the canonical case: it edits the live working tree from reviewers' findings each round, and its `<ROUND>` is an oscillation counter, not a prior-version fold. The guard does not apply to it.

**Convergence loop.** Re-derives an evolving artifact as new user input arrives; carries `<PRIOR_ROUNDS>` and folds in the new answers. Does NOT take the verbatim guard - the artifact is meant to change round over round. Instances: `interviewer` and `requirements-clarifier` (convergence-governed), `setup-agent` (invocation-capped). See `## Clarification Loops` for the loop exit criteria.

**Not a revision (phases).** Sequential phases - `design-prototyper` (`confirm-params` then `built`), `ux-prototyper` (`confirm-flow-params` then `built`), `capture-agent` (`PROPOSAL` then `WRITE`) - each emit a different artifact and carry forward the user's picks or approvals. The guard does not apply.

The orchestrator-written briefs (`doctrine/briefs.md`) are render artifacts and are never folded into any revision package.

After compaction, a revision in flight is reconstructed from the canonical run state plus the prior artifact (`## Compaction`).

## Compaction

After compaction, `hooks/reinject-canonical-state.sh` re-anchors the workflow pointer plus
the canonical run state: the current `<ROUTE>`, `<LIVE_SIGNALS>`, `<AVAILABLE_ARTIFACTS>`,
and `<PREMISES>`. The router recomputes the route from those, so resumption is
deterministic. Preserve manually only what is not in those blocks: the stage currently
mid-run and any gate awaiting the user. A pending plan-approval confirm (system or
trivial-code, waiting on the orchestrator-emitted `#plan-approved`) is one such gate
awaiting the user, preserved by that same rule. A brief pull in flight (`doctrine/briefs.md`)
is the same case folded in: the gate never leaves the picker, so preserving the gate awaiting the user
carries the pending paste-back too.

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
