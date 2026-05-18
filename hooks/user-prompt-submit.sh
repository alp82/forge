#!/usr/bin/env bash
# UserPromptSubmit hook: nudge Claude to re-classify follow-up requests
# after the pipeline has completed in the conversation.
#
# Trigger: Claude's pipeline commands write `<!-- pipeline-complete -->` at
# the end of their Step 6 summary. This hook greps for it in recent transcript
# lines. If found, it injects a classification reminder into Claude's context.

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

# Grep the tail of the transcript for the pipeline-complete marker
if tail -40 "$transcript_path" 2>/dev/null | grep -qF '<!-- pipeline-complete -->'; then
  cat <<'JSON'
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "FOLLOW-UP REMINDER: a pipeline completed in this conversation. This new request is a NEW TASK - per WORKFLOW.md 'Follow-up Requests', run the pipeline in WORKFLOW.md ## Pipeline directly. Intent confirmation is mandatory on every tier, including S: restate the outcome in 1-2 sentences and WAIT for the user. On an affirmation (y/yes/correct/proceed/looks right), continue. On any non-affirmation reply (free text, additions, corrections), treat as reshape and spawn the interviewer with that reply as the new RAW_REQUEST. The pipeline self-adapts to whatever tier the classifier returns - no command dispatch needed; the main agent orchestrates from WORKFLOW.md."}}
JSON
fi

exit 0
