---
description: Reflect on the current session to surface workflow friction worth tuning
argument-hint: (optional) area to focus on, e.g. "the clarify loop" or "the last fix"
---

# Reflect

Focus hint: $ARGUMENTS

Look back at the current session and surface only **big wins and big fails** worth acting on. Goal: signal that would change how alp-river is built, not a comprehensive audit.

**In-chat only.** No file writes, no memory writes, no subagent spawns. The main agent does this directly.

## Severity bar

Flag an item only if at least one holds:

- Recurring or systemic pattern, not a one-off blip.
- Real cost (tokens, wall-clock, user rounds) that would noticeably improve if fixed.
- Quality miss with downstream impact - slipped past reviewers, drove a wrong fix, misled the user.
- Workflow gap this session exposed - a step that should have fired and didn't, a spec that contradicts itself.

Routine variation, small papercuts, and "this could be slightly cleaner" do not clear the bar. If nothing clears it, say so in one sentence and stop.

## Lenses (scan, don't fill)

Render **only** the lenses that produce something above the bar. Drop empty lenses entirely - no headings, no `(nothing to flag)` filler.

- **Unexpected behavior** - surprises against design intent
- **Token-heavy steps** - disproportionate tokens for value returned
- **Slow steps** - heavy *to the user*: rounds with the user, clarify-loop length, time-to-first-useful-output (internal tool-call counts belong in token-heavy)
- **Quality issues** - reviewer misses, half-fixes, dropped captures, low signal-to-noise rounds
- **Backward-edge reasoning** - each edge used: trigger, necessity, what earlier step could have caught it

## Output shape

- One short bullet or sentence per surfaced item. Be concrete - name the file, step, or agent.
- Tag confidence `[likely]` or `[unsure]` per WORKFLOW.md "Confidence Tagging".
- End with **one Top change worth considering** only if something clears the bar. Otherwise omit it.
- Honest, not flattering. If the session was clean, say so in a sentence and stop.
