---
description: Manually draft and write an architectural decision record.
argument-hint: Decision title and a one-line summary (e.g. "use HTTP-only cookies for auth - rules out JWT-in-localStorage")
---

# ADR Pipeline

Manual entry: `$ARGUMENTS`

Use this when you want to record a decision deliberately. Four steps - confirm input, draft, present, write.

## Step 1: Confirm input

Parse `$ARGUMENTS` into a title and a one-sentence summary. If either is missing or ambiguous, ask the user one question to resolve it - keep this short. Do NOT enter the interview loop here; this is a deliberate entrypoint and the user has already framed the decision.

If `docs/adr/` does not exist:
- If `docs/` itself is missing: tell the user "docs/ not found - run `/alp-river:setup` first to bootstrap project context, then re-run this command." **STOP.**
- If `docs/` exists but `docs/adr/` does not: create `docs/adr/` (mkdir). One write, no scaffolded files.

Capture:
- `<DECISION_TITLE>` - the short title.
- `<DECISION_SUMMARY>` - 1-3 sentences capturing the choice and the constraint it locks in.
- `<SOURCE>` - "manual /alp-river:adr entry by user on {today YYYY-MM-DD}".
- `<EXTRA_CONTEXT>` - if the user supplied anything beyond title + summary, include it here verbatim; else "none".

## Step 2: Draft

Launch `adr-drafter` (opus, read-only) with the four input slots. Handle VERDICT:

- `drafted` → continue to Step 3 with `DRAFT` and `PROPOSED_FILENAME` slug.
- `rejected` → surface `ADR_REJECTED` to the user (reason, conflicting ADR path, recommendation). Stop - this command exits without writing. The user can edit the existing ADR manually or re-run with a re-framed title.

## Step 3: Present and write

Show the user the full DRAFT body (frontmatter + four sections), readable as the final file content, plus the proposed path: `docs/adr/NNNN-{kebab-title}.md` where `NNNN` is the next free 4-digit sequence (computed from `docs/adr/*.md` excluding `0000-template.md`).

Ask: `accept | edit | reject`.

- `accept` → write the DRAFT body verbatim. Replace literal `NNNN` in the H1 with the resolved number.
- `edit` → take the user's edited body and write that, with the same `NNNN` replacement.
- `reject` → skip the write.

## Step 4: Summarize

Report:

- ADR created (or rejected/skipped, with reason)
- Path: `docs/adr/NNNN-{kebab-title}.md`
- Status: proposed
- Source: manual entry

End with the literal line `<!-- pipeline-complete -->`.
