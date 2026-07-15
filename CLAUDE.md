# alp-river

Project-specific rules for this plugin repo. The pipeline workflow lives in `WORKFLOW.md`. Global rules live in `~/.claude/CLAUDE.md`. This file does not ship to consumers - Claude Code only loads CLAUDE.md from the user's working directory.

## Versioning

Plugin version lives in `.claude-plugin/plugin.json`. The same version is mirrored in `.claude-plugin/marketplace.json` and in the `Version` badge at the top of `README.md` - bump all three together, always.

- **Patch bump** after a successful task when the workflow itself changes: anything under `agents/`, `commands/`, `hooks/`, or `WORKFLOW.md`. Same trigger: add a `CHANGELOG.md` entry, and update `README.md` if the public surface description shifts.
- **No bump** for doc-only changes (README, CHANGELOG, CLAUDE.md, comment polish). `marketplace.json` listing edits (description, keywords) are metadata, not workflow.
- **Minor and major** are manual. Don't auto-bump.

## CHANGELOG style

See `WORKFLOW.md` § "Changelog Style" - one canonical home for the rules.

## Doctrine hygiene

Before adding an instruction anywhere under `agents/`, `doctrine/`, `commands/`, `hooks/`, or `WORKFLOW.md`, run a three-check meta-rule:

1. **Does an existing channel or slot already carry this?** If a map, contract, or section already owns the fact, extend it not restate - one home, not a second copy somewhere a reader will diverge from.
2. **Is the fact defined exactly once?** A rule repeated across files drifts: one copy gets edited, the other rots. Pick the canonical home and cross-reference it ("See doctrine/...") from anywhere else that needs to point at it.
3. **Does a cheap canary protect it?** A load-bearing literal earns a short pinned phrase the self-audit watches, so deleting or rewording it past recognition trips the doctrine-integrity check instead of silently rotting.

This rule binds this repo's own changes - it governs how alp-river is authored, not anything shipped to a consumer. Its teeth are exactly two: the self-audit's doctrine-hygiene lens (which flags an instruction line duplicated verbatim across `agents/`/`doctrine/`) plus author discipline at edit time. CLAUDE.md itself is neither shipped nor injected into any agent, so nothing enforces this for you automatically - the lens catches cross-file duplication after the fact, and the rest is the author honoring the three checks above.

## Leitwort usage

A leitwort is a leading word: a short, memorable phrase an agent restates in its own reasoning to steer its own behavior. When authoring an agent or doctrine stage, anchor its core stance on one, and prefer a phrase with trained lineage the model already carries ("deletion test", "tracer bullet", "test seams", "YAGNI ladder", "name the danger") over a coined one.

1. **Anchor over enumerate.** Give a stage one named leitwort and let its checklist of concerns hang off that anchor as supporting detail; a flat list with no anchor is the weakest form.
2. **Reinforce it.** A leitwort used once is inert. Recur it at the points where the agent acts - the anchors woven through `agents/plan-challenger.md` and `agents/discuss.md` are the canonical example.
3. **One concept, one name.** Naming the same idea two ways across stages dilutes both; pick the canonical phrase and reuse it verbatim.
4. **Keep it earned.** A job that reads fine as a literal instruction stays literal; a forced or fluffy coinage with no trained association tickles nothing and just spends words.

## Agent skills

### Issue tracker

Issues live in the `alp82/alp-river` GitHub repo, managed via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles use their default label strings. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
