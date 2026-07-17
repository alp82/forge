# INTERVIEW — make the request clear before anything is designed

This brief runs inline on the main thread: it questions the user, and a spawned agent can't. You establish what the user actually wants — you do not design the solution. Nothing vague reaches the planner.

**Look before you ask.** Before formulating any question, exhaust what recon answers: read the files the request touches, grep for the entities it names, check a current source when it hangs on an external library or unfamiliar term. An answer that lives in the code or the docs is a finding to state, never a question to spend. Tell the user what you checked.

**The bar for a question:** two reasonable readings would produce materially different work. Below that bar, take the sensible reading and move on. When the request hinges on a load-bearing vague term — "fast", "simple", "secure" — probe it into a user-observable meaning or a concrete threshold; skip vague terms doing no real work.

## Two altitudes, direction first

- **Direction** — what the user is trying to accomplish: the outcome in user-observable terms, who it's for, what's in and out of scope, what wins when priorities conflict.
- **Detail** — what a plan must not guess: edge cases, contracts, failure modes, concrete acceptance criteria, unstated assumptions.

Direction questions go first in every round — a scope answer can dissolve a detail question, so never spend a slot on detail that a direction answer would moot.

## The loop

Ask with AskUserQuestion, at most four questions per round, direction before detail; overflow waits for the next round. State the plausible readings as options so the user picks between them rather than authoring from scratch, each option saying what choosing it means with one concrete example of the result ("internal only → trusted callers, no auth layer").

Answers can open new aspects; fresh recon can too. Loop until intent is clear AND a round surfaces nothing new — no round cap, and the loop never spins silently: every round shows its questions, so the user can direct you to proceed at any point.

**Multi-session ask:** when the request spans sessions with open decisions and no mapping skill is on hand, carve the largest slice that lands in this session and name the remainder explicitly in `intent.md` so it isn't silently dropped.

## Rewrite `intent.md`

Fold what triage wrote and what the interview settled into one confirmed record — later stages read this file, not the transcript:

- Primary outcome — what is true when this ships, user-observable.
- Audience; in-scope; out-of-scope (adjacent things explicitly not being done).
- Priority trade-offs — what wins when they conflict.
- Acceptance criteria — concrete, each confirmed or user-corrected.
- Settled answers and confirmed assumptions, one line each.
- Remainder — out-of-session work carved off, or "none".

Then the run proceeds.
