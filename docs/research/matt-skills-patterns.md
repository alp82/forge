# Matt Pocock skill patterns

Date: 2026-07-15. Question: what patterns make Matt Pocock's skills work - naming, composability, prose style, structure - and which are transferable to alp-river?

Primary sources: the 21 installed skills under `~/.claude/skills/` (symlinks into `~/.agents/skills/`; paths below use `skills/<name>/...` as shorthand for `/home/alp/.agents/skills/<name>/...`), plus the upstream repo [mattpocock/skills](https://github.com/mattpocock/skills) ("Skills for Real Engineers. Straight from my .claude directory", v1.1.0 as of 2026-07). The installed set excludes `computer-use`, `orca-cli`, `orchestration` (Orca skills, different author, different symlink dates) and `find-skills` (skills.sh ecosystem installer, not in Matt's README skill list). Every claim cites a file path (line refs where useful) or a URL. House style: hyphens only; em-dashes inside quoted passages are rendered as hyphens.

## Executive summary

Matt's system is 21 prompt files (~15.9 K words of SKILL.md total, median ~865 words) plus ~25 sibling reference files and exactly one shell script. No hooks, no agent definitions, no router code, no run-state. The load-bearing patterns: a two-tier naming scheme (one-word primitives, verb-phrase commands), composability via literal `/skill-name` mentions in prose, an explicitly theorized leitwort discipline (he calls them "leading words" and uses the word "Leitwort" himself), repo-native state (issue tracker, `CONTEXT.md`, plain files) instead of run-state, and a per-repo config layer written once by a setup skill. What substitutes for machinery: the human is the router, completion criteria are the gates, the tracker is the state machine, and the harness's generic subagents are the fleet. alp-river has already absorbed one full pattern (the `docs/agents/*.md` config layer - this repo's `CLAUDE.md` "Agent skills" section is `setup-matt-pocock-skills` output).

## 1. Naming conventions

### The actual names

Model-invoked (8, description always in context): `grilling`, `domain-modeling`, `codebase-design`, `prototype`, `research`, `tdd`, `code-review`, `diagnosing-bugs`.

User-invoked (13, `disable-model-invocation: true`, zero context cost): `wayfinder`, `grill-me`, `grill-with-docs`, `handoff`, `implement`, `triage`, `to-spec`, `to-tickets`, `improve-codebase-architecture`, `setup-matt-pocock-skills`, `teach`, `ask-matt`, `writing-great-skills`.

(Membership and invocation split verified by frontmatter grep across all 25 installed SKILL.md files: only 4 frontmatter fields ever appear - `name` 25x, `description` 25x, `disable-model-invocation` 13x, `argument-hint` 2x. All 13 `disable-model-invocation` occurrences are Matt's skills. Upstream README confirms the same user/model split.)

### What makes them sticky

- **The name is the activity or the artifact, not the role.** `grilling` names what happens to you; `wayfinder`, `handoff`, `prototype`, `triage` name a thing you already have priors for. Contrast alp-river's role-compound agent names (`correctness-reviewer`, `prototype-identifier`, `acceptance-reviewer`) which describe a position in a pipeline, not an experience.
- **Names double as leading words.** `writing-great-skills/SKILL.md:65`: "when the same word lives in your prompts, docs, and code, the agent links that shared language to the skill and fires it more reliably." The name is chosen to be the trigger vocabulary, not just a label.
- **Transformations read as prepositions**: `to-spec`, `to-tickets` - "turn the current conversation into X" (`to-spec/SKILL.md:3`). Three tokens, direction encoded.
- **Wrappers read as imperatives addressed to the agent**: `grill-me`, `ask-matt`, `implement`, `teach`.

### Exceptions - the framing "memorable one-word names" is only half true

12 of 21 names are multi-word. The real pattern is two-tier: **one-word names for reusable primitives** (the model-invoked layer other skills call: `grilling`, `prototype`, `research`, `tdd`) and **verb-phrase names for user-facing flows** (`grill-with-docs`, `improve-codebase-architecture`, `setup-matt-pocock-skills`). The longest names sit exactly where the human types them rarely and the model never fires them, so length costs nothing per the context-load model in `writing-great-skills/SKILL.md:15-18`.

## 2. Composability

### How skills invoke each other - the actual phrasing

Invocation is a bare `/name` mention in prose, nothing more. The extreme case is a whole skill that is one composition line:

- `grill-with-docs/SKILL.md` (7 lines, 34 words total): body is exactly "Run a `/grilling` session, using the `/domain-modeling` skill."
- `grill-me/SKILL.md` (7 lines, 20 words): body is "Run a `/grilling` session."

Other quoted invocations:

- `implement/SKILL.md:9,13`: "Use /tdd where possible, at pre-agreed seams." ... "Once done, use /code-review to review the work."
- `wayfinder/SKILL.md:111`: "Run a `/grilling` and `/domain-modeling` session to pin down what this map is finding its way to"; `:123`: "invoke the skills the `## Notes` block names. If in doubt, use `/grilling` and `/domain-modeling`."
- `triage/SKILL.md:76`: "run the `/grilling` and `/domain-modeling` skills together - grill it into shape one question at a time."
- `improve-codebase-architecture/SKILL.md:13`: "Run the `/codebase-design` skill for the architecture vocabulary (**module**, **interface**, **depth**, **seam**...). Use these terms exactly in every suggestion."
- `to-tickets/SKILL.md:107`: "Work the frontier one ticket at a time with `/implement`, clearing context between tickets."

### How a skill declares when another should take over

Handover is declared as an explicit condition plus the successor's name:

- `diagnosing-bugs/SKILL.md:134`: "If the answer involves architectural change (no good test seam, tangled callers, hidden coupling) hand off to the `/improve-codebase-architecture` skill with the specifics. Make the recommendation **after** the fix is in, not before."
- `tdd/SKILL.md:36`: "Refactoring is not part of the loop. It belongs to the review stage (see the `code-review` skill), not the red -> green implementation cycle."
- `ask-matt/SKILL.md:44`: wayfinder "merges onto the main flow at **`/to-spec`** (or, if the effort turned out small enough, straight to **`/implement`**)."
- Missing-precondition kickback: `code-review/SKILL.md:13`, `to-spec/SKILL.md:9`, `wayfinder/SKILL.md:25` all carry the same sentence shape: "The issue tracker should have been provided to you - run `/setup-matt-pocock-skills` if not."

### The routing layers

- **Mechanical constraint** (`writing-great-skills/GLOSSARY.md:27-28`): only model-invoked skills can be reached by other skills; a user-invoked skill "has no description, nothing but the human can reach it." So the composable layer is exactly the 8 one-word primitives, by construction.
- **The router is a document, not code.** `ask-matt/SKILL.md` (76 lines, 1,213 words) opens "You don't remember every skill, so ask" and defines the whole flow graph in prose: a "main flow: idea -> ship" (`grill-with-docs` -> prototype detour via `handoff` -> `to-spec` -> `to-tickets` -> `implement`, which "builds each issue by driving `/tdd` internally... then closes out by running `/code-review`", `:26`), three "on-ramps" (`triage`, `diagnosing-bugs`, `wayfinder`), and a "vocabulary underneath" layer (`domain-modeling`, `codebase-design`) described as "model-invoked references that run *beneath* the other skills - each the single source of truth for its vocabulary" (`:54`).
- **Context boundaries are part of the composition.** `ask-matt/SKILL.md:30-32` prescribes where windows break: "Keep steps 1-3 in **one unbroken context window**... Each `/implement` then starts fresh, working from the ticket," bounded by the "smart zone (~120k tokens)."

## 3. Prose style

### Brevity, measured

Lines/words per SKILL.md (`wc`, 2026-07-15): grill-me 7/20, grill-with-docs 7/34, research 12/133, grilling 12/135, implement 15/70, handoff 16/134, prototype 26/468, tdd 36/506, improve-codebase-architecture 66/801, domain-modeling 74/515, to-spec 75/501, ask-matt 76/1213, writing-great-skills 83/1526, code-review 89/1104, to-tickets 107/923, triage 112/1003, codebase-design 114/865, setup-matt-pocock-skills 116/1039, wayfinder 127/1962, diagnosing-bugs 134/1411, teach 140/1490.

Sum: ~15.9 K words across 21 entry files; median 865; the largest (wayfinder, 1,962 words) is still a 2-3 minute read. Every skill fits one read. For contrast: alp-river's `WORKFLOW.md` alone is 3,262 lines / 35,304 words - one doctrine document outweighs Matt's entire entry-file corpus 2.2x.

Brevity is enforced by a named discipline, not taste: `writing-great-skills/SKILL.md:59` "hunt **no-ops** sentence by sentence... when one fails, delete the whole sentence rather than trim words from it", with named failure modes **sediment**, **sprawl**, **duplication**, **no-op**, **negation** (`:74-83`).

### Leitworts - explicitly theorized, same word

`writing-great-skills/GLOSSARY.md:131`: "A compact concept - also called a _Leitwort_ - already living in the model's pretraining, that the agent thinks with while running the skill... Repeated as a token, never as a sentence, it accumulates a distributed definition." And `:131`: "a made-up word recruits no priors - you pay in definition tokens what a pretrained word gives free. Reach for an existing word first." This is the same doctrine as alp-river's `CLAUDE.md` "Leitwort usage" section, independently converged (or cross-pollinated).

Leitworts in the wild: **fog of war / frontier / destination** (wayfinder), **tight / red / red-capable** (diagnosing-bugs), **seam / deep module / deletion test** (codebase-design, tdd, to-spec), **tracer bullet / vertical slice / expand-contract / blast radius** (to-tickets, tdd), **throwaway** (prototype), **relentless** (grilling), **smart zone / zone of proximal development** (ask-matt, teach).

### Stance-teaching - exemplary passages

1. `grilling/SKILL.md:6,10` (the whole skill is 12 lines, written in the user's voice): "Interview me relentlessly about every aspect of this plan until we reach a shared understanding." ... "If a *fact* can be found by exploring the codebase, look it up rather than asking me. The *decisions*, though, are mine - put each one to me and wait for my answer."
2. `diagnosing-bugs/SKILL.md:14,31`: "**This is the skill.** Everything else is mechanical. If you have a **tight** pass/fail signal for the bug - one that goes red on _this_ bug - you will find the cause... If you don't have one, no amount of staring at code will save you." ... "Build the right feedback loop, and the bug is 90% fixed."
3. `prototype/SKILL.md:8`: "A prototype is **throwaway code that answers a question**. The question decides the shape."
4. `wayfinder/SKILL.md:13,88`: "produce decisions, not deliverables" ... "**Fog or ticket?** The test is whether you can state the question precisely now - _not_ whether you can answer it now."
5. `writing-great-skills/SKILL.md:7`: "A skill exists to wrangle determinism out of a stochastic system. **Predictability** - the agent taking the same _process_ every run, not producing the same output - is the root virtue; every lever below serves it."

The common shape: open with the stance in one bold sentence, hang the checklist off it, end steps on checkable completion criteria ("Done when **every remaining element is load-bearing**", `diagnosing-bugs/SKILL.md:78`). Negative instructions are rare and, when present, paired with the positive move - per his own negation rule (`writing-great-skills/SKILL.md:83`).

## 4. Structural conventions

### File layout

`<skill>/SKILL.md` plus optional flat sibling reference files, mostly SHOUTING-KEBAB named for what they hold: `GLOSSARY.md`, `CONTEXT-FORMAT.md`, `ADR-FORMAT.md`, `AGENT-BRIEF.md`, `OUT-OF-SCOPE.md`, `LOGIC.md`/`UI.md`, `DEEPENING.md`/`DESIGN-IT-TWICE.md`, `HTML-REPORT.md` (tdd's lowercase `tests.md`/`mocking.md` are the exception). No nesting beyond one level; one `scripts/` dir in the whole corpus (`diagnosing-bugs/scripts/hitl-loop.template.sh`). Sibling files are reached by "context pointers" whose wording encodes the load condition - e.g. `prototype/SKILL.md:14-15` branches to `LOGIC.md` or `UI.md` by which question is being answered ("Branching is the cleanest disclosure test: inline what every branch needs, and push behind a pointer what only some branches reach", `writing-great-skills/SKILL.md:42`).

### Frontmatter

Four fields total across all skills: `name`, `description`, `disable-model-invocation`, `argument-hint`. No model pins, no tool grants, no signal/route declarations. Contrast one alp-river agent: `agents/triage.md:1-39` carries `model`, `tools`, and a `stage:` block with 4 routes, 2 data slots, and 22 published signals before the prompt begins.

### State and artifacts - everything lives in repo-native stores

- **wayfinder** -> the issue tracker is the store: the map is "a single issue... labelled `wayfinder:map` - the canonical artifact" (`wayfinder/SKILL.md:21`), tickets are child issues, claiming is "assigning it to the dev" (`:67`), and dependencies use "the tracker's **native** dependency relationship - essential because it renders the frontier _visually_ in the tracker's own UI" (`:69`). Cross-session persistence and multi-session concurrency come free from the tracker.
- **domain-modeling** -> `CONTEXT.md` + `docs/adr/`, created lazily ("only when you have something to write", `domain-modeling/SKILL.md:40`), updated inline mid-conversation ("Don't batch these up", `:62`).
- **triage** -> tracker labels are the state machine (five state roles, `triage/SKILL.md:31-45`); rejected requests persist in `.out-of-scope/*.md`, one file per concept (`triage/OUT-OF-SCOPE.md:17`).
- **to-tickets** -> issues with native blocking edges, or `.scratch/<feature>/issues/NN-<slug>.md` locally; **to-spec** -> an issue with the `ready-for-agent` label.
- **handoff** -> a markdown file in the OS temp dir, deliberately outside the workspace (`handoff/SKILL.md:8`); **research** -> "a single Markdown file, citing each claim's source... where the repo already keeps such notes" (`research/SKILL.md:11-12`); **prototype** -> "commit it to a throwaway branch, out of main, and leave a context pointer to that branch on the implementation issue" (`prototype/SKILL.md:26`); **teach** -> the current directory as a stateful workspace (`MISSION.md`, `learning-records/`, `lessons/`).
- **Per-repo config** -> `setup-matt-pocock-skills` writes `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md`, `docs/agents/domain.md` and an `## Agent skills` block in `CLAUDE.md`/`AGENTS.md` (`setup-matt-pocock-skills/SKILL.md:84-111`). Other skills read those files instead of carrying tracker specifics.

There is no run-state object, no session JSON, no signals: state is either in the conversation or in a file/issue a human can read.

## 5. Machinery deliberately avoided

Verified by inspection: the 21 skill dirs contain 47 files - 46 markdown, 1 bash template. No `hooks/`, no `agents/`, no `hooks.json`, no settings, no scripts beyond the HITL template (and that script exists only so a human-driven repro loop stays structured, `diagnosing-bugs/SKILL.md:29`). The upstream repo has a `.claude-plugin/` dir, but purely as a distribution channel ("Claude Code plugin: manages the skills as read-only bundles that auto-update", [github.com/mattpocock/skills](https://github.com/mattpocock/skills)); the payload is still only skills. The README states the stance: frameworks "like GSD, BMAD, and Spec-Kit attempt to help by controlling the process, they sacrifice flexibility and complicate debugging"; his skills are "small, easy to adapt, and composable" ([README](https://github.com/mattpocock/skills/blob/main/README.md)).

How each piece of machinery is substituted:

| Machinery | alp-river has | Matt substitutes |
|---|---|---|
| Router (hook/code) | `hooks/route.py`, 240 lines, signal-driven | The human, indexed by `ask-matt` - a prose flow map; plus model-invocation descriptions for the 8 primitives |
| Agent definitions | 42 `agents/*.md` with tools/model/stage frontmatter | The harness's generic subagents, prompted inline: `code-review/SKILL.md:60` "Use the `general-purpose` subagent for both" (with the full brief and a "Under 400 words" cap written in the skill); `improve-codebase-architecture/SKILL.md:22` "use the Agent tool with `subagent_type=Explore`"; `research/SKILL.md:6` "Spin up a **background agent**" |
| Stop/verify gates | `verify-tests.py`, `verify-build.py` stop hooks | Checkable completion criteria + explicit halt lines: "No red-capable command, no Phase 2" (`diagnosing-bugs/SKILL.md:60`); "Do not enact the plan until I confirm" (`grilling/SKILL.md:12`) |
| Signals/run-state | 76 signals, 40 slots, 119 output fields (audit § 2.1) | Tracker labels, blocking edges, assignees, and file presence - all human-visible |
| Context injection (SessionStart hook) | `inject-workflow.sh` | The `## Agent skills` block in CLAUDE.md pointing at `docs/agents/*.md`, written once by setup |
| Context management | Compaction doctrine | `/handoff` + prescribed window boundaries ("clearing context between tickets", smart zone) |

The honest caveat: machinery is avoided at the *definition* layer, not the *execution* layer. Skills freely spawn parallel subagents and background agents - they just never ship agent definitions, so there is nothing to version, permission, or keep in sync. And nothing enforces anything: a skipped `/code-review` is silently skipped. Matt accepts human discipline as the enforcement mechanism; alp-river's audit shows its enforcing hooks are precisely among the few components with measured payoff (`docs/research/pipeline-audit.md` § "Verdict list": verify-tests "blocked stops on failing suites dozens of times at a median 2.3 s").

## 6. Transferable vs not

Judged against alp-river as it stands (42 agents, 4 commands, 15 hooks, 35 K-word WORKFLOW.md) and the audit's cost findings.

- **Two-tier naming (one-word primitives, verb-phrase flows)** - transfers directly and cheaply. alp-river's role-compounds (`prototype-identifier`, `acceptance-reviewer`) name pipeline positions; renaming survivors of a keep/cut to activity words (`triage`, `challenge`, `fix`, `verify`) makes them typeable and leitwort-grade. Cost: churn in doctrine cross-references.
- **Composability by prose `/name` mention** - transfers for a skill-first surface, but it replaces the deterministic router with model/human judgment. The audit says route decisions currently cost zero tokens (`route.py`); prose routing spends model attention instead and drops guarantees (parallel-wave composition, lock ordering). Judgment: adopt for the outer surface (user picks the flow, a router document replaces the go-command's orchestration prose), keep deterministic code only where the audit showed it earning (test gates). The `ask-matt` pattern - one user-invoked flow map - is a direct, zero-risk steal.
- **Leitwort prose style** - already alp-river doctrine (`CLAUDE.md` "Leitwort usage"); convergent, no adoption needed. What is worth importing: the **no-op sentence test** ("delete the whole sentence rather than trim words", `writing-great-skills/SKILL.md:59`) and the named failure modes (sediment, sprawl, negation) as lenses for the existing self-audit - they operationalize the doctrine-diet the audit already motivates.
- **One-read brevity with measured budgets** - transfers and is the highest-leverage import. Matt's whole entry corpus is under half of WORKFLOW.md alone. Adopting it means each surviving stage's contract must fit its own SKILL.md-sized file with sibling reference disclosed behind pointers - which is a restructuring of WORKFLOW.md + `doctrine/`, not an edit.
- **Minimal frontmatter / no signal vocabulary** - transfers only if the deterministic router goes. The ~280-token named vocabulary is the audit's top friction; Matt shows a working system where the entire coordination vocabulary is five tracker labels and a `wayfinder:map` label. Judgment: the signal system and the skill model cannot coexist at full size; a skill-first cut collapses signals into prose conditions and tracker labels.
- **Repo-native state (tracker as store, CONTEXT.md, .out-of-scope/)** - transfers; partially already adopted. This repo's `docs/agents/issue-tracker.md`, `triage-labels.md`, `domain.md` are literally `setup-matt-pocock-skills` output referenced from `CLAUDE.md`. Extending it (wayfinder-style maps for multi-session efforts, resolution comments instead of run-state) costs nothing and buys human-visible, concurrency-safe persistence.
- **User-invoked vs model-invoked split (context load vs cognitive load)** - transfers directly. alp-river's 42 agent descriptions all ride in the orchestrator's context every turn; Matt pays that for only 8 primitives and makes 13 flows free. Any skill-first alp-river should default new surfaces to `disable-model-invocation: true` and promote to model-invoked only on demonstrated need.
- **No enforcement hooks** - does not transfer wholesale. The audit's evidence-backed keepers include exactly the enforcing machinery Matt lacks (verify-tests stop gate, block-git-writes). Judgment: keep the 2-3 measured-payoff hooks; drop hooks whose job prose can do (context injection is already just a pointer; catalog generation only exists because the agent fleet exists).
- **HITL/AFK ticket typing** (`wayfinder/SKILL.md:75`: "A HITL ticket only resolves through that live exchange; the agent never stands in for the human's side") - transfers as a sharper vocabulary for alp-river's gate concept (safety-gate/ship-gate are HITL points); worth naming in whatever survives.

## Appendix: sources

- Installed skills: `/home/alp/.agents/skills/<name>/` (symlinked from `/home/alp/.claude/skills/`), read in full 2026-07-15; word/line counts via `wc`.
- Upstream: [github.com/mattpocock/skills](https://github.com/mattpocock/skills) and its [README](https://github.com/mattpocock/skills/blob/main/README.md) (fetched 2026-07-15). Upstream layout (`skills/engineering/`, `skills/productivity/`, `.claude-plugin/`), install channels (skills.sh copy-in vs read-only plugin), semver + CHANGELOG noted from the repo. One upstream-only skill not installed locally: `resolving-merge-conflicts`.
- Contrast: `/home/alp/dev/projects/alp-river/WORKFLOW.md` (structure + size only), `agents/` and `commands/` listings, `agents/triage.md` in full, `docs/research/pipeline-audit.md` for measured costs.
