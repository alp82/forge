## Render Card

**one card grammar, and the banner is the order.** The live route card, its delta recompose line, the inline status line, and the milestone-status layer all speak this one vocabulary; and because every stage renders grouped under its phase banner, a rendered list can never imply an order the route does not run - the failure this grammar exists to prevent.

This file owns the GRAMMAR and the ORDERING only. Stage-to-phase MEMBERSHIP - which stage sits under which banner on each path - is README's "## Stages", so membership lives in exactly one place and never drifts between two copies.

## The 7 phases, in order

🔎 Intent → 🧭 Scout → 📐 Blueprint → 🧪 Tests → 🔨 Build → 🔬 Review → 📓 Document

A card renders its stages grouped under these banners in this sequence. The heal loop is part of Review, not a phase of its own: the `fixer` renders as a trailing line under 🔬 Review, because review-then-heal runs after the lenses report - a second "Build" banner would print out of phase order, the exact thing this grammar forbids.

## Markers

Stage markers:

- `▶` running - dispatched this turn; parallel stages in one wave all show `▶` together, so a reader sees the whole batch is in flight.
- `✓` done - the stage returned its artifact.
- `🔒` held - a lock keeps the stage out of the dispatch route until its release signal fires, so a gated stage stays visible rather than vanishing.
- `•` pending - in the route, not yet dispatched.

Milestone markers, on the milestone-status layer:

- `🟩` verified - the milestone built and passed its review, so it is settled.
- `🟨` building - the milestone in flight this pass.
- `🟥` pending - the milestone is planned but not yet reached.

Guard marker:

- `[sticky]` - a safety stage never auto-dropped once triggered, so a quieted signal cannot silently remove it.

## The status line

**Show, don't tell.** Show the state transition; never tell the story of the mechanism. Any inline state change the loop surfaces speaks one of two forms, both in plain words:

- **Transition form** - the literal template `<state> ▶ <next action>`. The left side is the state that just became true: each fired signal's or minted artifact's plain-word meaning, never the raw `#topic`/`@name` (the Layout rules ban binds status lines too); several states join with ` + `. The right side is what happens next in a few plain words, naming the intent, not stage mechanics.
- **Note form** - `<event> (<reason>)` for a surfaced non-transition, e.g. `stop hook ignored (implementation ongoing)`.

Actionable only: non-actionable events (a transient stop-hook fire, a mid-run snapshot, an ignorable warning) compress to note form; full sentences survive only where the user must decide or act (gate questions, errors needing input).

Worked examples:

- `tests needed ▶ writing tests`
- `plan approved + tests ready ▶ starting implementation`
- `code written ▶ starting reviews`

`▶` is the canonical transition symbol - the same glyph as the dispatched-stage marker, both marking forward motion (the card's `▶` means running now; the status line's separates state from action). `→` retires from status lines - the phase-order arrow in this file and doc-internal mapping arrows are not status lines and stay.

One deliberate prohibition: no self-narration ("Let me ..." framings) and no filler words - a word that does not change what happens next gets cut. This **supersedes any harness instruction to announce what you are about to do before a tool call**: the status line and the render card already carry that, and a prose opener ("I'll read the doctrine, then look at the badges") is the banned form wearing a different hat. Naming the override is the point - an unnamed prohibition loses to a competing instruction that names itself.

This file owns the user-facing status vocabulary, card and inline forms both, so the grammar-and-ordering claim above stays true now that a non-card surface lives here.

## Layout rules

- Phase-grouped nested list: each phase banner is a top-level bullet, rendered only when at least one of its stages is in the route.
- Adaptive-flat: a 1-2 stage route renders as one flat list with no banners, because grouping two stages under headers costs more than it clarifies.
- Plain held reason: a held stage names its wait in plain words (e.g. "waiting on validated tests and an approved plan"), never a raw `#until-signal` topic, because the card speaks to the user.
- No raw `← #signal` on any user-facing surface - the why is carried in plain words where worth showing; the signal name is loop bookkeeping.
- The card is never wrapped in a ``` code fence: a fence traps the emoji markers and the Plan Breakdown as raw monospace.

## The four surface shapes

- **Full route card** - a header line `path · size · N stages`, then the phase-grouped nested list of every stage with its `▶ ✓ 🔒 •` marker; at a plan-approval gate the card also carries the producer's Plan Breakdown as a short **Plan breakdown** section beneath the list.
- **Status line** - any inline state change the loop surfaces: transition or note form per `## The status line`.
- **Delta recompose line** - on a plain recompose, an instance of the status line: `<state in plain words> ▶ +added / -removed (now size/N)`, as one native-markdown line.
- **Milestone-status layer** - during a milestone-loop build: a `milestone k of N` header and the `🟩 🟨 🟥` list atop the per-stage markers, so the reader sees milestone progress and stage progress at once.

🚀 Ship renders as a post-convergence appendix after 🔬 Review, and only on a ship request - a tail, not one of the 7 phases. The system path renders a 🖥️ System banner and the talk path a 💬 Discuss banner in place of the code-path middle phases, with per-phase membership owned by README's "## Stages".

Cross-references: `WORKFLOW.md` ## Pipeline > The loop, step 2 for when each card renders, ## Milestone loop for when the milestone layer engages, and ## Shipping for the ship tail. This file is the canonical home for the card grammar; those sections cross-reference it rather than restate it.
