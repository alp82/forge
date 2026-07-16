# Name due diligence: forge vs forged across projects and skills

Date: 2026-07-16. Question: before the rename locked in [#10](https://github.com/alp82/alp-river/issues/10) executes, do existing projects or agent skills already own **forge** / **forged** in ways that should change the name - and which spelling does the repo take? Wayfinder ticket [#17](https://github.com/alp82/alp-river/issues/17). Also covers the second locked name, **`/crossfire`**, relayed from [#11](https://github.com/alp82/alp-river/issues/11).

Primary sources: registry JSON endpoints, the GitHub API, official product pages, and the actual `SKILL.md` / `plugin.json` manifests of every colliding project (fetched 2026-07-16). Aggregator and marketplace sites are used only as discovery indexes and are labeled as such. House style: hyphens only.

Throughout, two things are held apart deliberately: **a repo exists with this name** (common, mostly harmless) versus **this collision hurts us** (rare). Most of what follows is the former.

## Executive summary

The name survives, but one of #10's stated premises does not. #10 accepted the forge crowding as "cosmetic" on the grounds that "no collision exists in the agent-workflow space." That premise is **false as stated**: [ForgeCode](https://github.com/tailcallhq/forgecode) is a 7,461-star terminal AI coding agent, invoked as the literal command `forge`, and marketed as "think Claude Code, but with first-class support for many AI providers" - same category, same word. There is also a long tail of a dozen-plus small forge-branded Claude Code plugins pitching near-identical value props, and one exact bare-name skill collision ([EcoKG/forge-skills](https://github.com/EcoKG/forge-skills), `name: forge`, `/forge`, installing to `~/.claude/skills/forge/`) that is a near-clone of alp-river's own concept at 0 stars.

The conclusion nevertheless holds, on a **narrower and more honest basis** than #10 gave: none of these contest our actual install surface. `/forge` inside a Claude Code session is a different namespace from the OS `PATH`, and every exact-name skill collision found has effectively zero adoption. What the crowding costs us is **differentiation and search, not function** - a real cost, but a marketing one, and one #10 already chose to accept in substance if not in wording.

**Verdict: confirm #10 as locked, spelling `forge`.** Two guardrails attach (below). The premise correction is recorded because it changes what the decision rests on, not what the decision is.

## 1. The install surface: bare `/forge` as a Claude Code skill

This is the tier that matters most, because #10 put skills under **bare names with no plugin prefix** - the skill installs to `~/.claude/skills/forge/` and is typed `/forge`. A popular existing `/forge` skill would be a real collision even when no repo is.

| Name | Where | What it is | How crowded | Real collision for us? |
|---|---|---|---|---|
| **forge** (skill) | [EcoKG/forge-skills](https://github.com/EcoKG/forge-skills), verified at [`forge/SKILL.md`](https://github.com/EcoKG/forge-skills/blob/main/forge/SKILL.md) | Frontmatter is literally `name: forge`. Description: "Single /forge command for feature implementation, bug fixes, refactoring... Research + plan + execute + verify pipeline with file-based agent communication." `install.sh` runs `mkdir -p "$SKILLS_DIR/forge"`. | **0 stars**, last pushed 2026-03-21, not archived | **Exact match, zero impact.** Same folder, same command, and near-identical concept to alp-river's own pipeline. But nobody has installed it. It is not a collision that hurts us - it is evidence that forge is the *obvious* name for this exact idea, which means more will come. |
| **forge** (plugin) | [AlphaBravoCompany/forge-plugin](https://github.com/AlphaBravoCompany/forge-plugin) | `.claude-plugin/plugin.json` has `"name": "forge"`; commands are prefixed (`plan`, `help`, `cleanup`, `resume`), not a bare `forge` | 0 stars, **archived** March 2026 | No. Dead, and a prefixed-command plugin, not our bare-skills install slot. |
| Anthropic builtins | [code.claude.com/docs/en/commands](https://code.claude.com/docs/en/commands) | Full list of built-in and bundled commands (`/help`, `/init`, `/review`, `/simplify`, ...) | - | **No shadow risk.** Neither `/forge` nor `/crossfire` is a builtin or bundled command. |
| `tq-forge`, `claude-code-forge`, `skill-forge`, `agentforge`, `forge-cli`, ... | e.g. [tanishq286/tq-forge](https://github.com/tanishq286/tq-forge) | All use **prefixed** identifiers as the actual skill name | 0-1 stars each | No. Different install slot; coexistence. |
| **Claude Forge** | [sangrokjung/claude-forge](https://github.com/sangrokjung/claude-forge) | "oh-my-zsh for Claude Code" - 11 agents, 34-36 commands, 15-26 skills. Verified: ships `/plan`, `/tdd`, `/code-review`, `/loop-forge`, `/auto`, `/explore` and others - **no command named `/forge`**. Plugin name is `claude-forge`. | **776 stars** - by far the most prominent forge-branded Claude Code project | **No, but the loudest neighbor.** Does not claim `/forge` or the `forge` skill folder. It does own the phrase "Claude Forge" in this niche at 776 stars, which is a mindshare cost, not a functional one. |

**Local check:** this machine's actual install surface (`~/.claude/skills/`, 23 skills) and plugin cache contain no `forge` and no `crossfire`.

**Coverage gap, stated plainly:** GitHub code search indexes only a subset of repos and branches. Marketplace aggregators (agentskills.io, claudemarketplaces.com, aitmpl.com, claudepluginhub.com) were used as discovery indexes but not crawled exhaustively. Absence above means "not found via these searches," not "does not exist."

## 2. Projects named forge

| Name | Where | What it is | How crowded | Real collision for us? |
|---|---|---|---|---|
| **ForgeCode** | [tailcallhq/forgecode](https://github.com/tailcallhq/forgecode), [forgecode.dev](https://forgecode.dev/) | Terminal AI coding agent, "the world's top-ranked coding harness, leading TermBench 2.0"; multi-agent architecture with research/planning/execution sub-agents. Installed `curl -fsSL https://forgecode.dev/cli \| sh`, **invoked as the literal shell command `forge`**. | **7,461 stars**, pushed 2026-07-16 (today). Calibration: npm `forgecode` is only **2,464 downloads/month** - though it installs mainly via `curl \| sh`, so npm undercounts. Stars outrun install base. | **The strongest collision found - and still not fatal.** Same product category, same word, actively positioned against Claude Code. But it lives on the OS `PATH`; we live at `/forge` inside a Claude Code session. Different namespace. The real cost is **search and differentiation**: "forge ai coding" is now their term. |
| **Foundry `forge`** | [getfoundry.sh](https://getfoundry.sh/forge/overview/), [foundry-rs/foundry](https://github.com/foundry-rs/foundry) | "Compiles, tests, and deploys Solidity smart contracts. The core development tool in the Foundry suite." Typed daily as `forge build`, `forge test`. | **~10,500 stars**; dominant EVM toolkit | **No - different invocation surface.** A real `forge` binary on PATH for a large professional niche, but not a Claude Code command. Becomes real **only if we ship a bare `forge` executable** - see guardrail 1. |
| **Mistral Forge** | [mistral.ai/news/forge](https://mistral.ai/news/forge/) | "Train, align, and evaluate custom AI models." Enterprise model-training/customization infra. Announced **2026-03-17**. | Major AI-lab launch, heavy press | **No functional collision** (model training, not coding agents), but a big recent claim on "Forge" + "AI" mindshare. Dilutes search. |
| **Atlassian Forge** | [developer.atlassian.com/platform/forge](https://developer.atlassian.com/platform/forge/) | FaaS developer platform for Jira/Confluence/Bitbucket; has its own AI development toolkit page | Major, actively marketed | **Soft.** Different category (app platform). Owns "Forge developer platform" in search. |
| **`github.com/forge`** | [github.com/forge](https://github.com/forge) | **JBoss Forge** org - Java IDE tooling. 66 repos, most last pushed 2014-2019, core repo ~199 stars. | Dormant | No. The org handle is taken; the org is a ghost town. Rules out `github.com/forge` as our home - #10 already plans `alp82/forge`. |
| **Laravel Forge / SourceForge / MinecraftForge** | [forge.laravel.com](https://forge.laravel.com), [sourceforge.net](https://sourceforge.net), [MinecraftForge](https://github.com/MinecraftForge/MinecraftForge) (7,696 stars) | Server deploy SaaS / legacy code host / Minecraft modding API | Huge brand recognition | No - **pre-accepted in #10.** Different spaces. MinecraftForge and conda-forge drive most of the ~135,662 repos with "forge" in the name. |
| **"forge" = generic software forge** | [Wikipedia: Forge (software)](https://en.wikipedia.org/wiki/Forge_(software)), [Wiktionary](https://en.wiktionary.org/wiki/forge) noun sense 4 | "A forge is a web-based collaborative software platform for both developing and sharing computer applications" - GitLab, Gitea, Forgejo, Codeberg, SourceHut. The term spread from SourceForge (2001) and derives from the metalworking forge. | Dictionary-level generic | **Mild, worth knowing.** In a dev context, "forge" already means *code-hosting platform* to FOSS-literate ears. A small mis-set expectation, not a collision. |
| **electron/forge** (7,105), **digitalbazaar/forge** / `node-forge` (5,320 stars; **152M npm downloads/month**), **Card-Forge/forge** (2,518), **The-Forge** (5,606), **Puppet Forge**, **Homebrew `forge`** (ArrayFire viz lib) | various | Build tool / JS crypto / MTG rules engine / graphics framework / IaC module registry | Individually large | No. All different spaces. Note `node-forge`'s enormous download count belongs to the **hyphenated** name, not bare `forge`. |
| **Autodesk Forge** | [aps.autodesk.com blog](https://aps.autodesk.com/blog/autodesk-forge-becoming-autodesk-platform-services) | **Rebranded to Autodesk Platform Services (Dec 2022)** - actively moved *away* from the Forge name | Retired brand | No. Vacating, not occupying. |
| **Long tail of forge-branded Claude Code tools** | [nxtg-ai/forge-plugin](https://github.com/nxtg-ai/forge-plugin) ("governance for Claude Code"), [samahlstrom/forge-cli](https://github.com/samahlstrom/forge-cli) ("Portable AI agent toolkit for Claude Code"), `RapierCraftStudios/ForgeDock` ("autonomous AI dev pipeline for Claude Code - issue in, PR out"), [forge-agents/forge](https://github.com/forge-agents/forge) (25 stars, "Universal CLI for coding agents"), npm `claude-forge`, `cc-forge`, `@aion0/forge`, `@agentfare/forge` | Small repos/packages, 3-110 stars, npm downloads in the tens | Individually negligible | **No single collision - but the most underrated finding.** "Forge" is already the *default* word choice among small Claude Code workflow builders, several pitching almost exactly our pitch. We would join a cluster, not stand out in one. |

### Registries (bare name ownership)

We do not need a registry name - alp-river ships as a Claude Code plugin via marketplace, not npm/PyPI/crates. Recorded for completeness only:

| Registry | `forge` | `forged` |
|---|---|---|
| npm | Taken - ["A no customization 'build' system"](https://registry.npmjs.org/forge), v2.3.0, last published 2014 | Taken - [empty placeholder](https://registry.npmjs.org/forged), v0.0.1, no description |
| PyPI | Taken - [Dropseed's Django framework](https://pypi.org/pypi/forge/json) | Taken - tiny synthetic-data lib, last release 2021 |
| crates.io | Taken - [v0.1.0, 5,515 downloads, dead since 2017](https://crates.io/api/v1/crates/forge) | Taken - [forged.dev device provisioning, 9,565 downloads](https://crates.io/api/v1/crates/forged) |
| Homebrew | Taken - [ArrayFire viz library](https://formulae.brew.sh/api/formula/forge.json) | No formula found |

Both spellings are squatted everywhere, in every case by dormant or unrelated projects. Neither is available verbatim; neither matters for our distribution.

## 3. `/crossfire`

| Name | Where | What it is | How crowded | Real collision for us? |
|---|---|---|---|---|
| **crossfire** (skill + CLI) | [CodeDaraW/crossfire](https://github.com/CodeDaraW/crossfire), verified at [`skills/crossfire/SKILL.md`](https://github.com/CodeDaraW/crossfire/blob/main/skills/crossfire/SKILL.md) | `name: crossfire`. "Cross-agent code review and task delegation, supporting Codex, Cursor, and Claude Code." Installs a `crossfire` binary to `~/.local/bin/`. Its slash commands are **hyphenated** (`/crossfire-review`, `/crossfire-setup`), not bare `/crossfire`. | **2 stars**, pushed 2026-06-03, multi-language README | **Closest match, low impact.** Same word, same domain (cross-agent review) - conceptually near-identical to our renamed review command. But 2 stars, and its commands are hyphenated. A name-and-concept twin with no audience. |
| **crossfire** (skill) | [wpfleger96/ai-agent-rules](https://github.com/wpfleger96/ai-agent-rules), `src/ai_rules/config/skills/crossfire/SKILL.md` | `name: crossfire`. "Get multi-model perspectives (Codex + Gemini)" on a plan/diff/tests. | 4 stars, actively pushed | Bare-name match in a personal config repo, not a distributed marketplace plugin. Real only for someone who installs that repo's skills. |
| **Crossfire: Cross-LLM Debate** | [sderosiaux/agents-crossfire](https://github.com/sderosiaux/agents-crossfire) | Folder/repo is `agents-crossfire`, not bare `crossfire`; puts models in debate | 2 stars | Partial - concept branding only, no folder collision. |
| "Crossfire" as a section name | [nyldn/claude-octopus](https://github.com/nyldn/claude-octopus) (`skills/skill-parallel-agents/SKILL.md`, header "Crossfire: Adversarial cross-model review"), copied into at least 3 more repos | Internal section inside a differently-named skill | 0-low stars, but copy-pasted across 4+ repos | No collision. **But a signal:** "crossfire" is becoming an informal term of art for adversarial cross-model review - the exact meaning we intend. That is mild validation and mild crowding at once. |
| Crossfire the MMOFPS (Smilegate) / TBS Crossfire + CRSF RC protocol / [crossfire-rs](https://github.com/frostyplanet/crossfire-rs) (445 stars, Rust channels) / npm `crossfire` (dead DNS-SRV proxy) | various | Game / RC radio telemetry / async channel lib / networking | Game is huge in Asia | No. Zero install-surface overlap. Background search noise only. |

**`/crossfire` verdict: keep.** Nothing found has adoption. The honest caveat is that the word is independently converging on our exact meaning in this ecosystem, so the name is apt but will not stay distinctive.

## 4. Spelling: forge vs forged

**Recommendation: `forge`.** Three reasons, in descending weight.

**1. The counterfeit reading is not a tail risk for "forged" - it is the primary sense.** [Wiktionary](https://en.wiktionary.org/wiki/forged) lists the adjective `forged` as: (1) "Fake (as documents); falsified." (2) "Fabricated by forging or at a forge, by working hot metal." Counterfeit is listed **first**; metalworking second. The verb [`forge`](https://en.wiktionary.org/wiki/forge) inverts this - sense 1 is "To shape a metal by heating and hammering," with "To create a forgery of; to make a counterfeit item of" only at sense 4. The inflection flips which meaning arrives first. This is not a subtle connotation difference; it is a reversal of the default reading, and it lands on a tool whose entire pitch is trustworthy automated code changes. The surrounding evidence makes it worse: searching "forged code" in an AI context returns a solid wall of AI-forgery-and-fake-document material ([HYPR](https://blog.hypr.com/ai-forgery-epidemic), [Bytescare](https://bytescare.com/blog/ai-counterfeit), [Truescreen](https://truescreen.io/articles/document-forgery-ai/), [arXiv 2512.19228](https://arxiv.org/pdf/2512.19228)). "Forged code" is the accusation an AI codegen tool spends its life rebutting. Do not put it on the README.

**2. The identity split is real.** #10 makes `/forge` the entry verb. A README saying "forged" while the user types `/forge` teaches two names for one thing - which the repo's own leitwort doctrine forbids ("One concept, one name"). The badge reading buys nothing that the verb does not already earn.

**3. "forged" buys no collision relief.** This is the decisive practical point. The namespace math marginally favors `forged` (1,473 repos with "forged" in the name vs 135,662 for "forge"; weaker registry claimants). But the collision that actually matters - **ForgeCode** - owns *the word*, not the inflection. Nobody searching lands differently because we conjugated. `forged` pays the counterfeit cost and collects no benefit.

The one genuine argument for `forged` - that it reads as a badge ("forged in...") and is marginally more open - does not survive reason 1.

## 5. Verdict

**Confirm [#10](https://github.com/alp82/alp-river/issues/10) as locked. Spelling: `forge`. Keep `/crossfire`.**

No collision found rises to the bar of *hurting us*:

- The one exact bare-name `/forge` skill (EcoKG/forge-skills) has **0 stars** and no adoption, despite being an uncanny concept twin.
- The one same-category heavyweight (ForgeCode, 7,461 stars) contests the **shell PATH**, which we do not use. Our surface is `/forge` inside a Claude Code session.
- Everything else - Laravel Forge, SourceForge, MinecraftForge, Foundry, Atlassian, Mistral, JBoss - is a different space, and #10 already accepted this class of crowding.

**But #10's stated premise needs correcting in the record.** #10 wrote: "No collision exists in the agent-workflow space, and bare-name commands make the crowding cosmetic." The first clause is false - ForgeCode, `forge-agents/forge`, EcoKG/forge-skills, and a dozen-plus small forge-branded Claude Code plugins are all in the agent-workflow space. The second clause survives and is doing all the work: our install surface genuinely is uncontested. The decision is unchanged; its **basis** narrows from "nothing collides" to "the collisions are real but sit in namespaces we do not occupy, and cost differentiation rather than function."

**Two guardrails follow directly from the findings:**

1. **Never ship a bare `forge` executable on `PATH`.** Foundry's `forge` (~10.5k stars, typed daily by Solidity devs) and ForgeCode's `forge` both already live there. Our claim is the Claude Code command namespace and `~/.claude/skills/forge/` only. This is the single line between "coexistence" and "real collision," and it is entirely within our control. It belongs in the rename's execution spec.
2. **Do not budget on "forge" being findable.** #10 accepted that forge "will never be uniquely searchable"; this check confirms it is worse than assumed, since Mistral's March 2026 launch and ForgeCode now hold "forge + AI" specifically. Discovery must come from the marketplace listing, the repo path `alp82/forge`, and the docs - never from the bare word.

**One flag, not a recommendation.** The long-tail finding is the only thing here that could reasonably reopen the question: forge is already the *default* name for small Claude Code workflow plugins, several pitching near-identical value props. That is a differentiation problem #10 did not price, because #10 believed the space was empty. If standing out matters more to this project than the entry-verb reading does, the runner-up **sculpt** (recorded in #10 as having zero collisions) is the only candidate that fixes it, and this is the last cheap moment to switch. That trade - a better verb in a crowded field versus a good verb in an empty one - is a naming judgment call, not a research finding, and it belongs to the owner of #10. Absent that call, **the name is forge** and the rename should execute.
