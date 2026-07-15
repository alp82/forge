# alp-river pipeline audit

Date: 2026-07-15. Auditor: evidence-only pass over the installed plugin (1.4.0) and real session transcripts. This document supplies evidence for a keep/cut decision toward a public, skill-first toolkit (bar: memorable one-word names, composability, one-read brevity). It does not make the decision.

All numbers are measured from primary sources; every claim cites a file path, a session uuid, or a script output. Estimates are labeled. House style: hyphens only.

## Executive summary

**Corpus.** 42 active sessions in the plugin repo (2026-06-16 to 2026-07-15, ~298 MB of JSONL), plus 8 other project dirs where the plugin ran. 3,068 alp-river subagent spawns total across all projects; 951 of them in the plugin repo, 2,117 in consumer repos (aistack-web 415, alperortac 988, wts-monorepo 295, genius-prism 247, alfredo 178, system dirs 43). The pipeline is genuinely dogfooded outside its own repo.

**Headline cost numbers (plugin-repo corpus, 42 sessions).**

- Main-thread (orchestrator): 14.05 M output tokens, 2.9 M fresh input, 67.8 M cache-creation, 1.26 B cache-read.
- All 944 subagent transcripts combined: 8.9 M output tokens, 1.9 M fresh input, 133.6 M cache-creation, 1.11 B cache-read, 52.9 h cumulative subagent wall-clock.
- The "thin orchestrator" out-emits its entire worker fleet: 14.05 M vs 8.9 M output tokens, and it runs on the two most expensive models (opus-4-8: 10.3 M out; fable-5: 3.7 M out; measured per-message `model` fields).

**Headline latency.** End-to-end wall per run (deep-dive sessions): S-tier planned build 15 min; M-tier removal build 75 min; XL doctrine build 158 min, of which 66 min was the plan-challenge-revise ping-pong alone. The parallel review wave is the best-behaved phase: 7 lenses complete in the time of the slowest member (~5 min) instead of the ~16 min serial sum.

**Verdict list (evidence, not decision).**

Demonstrably earn their cost:

1. `plan-challenger` - repeatedly caught verified, concrete defects pre-implementation (a ship-gate timing hole that would have committed an unconverged tree; an unnecessary Write tool grant to four agents; a circular self-check that could never fail). See section 4.
2. `test-review` red-test validation plus the `verify-tests` stop gate - caught misaligned/false-green tests before implementation ~60 times and blocked stops on failing suites dozens of times at a median 2.3 s per check.
3. The parallel review wave (`correctness` + `acceptance` in particular) plus the `fixer` heal loop - cheap (fixer median 92 s), visibly closes findings, and the acceptance lens caught real half-executed plan items.
4. `triage` as an always-on haiku seed - median 42 s, ~5.7 K output tokens, and it roots every route.
5. The deterministic router (`hooks/route.py`, 240 lines) - route decisions cost zero tokens.

No recorded evidence of earning their cost (absence of evidence is the finding):

1. Seven of the 42 shipped agents have never been spawned in any project, ever: `explainer-prototyper`, `performance-prototyper`, `plan-arbiter`, `safety-gate`, `ship-executor`, `ship-gate`, `ux-prototyper`. The multi-plan doctrine (`doctrine/multi-plan.md`, 7.3 KB) has zero armed runs.
2. Near-zero use: `discuss` (1 spawn), `data-prototyper` (1), `system-investigator` (3), `code-prototyper` (8), `researcher` (9).
3. The Scout band (`health-checker` 64 spawns, `prototype-identifier` 64, `reuse-scanner` 66) runs on every significant build but no transcript shows its output changing a route or a plan in a traceable way; `prototype-identifier` produced a domain-prototyper follow-up in at most 9 of 64 runs.
4. 508 spawns (17% of all alp-river spawns) went to agent types that were later retired or merged away - paid-for review depth the fleet itself judged not worth keeping.

Biggest frictions: a ~280-token named vocabulary (76 signals, 40 XML slots, 119 output fields, plus markers, artifacts, and run-state keys); orchestrator overhead on premium models; and a revision model that re-spawns fresh agents - 60 planner revisions cost an average 166 K cache-write tokens and 218 s median wall each (5.1 h total).

## 1. Token and latency cost per stage

### 1.1 Per-stage averages, plugin-repo corpus

944 subagent transcripts, aggregated per agent type (script: `agg.py`, see appendix). "fresh" = uncached input tokens; cache-read is roughly an order of magnitude cheaper than fresh input, so output tokens and cache-creation dominate real cost. Median wall is more honest than mean (one `health-checker` transcript spans hours of idle and skews its mean to 1,371 s vs a 94 s median).

| stage (current fleet) | n | avg out tok | avg cache-create | avg cache-read | med wall s | avg turns |
|---|---|---|---|---|---|---|
| code-planner | 79 | 28,368 | 301,469 | 1,495,384 | 312 | 31.6 |
| plan-challenger | 52 | 22,005 | 288,170 | 1,792,155 | 403 | 38.0 |
| code-implementer | 61 | 18,415 | 221,808 | 4,971,436 | 261 | 71.6 |
| test-author | 38 | 10,239 | 137,186 | 2,034,177 | 128 | 36.8 |
| test-plan | 27 | 9,584 | 98,735 | 458,566 | 124 | 19.7 |
| clarifier | 10 | 7,917 | 104,891 | 218,188 | 125 | 10.3 |
| test-review | 29 | 7,512 | 160,861 | 681,360 | 110 | 20.2 |
| test-gap | 26 | 7,244 | 111,876 | 1,286,346 | 88 | 32.1 |
| acceptance-reviewer | 29 | 6,935 | 124,965 | 1,389,081 | 122 | 40.2 |
| correctness-reviewer | 76 | 6,116 | 104,618 | 619,529 | 104 | 24.5 |
| reuse-scanner | 26 | 5,858 | 185,426 | 1,184,535 | 101 | 35.7 |
| triage | 50 | 5,690 | 99,272 | 695,618 | 42 | 23.5 |
| shape-reviewer | 12 | 5,646 | 94,860 | 506,270 | 94 | 18.8 |
| fixer | 46 | 5,232 | 76,370 | 873,474 | 92 | 30.9 |
| health-checker | 26 | 4,734 | 176,017 | 1,586,618 | 94 | 47.7 |
| prototype-identifier | 25 | 4,466 | 121,191 | 800,894 | 72 | 32.0 |
| simplicity-reviewer | 44 | 3,948 | 86,461 | 513,474 | 74 | 18.3 |
| test-verifier | 41 | 1,846 | 40,370 | 184,043 | 28 | 14.7 |

The consumer-repo picture matches: in the alperortac project (1,003 spawn transcripts, 8.2 M output tokens, 36.5 h subagent wall) the same three stages lead - code-planner 26.2 K avg out / 326 s median, code-implementer 14.2 K / 200 s, plan-challenger 19.1 K / 167 s (script: `agg2.py`).

**Where the tokens go.** Blueprint (planner + challenger) and Build (implementer) are the cost centers - the three fable/opus-class stages hold the top three slots for output tokens per spawn everywhere measured. Review lenses are individually cheap (2-7 K out, 30-120 s) and run in parallel. Model tiering works as declared: triage/health-checker/prototype-identifier run on haiku, review surface lenses on sonnet, planner/challenger/implementer on fable-5 or opus-4-8 (measured per-message `model` fields, script `models.py`).

### 1.2 The orchestrator is the largest single consumer

Across the 42 plugin-repo sessions the main thread emitted 14.05 M output tokens - more than all 944 subagents combined (8.9 M) - and consumed 1.26 B cache-read tokens re-reading its own growing context every loop turn. All of it on opus-4-8 (10.3 M out) and fable-5 (3.7 M out); the router itself is free (deterministic `hooks/route.py`), so this cost is loop bookkeeping: render cards, status lines, reading stage returns, and relaying artifacts verbatim into the next spawn's prompt (avg spawn prompt: code-planner 7.6 KB, code-implementer 5.3 KB, plan-challenger 4.9 KB - measured from 951 Task calls).

### 1.3 End-to-end wall-clock per run (deep dives)

- **S-tier planned build** - session `2c047a4e` (2026-07-11), run 2 ("gitignore-hook restore"): triage 17:09 to fixer done 17:24 = **15 min** (triage 111 s, plan 152 s, implement 247 s, 2 reviews, fixer 22 s).
- **Document-authoring build** - session `263416f8` (2026-07-03), TODO.md run: 10:54 to 11:26 = **32 min** (triage 282 s, plan 502 s, implement 393 s, reviews, fixer).
- **M-tier removal build** - session `2c047a4e` run 1: 15:17 to 16:32 = **75 min**. Breakdown: triage+Scout ~13 min, plan-challenge-revise-rechallenge 19 min, TDD chain ~6 min, implementer 26 min (285 turns), 7-lens parallel review wave ~5 min, heal loop + 5 re-reviews ~2 min.
- **XL doctrine build** - session `154a6992` (2026-07-09), the doctrine-diet task: 06:28 to 09:06 = **158 min**. The plan-challenge ping-pong (plan 789 s, challenge 610 s, revise 516 s + 414 s, re-challenge 626 s, revise 482 s, re-challenge 531 s) consumed **66 min** before the first implementer ran at 08:18 - 110 min into the run.
- **Consumer work repo** - session `888246b9` (wts-monorepo, 2026-06-22/23): 65 spawns, 9.2 h cumulative subagent wall across multiple phases; single mid-size phase (triage 14:41 to fixer 16:45) ~2 h, dominated by implementer spawns of 19-100 min (largest single implementer: 6,002 s).

Sessions span far more wall than active work: `154a6992` spans 2.88 h with 0.60 h of active main-thread time (event gaps capped at 5 min); `888246b9` spans 33.5 h with 4.59 h active. Latency the user actually feels is the per-run figures above.

## 2. Friction points

### 2.1 Vocabulary an orchestrator (or user) must hold

Counted from the installed doctrine (script `vocab.py`):

- **76 signal topics** - 71 in the `doctrine/SIGNALS.md` tables plus 5 ship-tail signals defined only in `WORKFLOW.md` (`ship-requested`, `ship-ready`, `ship-approved`, `shipped`, plus `est-size` as used).
- **41 stages** in `generated/catalog.json`; 42 agent files.
- **40 XML-style input/output slots** (`<APPROVED_PLAN>`, `<REPLAN_REASON>`, `<SCOUT>`, ...).
- **119 ALL_CAPS output field names** across `agents/*.md` (`VERDICT`, `BLOCKERS`, `SIGNALS_PUBLISHED`, `EVIDENCE_RECEIPT`, ...).
- **6 @artifact names**, **4 run-state keys** (`live`, `available`, `ran`, `premises`) plus the `held` map, **8 card markers**, **10 phase/path banners** (`doctrine/render-card.md`).

Total: roughly 280 named tokens. Judged against the stated bar (memorable one-word names, one-read brevity), the grammar is internally consistent (lowercase-kebab, `family:qualifier`) but the volume is the friction, and several clusters are confusable by design:

- The signal `intent-confirmed` vs the artifact `confirmed-intent` differ only in word order; `WORKFLOW.md` (Pipeline, loop step 4) has to warn "two different keys, never conflated" - doctrine defending against its own vocabulary.
- The plan family needs four states (`plan-ready`, `plan-approved`, `plan-challenged`, `#direct-impl` silence) and the test family six (`test-cases-ready`, `tests-red`, `tests-misaligned`, `tests-ready`, `tests-green`, `tests-missing:<x>`).
- `est-size` is "advisory" but "load-bearing in exactly two decisions" (`WORKFLOW.md` Locks, Release policy), and the threshold is stated twice as De Morgan duals "kept in sync by this cross-reference" - a rule that requires two paragraphs to be co-edited is the opposite of one-read.
- Doctrine bytes an orchestrator is told to read on demand: `WORKFLOW.md` 52.4 KB (~13 K tokens), `SIGNALS.md` 10.3 KB, `render-card.md` 6.2 KB, `CATALOG.md` 4.3 KB. The 42 agent files total ~187 KB.

Direct user evidence that the vocabulary leaked and annoyed: `memory/feedback_speaking_names_in_io.md` (user flagged `R0.Q0: classifier gate scope-down | A: reduce scope` as cryptic) and `memory/feedback_terse_status_lines.md` (raw `#needs-tests`/`@diff` topics reaching the user's screen; the render-card grammar now bans raw topics on user surfaces).

### 2.2 Permission prompts

- Recorded hard denials are rare: 4 "user doesn't want to proceed" tool-result rejections across the 42 plugin-repo sessions (sessions `5f101a97` x2, `616d09c0`, `696e1fb9`).
- Approved-after-prompt events are not written to transcripts, so prompt count could not be measured - but the user's own memory file documents the pain: `memory/feedback_prefer_tools_over_shell.md` ("The user is repeatedly forced to approve read-only Bash commands and wants them to stop"), and `~/.claude/CLAUDE.md` carries a whole "Shell command hygiene" section as a standing mitigation. A `PermissionRequest` notification hook (`hooks/hooks.json`) pings the user on every prompt, so each one is a real interruption.
- The `block-git-writes.sh` PreToolUse guard fired 704 times in the corpus (zero-byte output; pure guard). It has a documented false-positive mode: `memory/project_guard_testing_from_inside_repo.md` - it "fires on raw command text even in string literals", which bit development inside the repo.

### 2.3 Hook overhead

From `hooks/hooks.json`: 8 hook events, 14 registrations. Measured (script `agg.py` + stop-hook scan):

- **SessionStart** `inject-workflow.sh`: ~2.1-2.3 KB injected per session start/resume/clear/compact; 97 firings, 105.6 KB total across the corpus. Cheap; this is the pointer-not-spec design working as intended.
- **PreToolUse(Agent)** `user-context-injector.sh`: per-spawn payload = doctrine slices (reviewers 8.3 KB: reviewer-contract + confidence-tagging + discoveries + communication; planner/challenger 3.4 KB; implementer 4.9 KB) + USER_CONTEXT (the whole memory dir for user-aware agents: 37.6 KB in alp-river, 76.0 KB in aistack-web, 28.0 KB in alperortac). A user-aware reviewer spawn in aistack-web starts ~84 KB (~21 K tokens) heavier before its task prompt. This is a large share of the measured 141 K average cache-creation per subagent spawn.
- **Stop / SubagentStop** `verify-tests.py` + `verify-build.py`: 825 Stop firings in the plugin repo (2,845 across six repos). verify-tests median 2.3 s, p90 5.8 s, max 19.5 s, cumulative 28.9 min in the plugin repo; verify-build median 23 ms. 72 stop events carried hook errors.
- **PostToolUse(Edit|Write)**: auto-format + gen-catalog + mark-code-change run on every file write (17 recorded attachment events; most output is silent).

Hook overhead is small in absolute terms; the USER_CONTEXT payload is the one measurable heavyweight, and it scales with memory-dir size, not task size.

### 2.4 Re-spawn costs (revisions are fresh spawns by design)

The Revision Contract (`WORKFLOW.md`) mandates fresh spawns with the prior artifact folded in. Measured across 4 projects by matching revision Task calls (prompts carrying `<REPLAN_REASON>` / `<TEST_CORRECTIONS>`) to their subagent transcripts (script `revcost.py`):

- **code-planner revisions: 60** (of 185 planner spawns, 32%). Average per revision: 22,177 output tokens, 166,200 cache-creation tokens, 638,629 cache-read; median wall 218 s; total 5.08 h and ~10 M cache-write tokens spent on re-spawning planners.
- **test-author revisions: 46** (of 126 spawns, 37%). Average 8,251 out, 96,251 cache-create; median 82 s; total 1.94 h.
- **clarifier loops** are also fresh spawns per round: 14 of 15 `clarifier` spawns and 23 of 35 legacy `requirements-clarifier` spawns carried `<PRIOR_ROUNDS>`.

The overhead vs a continuation is the context rebuild: each re-spawn re-pays the agent definition, doctrine injection, and prior-artifact fold (planner revision prompts average 6.8 KB) as fresh cache-writes, and the guard instruction ("reproduce exactly except where a correction applies") makes the model re-emit the full artifact (revision output 22 K tokens is ~78% of a first-pass plan's 28 K). Counterpoint for fairness: the sampled revisions carried real corrections (section 4), so the loop content was not waste - the mechanism is what costs.

### 2.5 Retired-fleet spend

508 spawns (17% of all 3,068) went to agent types that no longer exist in 1.4.0 (consistency-reviewer 57, structure-reviewer 55, plan-adherence-reviewer 46, capture-agent 45, requirements-clarifier 42, assumptions 40, reuse-reviewer 38, architecture-reviewer 36, quality-reviewer 34, naming-clarity 28, run-state-writer 82, interviewer 3, visual-verifier 2). Session `3a9bf555` (aistack-web, 2026-06-23) shows the June-era review wave at full fan-out: 16 lenses over one diff. The fleet was consolidated to 5-7 End-Review lenses by 1.4.0 - the project already concluded this depth was not worth it; the 508 spawns are the measured price of finding that out.

## 3. Quality degradation

### 3.1 User-flagged failures (memory feedback files - each records a real correction)

13 feedback files in `~/.claude/projects/-home-alp-dev-projects-alp-river/memory/`, all direct evidence the pipeline's output or behavior missed confirmed intent. Grouped:

- **Over-ceremony / noise** (4): `feedback_terse_status_lines.md` (verbose mechanism narration; user supplied before/after examples like "This build carries #needs-tests, so the implementer stays locked..." to `#needs-tests ▶ start writing tests`); `feedback_essentials_examples.md` ("user repeatedly stalls on abstract questions with 'don't know, need an example'"); `feedback_clarify_before_picker.md` (user twice chose "let me clarify" instead of answering a premature AskUserQuestion picker, session `5f101a97`); `feedback_no_manufactured_artifacts.md` (pipeline proposed seeding a ledger with sub-threshold entries to dogfood it; user: "we shouldnt add friction just for the sake of having something").
- **Process bypass** (1): `feedback_never_bypass_pipeline.md` - the agent skipped the pipeline for a "mechanical CSS edit", a scope question surfaced mid-stream that clarify would have caught; user: "this should never happen".
- **Wasted planning on an unmeasured premise** (1): `feedback_validate_premise_before_design.md` - "Lean-returns... took ~6 planning rounds before a ground-up profile showed reviewer returns were already lean (~2 KB) and the real lever was the inbound plan-handle." Six planner-challenger rounds spent on a fix for a cost that did not exist.
- **Vocabulary / altitude drift** (3): `feedback_speaking_names_in_io.md` (cryptic codes), `feedback_intent_restatement.md` (a Level-1 restate degenerated into a run-on enumeration of schema fields and function names), `feedback_affirmative_phrasing.md` (doctrine written as prohibitions).
- **Smaller repeated corrections** (4): `feedback_no_em_dashes.md`, `feedback_no_bump_for_tiny_edits.md` (three separate over-bump corrections logged), `feedback_fix_drift_dont_record.md` ("dont accept any drifts anymore, just fix it always"), `feedback_prefer_tools_over_shell.md`.

### 3.2 Kickbacks, disputes, and churn in the transcripts

Line-level marker counts across 4 projects (upper bounds - line hits include doctrine text that quotes the markers; script `revisions.py`):

- `scope-shift` mentions: 260; implementer-kickback phrasing: 174; `tests-misaligned`: 60; explicit challenger `VERDICT: revise` lines: 11.
- Hard counts from spawn prompts (not inflatable by doctrine text): 60 planner re-plans, 46 test-author correction rounds.
- Genuine `INPUT_ERROR: missing <slot>` emissions: effectively zero (6 line-hits in assistant text, none of them actual template-failure stops) - the Input Template Contract's failure mode almost never fires in practice.

### 3.3 Harness failures the pipeline absorbs

Session `3a9bf555` (aistack-web) shows four subagent spawns returning zero tokens in one afternoon (e.g. "Re-verify correctness post-fix", 06-24 13:08 and 13:12, each ~200 s wall, 1 turn, 0 output - the `[Tool result missing due to internal error]` class), each followed by a manual re-spawn. The Recovery doctrine exists because this really happens; the cost is a few minutes and a re-spawn each time.

### 3.4 Doctrine drift as measured quality debt

The doctrine-diet task itself (session `154a6992`, 2026-07-09) is primary evidence that the doctrine accretes wrongness: its brief (quoted in the triage prompt) lists phantom machinery in `doctrine/SIGNALS.md` - named subscribers ("cleanup gate", "after-plan gate", "cost gate") that existed as no stage anywhere, and `size-crossed` "published by router" while `hooks/route.py` emits no signals - plus two internal contradictions in WORKFLOW.md (est-size advisory vs load-bearing; empty-held convergence vs a held-map clause). A 516-line WORKFLOW.md had to be cut toward ~250 because stages and users were ignoring parts of it.

## 4. The keepers (and the unearned)

### 4.1 Evidence-backed keepers

**plan-challenger.** The strongest single case in the corpus. Sampled `<REPLAN_REASON>` packages show verified, concrete, pre-implementation catches, not style nits:

- Session `8b24fc17` (2026-06-25): challenger proved (against `route.py` line behavior) that the planned ship-gate would fire mid-build - "a Proceed would release the executor and commit/push an unconverged tree" - and that a second lock "would strand the executor in `held` forever". Both fixed before any code ran.
- Session `c07c8cb7` (2026-06-24): challenger's SIMPLER_ALTERNATIVE killed a Write-tool grant to four read-only agents (a real security-surface reduction); the user approved the alternative.
- Session `11981bab` (2026-06-16): challenger caught a milestone that "over-builds an anti-over-engineering feature, pins a tautology, and ships a red suite", including a self-check that was circular ("a name read from a case arm is non-orphaned by construction, so it can never fail").

Cost: 124 spawns all-projects, ~22 K out and 5-7 min per run, plus the revision churn it triggers (section 2.4). The samples say the churn carried substance.

**test-review + the TDD chain's misalignment catch.** `test-review` validated red tests before code 104 times all-projects and kicked tests back repeatedly: session `888246b9` (wts) shows "Fix red test alignment" (834 s test-author correction round) and session `3a9bf555` (aistack) "Fix GROUP W false-green tests" - false-green tests are exactly the defect class that silently ruins TDD. 46 measured test-correction rounds.

**verify-tests / verify-build stop gates.** Deterministic, cheap (median 2.3 s / 23 ms), and they block for real: "Stop hook feedback" block events appear 73 times in plugin-repo transcripts, 27 in aistack-web, 117 across seven repos (upper bounds include other stop hooks; the verify-gate fail message "Tests are failing. Fix them before completing." appears in 20+ plugin-repo sessions). This is the Instruction-to-hook principle (`WORKFLOW.md`) earning its keep: a mechanical recurring check moved out of prompts into a hook.

**The parallel review wave, correctness + acceptance lenses, and the fixer loop.** In `2c047a4e` the 7-lens wave finished in ~5 min (slowest member 302 s) vs a 16-min serial sum; the fixer then closed findings in 23 s and 5 re-reviews confirmed. The acceptance lens catches real intent gaps: a sampled finding reads "WORKFLOW.md:110 - plan item (g) half-executed: the effort-clause edit landed but..." (VERDICT: partial, session `2c047a4e`, 2026-07-11). The reviewer contract's mechanics also hold up in practice: findings arrive tagged `[likely]`/`[unsure]` with `SIGNALS_PUBLISHED` machine-readable convergence lines (`doctrine/reviewer-contract.md`).

**triage.** 163 spawns all-projects, haiku, median 42 s, ~5.7 K out. Every route roots in it and no memory file or transcript sampled shows a triage misroute the user had to correct (the one pipeline-bypass failure documented was the orchestrator skipping triage entirely, which argues for triage, not against it).

**The deterministic router.** `hooks/route.py` is 240 lines; route composition and recomposition costs zero model tokens per turn. Whatever else is cut, this design choice (routing as code, not prompting) is validated by the orchestrator-cost numbers in 1.2 - the expensive part of orchestration is everything except routing.

**Qualitative keepers (real effect, cost measured, benefit not quantifiable from transcripts):** USER_CONTEXT memory injection (user preferences like no-em-dashes and terse status lines demonstrably persist across sessions and repos - the corrections stopped recurring after being captured); the render-card/status-line grammar (it was shaped directly by user feedback in `feedback_terse_status_lines.md` and the raw-topic ban).

### 4.2 No evidence of earning their cost

Labeled explicitly: absence of evidence, measured over ~30 days and 3,068 spawns.

- **Never spawned anywhere, ever** (0 uses across all project dirs): `ship-gate`, `ship-executor` (the whole shipping tail), `safety-gate`, `plan-arbiter` (and with it every armed multi-plan run - `doctrine/multi-plan.md` 7.3 KB has zero exercises), `ux-prototyper`, `explainer-prototyper`, `performance-prototyper`. Their doctrine weight is nontrivial: Shipping, Locks (ship/safety clauses), multi-plan, and the milestone-arbiter interactions account for a large slice of WORKFLOW.md's hardest paragraphs.
- **Near-zero**: `discuss` (1 spawn - the talk path answers inline, so the stage almost never composes), `data-prototyper` (1), `system-investigator` (3), `code-prototyper` (8), `researcher` (9), `visual-verifier` (2, retired).
- **Scout band, weak signal**: `reuse-scanner` (66), `health-checker` (64), `prototype-identifier` (64) run on every significant build (~4-6 min combined per run, ~15 K out) but no sampled transcript shows a route or plan change traceable to their output; prototype-identifier led to a domain prototyper in at most 9 of 64 runs. They may steer plans invisibly (planners receive `<SCOUT>`), but nothing measurable demonstrates it.
- **est-size**: the advisory-but-load-bearing contradiction was real enough to be a named target of the doctrine-diet task (section 3.4). What remains is two decisions hanging on a signal the doctrine elsewhere calls a "readout".
- **run-state-writer** (82 spawns, retired): pure bookkeeping spend - 82 spawns averaging 740 output tokens and 13 s that the current design (no on-disk run state, `WORKFLOW.md` Compaction) deleted outright.

## Appendix: methodology

### Sources

- Plugin source: `/home/alp/.claude/plugins/cache/alperortac/alp-river/1.4.0/` (WORKFLOW.md, doctrine/, agents/, commands/, hooks/, generated/catalog.json). Dev repo `/home/alp/dev/projects/alp-river` matches plus docs/.
- Transcripts: `/home/alp/.claude/projects/-home-alp-dev-projects-alp-river/*.jsonl` (46 files, ~298 MB; 42 with activity) and per-session `*/subagents/*.jsonl` + `*.meta.json` (agentType, toolUseId). Additional project dirs scanned for alp-river spawns: `-home-alp-dev-projects-alperortac`, `-home-alp-dev-projects-aistack-aistack-web`, `-home-alp-dev-work-wts-wts-monorepo`, `-home-alp-dev-work-genius-repos-genius-prism`, `-home-alp-dev-projects-alfredo-*`, `-home-alp`, `-home-alp--config-hypr*`.
- Memory: `/home/alp/.claude/projects/-home-alp-dev-projects-alp-river/memory/*.md`.
- Excluded: session `9bde8a1a-4e91-46c6-b8c1-1a17f76c4961` (this audit).

### Deep-dive sessions

| session | date | repo | why chosen |
|---|---|---|---|
| `154a6992-4630-4cd9-a904-3bf5c8b5945d` | 2026-07-09 | plugin repo | XL build, plan-challenge ping-pong, milestone loop |
| `2c047a4e-3c94-44ad-b26c-6158b29b5054` | 2026-07-11 | plugin repo | recent 1.3.x-era, one M run + one S run in a session |
| `263416f8-8319-47bf-8417-591c88abff93` | 2026-07-03 | plugin repo | small doc-authoring build |
| `3a9bf555-86d9-4b98-8d7c-cc19f450297a` | 2026-06-23 | aistack-web | consumer repo, June-era 16-lens wave, harness failures |
| `888246b9-381d-4a5b-8d21-08b495c7786c` | 2026-06-22 | wts-monorepo | large real work repo, multi-phase |

### Computation

Python scripts in the session scratchpad (`agg.py`, `agg2.py`, `other_projects.py`, `deepdive.py`, `revisions.py`, `revcost.py`, `vocab.py`, `models.py`, `samples.py`). Token sums read `message.usage` (input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens) from assistant events. Subagent wall = last minus first timestamp of the subagent transcript. Active time = sum of inter-event gaps capped at 5 min. Revision costs matched spawn `tool_use.id` to `meta.json` `toolUseId`. Stop-hook data read from `system`/`stop_hook_summary` events (`hookInfos[].durationMs`). Never-spawned agents = 1.4.0 `agents/*.md` set minus all `agentType` values in every `*.meta.json` under `~/.claude/projects/*/*/subagents/`.

### Known limitations

1. **Version drift.** The corpus spans roughly a month of plugin versions (June sessions ran a 16-lens review wave and stages retired before 1.4.0; `154a6992` was injected with a 1.3.4 pointer). Per-stage numbers for retired stages describe the era they ran in; current-fleet numbers mix versions.
2. **Approved permission prompts are invisible.** Transcripts record denials (4 found) and PermissionRequest notifications exist as a hook, but a prompt the user approved leaves no distinct transcript event. Prompt-frequency friction is therefore evidenced by the user's memory files, not counted.
3. **Grep marker counts are upper bounds.** `scope-shift` (260), kickback phrasing (174), "Stop hook feedback" (117), and "Tests are failing" line counts include doctrine text quoting those strings, especially in the plugin repo which contains the hook source.
4. **Wall-clock conflates model latency, tool time, and queueing**; session spans include user idle (reported separately as active time). Per-stage medians are used to resist idle-skew outliers.
5. **No dollar figures.** Costs are reported in tokens split by fresh input / output / cache-create / cache-read; cache reads are roughly an order of magnitude cheaper than fresh input. Converting to currency would require pricing tables not audited here.
6. **SubagentStop hook durations** for implementer/fixer stops are not recorded in subagent transcripts, so their latency contribution (0-130 s per implementer stop by timeout bound) is unmeasured.
7. **Counterfactuals are out of reach.** For keepers, "caught X before implementation" is verifiable; whether a cheaper path would also have caught X is not. For the unearned, zero spawns proves non-use, not uselessness - `safety-gate` may simply never have met a destructive system step during the window.
