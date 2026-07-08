---
description: Review specified files for quality, bugs, duplication, and dead code
argument-hint: Space-separated file paths to review
---

# Code Review

Files to review: $ARGUMENTS

If `$ARGUMENTS` is empty, ask the user which files to review and stop.

## Process

**Memory**: Apply WORKFLOW.md "Subagent Context Inheritance" to both reviewer calls below.

Launch concurrently with `<TOUCHED_FILES>` set to the file paths above and `<APPROVED_PLAN>: none`:
- `correctness-reviewer` - bugs, type holes, dead code, convention adherence
- `shape-reviewer` - module shape: depth, seams, decomposition, layers, wrong tool - anchored on the deletion test
- `conventions-reviewer` - codebase-pattern consistency, naming clarity, and reuse, compared against existing examples

## Report

Present each reviewer's output verbatim under its own heading - full `VERDICT`, `FINDINGS`, `ACTION_NEEDED`, (for correctness) `OBSOLETE_CODE`, (for shape) `MODULES_ASSESSED`, and (for conventions) `EXAMPLES_COMPARED`. Do not reformat or summarize the findings themselves.

Then append:

1. **Bottom line** - one sentence on the change's overall state, calling out the worst verdict across the three reviewers.
2. **Next command** -
   - Both `pass` → done.
   - Any `warn` → name the one or two issues worth addressing.
   - Any `fail` → suggest `/alp-river:go`, point at the relevant `ACTION_NEEDED`.
