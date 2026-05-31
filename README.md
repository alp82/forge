# Alp River

> *A river of agents, composed to the task.*

**Featured in:** [Alper Ortac's AI Stack](https://aistack.to/stacks/alper-ortac-unw0sl)

Multi-step agent refinement for Claude Code. A deterministic router reads your request and composes the exact stages it needs - and only those - reshaping the set as the work reveals itself. Trivial asks stay out of your way; risky ones earn clarification, planning, adversarial challenge, test-first implementation, review, and self-heal.

The whole thing ships in one folder: a router-driven workflow, 40 composable stages, 6 slash commands, and hooks that compile the stage catalog, gate tests, and inject context.

## Latest updates

**1.0.5**

- Documentation, version, and configuration changes now finish in a few quick steps instead of the full process.
- Changes that add real logic still require failing tests to be written and checked before any code is touched.
- Trivial changes now get a focused correctness check rather than the full review pass.

**1.0.4**

- Multi-step tasks now run their steps in dependency order and reuse each step's real output instead of guessing ahead and redoing work.
- You now see which steps are planned, running, and done at every turn, instead of the work happening silently.
- The workflow recomputes the plan once per step instead of twice, cutting wasted work on every task.
- Background steps now hand back just their conclusion instead of a full transcript, leaving far more room before a long task fills up.

**1.0.3**

- Every code review now also flags unclear names - vague, misleading, or wrongly scoped - judged on their own terms.
- Code reviews now call out unstated assumptions: the inputs, ordering, and environment premises code relies on but never guards.

**1.0.2**

- Reporting a bug now drops you straight into a fix instead of a separate diagnosis track.
- Discussion mode lays out options with worked examples and asks the single question that matters, without touching your code.
- Throwaway prototypes skip the full review pass, running only the checks that matter for sandbox code.

**1.0.0**

- The workflow no longer sorts your task into a fixed size tier and runs a preset list of steps. It composes exactly the stages your task needs and reshapes them as the work reveals itself.
- New lightweight modes: drop into discussion or throwaway prototyping without the full build pipeline, and slide back into building when you're ready.
- Tests come first - implementation code can't be written until failing tests exist and have been checked against what you actually asked for.
- You can see what's about to run and why, and you're interrupted only when your answer would change the outcome.

**0.3.6**

- When the workflow asks you to decide something, each option shows a concrete example of what it produces.

**0.3.5**

- After compacting a long conversation, your task's state comes back intact.

Full history in [CHANGELOG.md](CHANGELOG.md).

## Install

In Claude Code:

```
/plugin marketplace add alp82/alp-river
/plugin install alp-river@alperortac
/reload-plugins
```

To pull updates later:
```
/plugin marketplace update alperortac
/reload-plugins
```

The pointer resolves to the plugin's installed path. If your setup restricts file reads, allow the agent to read the plugin's doctrine - on a standard install add `Read(~/.claude/plugins/cache/alperortac/alp-river/**)` to your `.claude/settings.json` allowlist.

## How to use

Describe what you want - in plain text, or via `/alp-river:go` if you want a discoverable trigger. Both run the same workflow; the essentials load automatically and the full doctrine is one read away, nothing to enable.

`triage` reads your request first and picks one of **three paths** - `build`, `spike` (throwaway prototype), or `talk` (discuss, no code) - plus the opening signals; a bug is a `build` with a `bug` signal, not its own path. The router composes a route from there and recomposes as stages publish what they find: discover no email infra and a research + prototype stage join; a plan that signs tokens pulls in a security review. Size (XS-XXL) is just a readout of how many stages the route ended up with.

You stay in the loop only at decisions that could change the outcome:

- **Intent** - when the request is clear, the workflow states its one-line read and proceeds (correct it in your next message if it's off). When it's genuinely ambiguous, the interviewer joins and loops with you until intent settles.
- **Clarifier questions** - the clarifier researches the codebase first, then asks only what's still open.
- **Design picker** - for UI work with multiple legitimate shapes, the design-explorer builds an interactive page and waits for you to paste a chosen spec back.
- **Cost / plan / stop gates** - fire when the route crosses into expensive territory or a plan is ready, never as fixed ceremony.

Everything else runs to convergence: the route is done when no signal triggers an unrun stage and every review lens is clean. Reviewer findings feed the fixer automatically.

## How the river flows

```mermaid
flowchart LR
    req([request]) --> triage
    triage -->|path + signals| router{router composes}
    router -->|next stage| stage[run a stage]
    stage -->|publishes signals + artifacts| router
    router -->|nothing left to trigger,\nall lenses clean| done([converged])
```

The router is deterministic code (`hooks/route.py`): membership is a stage's `subscribes` topics matched against the live signals (any one triggers it), filtered to the live path by each stage's `routes`; order is a topological sort of the `input`/`output` artifact dependencies. The catalog it reads (`generated/catalog.json`) is compiled from each agent's `stage:` frontmatter by a save-time hook. The judgment lives in the stages - `triage` frames, `prototype-identifier` flags novelty, each stage classifies its own findings - so the router never has to reason, just route.

A SessionStart hook injects a small essentials block plus a pointer to `WORKFLOW.md`; the agent reads the full doctrine on demand. After `/compact`, it re-anchors that pointer and restores the canonical run state (route, live signals, available artifacts, premises) so the router resumes deterministically.

Two rules never bend: **precedence** (a stage can't run before the artifacts it needs exist) and **asymmetric rigor** (skipping a stage needs a positive signal; adding one needs only doubt - safety stages stay in by default).

## Agents

40 composable stages plus a setup command, grouped by role. Each declares its routes and data/signal contract in frontmatter (see `doctrine/CATALOG.md`, `doctrine/SIGNALS.md`).

### Seed and intent
| Agent | Model | Role |
|-------|-------|------|
| triage | haiku | Always-on seed. Reads the request, publishes the path and opening signals (ambiguous, novel-domain, bug, risk sniffs, advisory est-size). |
| interviewer | opus | Probes scope, users, and success criteria when the request is ambiguous; loops until intent settles. |
| requirements-clarifier | opus | Surfaces ambiguity, edge cases, and proposed acceptance criteria before planning. |

### Pre-flight
| Agent | Model | Role |
|-------|-------|------|
| reuse-scanner | sonnet | Finds reusable code and quick-win refactors; flags missing infra and duplication. |
| health-checker | haiku | Scores code-health of the touched area, surfaces cleanup targets. |
| prototype-identifier | haiku | Flags external-API / SDK novelty; on high novelty, suggests two shapes to try. |
| researcher | haiku | Pulls library / framework / domain knowledge from the web. |
| prototyper | sonnet | Builds tracer-bullet prototypes in `.prototypes/` for high-novelty surface. |

### Design and plan
| Agent | Model | Role |
|-------|-------|------|
| design-explorer | opus | For UI tasks with multiple legitimate shapes: builds an interactive picker, binds the pasted-back spec. |
| planner | opus | Designs the blueprint; on multi-approach, presents 2-3 with a recommendation. |
| plan-challenger | opus | Adversarial review - holes, failure modes, simpler alternatives. |

### Tests (TDD-first)
| Agent | Model | Role |
|-------|-------|------|
| test-plan | sonnet | Derives concrete test cases from the plan's acceptance criteria. |
| test-author | sonnet | Writes the failing (red) tests before implementation. |
| test-review | opus | Validates the red tests against intent so code can't be written to the wrong tests. |
| test-gap | sonnet | Always-on coverage lens; pulls test-author back for untested behavior. |
| test-verifier | sonnet | Runs the suite and gates green. |

`implement` lists a green-light as an `input`, so the precedence graph forbids code before it exists. On a logic change only `test-review` mints that green-light, and only after validating the red tests - TDD is structural, not a guideline.

### Build, review, heal, capture
| Agent | Model | Role |
|-------|-------|------|
| implementer | opus | Executes the approved plan. Can kick back to the planner; the oscillation guard stops it from looping. |
| correctness / quality / acceptance / plan-adherence / naming-clarity / assumptions | sonnet/opus | Broad review lenses on every diff (`@diff -> @findings`). |
| structure / architecture / consistency / reuse / security / performance / accessibility / design-consistency / ux / visual-verifier | sonnet/opus | Specialist lenses, triggered by domain signals (security is `sticky`). |
| fixer | opus | Applies targeted fixes and reruns the lenses it touched until they're clean. |
| capture-agent | opus | Proposes glossary / stack / intent updates surfaced during the run, writes after approval. |

### Other paths and entry points
| Agent | Model | Role |
|-------|-------|------|
| discuss | opus | The `talk` path - lays out options with worked examples, surfaces tradeoffs, asks one sharp question; never writes code. |
| spike-build | sonnet | The `spike` path - builds throwaway runnable code in `.prototypes/` with relaxed ceremony. |
| investigator | opus | Root-cause debugging inside the `build` path (pulled in by a `bug` signal) - hypothesizes, repros, traces; stops at diagnosis. |
| adr-drafter | opus | Drafts a single ADR from a decision summary. Used by `/alp-river:adr`. |
| setup-agent | opus | Command-only (not a route stage). Bootstraps `docs/` via a guided interview. Used by `/alp-river:setup`. |

## Slash commands

```
/alp-river:go           Run the workflow. Triage routes; the router composes the stages it needs.
/alp-river:setup        Interactive bootstrap of docs/INTENT.md, docs/STACK.md, docs/GLOSSARY.md
/alp-river:adr          Draft and write a single architectural decision record
/alp-river:review       Review current changes for correctness + engineering quality
/alp-river:verify       Visual verification of UI changes
/alp-river:reflect      Reflect on the current session to surface workflow friction worth tuning
```

## Structure

```
alp-river/
├── .claude-plugin/plugin.json
├── WORKFLOW.md            <- router-loop doctrine
├── doctrine/
│   ├── CATALOG.md         <- stage frontmatter schema
│   └── SIGNALS.md         <- the controlled signal vocabulary
├── generated/catalog.json <- compiled stage catalog (tracked; the router reads it)
├── hooks/
│   ├── route.py           <- deterministic router
│   ├── gen-catalog.py     <- compiles agent frontmatter into the catalog
│   └── *.sh               <- inject-workflow, auto-format, context injection, ...
├── agents/                <- 40 stage definitions + setup-agent
├── commands/              <- 6 slash commands
└── templates/             <- copy into your project's docs/ for project-context injection
```

## Local development

Clone the repo and pass `--plugin-dir`:

```bash
git clone https://github.com/alp82/alp-river.git
claude --plugin-dir ./alp-river
```

## Author

Alper Ortac &middot; [x.com/alperortac](https://x.com/alperortac)
