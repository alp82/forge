# Review lens analysis

Date: 2026-07-16. Resolves wayfinder ticket #15 ("Per-lens catch analysis: what did each review lens actually find?"). Companion to `docs/research/pipeline-audit.md`, whose corpus this was meant to reuse.

This document supplies evidence for the deferred lens-set decision from [#8](https://github.com/alp82/alp-river/issues/8). It does not make the decision. House style: hyphens only.

**Read the next section before reading any table.** The forensics this ticket specified could not be performed. Nothing below reports a catch rate, because no catch rate is recoverable.

## 0. Headline: the requested measurement is not possible

The ticket asked for per-lens unique-catch rate, overlap rate, and noise rate, extracted from session transcripts. **Those numbers do not exist and are not reported here.** Two independent reasons, both verified:

**(a) The corpus is not on this machine.** The pipeline audit measured `/home/alp/dev/projects/alp-river` and sibling project dirs under `/home/alp/.claude/projects/` (~298 MB, 42 sessions, 3,068 spawns, 2026-06-16 to 2026-07-15). `/home/alp` does not exist here. This machine is `/home/alper`, and its entire transcript store is 26 MB / 48 JSONL files, dated 2026-04-01 to 2026-04-05 plus 2026-07-16 (today). The audit's corpus lives on a different machine.

**(b) No review lens has ever run in the corpus that IS here.** All 38 subagent transcripts on this machine resolve to generic Claude Code agents (`Explore` 20, `general-purpose` 13, `Plan` 3, read from every `*.meta.json` `agentType` field). Zero alp-river pipeline spawns of any kind. A grep for each of the eleven lens names across the whole store returns zero files, with exactly one apparent hit: this research agent's own transcript, which contains the lens names because they appear in its task prompt. That hit is self-contamination, not evidence.

**(c) Even with the corpus, the data would be thin.** The current lens set post-dates almost all of the audit window. `conventions-reviewer` and `shape-reviewer` were created 2026-07-08 (`git log --diff-filter=A`); the audit's window closed 2026-07-15. The consolidated five had **at most 7 days** of runtime in the corpus that was measured. The audit's own limitation #1 ("Version drift") already says its per-stage numbers "mix versions". A per-lens catch study of the current set was never available from that window, on any machine.

So this document does what the available primary sources can actually support, and labels every column honestly. The value table in section 5 carries `no data` in the unique-catch and noise columns. No estimates are substituted, and no numbers are invented.

### What is recoverable, and the substitute method

Four primary sources survive in-repo, and one secondary source:

| source | class | what it supports |
|---|---|---|
| `agents/*.md` lens definitions | primary | overlap **by construction**: what each lens is instructed to look for |
| `doctrine/SIGNALS.md`, `WORKFLOW.md` worked routes, `generated/catalog.json` | primary | the trigger wiring: standing vs conditional, and which lenses co-fire |
| git history of `agents/` + `CHANGELOG.md` | primary | the project's **revealed preference**: every lens add, cut, and merge, with motive |
| `doctrine/reviewer-contract.md` | primary | the shared contract and its roster |
| `docs/research/pipeline-audit.md` | secondary | spawn counts measured on the now-unreachable corpus |

The substitute method rests on a fact worth stating plainly: **the project already ran this experiment.** In v1.3.9 it cut twelve lenses to five in a single commit, using an explicit, written criterion. Rather than invent catch rates, this analysis applies that same criterion, which the repo authored and validated, to the eleven lenses that remain. That is a weaker instrument than transcript forensics. It is not a guess.

## 1. The project's own kill criterion (v1.3.9)

Commit `a066d3b` (2026-07-08, released as 1.3.9) deleted seven lenses, renamed one, and created one, taking the catalog from 50 to 44 stages. Its merge map, quoted from the `TASKS.md` diff in that commit:

> "Apply the approved grouping: (1) correctness-reviewer absorbs `agents/assumptions.md` (including its silent-failure focus); (2) simplicity-reviewer stays untouched; (3) a shape-reviewer merges architecture-reviewer and structure-reviewer; (4) a conventions-reviewer merges consistency-reviewer, naming-clarity, reuse-reviewer; (5) acceptance-reviewer absorbs plan-adherence-reviewer."

The criterion for outright deletion, quoted from the same diff, is the load-bearing sentence of this whole analysis:

> "Delete quality-reviewer outright: bloat findings route to simplicity-reviewer, hacky-shortcut/wrong-tool findings route to shape-reviewer. **Quality has no domain of its own and fails the leitwort test.**"

And the stated motive:

> "30-45% of the six named lens files is jurisdiction text ('not mine, X owns it') ... with five lenses the lane-policing prose loses its reason to exist."

So the repo's own test is two-pronged: **a lens must own a jurisdiction, not merely name a concern, and it must state its stance in one earned leitwort.** This is the CLAUDE.md § "Leitwort usage" rule applied as an execution test. The seven lenses that died (quality, naming-clarity, assumptions, reuse, consistency, plan-adherence, structure) died from being concerns absorbable into a lens that already owned the ground.

Two decisions from that commit matter directly here:

- **A `design-reviewer` merge of shape + simplicity was planned and then reprieved.** The task list read `Consolidate the review wave 12 -> 4 lenses` and was retargeted mid-flight to `12 -> 5`. Simplicity survived a targeted merge attempt against exactly the partner this analysis re-examines in section 4.
- **The three UI lenses were proposed for merger and the merge was not executed.** Quoted from the same task diff: "the three UI lenses (ux, accessibility, design-consistency) **optionally** merge into one ui-reviewer". They remain three files today. This is an open, already-approved-in-principle consolidation.

For the record, the founding irony: v0.1.0 (`986803a`, 2026-04-26) shipped eleven lenses, while its own CHANGELOG entry named the disease as assistants that "pile every reviewer onto every task and add friction where none is needed."

## 2. Trigger wiring: what actually co-fires

From `doctrine/SIGNALS.md` and the `WORKFLOW.md` "Worked routes" trace. "Standing" means gated on a signal any serious code build publishes; every lens is signal-gated, so the distinction is about which gate, not whether one exists.

| lens | subscribes | model | class |
|---|---|---|---|
| correctness | `#code-written` | opus | standing, every code build incl. the `sketch` route and the trivial `#direct-impl` path |
| simplicity | `#plan-ready` | sonnet | standing on every **planned** build; absent on the trivial path |
| shape | `#significant-build` | opus | standing on significant builds; `milestone-scope: local` |
| conventions | `#significant-build` | sonnet | standing on significant builds |
| acceptance | `#significant-build` | sonnet | standing on significant builds |
| security | `#auth-surface`, `#secrets`, `#perms-change` | opus | conditional, `guard: sticky`, routes `[code, sketch, system]`, `milestone-scope: local` |
| performance | `#perf-surface` | sonnet | conditional (demoted in 1.3.9) |
| accessibility | `#ui-touched` | sonnet | conditional |
| ux | `#ui-touched` | sonnet | conditional |
| design-consistency | `#ui-touched` | sonnet | conditional |
| test-gap | `#needs-tests` | sonnet | conditional (but its prose claims "always-on"; see 4.2) |

Two structural facts fall straight out of this table.

**One signal fans out to three lenses.** `SIGNALS.md:41` lists `ui-touched` with subscribers "accessibility, design-consistency, ux". The three UI lenses cannot fire independently: they share one trigger exactly, always co-fire, and never fire otherwise.

**The project has already ranked its own lenses.** `milestone-scope: local` is set on exactly three lenses: correctness, security, shape (`test-verifier` carries `both`). `WORKFLOW.md` EARLY-pass spec: "Only the milestone-scoped lenses run over that milestone's diff slice: `correctness-reviewer` + `security-reviewer` (surface-gated) + `shape-reviewer` + `test-verifier` (smoke)." When the workflow had to pick a reduced set to run per-milestone, it picked these. That is a revealed priority ordering, independent of any catch count.

## 3. Definitional overlap matrix

Overlap **by construction**: two lenses overlap when their briefs instruct the same finding. This is measurable from primary sources with the corpus absent, and every row below is backed by quoted text on both sides. Severity is graded by whether the duplicated instruction is fenced by explicit boundary language.

| pair | overlap | fenced? | severity |
|---|---|---|---|
| **shape × simplicity** | `shape:51-52` "Premature seam - interface with one adapter and no plausible second" / "Single-call abstraction - module with exactly one caller" vs `simplicity:32` "`yagni:` - an abstraction with one implementation, config nobody sets, or a layer with one caller". Substantially the same sentence. Plus `shape:87/:90` "Hand-rolling a primitive the framework provides" / "Wrong altitude - reinventing a stdlib primitive" vs `simplicity:30-31` "`stdlib:` - reinvented stdlib" / "`native:` ... doing what the platform already does" | **contradictory** | **critical** |
| **correctness × security** | `correctness:22` "Injection/XSS/auth bypasses" vs `security:25-26` "Auth bypasses - missing or incorrect authn/authz checks" / "Injection - SQL, XSS, command, template". Near-verbatim | none, either side | high, but see 4.5 |
| **correctness × conventions** | `correctness:3` "project convention adherence", `:28` "**Conventions**: Read the project's CLAUDE.md and verify compliance", `:49` tier 6 "Style or convention drift" vs the whole of `conventions:23-29` | partial: `correctness:49` "only if a cluster, never individually". No reciprocal | high |
| **accessibility × ux × design-consistency** | `a11y:28` "Form labels - inputs without labels, errors not linked to fields" vs `ux:25` "Form validation - inline, timely, clear error messages"; `a11y:24` "Color contrast" vs `dc:24` "Colors - palette/variables"; `ux:34` "consistency with the rest of the product beats theoretical best practice" instructs dc's entire mandate | **none between any pair** | **high** |
| **conventions × design-consistency** | method line duplicated near-verbatim: `conventions:19` "Always compare new code against 2-3 existing examples of the same kind before flagging" vs `dc:19` "Always compare against 2-3 existing UI components of similar kind before flagging". Anti-pattern lists mirror each other | none | high |
| **acceptance × test-gap** | `acceptance:47` "**VALIDATION: test** - confirm an automated test exists for this criterion ... If no test exists, mark `unmet`" vs `test-gap:17` "Compare the diff and its acceptance criteria against the tests that exist" | internally contradicted: `acceptance:23` "Do not re-review ... tests - that's other agents' job" vs `acceptance:47` | high |
| **correctness × shape** | `correctness:24` "signatures missing dependencies the body reaches for through module-level imports" vs `shape:62` "Module-level mutables read or written by exported functions without appearing in their signatures"; `correctness:32` contract premises vs `shape:58` "Unclear contract"; `correctness:37` purity vs `shape:78` "Side effects woven into computation" | only `shape:20`'s framing line; correctness cedes nothing | medium |
| **correctness × simplicity** | `correctness:26` "Code made obsolete by this change - functions no longer called" + `OBSOLETE_CODE:` output field vs `simplicity:30` "`delete:` - dead or speculative code" (its tier-1 finding) | none on dead code | medium |
| **shape × conventions** | `shape:54` "Missing seam where coupling is high" / `:67` locality vs `conventions:40-42` "Similar implementations that should be unified into a shared utility" / "Near-duplicate patterns suggesting a missing abstraction" | reciprocal and explicit (`shape:100`, `conventions:52`) - the best-fenced pair, still leaking | low |
| **performance × correctness / security / shape** | `performance:28` "Sync I/O on a hot path" vs `correctness:22` "resource leaks ... missing timeouts"; `performance:30` "Over-wide payload" vs `security:27` "Sensitive data exposure" | none; performance names no other lens anywhere | low |

### 3.1 The overlap-policing produced a coverage hole

The single most consequential finding available without transcripts. `shape:101` cedes tooling cuts to simplicity:

> "Line-count and stdlib/native/YAGNI-ladder cuts (the 5 deletion tags) are simplicity-reviewer's lane"

while `simplicity:61` cedes the same finding back to shape:

> "Flagging things other reviewers own: ... module shape / decomposition / **wrong tool** (shape-reviewer)"

And `shape:87` describes exactly that finding as its own criterion: "custom retry when the lib has built-in retry". So a hand-rolled-retry defect is **instructed away by both lenses**. Each file tells its reader the other owns it. This is not redundancy; it is a hole, and it was manufactured by the lane-policing prose that 1.3.9 predicted would "lose its reason to exist" at five lenses. It did not: `simplicity:61`, `shape:100-101`, `conventions:52`, `correctness:26/:54`, and `acceptance:23` are all still jurisdiction text in the consolidated set.

**The 1.3.9 consolidation achieved its lens count but not its stated goal.** That is a measured outcome, from the artifacts, and it is the strongest available argument that lens count is the wrong lever: the overlap did not come from having twelve lenses, and it did not leave at five.

### 3.2 Two smaller definitional defects

- **A carve-out aimed at the wrong agent.** `correctness:54` says "Reviewing test coverage - that's test-verifier's job." Coverage is `test-gap`'s job (`test-gap:3` "Always-on coverage lens"); `test-verifier` runs the suite. The fence points at the wrong lens.
- **test-gap is structurally orphaned.** `reviewer-contract.md:3` rosters "correctness, simplicity, shape, conventions, acceptance, security, performance, accessibility, design-consistency, ux" and omits test-gap. It is the only lens whose brief does not open with "Follows the Reviewer Contract". Yet it satisfies the contract's own discriminator (`reviewer-contract.md:42`): its `output` is `@findings` and it publishes `#clean` / `#findings:test-gap`. It is a reviewer by the contract's definition and absent from the contract's list.

## 4. Per-lens value table

Honest columns. `no data` means the measurement is unrecoverable per section 0, not that the value is zero.

| lens | unique-catch rate | noise rate | overlap partners (from definitions) | spawns in audit corpus | leitwort / jurisdiction |
|---|---|---|---|---|---|
| correctness | **no data** | **no data** | security (near-verbatim), conventions (high), shape (medium), simplicity (medium), performance (low) | 76 | "does it work" - widest mandate, only lens on every code build |
| simplicity | **no data** | **no data** | **shape (contradictory)**, correctness (dead code) | 44 | **YAGNI ladder** + 5 deletion tags + `net: -N lines` |
| acceptance | **no data** | **no data** | test-gap (high) | 29 | "whether the right thing was built" (`acceptance:19`) |
| test-gap | **no data** | **no data** | acceptance (high) | 26 | coverage - no leitwort; orphaned from the contract roster |
| shape | **no data** | **no data** | **simplicity (contradictory)**, correctness (medium), conventions (low) | 12 (7 days of runtime) | **deletion test** - "is this abstraction earning its keep" |
| conventions | **no data** | **no data** | correctness (high), design-consistency (high), shape (low) | not in audit table; created 7 days before window close | "does it match the neighbors" - compare against 2-3 examples |
| security | **no data** | **no data** | correctness (near-verbatim), performance (low) | not in audit table | named threat classes; only lens on all three paths |
| performance | **no data** | **no data** | correctness, security, shape (all low, all unfenced) | not in audit table | static cost readable from the diff |
| accessibility | **no data** | **no data** | **ux, design-consistency (unfenced, always co-fire)** | not in audit table | WCAG-class objective criteria |
| ux | **no data** | **no data** | **accessibility, design-consistency (unfenced, always co-fire)** | not in audit table | states: loading, error, empty |
| design-consistency | **no data** | **no data** | **ux, accessibility, conventions (all unfenced)** | not in audit table | tokens over magic numbers |

Spawn counts are from `pipeline-audit.md` § 1.1, measured on the unreachable corpus, and are **frequency, not value**. They cannot rank lenses: `correctness` fires on every code build by design and `shape` existed for one week of the window. The six lenses absent from the audit's table are absent for structural reasons, not because they were useless: the plugin repo contains 204 `.md`, 81 `.py`, 24 `.sh` files and **zero UI files** (no `.tsx`/`.jsx`/`.css`/`.vue`/`.svelte`/`.html` anywhere), so `#ui-touched` can never fire there and the three UI lenses were physically incapable of running in the audit's primary repo. Their only possible evidence was in consumer repos, on the missing machine.

## 5. Recommended lens set

Eleven definitions become **eight**: five standing, three conditional. The recommendation is deliberately conservative on the standing five and aggressive on the conditional tail, because that is where the evidence actually points.

| lens | verdict | rationale |
|---|---|---|
| **correctness** | **keep** (standing) | Ticket prior, audit keeper, widest gate (`#code-written`), milestone-scoped, opus. **Narrow it**: shed `:28` and tier-6 `:49` convention duty to conventions; retarget the mis-aimed `:54` carve-out at test-gap. Keep its baseline security sweep (see below). |
| **acceptance** | **keep** (standing), **absorbs test-gap** | Ticket prior, audit keeper ("plan item (g) half-executed" catch). Cleanest jurisdiction in the set (`:19` "Other reviewers check HOW the code is written. You check WHETHER the right thing was built"). It already does test-gap's job at `:47`. |
| **test-gap** | **merge** into acceptance | Matches the ticket prior. Independently supported: duplicated by `acceptance:47`, orphaned from the contract roster, no leitwort, and its prose ("Always-on") contradicts its own `#needs-tests` gate. Fix `acceptance:23` so coverage is explicitly acceptance's duty, not a denied one. |
| **shape** | **keep** (standing) | Owns a jurisdiction with a trained leitwort (**deletion test**); opus; one of three milestone-scoped lenses. **Conditional on the boundary fix below.** |
| **simplicity** | **keep** (standing on planned builds) | Owns a jurisdiction with a trained leitwort (**YAGNI ladder**), a unique output discipline (`net: -N lines possible`), and 5 named tags. It already survived a targeted merge into `design-reviewer` in 1.3.9. **Conditional on the boundary fix below.** |
| **conventions** | **keep** (standing) | Owns "does it match the neighbors" with a method no other lens has (`:19` compare against 2-3 existing examples). Do **not** merge it into correctness: correctness is already the widest mandate, and a merge would recreate exactly the shapeless catch-all that 1.3.9 killed quality-reviewer for being. Instead carve convention duty **out** of correctness. |
| **security** | **keep**, conditional | Already correctly gated, `guard: sticky`, opus, milestone-scoped, and the only lens spanning `[code, sketch, system]`. Lowest-risk keep in the set. |
| **performance** | **keep**, conditional | Already demoted in 1.3.9, with its mandate honestly narrowed to what its inputs support ("receives only touched files and cannot measure"). Distinct jurisdiction. Leave it alone. |
| **accessibility + ux + design-consistency** | **merge** into one conditional lens (`surface`) | The strongest merge case available. They share one trigger exactly (`SIGNALS.md:41`), always co-fire, never fire otherwise, and carry **zero** boundary language among them - the densest unfenced cluster in the fleet. The merge is already on record as approved-in-principle in the 1.3.9 task list and simply was not executed. `design-consistency` is `conventions`-for-pixels, duplicating its method line near-verbatim. |

### 5.1 The boundary fix shape and simplicity both need

Keeping both is only defensible if section 3.1's hole is closed. Assign the tooling/altitude group **one** owner. Recommendation: **simplicity takes `shape:85-90` (the "Approach" group)**, because simplicity's ladder (`:23` "stdlib -> native platform feature -> already-installed dependency") is literally the same test that group applies. Shape then keeps depth, seam, interface, hidden state, locality, decomposition, purity, and layer, and `shape:101` / `simplicity:61` are rewritten to point the same direction instead of at each other.

This is the highest-risk keep in the recommendation and the one a per-lens catch count would most cleanly settle. It is named as a judgment call, not an evidenced one.

### 5.2 Why the correctness x security duplication should survive

It reads as the worst overlap in section 3 (near-verbatim, unfenced on both sides) and it is the one overlap this analysis recommends **keeping**. `security` fires only on `#auth-surface` / `#secrets` / `#perms-change`, all published by `triage`. On a build where no risk signal fires, `correctness:22` is the *only* thing standing between the diff and an injection defect. Deleting it to remove the duplication would silently drop injection coverage from every unflagged build, which is precisely the failure `WORKFLOW.md` § "Asymmetric rigor" warns against: "A needless question costs mild annoyance; a wrong assumption costs the task." This overlap is a safety net, and it should be documented as deliberate rather than tidied away.

### 5.3 What is not recommended

**No lens is cut outright.** Section 0 is the reason: with no catch data, a cut is unfalsifiable, and the only lens ever cut outright (quality-reviewer) was cut on a definitional argument that no lens here reproduces. Every remaining lens either owns a jurisdiction with a leitwort, or merges into one that does.

## 6. What would settle the open questions

The three findings below are the ones this method cannot reach, in priority order:

1. **The shape/simplicity boundary** (5.1). Needs per-lens findings from real runs, tagged by which lens caught them.
2. **Whether the merged `surface` lens loses depth versus three specialists.** Merging saves no wall-clock (the wave is parallel; `pipeline-audit.md` § 1.3: 7 lenses in the time of the slowest) - it saves three brief files, against the toolkit's one-read brevity bar. The cost is focus, and a11y in particular carries objective compliance-grade criteria. Unmeasured either way.
3. **Whether `conventions` earns a standing spawn at all.** It has essentially no runtime anywhere (created 2026-07-08).

To make any of it answerable, the fleet must record what it cannot record today: each finding, its lens, whether the fixer acted on it, and whether it survived re-review. `doctrine/reviewer-contract.md` already mandates the raw material (confidence tags, `VERDICT`/`FINDINGS`, `SIGNALS_PUBLISHED` convergence lines), and 1.3.9 already narrows re-review to "only the checks that found the fixed problems re-run, plus the correctness check and the test suite" - which means the fixer already knows which lens owned each finding it closed. Persisting that mapping to a durable per-run artifact would make this exact study a query rather than an archaeology. **That is the recommendation this document is most confident about.**

## Appendix: methodology

### Sources

- Lens definitions: `agents/{correctness,acceptance,simplicity,shape,conventions,security,performance,accessibility,ux,design-consistency}-reviewer.md`, `agents/test-gap.md`, read in full.
- Contract and wiring: `doctrine/reviewer-contract.md`, `doctrine/SIGNALS.md`, `doctrine/code-doctrine.md`, `WORKFLOW.md` ("Worked routes", "Model Tiering", "Asymmetric rigor"), `generated/catalog.json`.
- History: `git log --diff-filter=A|D --follow -- agents/`, `git show a066d3b` (1.3.9 consolidation, incl. its `TASKS.md` diff), `CHANGELOG.md` in full.
- Secondary: `docs/research/pipeline-audit.md` § 1.1, § 4.1, and its limitation #1.

### Corpus verification (reproducible)

- `ls -d /home/alp` -> does not exist. The audit's corpus root is absent from this machine.
- `find /home/alper/.claude/projects -name '*.jsonl' | wc -l` -> 48; `du -sh` -> 26 MB; mtimes 2026-04-01..05 and 2026-07-16.
- Every `*.meta.json` `agentType` under `/home/alper/.claude/projects/*/*/subagents/` -> `Explore` (20), `general-purpose` (13), `Plan` (3). No alp-river stage, ever.
- `grep -rl '<lens>-reviewer' /home/alper/.claude/projects/` for all eleven lenses -> 0 files after excluding this agent's own transcript.
- UI surface check on the plugin repo -> zero `.tsx/.jsx/.css/.vue/.svelte/.html` files, so `#ui-touched` is unreachable there.
- Lens creation dates vs the audit window (closed 2026-07-15): conventions 2026-07-08, shape 2026-07-08, simplicity 2026-06-17, test-gap 2026-05-31, correctness 2026-05-02, acceptance 2026-04-26.

### Known limitations

1. **The headline limitation is section 0.** Unique-catch and noise rates are not reported because they are not recoverable. Every "no data" in section 4 is load-bearing and must not be read as zero.
2. **Definitional overlap is not behavioral overlap.** Two lenses instructed to look at the same thing may still report different findings, and a well-fenced pair may still collide in practice. Section 3 measures the briefs, not the behavior. This is the method's core weakness and the reason section 5 cuts nothing.
3. **Revealed preference is not proof.** The 1.3.9 consolidation is strong evidence of what the author concluded, not of what the transcripts showed. Its own goal (killing jurisdiction text) demonstrably was not met (3.1), so its judgment is credible but not authoritative.
4. **Spawn counts are frequency, era-confounded, and repo-confounded.** See section 4's note.
5. **The audit's own limitation #7 applies with full force**: counterfactuals are out of reach. "Lens X caught defect Y" was never recorded per-lens anywhere, so even a recovered corpus may not support a clean unique-catch attribution without the artifact recommended in section 6.
