## Briefs

**the overview comes first; the brief is details on demand, pulled never pushed.** A decision surface is offered at the cheapest form that still carries the choice, and the user is always free to pull up the brief or settle on the spot. The AI never forces the costly surface; it names the option and lets the human decide how much detail the moment is worth.

## The three surfaces

Each touchpoint offers a surface. A surface is offered, never imposed.

- **the inline question (overview)** (cheapest). Lay out the options in prose with a worked example, then close with the single question whose answer most changes the decision. No picker, no file. This is the default; a bare one-line restate that needs no choice stays here with nothing attached.
- **the picker** (the existing gate surface). The structured chooser per `WORKFLOW.md` ## Concise Surfacing Contract: 2-4 options, each with its own `description` + worked example, rendered with the producer's Plan Breakdown card where one exists. This is the standing gate.
- **the brief - render-only HTML in `.briefs/` + paste-back token** (the richer pull). A single static page the user opens to compare options at a glance, then pastes a verdict token back into chat. It sits ON TOP of the existing inline card - it replaces nothing. It is built only when the user pulls it, by picking the escalation option at the picker.

## Who writes the brief

The ORCHESTRATOR is the sole writer of the brief. It builds the page from the artifact the gate already has - the option laydown, the `CONFIRMED_INTENT` WHAT/WHY, the Plan Breakdown, or the competing-plans table - so nothing new is generated to host it. The surfacing agents OFFER the escalation option and DEFINE the expected paste-back token; they never write a file and never gain a Write tool. The orchestrator performs the Write INLINE on reading the user's pick, BEFORE awaiting the paste-back; this depends on the main agent's Write tool being available. The `design-prototyper` / `ux-prototyper` precedent (`WORKFLOW.md` ## Revision Contract) is a paste-back FORMAT analogy - those agents hand back a paste-back format, the orchestrator hosts the page - not a writer analogy (those sub-agents write their own files; here the main orchestrator writes). That split is what makes "render-only, no runtime" structurally true - the agents that reason cannot write, and the writer runs no logic.

This orchestrator-writes-the-doc precedent is scoped to `.briefs/` render artifacts only. It does NOT extend to `.alp-river/` writes: the per-turn run-state snapshot and the offloaded plan artifact are performed by subagents, not the orchestrator (see `WORKFLOW.md` loop step 4 and ### Artifact handles for the write-responsibility contract - not restated here).

## Brief trigger

The trigger is an orchestrator-inline rule, NOT a signal: the user pulled `See it as an interactive doc` (on the four lean-B surfaces, from inside the `See it in plain words` re-render; on the other surfaces, directly at the picker), so the orchestrator writes the `.briefs/<touchpoint>-<slug>.html` doc and waits for the paste-back. This is handled exactly like the trivial-code Hold-escalates-to-challenge precedent in `WORKFLOW.md` ### Gates / ## Locks - escalation lives in the option, the orchestrator reads the pick inline. No catalog routing, no new signal. The inline-escape default and the label pair are owned by `WORKFLOW.md` ## Concise Surfacing Contract.

## The brief contract (six parts)

a. **Render-only + paste-back ONLY.** No poll loop, no hosted DB, no live-annotation runtime. The page is static HTML the user reads; the only channel back is a token pasted into chat. Concepts are borrowed from richer agent-native surfaces (a lavish per-axis comparison, a doc the human marks up) but their runtimes are explicitly rejected - nothing runs, nothing phones home.
b. **Chooser / confirmer, never a freeform comment surface.** The page presents the same bounded options the picker carries and collects a verdict, not open-ended prose. It enriches the comparison, it does not widen the decision.
c. **A matched escalation label pair.** Two labels, learned once. `See it in plain words` is the inline escape that rides the picker as ONE option on the four lean-B surfaces (plan-challenger, plan-arbiter, interviewer intent-confirm, requirements-clarifier direction/confirm): picking it re-renders the same decision inline in plain words and re-emits the same picker. `See it as an interactive doc` is the HTML depth upgrade, pulled from inside that plain re-render via the paste-back token - the render-only `.briefs/` page. The inline-escape default and this label pair are owned canonically by `WORKFLOW.md` ## Concise Surfacing Contract (Brief escalation); this file stays canonical for the `.briefs/` artifact and the paste-back token.
d. **A one-tap downward exit is always guaranteed.** Every picker that offers the brief escalation also keeps a one-tap "approved as-is" path that needs no doc interaction at all. Pulling the brief is never the only way forward.
e. **Escalation is lazy and never excuses a lazy picker's question.** The brief is built only on pull, so it costs nothing until wanted. Because it may never be built, the picker's question stays fully self-sufficient: its own worked example and its complete option set carry the decision on their own. The escalation adds depth; it never offloads the work the picker owes.
f. **A pulled brief closed without pasting leaves the gate PENDING.** The gate never leaves the picker: the picker REMAINS the open gate until a verdict token arrives. A doc opened and abandoned changes nothing - there is no "brief dismissed" signal to fire, because the gate was always sitting at the picker waiting for its verdict.

## The `.briefs/` convention

Briefs persist on disk under `.briefs/`, gitignored, sibling to `.prototypes/`. One file per touchpoint+slug, `.briefs/<touchpoint>-<slug>.html`; the orchestrator overwrites it on re-render. THE SLUG is derived from the gate's subject - the same shape as the prototypers' slug - a short kebab-case reduction of the decision under discussion (e.g. the intent's primary outcome, the plan's headline). Slug reduction: lowercase the source text, replace every non-alphanumeric character with `-`, collapse consecutive `-` runs to one, trim leading/trailing `-`, and cap at 40 characters. Overwrite on re-render for the same touchpoint+subject is the INTENDED behavior, not a collision accident - a repeated brief pull on the same decision refreshes the page in place.

## Token grammar (the three new surfaces only)

The paste-back token is scoped to the THREE NEW surfaces and reads:

```
verdict: <value> | keep: <...> | drop: <...>
```

for the intent-confirm and the plan/discuss surfaces. The multi-plan arbiter surface uses `graft:` in place of `drop:`:

```
verdict: <value> | keep: <...> | graft: <...>
```

`design-prototyper` and `ux-prototyper` are UNTOUCHED. They capture their own `key: value | key: value` spec VERBATIM into `LOCKED_DESIGN_SPEC` / `LOCKED_UX_SPEC`; nothing parses those, they carry no `verdict:` field, and they are not a brief surface. There is NO shared parser - each surface's token is read where it lands. Retrofitting `design`/`ux` is out of scope.

## Which surfaces carry the option

The four surfaces are **discuss**, **interviewer (intent confirm)**, **plan-challenger**, and **plan-arbiter**. The general grammar shape is in `## Token grammar` above; each agent's escalation section is the canonical home for its specific verdict vocabulary (the per-surface verdict values are not restated here).

## safety-gate special case

A `safety-gate` brief is a richer blast-radius PREVIEW only. The decision stays a stark Proceed / Abort binary; it never becomes a multi-field paste-back. The escalation buys the user a clearer look at what the destructive step touches, not a wider set of choices.

## Cross-references

See `WORKFLOW.md` ## Concise Surfacing Contract for the inline-question and picker rules, ### Gates / ## Locks for the orchestrator-inline escalation pattern and the orchestrator-writes-the-doc rule, and ## Compaction for how a brief pull in flight is preserved. This file is the canonical home for briefs; those sections cross-reference it rather than restate it.
