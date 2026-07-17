<div align="center">

# forge

## Plan · attack the plan · build test-first · review in crossfire

[![Stars, Forks, Open Issues and License](https://shieldcn.dev/group/github/stars/alp82/forge+github/forks/alp82/forge+github/open-issues/alp82/forge+github/license/alp82/forge.svg?variant=secondary)](https://github.com/alp82/forge)

[![Claude Code](https://shieldcn.dev/badge/Claude-Code-D97757.svg?logo=anthropic&variant=branded&size=lg)](https://claude.com/claude-code)
[![Skills](https://shieldcn.dev/badge/Skills-first-D97757.svg?logo=anthropic&variant=outline&size=lg)](skills/forge/SKILL.md)
[![Version](https://shieldcn.dev/badge/version-2.0.3-D97757.svg?variant=outline&size=lg)](CHANGELOG.md)

<br>

A code-change workflow for Claude Code. Your request gets planned, the plan gets attacked, the code gets written with tests, and a panel of reviewers shoots at it before you ever see it.

**Site:** [alp82.github.io/forge](https://alp82.github.io/forge/) — live demos: the full run, every stage, the crossfire wave

**Featured in:** [Alper Ortac's AI Stack](https://aistack.to/stacks/alper-ortac-unw0sl)

</div>

---

## Install

```
/plugin marketplace add alp82/forge
/plugin install forge@alperortac
/forge:setup-forge
```

The setup runs once, plugin-prefixed; it installs the bare command names, so from then on it's `/setup-forge` everywhere. Plugin updates propagate on their own — no re-run needed.

Upgrading from alp-river? Three steps in the [2.0.0 changelog entry](CHANGELOG.md).

> [!TIP]
> Run the main session on a top-tier model at high effort. The orchestrator drives every routing decision, so a weaker main model degrades the whole pipeline.

## Use

One verb. Describe the change you want in your own words.

```
/forge add rate limiting to the public API
/forge #482                    # or point it at a ticket
/crossfire                     # review what's already there
```

## See it run

<!-- MEDIA SLOT: hero cast | source: demo/playbooks/hero.play → demo/casts/hero.cast → agg | regen: demo/build.sh -->

![A full forge run: plan attacked, tests reviewed, crossfire wave, fix](docs/assets/forge-hero.gif)

Per-stage micro-casts and the standalone crossfire wave play on [the site](https://alp82.github.io/forge/).

## What happens

| Stage | What it does |
|-------|--------------|
| triage | Sizes the request and detects what's missing: unknowns get interviewed, unproven externals get prototyped, missing knowledge gets researched, a bug gets diagnosed before anything is built. |
| plan | Writes the approach to a file, not the chat — the next stage reads a document, and a fresh agent can pick it up after compaction. |
| challenge | A second agent tries to break the plan before a line is written. Cheapest possible place to be wrong. |
| tests | Writes the red tests first, aimed at the behavior the request asked for — then a second agent hunts for false green: the test that passes with the feature deleted, the mock asserting on itself. Code waits until the tests prove something. |
| implement | Makes the change against the surviving plan and turns the tests green. |
| crossfire | Independent reviewers hit the diff at once, each carrying one lens, blind to the others. Also runs standalone as `/crossfire` on any diff, branch, or file set. |
| fix | Works the findings until the diff survives a clean re-run of the wave. |

With a worker CLI on PATH (codex, gemini, opencode), the challenge and the crossfire wave each get a different-model second opinion — read-only, failure visible, never blocking.

## It can't skip the review

Prompts get forgotten under compaction; hooks don't. Forge ships six of them. If code changed and the review never ran, the session refuses to end.

## It's just markdown

No agent definitions, no config language, no signal vocabulary. Every stage is a markdown file you can read in one sitting and edit with your own opinions — start at [`skills/forge/SKILL.md`](skills/forge/SKILL.md). The plugin is a delivery mechanism, nothing more.

## Works with your tracker

Point `/forge` at a ticket and it reads the ticket as the request, then posts the verdict back and closes it. No tracker? Nothing is missing — the contract lies dormant.

---

Contributing / internals → [CONTRIBUTING.md](CONTRIBUTING.md)

---

## ✍️ Author

Alper Ortac &middot; [x.com/alperortac](https://x.com/alperortac)
