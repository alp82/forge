# Changelog

All notable changes to alp-river. Versions match `.claude-plugin/plugin.json`.

## 1.2.15 - 2026-06-24

- A finished run now ends with a timing summary: total time, time per phase, and time per milestone when the work was built in milestones.

## 1.2.14 - 2026-06-24

- Removed the opt-in screenshot-based visual check because they were unreliable
- The static UI reviews and the design and flow preview pages are unchanged.

## 1.2.13 - 2026-06-18

- A big change with several genuinely different ways to build it can now explore those approaches in parallel and settle on the strongest one, or blend the best parts, before any code is written.

## 1.2.12 - 2026-06-17

- The specialist review and build voices now open by stating their guiding principle in their own words, so each stays in character throughout its work.

## 1.2.11 - 2026-06-17

- The workflow health scorecard now also flags when the same instruction is copied across files and when a hard rule lacks a stated reason.
- Post-build plan checks now follow a structured receipt the build leaves behind, so each planned item traces straight to where it landed.

## 1.2.10 - 2026-06-17

- The workflow health scorecard now tracks a sixth area that flags when load-bearing doctrine wording goes missing.
- Code review now reports bloat as a concrete cut with its replacement named and the lines saved tallied, instead of vague "could be simpler" hedges.
- The doctrine now spells out a floor that must never be simplified away - input validation, data-loss-preventing error handling, security, accessibility, calibration, and the one runnable check behind non-trivial logic.

## 1.2.9 - 2026-06-13

- The handful of stages that were pinned to a now-retired model tier (planning, plan challenge, the intent loops, debugging, and the deepest reviews) now run on the most capable available tier, so no stage points at a model that is no longer offered.

## 1.2.8 - 2026-06-11

- A clear follow-up request now proceeds immediately on a one-line restatement instead of pausing for confirmation; only a genuinely ambiguous one stops to settle intent first.
- Intent and review stages now run at a calmer thinking budget, so clarification loops settle faster and post-build reviews raise fewer speculative flags; the generative planning and plan-challenge stages keep full budget.

## 1.2.7 - 2026-06-11

- The stages whose single output steers the rest of the run - intent, planning, plan challenge, debugging, and the deepest reviews - now run on Claude Code's most capable model tier.

## 1.2.6 - 2026-06-06

- A new command reports a health scorecard for the workflow itself, ranked by the fixes that would help most.
- Reflection can now review saved notes against their conventions and capture new ones, proposing each change for approval before writing.
- Code review now names the specific silent-failure traps it checks for, so swallowed errors and missing timeouts get caught.

## 1.2.5 - 2026-06-05

- The per-turn pipeline status now renders as formatted text, so its step icons and progress markers show reliably instead of as raw monospace.
- The plain-language plan summary shown before approval now reads as formatted prose rather than a monospace block.

## 1.2.4 - 2026-06-05

- Code review now flags unsafe database migrations - non-reversible changes, constraints added without a backfill, and renames that break instances still running during a rollout.
- The build and test completion checks are more reliable, so a failing build or suite can no longer slip through to a clean finish.

## 1.2.3 - 2026-06-05

- Reviews now surface a finding only when it carries a concrete, observable consequence, cutting "this could be cleaner" noise from the results.
- A review no longer flags an issue that a guard or framework default outside the change already fully handles before the touched code runs.
- Debugging now traces the full chain from cause to symptom and treats an unexplained jump as the next thing to investigate rather than a conclusion.
- When candidate causes keep getting ruled out, the investigator steps back to ask why it is stuck instead of spawning more variations of a dead theory.

## 1.2.2 - 2026-06-04

- Fact-gathering and review steps now lead with the essentials and call out what they couldn't determine instead of guessing to fill a gap.
- The assistant lists the unknowns it hit and says plainly when it doesn't know, rather than answering with silent confidence.
- The reflect command drops its report template: it lists the big issues as plain bullets, or says nothing clears the bar in one line.

## 1.2.1 - 2026-06-04

- A build or type-check now runs when Claude finishes a task, blocking a broken build that the tests didn't catch.
- The after-edit formatter now reports lint problems rather than silently rewriting code to fix them.
- The finish-line test check now catches failures it had been silently letting through.
- A missing or timed-out test runner is no longer misread as a failing test.

## 1.2.0 - 2026-06-04

A big change is now built and reviewed in verified increments instead of in a single pass at the end, so problems surface early while each piece is small.

- A large change is broken into checkpoints, with each one built, reviewed, and confirmed before the next begins.
- A step that drifts from the agreed plan pauses for a fresh look instead of carrying the drift forward.
- Small changes proceed exactly as before, with no extra ceremony.

## 1.1.11 - 2026-06-03

- Plan approval now shows a short plain-language summary, a concrete example, and a small visual before you confirm.
- The smallest auto-approved changes stay silent as before.

## 1.1.10 - 2026-06-03

- Correctness review now runs on a stronger model for sharper findings on every change.
- Performance review catches more real slowdowns - loops that scale badly with data size and waits that should run in parallel.

## 1.1.9 - 2026-06-03

- A change that writes to a database, file, network, or payment system is now reviewed for whether running it twice is safe, flagging any step that would double-apply or corrupt on a re-run.

## 1.1.8 - 2026-06-03

- Each step now runs at a thinking depth matched to its job instead of all inheriting the deepest setting, so the hardest planning and reviews go deep while routine checks stay lean.
- The security review and the external-research step each moved to a stronger model for more reliable findings.

## 1.1.7 - 2026-06-02

- Planning and troubleshooting steps now look up a library, package, or version against current sources whenever the work commits to one, instead of only when something feels uncertain.
- Each looked-up fact is recorded with its source and a confidence tag, so an assumption that could not be confirmed is visible rather than silently trusted.

## 1.1.6 - 2026-06-02

- Risky parts of a task are now de-risked by a prototype matched to what is actually uncertain - an integration, a data shape, or whether something is fast enough.
- When the look of a UI is unsettled you get a visual picker; when the steps a user moves through are unsettled you get a separate clickable walk-through, each handed straight to the plan.

## 1.1.5 - 2026-06-02

- A step whose result is lost to an internal error now recovers on its own from the work already on disk, instead of stalling the run.
- A step that hangs is now noticed and unstuck automatically, so a single stuck step no longer freezes everything behind it.
- You are pulled in only when the recovered work genuinely does not add up, not on every hiccup.

## 1.1.4 - 2026-06-01

- Every code or system change now waits for plan approval before any edit is made, so nothing runs on a plan you have not okayed.
- A small system or trivial change clears that approval with a single tap, and a one-file change clears it automatically.
- How deeply a change is reviewed no longer rides on whether it needs tests, so a large change gets a full review even when there is nothing new to test.

## 1.1.3 - 2026-06-01

- The worked examples in the workflow guide now match what a run actually does.
- A run shows a compact status card instead of narrating each step as it happens.
- Runs are quieter and cost less context per task.

## 1.1.2 - 2026-06-01

- An unclear system or OS request now asks a clarifying question instead of stalling.
- Cancelling a destructive system step now ends the run cleanly, with nothing applied.

## 1.1.1 - 2026-05-31

- A research or review step that gets stuck on a slow or unreachable source no longer hangs the workflow - it gives up on that step and either moves on or tells you.

## 1.1.0 - 2026-05-31

The pipeline now recognizes four kinds of work instead of three, each routed to the steps it actually needs.

- Loose discussion stays fast and inline; a web search or a quick visual is offered before it runs, never forced.
- Throwaway exploration now spans code, diagrams, and mockups in one sandbox, not just code.
- System and OS-level work - configs, troubleshooting, command-line tooling - is its own track, with a safety check before anything destructive or irreversible runs.
- Independent checks now run in parallel instead of one after another, so results come back sooner.

## 1.0.8 - 2026-05-31

- When the workflow reworks an earlier plan after a correction, it now amends that exact plan instead of redrafting it from scratch, so your prior decisions survive.
- When tests need a fix or fill, the existing tests are amended in place rather than rewritten, keeping the cases you already had.

## 1.0.7 - 2026-05-31

- A malformed router call - a mistyped request key, or a request that isn't a JSON object at all - now fails loudly (names the problem, exits nonzero) instead of silently dropping it and looking like a finished task.
- UI-only reviews (accessibility, design consistency, UX) now fire only when a change actually touches UI files, instead of on every logic change.
- The screenshot-based visual check is now strictly opt-in - it runs only when you ask for it.
- The planner now receives the investigator's diagnosis on a bug fix, so it designs against the identified root cause.

## 1.0.6 - 2026-05-31

- Documentation, config, and version-only changes now go straight to implementation, with no test-writing step when there is nothing to test.
- Logic changes still hold the build until failing tests are written and validated first.

## 1.0.5 - 2026-05-31

- Documentation, version, and configuration changes now finish in a few quick steps instead of the full process.
- Changes that add real logic still require failing tests to be written and checked before any code is touched.
- Trivial changes now get a focused correctness check rather than the full review pass.

## 1.0.4 - 2026-05-31

- Multi-step tasks now run their steps in dependency order and reuse each step's real output instead of guessing ahead and redoing work.
- You now see which steps are planned, running, and done at every turn, instead of the work happening silently.
- The workflow recomputes the plan once per step instead of twice, cutting wasted work on every task.
- Background steps now hand back just their conclusion instead of a full transcript, leaving far more room before a long task fills up.

## 1.0.3 - 2026-05-31

- Every code review now also flags unclear names - vague, misleading, or wrongly scoped - judged on their own terms.
- Code reviews now call out unstated assumptions: the inputs, ordering, and environment premises code relies on but never guards.

## 1.0.2 - 2026-05-31

- Reporting a bug now drops you straight into a fix instead of a separate diagnosis track.
- Discussion mode lays out options with worked examples and asks the single question that matters, without touching your code.
- Throwaway prototypes skip the full review pass, running only the checks that matter for sandbox code.

## 1.0.1 - 2026-05-30

- Documentation and the glossary now match the composed-route model end to end - the old step-and-tier diagrams, the retired complexity classifier, and stale "backward-edge budget" references are gone.

## 1.0.0 - 2026-05-30

This is a ground-up rewrite of how alp-river works. Every prior version sorted your task into one of five size tiers and ran a fixed list of steps for that tier - the size decided the work. That model is gone. A deterministic router now reads your request and composes a route from a catalog of independent stages, assembling only what the task needs and reshaping it mid-flight as each stage discovers more. Size is no longer a dial you're sorted into; it's a readout of whatever route the work earned. The fixed pipeline, the tier gates, the backward-edge budget - all of it collapsed into a single rule: keep composing until the route converges.

- Routine changes move faster and interrupt you less; big or risky ones still earn clarification, planning, adversarial challenge, and review - because the work called for it, not because a tier label said so.
- New lightweight modes: drop into discussion or throwaway prototyping without spinning up the whole build pipeline, and slide back into building when you're ready.
- Tests come first - the workflow can't write implementation code until failing tests exist and have been checked against what you actually asked for.
- You can see what is about to run and why, and you are interrupted only when your answer would change the outcome.

## 0.3.6 - 2026-05-30

- When the pipeline asks you to decide something, each option now shows a concrete example of what it produces - so you can answer without first asking for one.
- Those prompts now lead with the decision and cut the filler, making the choice easier to grab at a glance.

## 0.3.5 - 2026-05-29

- The workflow now loads reliably at the start of every session instead of arriving cut off.
- After compacting a long conversation, your task's intent, plan, and decisions come back intact.
- Automated reviews and planning now consistently apply the shared review and code-quality rules they previously only pointed at.

## 0.3.4 - 2026-05-20

- Planning, implementation, and review now lean toward simpler local code with explicit dependencies and strong types.
- Reviews call out the AI-style code that creeps in - defensive branches no one needs, layers without a second use, hidden state.

## 0.3.3 - 2026-05-20

- Eight pipeline agents now have an optional persona voice - prototyper as an optimist, plan-challenger as a skeptic, fixer as a cynic, security-reviewer as a defender, and others.
- Override or swap any agent's persona under `alpRiver.psychologyOverrides` in `.claude/settings.local.json`.

## 0.3.2 - 2026-05-19

- `/alp-river:reflect` looks back at the current session and surfaces friction worth tuning in the workflow.

## 0.3.1 - 2026-05-19

- New chats in a project with no setup get a one-line nudge before you start typing.
- The same nudge now shows up on medium tasks too, not just big ones.

## 0.3.0 - 2026-05-18

Simplification: the four entry commands fold into one, and the assistant figures out what kind of work you mean from how you describe it.

- One command - `/alp-river:go` replaces the old `/feature`, `/plan`, `/investigate`, and `/fix`.
- The assistant figures out from your text whether it's a bug or a feature.
- On bigger tasks you get a Continue/Stop choice after the plan - design-only is one keystroke.
- Plain chat works without the command. Same pipeline either way.

## 0.2.6 - 2026-05-17

- Every follow-up confirms intent first - even one-liners.
- UI design choices get a picker page you flip through, not a text debate.

## 0.2.5 - 2026-05-16

- Acceptance criteria declare how they get verified - and the reviewer enforces it.
- Visual review is opt-in - one keystroke when you want it, silent when you don't.
- High-novelty work gets two prototypes side-by-side, not one.

## 0.2.4 - 2026-05-15

- Work that's too big gets flagged before it starts - split it, force it through, or drop it.

## 0.2.3 - 2026-05-13

- Intent, clarify, and plan-critique rounds ask via a picker, not prose.

## 0.2.2 - 2026-05-11

- Big jobs pause to ask if they're worth doing - keep going, narrow, or drop.
- The plan critic flags when a plan reaches farther than the goal needs.

## 0.2.1 - 2026-05-10

- New architecture review catches shallow wrappers and leaky interfaces.
- Quality and structure reviews now own clearly separate concerns.

## 0.2.0 - 2026-05-08

Project context becomes a first-class input. Subagents read your project's intent, stack, glossary, and prior decisions automatically instead of guessing.

- Subagents auto-read project context from `docs/` - intent, stack, glossary, ADRs.
- `/alp-river:setup` bootstraps those docs interview-style.
- Reviewers record novel terms and drift during a run; you pick what to keep.
- `/alp-river:adr` drafts a single architectural decision record from title + summary.

## 0.1.5 - 2026-05-02

- `/compact` no longer resets in-progress work.
- Pipeline steps read sequentially - the old conditional step is folded in.

## 0.1.4 - 2026-05-02

- Intent and clarification loop until nothing new comes up (cap 5 rounds).
- Agents check the codebase and the web before asking you.
- The main agent doesn't read your code during intent confirmation - a subagent does.

## 0.1.3 - 2026-05-02

- Code review splits into two passes - correctness and quality - so one no longer softens the other.

## 0.1.2 - 2026-05-02

- The intent restatement says what should be true when done, not how it gets done.

## 0.1.1 - 2026-05-01

- Reviewers read changed files directly - no more pre-built diff.
- Adjacent cleanup is its own thing now, not mixed into reviewer findings.
- Health-checker and fixer cleaned up.
- Workspace config added for local dev.

## 0.1.0 - 2026-04-26

Initial release. A multi-step pipeline that scales by task size - small tasks skip the heavy gates, big ones get full review and self-heal.

Most code assistants either rush past intent and get the wrong thing, or pile every reviewer onto every task and add friction where none is needed. alp-river splits the difference. A classifier reads each task, picks the right depth, and runs the matching set of specialist agents underneath.

- Tasks get classified S, M, L, or XL - small ones skip review, big ones get the full pipeline.
- Plan, build, review, and self-heal are separate steps so they don't soften each other.
- After-compaction state recovery so long sessions don't lose your intent or plan.
- Five slash commands cover feature work, fixes, plans, investigations, and reviews.
