# Agent-workflow landscape survey

Date: 2026-07-15. Question: how do other agent-workflow systems solve what alp-river solves, and what is the current state of the art for skill collections, pipeline orchestration, and multi-model dispatch? Wayfinder ticket #7.

Primary sources only: repo READMEs and source files (fetched 2026-07-15 unless dated otherwise), official docs, the locally installed plugins under `~/.claude/plugins/cache/`, and this repo's own research docs. Secondary lists are used only as discovery indexes and are labeled as such. House style: hyphens only. The survey feeds two decisions: (a) keep/cut/merge of alp-river's capability set, and (b) how GPT/Codex workers get spawned from a Claude Code orchestrator.

## Executive summary

The field has converged on three findings that matter for alp-river. First, the winning skill collections are small: superpowers ships 14 skills, Matt Pocock ships 21, Anthropic's own feature-dev plugin ships 3 agents - nobody with real adoption ships anything near alp-river's 42 agents, and every high-adoption system stores state in human-legible artifacts (plans, tickets, ledger files) rather than a signal vocabulary. Second, enforcement is alp-river's rarest asset: almost the entire landscape relies on prose discipline ("you ABSOLUTELY MUST invoke the skill"), while alp-river's deterministic router and stop-gate hooks - exactly the components the pipeline audit found earning their cost - have no widely adopted analog. Third, for multi-model dispatch the state of the art is the officially shipped OpenAI Codex plugin (installed locally, read in full): a radically thin pattern - one Bash-only forwarder subagent, a ~5 K-line companion Node script owning all job state, verbatim output contracts, and an optional cross-vendor Stop-hook review gate. The CLI-as-forwarder pattern is beating the MCP-bridge pattern (PAL/Zen MCP looks stalled since 2025-12; Codex's own MCP mode has an unresolved non-interactive approval gap), and `codex exec --json --output-schema` gives a structured-return surface that maps cleanly onto alp-river's stage-contract model.

## 1. Skill collections and workflow systems

### 1.1 The Agent Skills standard

The substrate everything now builds on. A skill is "a folder containing a `SKILL.md` file" with `name` and `description` as the only required frontmatter; agents load skills by three-stage progressive disclosure - discovery (name+description only), activation (full SKILL.md), execution (bundled files on demand) ([agentskills.io](https://agentskills.io)). "Originally developed by Anthropic, released as an open standard"; the client showcase lists 40+ adopters including Cursor, GitHub Copilot/VS Code, Gemini CLI, OpenAI Codex, Goose, OpenCode, Amp, and Kiro. Portability across harnesses is now free for anything expressed as plain skills - and unavailable to anything that depends on Claude Code-specific machinery (hooks, agent frontmatter, routers).

[anthropics/skills](https://github.com/anthropics/skills) (~161 K stars) is the reference collection: document skills (DOCX/PDF/PPTX/XLSX, "source-available, not open source"), creative/development/enterprise categories, distributed via Claude Code marketplace, claude.ai, and the Skills API. It is a library of capabilities, not a workflow system - no pipeline, no gates.

Claude Code's plugin system ([code.claude.com/docs/en/plugins](https://code.claude.com/docs/en/plugins)) is the distribution layer alp-river already uses: skills, agents, hooks, MCP servers, LSP servers, background monitors, and `settings.json` defaults in one installable unit, plus two Anthropic-run marketplaces (`claude-plugins-official`, curated; `claude-community`, reviewed submissions). Community metric trackers (discovery indexes: [quemsah/awesome-claude-plugins](https://github.com/quemsah/awesome-claude-plugins), [ccplugins/awesome-claude-code-plugins](https://github.com/ccplugins/awesome-claude-code-plugins)) count thousands of plugins across ~190 marketplaces as of June 2026, with install leaders Frontend Design (~829 K), Superpowers (~752 K), Context7 (~349 K).

### 1.2 obra/superpowers - the adoption leader among methodologies

"A complete software development methodology for your coding agents, built on top of a set of composable skills" ([README](https://github.com/obra/superpowers)); ~255 K stars, installable on "10+ coding agents". Exactly 14 skills in four bands ([skills/](https://github.com/obra/superpowers/tree/main/skills)): testing (test-driven-development), debugging (systematic-debugging, verification-before-completion), collaboration (brainstorming, writing-plans, executing-plans, dispatching-parallel-agents, requesting-code-review, receiving-code-review, using-git-worktrees, finishing-a-development-branch, subagent-driven-development), meta (writing-skills, using-superpowers).

The enforced pipeline mirrors alp-river's spine: brainstorming (Socratic refinement) -> git worktree isolation -> writing-plans ("bite-sized tasks (2-5 minutes each)") -> subagent-driven development with two-stage review -> TDD ("RED-GREEN-REFACTOR: write failing test, watch it fail, write minimal code") -> code review against the plan -> branch finishing. Routing is a prose meta-skill: [using-superpowers](https://github.com/obra/superpowers/blob/main/skills/using-superpowers/SKILL.md) mandates "If you think there is even a 1% chance a skill might apply to what you are doing, you ABSOLUTELY MUST invoke the skill", ordered "process skills come first", backed by a "Red Flags" rationalization table. That is the entire router - no code, no signals, model discipline only.

### 1.3 The spec-driven frameworks

- **[github/spec-kit](https://github.com/github/spec-kit)** (~121 K stars): "specifications become executable". Fixed five-phase sequence - constitution, specify, plan, tasks, implement - exposed as slash commands (`/speckit.specify`) across "30+ AI coding agents". Gates are document-shaped: an optional clarify step before planning, an analyze step for "cross-artifact consistency validation", custom checklists, and a post-implementation converge assessment.
- **[BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD)** (~51 K stars, V6): "12+ domain experts (PM, Architect, Developer, UX, and more)" as persona agents, 34+ workflows, "Scale-Domain-Adaptive" planning depth "that adjusts from bug fixes to enterprise systems". The heaviest framework surveyed; the closest analog to alp-river's fleet-of-roles design.
- **GSD (Get Shit Done)**: meta-prompting system for Claude Code targeting "context rot" - phases discuss/plan/execute/verify, "each phase keeps its own focused context", 69 commands and 24 agents, ~23 K stars as of March 2026. Cautionary tale: after a trust incident the original repo is considered compromised and development moved to [open-gsd/get-shit-done-redux](https://github.com/open-gsd/get-shit-done-redux) - framework repos are a supply-chain trust surface.
- **[Agent OS](https://github.com/buildermethods/agent-os)** (Builder Methods): standards-extraction middleware - "agents that build the way you would" - which documents a codebase's conventions and deploys them contextually. Convention layer only, no pipeline.

### 1.4 Anthropic's own workflow plugins

The official `claude-plugins-official` set contains 13 Anthropic-built plugins ([anthropics/claude-code plugins/README](https://github.com/anthropics/claude-code/blob/main/plugins/README.md)). Relevant here: **feature-dev** ("a structured 7-phase approach" with exactly three agents - code-explorer, code-architect, code-reviewer); **code-review** ("automated PR code review using multiple specialized agents" - five parallel Sonnet agents with confidence-based filtering to cut noise); **commit-commands** (`/commit`, `/commit-push-pr`); **security-guidance** (a hook watching nine dangerous patterns); **ralph-wiggum** (iterative self-referential loops with exit interception). Anthropic's own dogfood pipeline is 3-5 agents per workflow and one enforcing hook - an order of magnitude leaner than alp-river, with the same parallel-review-plus-confidence-filter shape alp-river's audit validated.

### 1.5 Passive convention layers (for completeness)

Cursor rules ([PatrickJS/awesome-cursorrules](https://github.com/PatrickJS/awesome-cursorrules), ~40 K stars) and aider's `CONVENTIONS.md` loaded via `--read`/`.aider.conf.yml` ([aider docs](https://aider.chat/docs/usage/conventions.html)) are static context injection - guidelines, not workflows. No composition, no gates. They matter only as evidence that the lowest-machinery tier of the market is enormous.

### 1.6 Matt Pocock's skills

Covered in depth by the sibling doc (`docs/research/matt-skills-patterns.md`): 21 prompt-only skills, two-tier naming, prose composition, repo-native state, zero hooks. The quality bar this effort aims at; not restated here.

## 2. Composition, quality gates, and review loops

### 2.1 Composition and routing

Three mechanisms exist in the wild, in ascending order of machinery:

1. **Prose mention** - a skill names another skill and the model follows (Matt's `/grilling`, superpowers' skill references, BMAD's `bmad-help`). Cheapest; no guarantees.
2. **Meta-skill router** - a dedicated always-on skill that forces skill lookup before action (superpowers' using-superpowers "1% chance" rule; Matt's `ask-matt` flow map). Still prose; adds a checkable discipline.
3. **Fixed command sequence** - spec-kit's numbered phases, GSD's phase commands. Deterministic order, but the human drives each transition.

Nobody else routes with code. alp-river's `hooks/route.py` (240 lines, zero tokens per decision, per `docs/research/pipeline-audit.md`) is unique in the surveyed field. The corollary: nobody else needs a 76-signal vocabulary either - the systems above coordinate through documents the human can read (specs, plans, tickets, ledger files).

### 2.2 Review loops - the field's common shape

Superpowers' [subagent-driven-development](https://github.com/obra/superpowers/blob/main/skills/subagent-driven-development/SKILL.md) is the most fully specified loop and reads like a lean alp-river: the orchestrator "curates exactly what context is needed; bulk artifacts move as files, not pasted text", dispatches a fresh implementer per task "never the full session history", then a task reviewer issuing **two mandatory verdicts** - "spec compliance AND task quality are both required" ("spec compliance prevents over/under-building"). Critical/Important findings spawn fix subagents, fixed code "returns to the same reviewer for re-approval", and passing tasks reach a "final whole-branch review on the most capable model". Progress lives in "a ledger file (surviving context compaction)". [requesting-code-review](https://github.com/obra/superpowers/blob/main/skills/requesting-code-review/SKILL.md) adds severity triage (Critical/Important/Minor), reviewer context isolation ("the reviewer gets precisely crafted context for evaluation - never your session's history"), and sanctioned push-back ("push back with technical reasoning").

Anthropic's code-review plugin runs five parallel Sonnet lenses with confidence scoring to filter noise - structurally identical to alp-river's parallel review wave plus confidence tagging. spec-kit gates on artifacts instead of reviewers (analyze/checklists/converge). BMAD reviews through persona agents (QA/Test Architect module).

Direct mapping to alp-river's fleet: superpowers' spec-compliance verdict = acceptance-reviewer; task-quality verdict = correctness + simplicity lenses; fix subagent + re-review = fixer + re-run set; final whole-branch review on the strongest model = a model-tiering move alp-river already systematizes. Both audit-validated keepers (parallel wave, fixer loop) and validated cuts (16-lens waves) are corroborated by what the adoption leaders converged on.

### 2.3 Enforcement - the field's gap

Every system above enforces its gates with prose. Superpowers' TDD skill has no hook that blocks a stop on red tests; a skipped review is silently skipped (same finding as for Matt's skills in the sibling doc). The only mechanical gates found anywhere: alp-river's verify-tests/verify-build Stop hooks (median 2.3 s, blocked dozens of real stops per the audit), Anthropic's security-guidance pattern hook, ralph-wiggum's exit interception, and the Codex plugin's stop-review-gate (section 3.1) - which spends an entire Codex run per stop where alp-river spends a deterministic 2-second check. Instruction-to-hook is a real differentiator, not table stakes.

## 3. Multi-model dispatch: GPT/Codex from a Claude Code session

### 3.1 The installed OpenAI Codex plugin (primary source, read in full)

OpenAI ships an official Claude Code plugin - `codex` v1.0.4, repo [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc), announced 2026-03-31 ([OpenAI community post](https://community.openai.com/t/introducing-codex-plugin-for-claude-code/1378186)) - installed locally at `/home/alp/.claude/plugins/cache/openai-codex/codex/1.0.4/`. Its architecture is the most instructive artifact in this survey:

- **One thin forwarder agent.** `agents/codex-rescue.md`: sonnet, Bash-only, "a thin forwarding wrapper around the Codex companion task runtime" whose "only job is to forward the user's rescue request" in "exactly one `Bash` call" to `codex-companion.mjs task`. It is forbidden to inspect the repo, monitor progress, or do follow-up work. All intelligence lives in the script, none in the agent.
- **A companion script owning all state.** `scripts/codex-companion.mjs` + `scripts/lib/` (~5.1 K lines JS): job records, background jobs with `/codex:status` polling, `/codex:result`, `/codex:cancel`, log files, and a persistent Codex **app-server broker** (`app-server-broker.mjs`) speaking JSON-RPC to a long-lived Codex process - thread continuation via `--resume-last` rides on it.
- **Skills as internal contracts.** Three `user-invocable: false` skills: `codex-cli-runtime` (the forwarding contract), `gpt-5-4-prompting` ("prompt Codex like an operator, not a collaborator" - XML block recipes: `<task>`, `<structured_output_contract>`, `<verification_loop>`, `<grounding_rules>`), and `codex-result-handling` (verbatim relay, "if Codex was never successfully invoked, do not generate a substitute answer at all", and "auto-applying fixes from a review is strictly forbidden").
- **Review commands with the wait/background choice surfaced.** `/codex:review` and `/codex:adversarial-review` size the diff first, then ask once (AskUserQuestion) whether to wait or background; adversarial-review "challenges the chosen implementation, design choices, tradeoffs, and assumptions".
- **A cross-vendor Stop-hook gate.** `hooks/hooks.json` registers an optional Stop hook (900 s timeout) running `prompts/stop-review-gate.md`: Codex reviews the previous Claude turn and must open with exactly `ALLOW: <reason>` or `BLOCK: <reason>`, grounded in repository state ("do not treat the previous Claude response as proof that code changes happened"). A GPT model gating a Claude agent's stop is the strongest cross-model quality-gate pattern found anywhere.
- **Runtime controls as flags, not prompts.** `--model` (with a `spark` alias for `gpt-5.3-codex-spark`), `--effort none|minimal|low|medium|high|xhigh`, `--write` default-on, `--resume`/`--fresh` - routing controls stripped from task text.

### 3.2 Codex CLI's automation surfaces

Three first-party ways to drive Codex programmatically ([non-interactive mode docs](https://developers.openai.com/codex/noninteractive), [MCP docs](https://developers.openai.com/codex/mcp)):

1. **`codex exec`** - headless single run: prompt as argument or stdin, progress to stderr, "only the final agent message to stdout"; `--json` turns stdout into a JSONL event stream; `--output-schema` enforces "structured JSON responses conforming to a specified schema"; `--ephemeral` skips session persistence; `--sandbox` defaults to read-only; `codex exec resume --last` continues a thread. This is the natural spawn surface for a Codex stage worker: an orchestrator can demand output that parses into its own stage contract.
2. **`codex mcp-server`** - exposes `codex()` and `codex-reply()` tools over MCP so any MCP client can delegate sessions. Marked experimental, and it has a live blocker for unattended use: "no way to allow MCP tool calls non-interactively without `--dangerously-bypass-approvals-and-sandbox`" ([openai/codex#24135](https://github.com/openai/codex/issues/24135)).
3. **App-server JSON-RPC** - the persistent-process protocol the official plugin brokers; richer (interrupts, native review mode) but undocumented-as-stable.

### 3.3 General multi-model dispatch patterns

Four distinct patterns, with representatives:

| Pattern | Representative | Mechanism | State |
|---|---|---|---|
| CLI-as-forwarder | codex plugin ([openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc)); Orca worktree spawns (local `orca-cli` skill) | Subagent or script shells out to the other vendor's CLI; result returned verbatim | Shipping, official, actively developed |
| MCP bridge | [PAL MCP, ex-Zen](https://github.com/BeehiveInnovations/zen-mcp-server) (11.7 K stars): `chat`, `thinkdeep`, `consensus`, `codereview`, `precommit`, `clink` CLI-to-CLI, "context revival" across resets; codex mcp-server; [multi_mcp](https://github.com/religa/multi_mcp) | Other models exposed as MCP tools inside the session | PAL's last push 2025-12-15 - seven months stale; codex MCP experimental with the approval gap above |
| API proxy/router | [claude-code-router](https://github.com/musistudio/claude-code-router) (35.8 K stars): "one stable local endpoint", header/body/model-prefix routing, fallbacks, credential pools, "fusion models" | Swaps which model answers the harness's API calls | Active, sponsor-backed - but it substitutes the brain rather than adding a second worker; one model at a time per request |
| Cross-vendor hook gate | codex plugin stop-review-gate | The other vendor's model gates the primary agent's lifecycle via hooks | Shipping, opt-in |

Verdict for alp-river's dispatch decision: the forwarder pattern won. It preserves the orchestrator's context (output arrives as one tool result), needs no MCP approval story, inherits the harness's background-task machinery, and the officially supported `codex exec --json --output-schema` surface means a Codex worker can be held to the same structured stage contract as any alp-river agent. The MCP-bridge route adds a live server dependency and an unresolved sandbox/approval gap; the proxy route solves a different problem (provider freedom, not second opinions).

## 4. Comparative verdict

### 4.1 What the field does better than alp-river

- **Size discipline.** Adoption concentrates at 3-21 units: feature-dev 3 agents, superpowers 14 skills, Matt 21 skills, GSD's 24 agents already drew "context rot" criticism it exists to fix. alp-river's 42 agents (7 never spawned, 5 near-zero, per the pipeline audit) sit far past the field's demonstrated ceiling - the landscape independently corroborates the audit's cut list.
- **Human-legible state.** Every surveyed system coordinates through artifacts a human reads directly - specs (spec-kit), tickets (Matt), ledger files (superpowers), git worktrees. No one else carries a ~280-token signal/slot/field vocabulary; the audit already named it alp-river's top friction, and the field shows it is not necessary for pipeline rigor.
- **Portability.** Superpowers runs on 10+ harnesses, spec-kit on 30+, anything skill-shaped on 40+ clients via the Agent Skills standard. alp-river's hook-and-router core is Claude Code-only; every capability moved from machinery to skills gains this for free.
- **Cross-model leverage.** The codex plugin and PAL's `consensus` get a second frontier model's judgment on plans and diffs. alp-river's plan-challenger is its strongest validated stage while being same-model; the field shows a straightforward upgrade path (adversarial review by a different vendor's model).
- **One-read brevity.** Superpowers' whole methodology and Matt's whole corpus are each smaller than WORKFLOW.md alone (35 K words) - already established by the sibling docs; the wider field confirms it is the norm, not a Matt idiosyncrasy.

### 4.2 What alp-river has that the field lacks

- **Routing as code.** No surveyed system has a deterministic zero-token router; the alternatives are prose meta-skills and fixed command sequences. The audit shows orchestration cost lives everywhere except routing - `route.py` is a genuine, keepable differentiator.
- **Mechanical enforcement.** verify-tests/verify-build stop gates and block-git-writes have no prose-framework equivalent; the field's gates are skippable by construction. The only comparable mechanism (codex stop-review-gate) costs a full model run per stop versus 2.3 s deterministic.
- **Red-test validation.** Superpowers and everyone else run prose TDD; none has alp-river's test-review stage that catches misaligned/false-green tests before implementation (~60 documented catches). This specific defect class is unguarded across the entire field.
- **Adversarial plan challenge as a dedicated stage.** spec-kit's analyze step checks artifact consistency and codex adversarial-review challenges finished diffs; only alp-river attacks the plan pre-implementation with documented concrete catches.
- **Systematic model tiering.** Superpowers gestures at it ("final review on the most capable model"); alp-river's per-stage haiku/sonnet/opus mapping is measured working (audit § 1.1). No surveyed system declares per-stage model economics.
- **Evidence culture.** No other project publishes a token-level audit of its own pipeline. The keep/cut decision alp-river is about to make is itself a capability the field lacks.

### 4.3 Implications for the two decisions

**Keep/cut:** the landscape validates cutting to a superpowers-scale core (roughly: triage, plan, challenge, TDD chain, implement, 2-3 review lenses, fix, verify hooks, router) and collapsing signals into human-legible artifacts. The components to protect are precisely the ones the field cannot copy with prose: the deterministic router, the stop-gate hooks, test-review, plan-challenger, model tiering. Everything with zero spawns has zero analog earning its place anywhere else either.

**Codex dispatch:** adopt the forwarder pattern, not an MCP bridge. Concretely: a thin Bash-only stage worker (or the installed codex plugin itself for rescue/review use) invoking `codex exec --json --output-schema` so Codex returns parse into alp-river's stage contract; `--effort`/`--model` as flags outside task text; verbatim-relay and no-substitute-answer rules copied from `codex-result-handling`; and the stop-review-gate pattern available as an opt-in second-vendor gate for high-stakes builds. The plugin's division of labor - dumb agent, smart script - is also the answer to the audit's orchestrator-cost finding: job control in code costs zero orchestrator tokens.

## Appendix: sources

Local (read 2026-07-15):

- `/home/alp/.claude/plugins/cache/openai-codex/codex/1.0.4/` - agents/codex-rescue.md, skills/codex-cli-runtime/SKILL.md, skills/gpt-5-4-prompting/SKILL.md, skills/codex-result-handling/SKILL.md, commands/review.md, commands/adversarial-review.md, hooks/hooks.json, prompts/stop-review-gate.md, scripts/ (line counts via `wc`), .claude-plugin/plugin.json
- `/home/alp/dev/projects/alp-river/docs/research/pipeline-audit.md` (alp-river cost evidence)
- `/home/alp/dev/projects/alp-river/docs/research/matt-skills-patterns.md` (Matt Pocock deep dive)
- `/home/alp/.claude/plugins/cache/alperortac/alp-river/1.4.0/WORKFLOW.md` (structure skim)

Web (fetched 2026-07-15):

- [agentskills.io](https://agentskills.io) - Agent Skills spec and client showcase
- [github.com/obra/superpowers](https://github.com/obra/superpowers) - README, skills listing, using-superpowers, subagent-driven-development, requesting-code-review SKILL.md files
- [github.com/anthropics/skills](https://github.com/anthropics/skills) - README
- [code.claude.com/docs/en/plugins](https://code.claude.com/docs/en/plugins) - plugin system and marketplaces
- [github.com/anthropics/claude-code plugins/README.md](https://github.com/anthropics/claude-code/blob/main/plugins/README.md) - official plugin set
- [github.com/github/spec-kit](https://github.com/github/spec-kit), [github.com/bmad-code-org/BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD), [github.com/buildermethods/agent-os](https://github.com/buildermethods/agent-os), [github.com/open-gsd/get-shit-done-redux](https://github.com/open-gsd/get-shit-done-redux) - READMEs
- [github.com/openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc); [community.openai.com announcement](https://community.openai.com/t/introducing-codex-plugin-for-claude-code/1378186)
- [developers.openai.com/codex/noninteractive](https://developers.openai.com/codex/noninteractive) (redirects to learn.chatgpt.com/docs/non-interactive-mode), [developers.openai.com/codex/mcp](https://developers.openai.com/codex/mcp), [openai/codex#24135](https://github.com/openai/codex/issues/24135)
- [github.com/BeehiveInnovations/zen-mcp-server](https://github.com/BeehiveInnovations/zen-mcp-server) (now pal-mcp-server), [github.com/musistudio/claude-code-router](https://github.com/musistudio/claude-code-router), [github.com/religa/multi_mcp](https://github.com/religa/multi_mcp)
- [aider.chat/docs/usage/conventions.html](https://aider.chat/docs/usage/conventions.html), [github.com/PatrickJS/awesome-cursorrules](https://github.com/PatrickJS/awesome-cursorrules)
- Star/date figures: GitHub API (search + repo endpoints), 2026-07-15
- Discovery indexes only (claims traced to owning repos where used): [quemsah/awesome-claude-plugins](https://github.com/quemsah/awesome-claude-plugins) (install metrics, 2026-06-01), [ccplugins/awesome-claude-code-plugins](https://github.com/ccplugins/awesome-claude-code-plugins)
