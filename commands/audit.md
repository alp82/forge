---
description: Self-audit the alp-river plugin and report a health scorecard with top fixes
argument-hint: (none)
---

# Self-Audit

Run the deterministic self-audit and present its scorecard. All scoring lives in the hook;
this command only runs it and renders the result.

## Process

Run `python3 hooks/audit.py` from the plugin root. It prints a human scorecard followed by
a `SCORECARD_JSON` line. Parse that line: find the line starting with `SCORECARD_JSON ` and
`json.loads` the remainder.

## Report

1. **Overall** - the `overall` score out of 100.
2. **Categories** - each of the five categories with its score, sorted by name.
3. **Top fixes** - the `top_fixes` list verbatim, worst-scoring category first. If empty,
   state that all categories are clean.
