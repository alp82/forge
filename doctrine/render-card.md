## Render Card

**one card grammar, and the banner is the order.** The live route card and its delta recompose line, the milestone-status layer, and the run-timing readout all speak this one vocabulary; and because every stage renders grouped under its phase banner, a rendered list can never imply an order the route does not run - the failure this grammar exists to prevent.

This file is the single home for the card grammar - the markers, the layout rules, and the phase ordering every card surface shares. It owns the GRAMMAR and the ORDERING only. Stage-to-phase MEMBERSHIP - which stage sits under which banner on each path - is owned by README's "## Stages", grouped there per path; this file states the phase order and points there for what fills each phase, so the membership lives in exactly one place and never drifts between two copies.

## The 7 phases, in order

The banner order, macro-scale, is fixed:

🔎 Intent → 🧭 Scout → 📐 Blueprint → 🧪 Tests → 🔨 Build → 🔬 Review → 📓 Document

The banner is the order: a card renders its stages grouped under these phase banners in this sequence, so the rendered shape always reads in the order the route actually runs and can never imply a sequence the route does not follow. This section states the order; it does not enumerate which stages belong to each phase - that membership is README's "## Stages", per path.

The heal loop is part of Review, not a phase of its own: the `fixer` renders as a trailing line under the 🔬 Review banner, because the review-then-heal cycle runs after the lenses report rather than as a separate banner of its own. Emitting a second "Build" banner for the fixer would print a banner out of phase order, the exact thing this grammar forbids.

## Markers

Stage markers, each glossed with why it reads the way it does:

- `▶` running - the stage is dispatched this turn; parallel stages in one wave all show `▶` together, so a reader sees the whole batch is in flight.
- `✓` done - the stage returned its artifact.
- `🔒` held - a lock keeps the stage out of the dispatch route until its release signal fires, so a gated stage stays visible rather than vanishing.
- `•` pending - in the route, not yet dispatched.

Milestone markers, on the milestone-status layer:

- `🟩` verified - the milestone built and passed its review, so it is settled.
- `🟨` building - the milestone is the one in flight this pass.
- `🟥` pending - the milestone is planned but not yet reached.

Guard marker:

- `[sticky]` - a safety stage that is never auto-dropped once triggered, so a quieted signal cannot silently remove it.

## Layout rules

- Phase-grouped nested list: each phase banner is a top-level bullet, rendered only when at least one of its stages is in the route, with that phase's stages as sub-bullets beneath it.
- Adaptive-flat: a 1-2 stage route renders as a single flat list with no phase banners, because grouping two stages under headers costs more than it clarifies.
- Plain held reason: a held stage names its wait in plain words (e.g. "waiting on validated tests and an approved plan"), never a raw `#until-signal` topic, because the card speaks to the user and the bare topic is internal vocabulary.
- No raw `← #signal`: no user-facing card surface shows the raw `#topic` that pulled a stage in; the why is carried in plain words where it is worth showing, since the signal name is loop bookkeeping the reader does not need.
- The card is never wrapped in a ``` code fence: a fence traps the emoji markers and the Plan Breakdown as raw monospace, the exact bug this native-markdown grammar avoids.

## The four surface shapes

**Full route card.** A header line `path · size · N stages`, then the phase-grouped nested list of every stage in the route with its `▶ ✓ 🔒 •` marker. At a plan-approval gate the card also carries the producer's Plan Breakdown as a short **Plan breakdown** section beneath the list.

**Delta recompose line.** Rendered on a plain recompose: lead with the plain why (the new signal's message in words), then `+added / -removed (now size/N)`, as one native-markdown line - example: `Touches the auth surface, so a security review joins: +security-reviewer (now L/6)`. No raw `← #signal` rides this line.

**Milestone-status layer.** During a milestone-loop build the card adds this layer atop the per-stage markers: a `milestone k of N` header and the milestone list marked `🟩` / `🟨` / `🟥`. The stage lines keep their own `▶ ✓ 🔒 •` markers underneath, so the reader sees milestone progress and stage progress at once.

**Run-timing readout.** Rendered once, at build-convergence. This file owns its LAYOUT; the stage-to-group membership it rolls up is README's "## Stages". Shape:

- Header line `Run complete - <total> total`.
- Total (always shown) = wall-clock from the first stage's dispatch to convergence.
- Per-group breakdown (shown when more than one group ran) = one indented line per banner group that ran, `<emoji> <Group>  <time>`, the time being the sum of the `duration_ms` of that group's stages; list only groups that actually ran. A one-stage route shows only the total, since there is nothing to break down.
- Per-milestone block (only when the milestone loop ran) = above the group breakdown, one line per milestone `milestone k of N - <time>`, summing the `duration_ms` of the stages dispatched within that milestone. Omit this block on a single-pass build.
- Format durations human-readable: `<m>m <ss>s` at or above a minute, `<s>s` below (e.g. `4m 12s`, `41s`).

## Ship and path ordering notes

🚀 Ship renders as a post-convergence appendix after 🔬 Review, and only on a ship request - it is a tail, not one of the 7 phases. The run-timing readout fires at build-convergence, before the ship tail runs, so ship stages never appear in it. The system path renders a 🖥️ System banner and the talk path a 💬 Discuss banner in place of the code-path middle phases, with each path's per-phase membership owned by README's "## Stages".

## Cross-references

See `WORKFLOW.md` ## Pipeline > The loop, step 2 for when each card renders during the loop, ## Milestone loop for when the milestone layer engages, ## Convergence > Run-timing readout for the timing trigger and how durations are measured, and ## Shipping for the ship tail. README's "## Stages" owns stage-to-phase membership per path. This file is the canonical home for the card grammar; those sections cross-reference it rather than restate it.
