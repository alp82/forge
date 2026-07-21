# Complexity- and risk-based routing: prior-art survey

Date: 2026-07-21.

Question: how do other systems route work by complexity and/or risk, and does prior art favor routing on ONE complexity scalar or TWO axes (size x risk)? forge's router currently sizes every request as a binary `trivial | standard` and then fires a fixed pipeline (plan, challenge, tests, a 5-lens review wave, fix); the middle ground gets the full pipeline when it should not. This survey feeds the pipeline-router redesign.

This feeds forge issue #68 (parent #67) and the router redesign.

Primary sources only: arXiv abstracts/papers, official vendor docs (OpenAI, Anthropic), standards glossaries (ISTQB), first-party engineering sources (Google Testing Blog, Google eng-practices, the Google SRE book, Google Research), and vendor product docs. Secondary write-ups (ITIL summaries, Medium explainers) are used ONLY as discovery indexes and are labeled `[secondary]`. Load-bearing claims were fetched from the source that owns them; fetch dates are noted where a page can drift. House style: hyphens only.

## Executive summary

Prior art splits cleanly along a domain line, and the split is the answer.

- **Where the system routes a fixed query to a model/effort level, routing is single-scalar.** RouteLLM, FrugalGPT, OpenAI `reasoning_effort`, Anthropic adaptive thinking, and Mixture-of-Depths all collapse the decision to ONE number (a difficulty/win-probability estimate, or a human-set effort dial). None of them carry a second orthogonal axis.
- **Where the system routes *engineering work* by how much process it deserves, routing is two-axis.** ISTQB/ISO risk-based testing is explicitly `risk level = likelihood x impact`. Google's review doctrine scales scrutiny with change SIZE while CODEOWNERS scales *who must approve* by PATH (ownership/sensitivity) - two independent axes. ITIL change management tiers on impact x urgency. These are the closest analogs to forge's actual job.
- **Verdict signal: lean TWO axes (size x risk).** The prior art that most resembles forge's problem - deciding how much plan/test/review a *code change* deserves - is consistently two-dimensional, because size and risk genuinely dissociate (a one-line change to auth is small-and-dangerous; a 400-line docs refactor is large-and-safe). Single-scalar wins only in the LLM-routing cluster, and that cluster is a *weaker* analogy: it routes model choice for an already-fixed prompt, where difficulty and stakes are correlated enough to collapse into one number. forge is routing process depth for a change, where they do not.
- **Second design axis worth stealing: mid-flight escalation.** Cascades (FrugalGPT), confidence-gated early-exit sampling, SRE error-budget throttling, and deployment rings all RE-ROUTE after starting - cheap first, escalate on a signal. Pure classifiers (RouteLLM, `reasoning_effort`, ITIL pre-classification) decide once. forge today is a one-shot classifier; a cascade shape (start lean, escalate the moment a risk signal fires) is an available and well-precedented alternative to sharper up-front classification.

---

## 1. Adaptive-compute LLM routing

The cluster where single-scalar routing dominates. Note the analogy is imperfect: these systems pick a *model or compute depth* for a query whose content is already fixed, whereas forge picks *how much workflow* a change deserves.

### 1.1 RouteLLM (LMSYS)

Learned binary router that dispatches each query to a strong or a weak model ([arXiv:2406.18665](https://arxiv.org/abs/2406.18665); [LMSYS blog, 2024-07-01](https://www.lmsys.org/blog/2024-07-01-routellm/); [lm-sys/RouteLLM repo](https://github.com/lm-sys/routellm)).

- **Axis/axes:** SINGLE scalar. A win-prediction model outputs one number - the probability the strong model's answer would be preferred - and routing is a threshold on that scalar. No second axis.
- **Thresholds:** Learned from human preference data, then the operating cutoff is *calibrated to a cost target* the user picks (e.g. "I want ~50% of calls to hit GPT-4"); the paper sweeps the threshold to trace a cost-quality curve. So: learned scoring function, human-configured operating point.
- **Uncertainty:** Encoded in the win-probability itself; queries near the threshold are the uncertain ones and the cost target decides which way they fall. No explicit hedging or default-to-strong beyond where the operator sets the knob.
- **Escalation:** One-shot classify. The route is chosen before generation; there is no retry-if-bad cascade in the core method.

### 1.2 FrugalGPT (Stanford)

The canonical LLM *cascade* ([arXiv:2305.05176](https://arxiv.org/abs/2305.05176)). Three strategies (prompt adaptation, LLM approximation, LLM cascade); the cascade is the routing-relevant one, reporting up to ~98% cost reduction versus always-GPT-4.

- **Axis/axes:** SINGLE scalar per hop - a generation *reliability score* on the current model's answer.
- **Thresholds:** A learned scoring function plus per-model thresholds fit under a user budget constraint (an optimization over cost-accuracy tradeoff).
- **Uncertainty:** Explicit. The reliability score IS the uncertainty estimate; a low score is what triggers the next hop.
- **Escalation:** YES - this is the defining feature. Queries run through a chain of models ordered cheap-to-expensive; each answer is scored, and only answers that fail the reliability threshold are escalated to the next, more expensive model. Mid-flight re-routing by construction.

### 1.3 OpenAI `reasoning_effort`

Official per-request compute dial ([OpenAI reasoning guide](https://developers.openai.com/api/docs/guides/reasoning), fetched 2026-07-21).

- **Axis/axes:** SINGLE dial. Values `none | minimal | low | medium | high | xhigh | max` (model-dependent) on one effort axis. (A separate `reasoning.mode` `standard|pro` exists on some newer models, making that model narrowly two-dimensional - but the primary control is one axis.)
- **Thresholds:** Human-configured (the caller sets the level); default is model-specific (e.g. `medium`). Not learned per request by the router.
- **Uncertainty:** Handled *inside* the level - "models reason adaptively across reasoning efforts, using fewer tokens for simpler tasks and thinking harder for complex tasks." The floor is set by the human; the model spends within it.
- **Escalation:** One-shot per call. The caller can re-issue at a higher effort, but the API does not auto-escalate.

### 1.4 Anthropic extended thinking / adaptive thinking

Two generations of the same single-axis control ([Extended thinking docs](https://platform.claude.com/docs/en/build-with-claude/extended-thinking), fetched 2026-07-21).

- **Axis/axes:** SINGLE dial. Legacy `budget_tokens` is one number (max internal reasoning tokens); the newer, recommended *adaptive thinking* replaces it with an `effort` dial where the model self-decides depth per request. Still one axis.
- **Thresholds:** `budget_tokens` is human-configured (you predict the depth up front). Adaptive thinking moves the decision into the model: the human sets an effort level, the model picks depth within it. Explicitly noted that `budget_tokens` is deprecated in favor of the model deciding.
- **Uncertainty:** Adaptive thinking is the uncertainty story - "the model determines when and how much to think on each request"; it may use far less than any budget.
- **Escalation:** One-shot per call (with interleaved thinking spanning tool calls, but no bad-answer-triggered re-route).

### 1.5 Mixture-of-Depths (DeepMind)

Routing as an *architectural* analogy - per-token, per-layer compute allocation ([arXiv:2404.02258](https://arxiv.org/abs/2404.02258)).

- **Axis/axes:** SINGLE scalar. A top-k router scores tokens; the top-k at each layer get full self-attention+MLP, the rest take the residual shortcut. One learned importance score per token.
- **Thresholds:** The compute budget is fixed a priori (k is fixed, giving a static compute graph); the router *learns* which tokens clear the bar. Fixed budget, learned selection.
- **Uncertainty:** Implicit in the learned score; no confidence gate.
- **Escalation:** One-shot within a forward pass (no re-routing).

*Design note:* MoD is the purest statement of "fix the budget, learn what deserves it" - the inverse of forge, which currently fixes the *pipeline* and only coarsely decides what deserves it.

### 1.6 Confidence-gated early-exit sampling (self-consistency family)

A body of work that turns self-consistency into an adaptive cascade: keep sampling only while uncertain. Adaptive-Consistency ([arXiv:2305.11860](https://arxiv.org/abs/2305.11860)); Early-Stopping Self-Consistency ([arXiv:2401.10480](https://arxiv.org/abs/2401.10480)); Confidence-Guided Early Stopping / CGES ([arXiv:2511.02603](https://arxiv.org/abs/2511.02603)); Reliability-Aware Adaptive Self-Consistency / ReASC ([arXiv:2601.02970](https://arxiv.org/abs/2601.02970)).

- **Axis/axes:** SINGLE scalar - a running confidence/posterior over the current answer.
- **Thresholds:** A stopping criterion; CGES halts once posterior mass over a candidate exceeds a threshold (Bayesian), cutting model calls ~69% while matching accuracy.
- **Uncertainty:** This IS an uncertainty-driven method end to end.
- **Escalation:** YES (in the "keep going" direction) - it *de-escalates* early on easy items and spends more samples on hard ones. Same cascade logic as FrugalGPT, applied to sample count instead of model tier.

### 1.7 Martian model router `[vendor]`

Commercial production router ([withmartian.com](https://route.withmartian.com/)); vendor claims, treated as a market-signal not an independent result.

- **Axis/axes:** Markets itself as MULTI-criteria - routes on "cost, latency, accuracy, and custom business requirements" - but the per-request decision is still "which single model wins this query," i.e. a scalarized objective over those criteria.
- **Thresholds:** Proprietary ("model mapping"); operator sets cost/latency/quality targets.
- **Uncertainty / escalation:** Offers fallbacks (a degenerate escalation on failure) and observability; core route is one-shot.

---

## 2. Risk-based testing / risk-based QA

The cluster where two-axis routing is *doctrine*, and the single closest match to forge's "how much QA does this change deserve" question.

### 2.1 ISTQB / ISO 29119 risk-based testing

The standards-body definition, and the cleanest two-axis statement in the whole survey ([ISTQB glossary: risk-based testing](https://glossary.istqb.org/en_US/term/risk-based-testing); [risk likelihood](https://glossary.istqb.org/en_US/term/risk-likelihood); fetched via glossary 2026-07-21).

- **Axis/axes:** TWO, multiplied. ISTQB: risk-based testing is "an approach... to reduce the level of product risks... [using] risk levels to guide the test process." A risk is "a factor that could result in a future negative consequence, characterized by *likelihood and impact*," and **risk level is computed from likelihood x impact**. Test depth is allocated in proportion to that product. This is exactly the size-x-risk shape - one axis is "how likely to break," the other "how bad if it does."
- **Thresholds:** Human-configured via a risk matrix (likelihood bands x impact bands -> a grid of low/medium/high cells); each cell maps to a prescribed test intensity. Qualitative or quantitative rating, set by stakeholders.
- **Uncertainty:** Default-to-deep on the high-impact axis regardless of likelihood - a low-probability catastrophic risk still earns scrutiny. The matrix bakes in conservatism on the impact dimension.
- **Escalation:** Iterative, not one-shot. RBT is explicitly a "start early, revisit throughout the project" loop; risk levels are reassessed as the product changes and testing re-prioritized. So it re-routes over the life of the work.

### 2.2 Google test-size taxonomy (small / medium / large)

Google routes tests into three sizes by *resource footprint*, not by risk ([Google Testing Blog: Test Sizes, 2010](https://testing.googleblog.com/2010/12/test-sizes.html); [Software Engineering at Google, ch. Testing Overview](https://abseil.io/resources/swe-book/html/ch11.html)).

- **Axis/axes:** SINGLE axis for the taxonomy itself - "size refers to the resources required to run a test case" (memory, processes, time). Small = one process, no blocking calls; Medium = single machine, localhost only; Large = real production environment, multiple features. But Google pairs this with a *separate* scope notion (unit/integration/system) and the test-pyramid ratios, so in practice test *strategy* is two-dimensional (size x scope). The size axis is a proxy for blast radius / determinism, distinct from the change's risk.
- **Thresholds:** Fixed, mechanical definitions (a test that touches the network above localhost is by definition not Small). Not learned; enforced by the build system.
- **Uncertainty:** Not a routing concern here; sizes are deterministic constraints.
- **Escalation:** None per test; the *portfolio* is shaped by pyramid ratios (many small, few large).

### 2.3 Change-based test selection (Google TAP / predictive selection)

How test *breadth* scales to the change, not the whole suite every time ([Google Testing Blog: Testing at the speed and scale of Google, 2011](https://testing.googleblog.com/2011/06/testing-at-speed-and-scale-of-google.html); Predictive Test Selection, [arXiv:1810.05286](https://arxiv.org/abs/1810.05286)).

- **Axis/axes:** SINGLE axis in classic form - the *dependency distance* from the change. TAP builds a dependency graph; a change to a file selects exactly the tests transitively depending on it. Predictive Test Selection (Facebook, same problem) adds a *learned* probability-that-this-test-fails-given-this-change, which is a second, risk-flavored signal layered on the pure-reachability axis.
- **Thresholds:** Reachability is exact (graph-derived). The predictive variant learns a failure-probability threshold from historical CI data.
- **Uncertainty:** Predictive selection is explicitly probabilistic - it hedges by running tests above a learned failure-likelihood cutoff even when not certain they will fail.
- **Escalation:** Two-tier in practice - fast/affected tests presubmit, the fuller suite postsubmit. That is a cascade: cheap gate first, broad gate later.

### 2.4 Mutation testing prioritization at Google

How Google makes an expensive QA technique proportionate ([State of Mutation Testing at Google, ICSE-SEIP 2018 / research.google](https://research.google/pubs/state-of-mutation-testing-at-google/); [Practical Mutation Testing at Scale, arXiv:2102.11378](https://arxiv.org/abs/2102.11378)).

- **Axis/axes:** Effectively TWO filters combined - (a) *diff-based*: only mutate lines the change touched (a size/locality axis), and (b) *productivity/arid-line* filtering plus statement-coverage gating (a value/risk axis - skip lines that are uncovered or "uninteresting"). Mutants are surfaced only where both fire.
- **Thresholds:** Coverage gate is mechanical (no coverage -> no mutant); arid-line suppression is a learned/heuristic productivity model tuned against developer feedback in code review.
- **Uncertainty:** Handled by surfacing a *tiny* number of high-confidence "productive" mutants rather than defaulting to the full mutant set - bias toward precision over recall.
- **Escalation:** One-shot per change, but incremental across the codebase's evolution (mutants ride the diff).

---

## 3. Staged / tiered code review

Two distinct axes appear here and they do not collapse: review *scrutiny* scales with change SIZE; required *approvers* scale with change PATH/ownership.

### 3.1 Google "Standard of Code Review" + small-CL doctrine

Scrutiny is proportionate to size, encoded as culture rather than a matrix ([The Standard of Code Review](https://google.github.io/eng-practices/review/reviewer/standard.html); [Small CLs](https://google.github.io/eng-practices/review/developer/small-cls.html), fetched 2026-07-21; [Software Engineering at Google, ch. Code Review](https://abseil.io/resources/swe-book/html/ch09.html)).

- **Axis/axes:** SIZE is the dominant routing axis. The small-CL guide: "It's easier for a reviewer to find five minutes several times to review small CLs than to set aside a 30 minute block to review one large CL," and reviewers "have discretion to reject your change outright for the sole reason of it being too large." Large changes measurably *lose* thoroughness ("important points get missed or dropped"). So the system pushes changes small precisely so scrutiny stays uniform - size is managed rather than used to dial review depth up.
- **Thresholds:** Norms, not hard cutoffs - "not seeking perfect code," approve if it "improves code health." Human judgment, culturally calibrated.
- **Uncertainty:** Reviewer can LGTM-with-comments (approve while flagging non-blocking items) - a graduated rather than binary gate.
- **Escalation:** Yes - disagreement escalates from the reviewer to a senior/owner or a wider forum; oversized CLs get bounced back to be split.

### 3.2 GitHub CODEOWNERS + path-based required reviewers

The clean SECOND axis: who must review is a function of *which files*, orthogonal to how big the change is ([About code owners](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners); [Managing a branch protection rule](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/managing-a-branch-protection-rule); [Required reviewer rule GA, 2026-02-17](https://github.blog/changelog/2026-02-17-required-reviewer-rule-is-now-generally-available/)).

- **Axis/axes:** PATH/sensitivity axis, independent of size. A change touching an owned path pulls in that path's required reviewers; touch two owned areas and BOTH owner sets are required. "Most specific matching rule takes priority." This is the design that keeps risk (what you touched) separate from size (how much you touched).
- **Thresholds:** Human-configured, declaratively, as path globs -> required teams, plus branch-protection rules (required approvals count, required owner review).
- **Uncertainty:** Conservative by construction - if a change *might* affect a sensitive path, matching a broad glob to that path forces the review. Default-to-strict.
- **Escalation:** Structural, not dynamic - the rule fires at PR-open based on the diff's paths; there is no mid-review re-route (the routing is one-shot, but on the path axis rather than a size scalar).

### 3.3 Branch-protection / rulesets tiering `[GitHub docs]`

Branch protection and repository rulesets let required-reviews, required-checks, and required-owner-approval differ *per branch and per path*, so the same repo runs a light gate on a feature branch and a heavy gate on `main`. This is tiering by blast radius of the *target*, a third dimension beyond change size and change path.

---

## 4. Proportionate process generally (CI/CD, deploy, change management)

Blast-radius-sized governance. The recurring shape is a small set of named tiers (not a continuous scalar) plus a dynamic throttle.

### 4.1 ITIL change types: standard / normal / emergency `[secondary index]`

The canonical tiering scheme for changes. ITIL itself is the primary authority; the concrete descriptions below were read from a vendor summary used only as a discovery index ([ManageEngine ITIL change types, secondary](https://www.manageengine.com/products/service-desk/it-change-management/it-change-types.html)).

- **Axis/axes:** TWO underlying axes collapsed into named tiers. Standard = pre-approved, low-impact, well-known (low impact, low uncertainty). Normal = full assessment/scheduling/authorization, itself split into minor vs major by *impact and urgency*. Emergency = high impact AND high urgency, expedited path. So the tiering is a discretization of impact x urgency.
- **Thresholds:** Human-configured policy - an org defines which change models are "standard" (pre-authorized, skip the CAB) versus "normal" (route to the Change Advisory Board) versus "emergency" (route to the smaller, faster ECAB).
- **Uncertainty:** Default-to-heavy on first occurrence - a standard change must pass full risk assessment and authorization *the first time*; only after it is proven routine does it get the pre-approved fast lane.
- **Escalation:** Tier is chosen up front by classification, but the emergency path is exactly a mid-flight escalation to a compressed ECAB approval when urgency spikes.

*Steal:* the "standard change = pre-approved, skip the board" tier is the direct analog of forge's `trivial` bypass - and ITIL earns the bypass by requiring the *first* instance to run the full process. A repeatable pattern gets fast-laned only after it has been proven safe once.

### 4.2 Google SRE error budgets

The strongest example of *dynamic* proportionate friction - process weight is a function of remaining budget, recomputed continuously ([Google SRE book, Embracing Risk](https://sre.google/sre-book/embracing-risk/), fetched 2026-07-21; [Error Budget Policy, SRE Workbook App. B](https://sre.google/workbook/error-budget-policy/)).

- **Axis/axes:** SINGLE scalar - remaining error budget (allowed unreliability minus consumed). Release friction is a function of that one number.
- **Thresholds:** Derived from the SLO (the budget = 1 - SLO target), so a fixed formula, but the SLO target is human-negotiated. The control loop: "as long as the system's SLOs are met, releases can continue."
- **Uncertainty:** The budget IS the uncertainty buffer; you spend risk against it and the buffer absorbs variance.
- **Escalation:** YES, and graduated - "if SLO violations occur frequently enough to expend the error budget, releases are temporarily halted," and "more subtle... approaches" slow or roll back releases as the budget nears exhaustion. Friction rises smoothly as headroom falls. Self-policing: teams throttle *themselves* to protect their launch.

### 4.3 Microsoft deployment rings / progressive exposure

Blast-radius sizing via staged exposure ([Progressively expose releases using deployment rings, Azure DevOps](https://learn.microsoft.com/en-us/azure/devops/migrate/phase-rollout-with-rings)).

- **Axis/axes:** SINGLE axis - population exposure (canary -> early adopters -> general). Orthogonal feature-flags fine-tune within a ring, giving a practical second knob.
- **Thresholds:** Human-configured gates per ring - "IT administrators set criteria to control deferral time or adoption that should be met before deployment to the next broader ring."
- **Uncertainty:** Handled by *staging* - each ring is a cheap check that catches issues "before release to production," so the design assumes you are uncertain and buys observation before widening.
- **Escalation:** This is the deployment-side cascade - promote to the next ring only if the current ring stays healthy; a regression halts promotion or rolls back. Re-route by construction.

### 4.4 Progressive delivery / canary (blast-radius framing) `[vendor/secondary]`

Canary and progressive delivery generalize rings: send a change to a small slice, watch metrics, widen or abort. Same cascade shape as 4.2/4.3. DORA's "change failure rate" is the outcome metric this whole family optimizes - it frames *change* (not size alone) as the unit of risk, reinforcing that governance is proportioned to a change's blast radius, not merely its diff size.

---

## Cross-cutting synthesis: one scalar or two axes?

**Which fields collapse to one dimension, and which keep two:**

| Domain | Routing axis/axes | Collapses or keeps two? |
| --- | --- | --- |
| RouteLLM, FrugalGPT, `reasoning_effort`, adaptive thinking, MoD, early-exit sampling | difficulty / win-prob / effort / confidence | **One scalar** |
| Martian `[vendor]` | scalarized cost+latency+quality | One (scalarized) |
| ISTQB / ISO risk-based testing | **likelihood x impact** | **Two (multiplied)** |
| Google test sizes | resource footprint (+ scope) | One primary (two in practice) |
| Change-based / predictive test selection | dependency distance (+ learned fail-prob) | One (two in the predictive variant) |
| Google mutation testing | diff-locality x productivity/coverage | **Two (filters ANDed)** |
| Google review scrutiny | change SIZE | One |
| CODEOWNERS / required reviewers | change PATH / ownership | **Second, orthogonal axis** |
| Branch protection / rulesets | target-branch blast radius | Adds a third |
| ITIL change types | impact x urgency -> named tiers | **Two (discretized)** |
| SRE error budget | remaining budget | One (dynamic) |
| Deployment rings / canary | exposure population | One (staged) |

**The pattern is domain-conditioned, and that resolves the question.** Single-scalar routing owns the LLM-adaptive-compute domain, where the router picks a model or compute depth for a *query whose content is already fixed* - there, difficulty and stakes are correlated enough that one number suffices. Two-axis routing owns the domain forge actually lives in: deciding how much *engineering process* (plan / test / review / deploy scrutiny) a *change* deserves. Every close analog in that domain - risk = likelihood x impact, mutation testing's diff-locality x productivity, review's size axis plus CODEOWNERS' path axis, ITIL's impact x urgency - keeps two axes, because for a code change, size and risk genuinely dissociate. A one-line auth change is small-and-dangerous; a bulk rename is large-and-safe. A single scalar cannot express that cell of the matrix, which is exactly the "middle ground gets the full pipeline" complaint driving this redesign.

**Verdict signal: adopt TWO axes (size x risk).** The evidence favoring two axes comes from the sources whose *problem* matches forge's (proportioning process to a change). The evidence favoring one scalar comes from sources solving a *different, weaker-analogy* problem (routing a fixed prompt to a model). Weight by analogy quality and the two-axis case is stronger. The single most transferable primitive is ISTQB's risk matrix: bands on a likelihood/size axis crossed with bands on an impact/risk axis, each cell mapping to a prescribed process depth.

**Second, independent design decision - one-shot classify vs mid-flight escalate.** This is orthogonal to the axes question and prior art is split by mechanism, not domain: *classifiers* decide once (RouteLLM, `reasoning_effort`, ITIL up-front change-type, CODEOWNERS at PR-open), while *cascades* start cheap and escalate on a signal (FrugalGPT, confidence-gated early-exit, SRE error-budget throttle, deployment rings/canary, Google's presubmit-then-postsubmit tiers). forge today is a pure one-shot classifier. The cascade camp is large and load-bearing, and its lesson is concrete: you do not have to classify perfectly up front if you can escalate when a risk signal fires mid-run (a test surfaces a security-sensitive path; a challenge finds the plan is load-bearing; a lens raises a blocking concern).

## What forge could steal

1. **Route on two axes, size x risk, not one `trivial|standard` scalar.** Cross a size/scope band with a risk/blast-radius band (ISTQB risk matrix) and map each cell to a pipeline depth. This is the direct fix for "the middle ground gets the full pipeline": a large-but-safe change and a small-but-dangerous change land in *different* cells instead of both defaulting to `standard`.
2. **Derive the risk axis from PATH, like CODEOWNERS.** Touching auth/payments/migrations/infra should raise the risk band regardless of diff size - a cheap, declarative, path-glob signal that is orthogonal to size and matches how the whole review world already routes sensitivity.
3. **Consider a cascade shape over sharper up-front classification.** Start lean (plan + tests) and let a risk signal *escalate* into the challenge stage or the full 5-lens wave - FrugalGPT/early-exit/error-budget precedent says escalate-on-signal beats trying to size everything perfectly at the door. Keeps the one-shot classifier as the fast path and adds an escape hatch to depth.
4. **Earn the trivial bypass the ITIL way.** A "standard change" skips the board only after its first instance passed the full process. forge's `trivial` fast-lane is safest when reserved for change *shapes* already proven safe, not judged safe on first sight.
5. **Graduate the gates, do not just branch them.** Google review's LGTM-with-comments and SRE's smooth budget-driven slowdown both avoid binary gates. A lens raising a non-blocking concern need not trigger the whole fix loop; a graduated response (note vs block) reduces the all-or-nothing pipeline cost.
6. **Keep the risk axis conservative (default-to-deep on impact).** RBT and ITIL both keep scrutiny high for low-probability, high-impact changes. Whatever forge's risk estimator, it should bias toward depth on the impact dimension - a rare catastrophic path is exactly where the full pipeline earns its cost.
