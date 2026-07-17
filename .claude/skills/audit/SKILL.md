---
name: audit
description: Self-audit this repo's skill-first shape - hook suite, word budgets, cross-file duplication, dangling brief paths, version mirrors - and report a scorecard with top fixes
disable-model-invocation: true
---

# Self-audit

Run the deterministic checks below and report a scorecard. Every check is a command whose output decides — no judgment calls, no prose scoring.

## Checks

1. **Hook suite & release gate** — `python3 -m pytest hooks/tests -q` from the repo root. Green = pass; a failure names its own fix.
2. **Word budgets** — every `skills/**/*.md` and `.claude/skills/**/*.md` fits one read: ~865-word target, 2,000-word hard ceiling. `wc -w` each file; over ceiling = fail, over target = warn. List offenders with their counts.
3. **Doctrine hygiene** — no instruction line duplicated verbatim across skill files (the enforcement half of CLAUDE.md's three-check meta-rule). Normalize lines (trim whitespace; drop blanks, headings, fences, and table rows), keep lines ≥ 40 characters, and flag any line appearing in more than one file. Duplication = fail, naming both files.
4. **Dangling brief paths** — every brief a SKILL.md or brief references as a `NAME.md` / `../dir/NAME.md` sibling path exists on disk, resolved relative to the referencing file. A missing target = fail.
5. **Version mirrors** — `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` `metadata.version`, and the README version badge agree (also pinned by the pytest gate). Report the three values.

## Report

1. **Overall** — categories passed / total.
2. **Categories** — one line each: pass / warn / fail, with the evidence count (files over budget, duplicated lines, missing paths).
3. **Top fixes** — the concrete fix per failing category, worst first. If nothing fails, state that all categories are clean.
