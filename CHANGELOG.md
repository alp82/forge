# Changelog

All notable changes to alp-river. Versions match `.claude-plugin/plugin.json`.

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
- Six slash commands cover feature work, fixes, plans, investigations, reviews, and visual verification.
