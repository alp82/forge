---
description: Run the alp-river pipeline. Triage routes the request; a deterministic router composes the stages it needs.
argument-hint: Describe what you want done
---

# Go

Task: $ARGUMENTS

Run the composed-route pipeline per WORKFLOW.md `## Pipeline`. The router figures out the rest:

- `triage` reads your request, picks the path (build / spike / talk) and seeds the opening signals (a bug is a `build` with a `bug` signal, not its own path).
- The deterministic router (`hooks/route.py`) assembles the stages your task needs and recomposes as it learns more - growing on discovered signals, shrinking when they clear.
- Gates fire only at decisions that could change the outcome. Size (XS-XXL) is a readout of the assembled route, not a setting.

End with the literal line `<!-- pipeline-complete -->` at the final stop or summary.
