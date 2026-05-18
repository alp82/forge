---
description: Visual verification of UI changes using playwright-cli screenshots
argument-hint: URL or component to verify (required)
---

# Visual Verification

Target: $ARGUMENTS

If `$ARGUMENTS` is empty, ask the user for a target URL or component and stop.

**Memory**: Prepend `USER_CONTEXT` to `visual-verifier` per WORKFLOW.md §"Subagent Context Inheritance".

Launch the `visual-verifier` agent with:
- `<TARGET>` - the value of `$ARGUMENTS`.
- `<CONFIRMED_INTENT>` - a short restatement of why this is being verified (from the user's prior request, or "ad-hoc visual verification" for one-shot use).
- `<TOUCHED_FILES>` - any UI files the user named, or "ad-hoc - no specific touched files".

Report the results and display any screenshots taken.
