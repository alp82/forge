# TODO - slim-down execution backlog

Eight self-contained work orders that slim the alp-river pipeline: fewer spawns, fewer lenses, less doctrine, and a batch of probe-verified hook bugs.

**Authority.** These tasks come from a user-approved 8-task slim-down plan (a four-agent critical analysis of this repo plus a comparison against current community meta). Every file:line reference was verified against the repo on 2026-07-03. The groupings and fixes are settled - execute them, do not re-litigate them.

**Run protocol.** One task per fresh session: start `/alp-river:go` and paste the entire task section (heading through last acceptance bullet) as the request. Each section is the sole record of its analysis - no other source exists on disk.

**Ref drift.** Line numbers drift as tasks land. Re-locate every reference by its backticked anchor phrase (Grep for it) before editing; the anchor quotes real text from the target file.

**Versioning.** Every task changes `agents/`, `hooks/`, or `WORKFLOW.md`, so CLAUDE.md `## Versioning` applies per task - follow it there, it is not restated here.

**Order.** Suggested order: 1, 2, 3, 4, 7, 8, 6, 5. Hard constraint: run Task 5 after Tasks 1, 3, 4, and 7 - all four edit WORKFLOW.md and Task 5 rewrites it. Soft constraint: Tasks 6 and 7 both edit `hooks/user-context-injector.sh` - run them serially, 7 first, so the merged clarifier's allowlist entry lands before the injector rewrite.

- [x] Task 1 - Delete the run-state-writer agent
- [x] Task 2 - Gate Stop verification on did-code-change; fix auto-format registration
- [ ] Task 3 - Make the trivial path trivial
- [ ] Task 4 - Consolidate the review wave 12 -> 4 lenses; shrink fixer blast radius
- [ ] Task 5 - Doctrine diet
- [ ] Task 6 - Injector diet
- [ ] Task 7 - Merge interviewer + requirements-clarifier
- [ ] Task 8 - Guard/hook bug fixes

## Task 1 - Delete the run-state-writer agent

**Goal:**
Stop paying one sonnet subagent spawn per loop turn for a JSON snapshot the orchestrator can write natively - or skip entirely - without losing durability.

**Evidence:**
- WORKFLOW.md:119 (anchor `HARD REQUIRED step-4 action`) - loop step 4 dispatches the run-state-writer subagent fire-and-forget in the background on every loop turn to write `.alp-river/runs/<run-id>/run-state.json`; a typical run has 15-25 loop turns, so 15-25 spawns per run.
- WORKFLOW.md:119 (anchor `two in-flight writers can land out of order`) - the doctrine itself concedes out-of-order-write races and lost in-flight writes as the cost of fire-and-forget.
- WORKFLOW.md:119 (anchor `not even as a fallback after a failed write`) - the doctrine forbids the orchestrator's native Write on the file even as a fallback, forcing the subagent indirection.
- WORKFLOW.md:323 in `## Durability` (anchor `persists its canonical run state to disk every turn`) plus step 4's own scoping (anchor `route-recomputation plus reconcile-from-tree`) - durability already rests on route recomputation plus reconcile-from-tree, not on snapshot freshness, so the dedicated writer buys almost nothing.

**Changes:**
- Delete `agents/run-state-writer.md`.
- Rewrite WORKFLOW.md loop step 4 so the orchestrator writes `run-state.json` with its native Write tool; drop the dispatch contract, the fire-and-forget caveats, and the no-inline-write prohibition. (One-line alternative worth considering while editing: drop the snapshot entirely and let `## Durability` rest on route recomputation plus reconcile-from-tree alone.)
- Sweep the verified reference list: WORKFLOW.md (:119 and :323), README.md (:328, anchor `off-route utility the orchestrator dispatches each turn`; :396, anchor `2 off-route utilities`), docs/GLOSSARY.md (:269, anchor `Defined in agents/run-state-writer.md`), hooks/tests/test_fable_tier_and_subagent_writes.py (:395, anchor `Group B - Change 2` - update its tier and write assertions to the new ownership), hooks/recover-run-state.sh (:160, anchor `dispatch the run-state-writer subagent` - update only the injected wording; keep read-back behavior unchanged).
- Regenerate `generated/catalog.json` via `hooks/gen-catalog.py`.

**Acceptance:**
- `agents/run-state-writer.md` is gone.
- A repo-wide grep for `run-state-writer`, excluding TODO.md and CHANGELOG.md, finds no matches.
- WORKFLOW.md step 4 names the orchestrator's native Write (or documents the no-snapshot decision).
- The regenerated catalog carries no run-state-writer stage.
- Hooks tests pass: `uv run --no-project --with pyyaml --with pytest pytest hooks/tests/`.
- `hooks/recover-run-state.sh` read-back behavior is unchanged.

## Task 2 - Gate Stop verification on did-code-change; fix auto-format registration

**Goal:**
Stop chat-only turns from paying up to ~320s of test and build verification, and make the auto-format hook actually run async with pinned-dependency npx calls.

**Evidence:**
- hooks/hooks.json:104-120 (anchor `"Stop"`) runs `verify-tests.py` (timeout 130, hooks.json:111, anchor `verify-tests.py`) then `verify-build.py` (timeout 190, hooks.json:116, anchor `verify-build.py`) on every Stop with no code-change check - a chat-only turn can pay up to ~320s.
- Known pain from live runs: the verifiers fire during intentional TDD red windows and while a backgrounded implementer is mid-write; this recurred across 4 milestones in one session.
- hooks/auto-format.sh:4 (anchor `Runs async so it doesn't block Claude.`) claims async, but its hooks.json entry (:88-95, anchor `auto-format.sh`) has no `async` field, so it blocks every Edit/Write for up to 30s.
- hooks/auto-format.sh:80 (anchor `npx prettier --write`) and :90 (anchor `npx @biomejs/biome format --write`) lack `--no-install`, while the lint calls at :86 (anchor `npx --no-install eslint`) and :95 (anchor `npx --no-install @biomejs/biome lint`) have it - a format call in a project without the tool can trigger a package install mid-hook.

**Changes:**
- Add a PostToolUse(Edit|Write) hook that drops a did-code-change marker file; make `verify-tests.py` and `verify-build.py` check it first - exit fast when absent - and clear it after a verified run.
- Exempt declared TDD red windows and any live backgrounded side-effecting stage from Stop verification.
- Add `"async": true` to the auto-format entry in hooks.json (copy the pattern from the notify entries at hooks.json:129 and :142, anchor `"async": true`).
- Add `--no-install` to both npx format calls, mirroring the lint form.

**Acceptance:**
- A chat-only Stop runs neither verifier.
- An Edit-turn Stop runs both verifiers, then clears the marker.
- The red-window and backgrounded-stage exemptions are honored.
- The auto-format hooks.json entry carries `"async": true`.
- Both npx format calls carry `--no-install`.

## Task 3 - Make the trivial path trivial

**Goal:**
A one-line, single-file change should not cost 6-8 subagent spawns; give the trivial-code route a genuinely short path.

**Evidence:**
- WORKFLOW.md:141 (anchor `this single router call is just the planner`) - the trivial-code worked route spends 6-8 spawns on a one-line change: triage -> code-planner -> plan gate -> code-implementer -> two review lenses (correctness + simplicity), plus router calls.
- This runs counter to current guidance; Anthropic's own heuristic: "if you could describe the diff in one sentence, skip the plan".

**Changes:**
- Rewrite the WORKFLOW.md trivial-code worked route: single-file changes at est-size <= S skip code-planner and the plan gate entirely, implement directly off confirmed intent, and take one review lens (correctness). Keep the full path for anything touching >1 file or estimated above S.
- Adjust agent frontmatter `routes`/`subscribes` as needed so the router composes the short path.
- Verify (rather than edit) the `## Locks` release policy: the plan gate arms only when a plan exists, so with no planner `#plan-ready` never fires and the lock stays inactive by design - the analog is the TDD gate at WORKFLOW.md:363 (anchor `so the lock is inactive`).

**Acceptance:**
- The worked route shows the short path for a single-file S change.
- The full path is intact above the threshold (>1 file or >S).
- `generated/catalog.json` regenerates clean via `hooks/gen-catalog.py`.
- `## Locks` is confirmed compatible without edits, or minimally adjusted.

## Task 4 - Consolidate the review wave 12 -> 4 lenses; shrink fixer blast radius

**Goal:**
Collapse the twelve-lens review wave into four always-on lenses with clear ownership, and stop the fixer from re-firing most of the wave after every fix.

**Evidence:**
- WORKFLOW.md:140 (anchor `the full Review wave`) - a significant build runs 12 lenses: correctness and simplicity always-on; quality, architecture, structure, consistency, performance, reuse, acceptance, plan-adherence, assumptions, naming-clarity on `#significant-build`.
- agents/acceptance-reviewer.md:29 (anchor `files listed in the plan were actually created/modified as described`) already checks plan adherence - a full overlap with plan-adherence-reviewer.
- agents/fixer.md:40 (anchor `correctness-reviewer → any code change`) - the domain mapping sends 6 reviewers at "any code change", so every fix re-fires most of the wave: near-quadratic re-review.
- agents/performance-reviewer.md:44 (anchor `Reporting perf costs you haven't measured`) forbids unmeasured findings, yet the agent receives only `<TOUCHED_FILES>` (:52) - it cannot measure anything, so its mandate contradicts its inputs.
- 30-45% of the six named lens files is jurisdiction text ("not mine, X owns it") backed by doctrine/reviewer-contract.md:29 (anchor `### Cut lanes`); with four lenses the lane-policing prose loses its reason to exist.

**Changes:**
- Apply the approved grouping: (1) correctness-reviewer absorbs `agents/assumptions.md` (including its silent-failure focus); (2) a design-reviewer merges quality-reviewer, simplicity-reviewer, architecture-reviewer, structure-reviewer; (3) a conventions-reviewer merges consistency-reviewer, naming-clarity, reuse-reviewer; (4) acceptance-reviewer absorbs plan-adherence-reviewer.
- Keep the conditionals: security-reviewer stays as is; the three UI lenses (ux, accessibility, design-consistency) optionally merge into one ui-reviewer gated on `#ui-touched`; test-gap and test-verifier stay.
- Fold a static-cost-only performance lens into design-reviewer, or fix performance-reviewer's mandate to match its inputs.
- Delete the jurisdiction text from the surviving lenses and the `### Cut lanes` section from doctrine/reviewer-contract.md.
- New fixer rule: re-fire only the lens(es) whose findings were fixed, plus correctness.
- Update the WORKFLOW.md worked routes and README `## Stages`; regenerate the catalog.
- Note native `/code-review ultra` as the END-wave alternative for XL diffs.

**Acceptance:**
- The always-on set is exactly correctness / design / conventions / acceptance.
- The absorbed lens files and `agents/plan-adherence-reviewer.md` are deleted.
- The Cut-lanes section is gone.
- The fixer re-fire rule is updated.
- Catalog and README match the new lens set.

## Task 5 - Doctrine diet

**Goal:**
Cut WORKFLOW.md from 516 lines toward ~250 by deleting phantom machinery, resolving contradictions, and removing ceremony that no stage or user ever exercises. Community meta agrees: "Bloated CLAUDE.md files cause Claude to ignore your actual instructions" - the same holds for a 516-line doctrine file injected into every run.

**Evidence:**
- WORKFLOW.md is 516 lines; target is ~250.
- Phantom machinery in doctrine/SIGNALS.md - named subscribers that exist as no stage anywhere: :63 (anchor `cleanup gate`), :79 (anchor `after-plan gate`), :120 (anchor `cost gate (advisory only`); :121 (anchor `size-crossed`) claims "published by router" while `hooks/route.py` emits no signals at all.
- Contradiction one: WORKFLOW.md:134 (anchor `never picks stages`) declares est-size advisory only, while :368-370 (anchor `load-bearing`) makes it load-bearing for the trivial-code auto-release decision.
- Contradiction two: WORKFLOW.md:121 (anchor `is never convergence`) requires an empty held map for convergence, while SIGNALS.md:138 (anchor `A route is **done** when`) defines convergence without that clause.
- Ceremony: doctrine/briefs.md carries a two-level escalation ladder - plain-words re-render then a `.briefs/` HTML doc (briefs.md:27, anchor `See it in plain words`), paste-back token grammars (:38, anchor `The paste-back token`), slug reduction (:34, anchor `Slug reduction`), and a wait-for-paste-back step (:15, anchor `awaiting the paste-back`); doctrine/render-card.md's grammar reduces to a minimal card; the Run-timing readout with per-group/per-milestone rollups (WORKFLOW.md:117, anchor `Run-timing readout`; :294, anchor `renders one final timing card`) goes entirely.

**Changes:**
- Delete the phantom mechanisms (cleanup gate, after-plan gate, cost gate, size-crossed) from SIGNALS.md and every reference to them.
- State est-size in exactly one home, resolving advisory-vs-load-bearing.
- Align the two convergence definitions on one clause set: one canonical home, cross-referenced from the other.
- Delete the briefs escalation ladder and all `.briefs/` references; keep the plain inline card.
- Reduce doctrine/render-card.md to a minimal card grammar.
- Remove the Run-timing readout entirely (WORKFLOW.md:117, :294, and its render-card.md layout section).
- Cut WORKFLOW.md toward ~250 lines.

**Acceptance:**
- Deleted mechanisms are unreferenced repo-wide, excluding TODO.md and CHANGELOG.md.
- est-size is stated in exactly one home.
- The briefs escalation and every `.briefs/` reference, excluding TODO.md and CHANGELOG.md, are gone.
- WORKFLOW.md is near 250 lines.

**Ordering:**
Run after Tasks 1, 3, 4, and 7 - all four edit WORKFLOW.md and this task rewrites it.

## Task 6 - Injector diet

**Goal:**
Shrink the per-spawn context injector: stop re-reading the world on every subagent spawn, stop corrupting strict output contracts with persona directives, and drop the subprocess fan-out.

**Evidence:**
- `hooks/user-context-injector.sh` is 505 lines and fires on every PreToolUse(Agent) dispatch (hooks.json:81, anchor `user-context-injector.sh`); it re-reads MEMORY.md plus linked memory files, docs, ADR summaries, doctrine slices, and a persona on each spawn - a 15-spawn run re-reads everything 15 times.
- user-context-injector.sh:478 (anchor `restate your Anchor above in your own voice`) orders every persona-mapped agent to open its response by restating its Anchor - which corrupts strict output contracts (the fixer's `FIXED:`/`RE_RUN_SET:` lines, the investigators' `SEVERITY`/`COMPLEXITY` lines).
- The psychology layer maps only 13 of the 52 agent files (`psychology/agent-map.json`); no core review lens has a persona; each persona's Conflict rule declares itself advisory.
- A ~60-line awk ADR parser embedded at :221-280 (anchor `extracted=$(awk`) fans out one subprocess per ADR file on every spawn.

**Changes:**
- Cut the Anchor-restate directive at :478.
- Psychology decision: keep personas only for discuss + plan-challenger (the default), or delete the layer entirely (`psychology/`, `agent-map.json`, the PSYCHOLOGY block in the injector).
- Rewrite the ADR parser in Python or simplify it - one pass, no per-ADR subprocess.
- Slice doctrine injection per agent type so each spawn receives only its relevant slice.

**Acceptance:**
- The Anchor-restate directive is gone.
- Strict-output agents receive no persona ordering.
- `agent-map.json` matches the kept persona set (or is deleted with the layer).
- No per-ADR subprocess fan-out remains.

**Ordering:**
Serialize with Task 7, Task 7 first - both edit `hooks/user-context-injector.sh`, and the merged clarifier's allowlist entry must land before this rewrite.

## Task 7 - Merge interviewer + requirements-clarifier

**Goal:**
One clarifier agent instead of two near-identical ones, so a user faces at most 5 question rounds before a plan exists instead of up to 10.

**Evidence:**
- Both agents are research-first question loops with a 5-round cap (agents/interviewer.md:26 and agents/requirements-clarifier.md:30, both anchor `capped at 5 rounds`), PRIOR_ROUNDS folding (interviewer.md:57 and requirements-clarifier.md:74, anchor `compressed log of prior rounds`), and AskUserQuestion pickers.
- The split rests on an altitude judgment that leaks both ways: the interviewer probes out-of-scope boundaries while requirements-clarifier.md:40 (anchor `adjacent things that might be in or out - force a decision`) probes the same.
- Because each loop carries its own 5-round cap, a user can face up to 10 question rounds before any plan exists.

**Changes:**
- Author one clarifier agent handling both altitudes (intent-level and requirements-level) under a single 5-round cap.
- Delete `agents/interviewer.md` and `agents/requirements-clarifier.md`.
- Update WORKFLOW.md `### Intent` and `## Clarification Loops`, and the `## Concise Surfacing Contract` picker-eligible list.
- Update the injector allowlists in `hooks/user-context-injector.sh`: the case statement (interviewer arm at :77, requirements-clarifier arm at :79), READ_MAP (:119-120), and the briefs map entry (:189).
- Regenerate `generated/catalog.json` via `hooks/gen-catalog.py`.

**Acceptance:**
- Exactly one clarifier agent remains.
- At most 5 question rounds occur before a plan exists.
- Every reference surface (WORKFLOW.md sections, injector allowlists, picker-eligible list) is updated.
- The catalog regenerates clean.

**Ordering:**
Run before Task 6 - both edit `hooks/user-context-injector.sh`, and this task's merged-clarifier allowlist entry must land before the Task 6 injector rewrite.

## Task 8 - Guard/hook bug fixes

**Goal:**
Fix four probe-verified hook bugs: the git-write guard's false positives and fail-closed jq dependency, the macOS notification injection, the audit rationale-marker false matches, and the catalog generator's universal PyYAML tax.

**Evidence:**
- `hooks/block-git-writes.sh` greps the raw command string via regexes at :69 (anchor `blocked_verbs=`) and :74 (anchor `blocked_push_destructive=`), applied at :92 (anchor `grep -qE`). Probe-verified false positives: `git commit -m "docs: explain why git reset is blocked"` is blocked (verb inside the message), `echo "never run git reset --hard"` is blocked, and read-only `git stash list` is blocked. Probe-verified bypasses: `g''it reset --hard`, `git${IFS}reset`, `bash script.sh`, and python subprocess all pass.
- The guard fails CLOSED when jq is missing (block_static at :32-34, anchor `requires jq`), so a missing dependency blocks every commit.
- `hooks/notify.sh:26` (anchor `display notification`) interpolates the message unescaped into the osascript AppleScript literal - injection via quotes/backslashes; the notify-send path at :20 (anchor `notify-send -u normal`) is safe.
- `hooks/audit.py:70-81` (anchor `RATIONALE_MARKERS`) includes naked substrings `"so "` (:73) and `"since"` (:77), so "also" and "torso" count as rationale; the comment at :68 (anchor `naked-substring matches`) already flags the fragility.
- `hooks/gen-catalog.py:29-33` (anchor `import yaml`) imports yaml at module load, before the hook-payload early return at :42 (anchor `changed_path_from_hook_payload`), so every Edit/Write in every project pays PyYAML startup.

**Changes:**
- In block-git-writes.sh, match the command position (first token per pipeline segment) instead of substring-anywhere, and decide fail-open-with-warning when jq is absent (or document the deliberate fail-closed choice).
- Escape the message in the macOS osascript branch of notify.sh.
- Word-bound the rationale markers in audit.py, or drop the metric.
- Move the yaml import in gen-catalog.py below the hook-payload early return.

Safety notes for this task: run tests via `uv run --no-project --with pyyaml --with pytest pytest hooks/tests/`; probe the guard via pytest or split literals, never inline shell; this task's own text trips the guard if pasted into Bash - use the Read/Grep tools while working it.

**Acceptance:**
- The named false positives pass (commit message, echo string, `git stash list`).
- A jq-absent environment warns and allows (or the documented decision holds).
- Quotes and backslashes in a notification render safely on macOS.
- "also" no longer counts as rationale.
- A non-plugin Edit pays no yaml import.
- Hooks tests are green.
