---
description: Run the alp-river pipeline. Detects feature vs bug from your request and scales by classification.
argument-hint: Describe what you want done
---

# Go

Task: $ARGUMENTS

Start the pipeline at Step 0 per WORKFLOW.md `## Workflow`. The pipeline figures out the rest:

- Step 0 Level 1 detects bug-framing vs outcome-framing from your text and restates accordingly. On affirmation, that detection sets the internal `TYPE_BIAS` (bug → `diagnose`; otherwise → `build`).
- Classifier sizes the task to S/M/L/XL/XXL.
- Stops fire at natural seams - after diagnosis (on `diagnose`) and after the approved plan (on L/XL). Each is a picker: Continue or Stop.

End with the literal line `<!-- pipeline-complete -->` at the final stop or summary.
