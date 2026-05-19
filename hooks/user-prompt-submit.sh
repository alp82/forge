#!/usr/bin/env bash
# UserPromptSubmit hook: nudge Claude to enter the pipeline before editing code.
#
# Two branches, gated on whether the pipeline has run in this conversation:
#   - Pipeline-complete marker present (follow-up request) -> re-classify reminder.
#   - No marker yet (fresh session or pre-pipeline prompt) -> entry reminder so
#     non-trivial prompts can't pattern-match "small/mechanical" into "skip the
#     pipeline" and go straight to Edit/Write.
#
# Trigger: Claude's pipeline commands write `<!-- pipeline-complete -->` at
# the end of their Step 6 summary. This hook greps for it in recent transcript
# lines to pick which reminder to inject.

set -euo pipefail

input=$(cat)
transcript_path=$(echo "$input" | jq -r '.transcript_path // empty' 2>/dev/null)
prompt=$(echo "$input" | jq -r '.prompt // empty' 2>/dev/null)

# Skip trivial follow-ups ("ok", "thanks", "yes") - the rule is for real requests
if [ "${#prompt}" -lt 20 ]; then
  exit 0
fi

# Need a transcript to detect pipeline completion
if [ -z "$transcript_path" ] || [ ! -f "$transcript_path" ]; then
  exit 0
fi

# Grep the tail of the transcript for the pipeline-complete marker; pick branch.
if tail -40 "$transcript_path" 2>/dev/null | grep -qF '<!-- pipeline-complete -->'; then
  cat <<'JSON'
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "FOLLOW-UP REMINDER: a pipeline completed in this conversation. This new request is a NEW TASK - per WORKFLOW.md 'Follow-up Requests', run the pipeline in WORKFLOW.md ## Pipeline directly. Intent confirmation is mandatory on every tier, including S: restate the outcome in 1-2 sentences and WAIT for the user. On an affirmation (y/yes/correct/proceed/looks right), continue. On any non-affirmation reply (free text, additions, corrections), treat as reshape and spawn the interviewer with that reply as the new RAW_REQUEST. The pipeline self-adapts to whatever tier the classifier returns - no command dispatch needed; the main agent orchestrates from WORKFLOW.md."}}
JSON
else
  cat <<'JSON'
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "PIPELINE ENTRY: code-modifying prompts (edit, add, fix, refactor, rename, even one-liners) invoke `/alp-river:go` BEFORE any Edit/Write - never skip because the request feels small or mechanical. Pure conversation (questions, explanations, status checks) skips the pipeline. When in doubt, invoke `/alp-river:go` - the classifier sizes trivial cases at S cheaply."}}
JSON
fi

exit 0
