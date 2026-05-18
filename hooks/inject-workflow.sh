#!/usr/bin/env bash
# SessionStart hook: injects alp-river's WORKFLOW.md into the session as foundational context.
# The plugin lives wherever Claude Code mounts it; ${CLAUDE_PLUGIN_ROOT} resolves to that path.

set -euo pipefail

workflow_file="${CLAUDE_PLUGIN_ROOT}/WORKFLOW.md"

if [[ ! -f "$workflow_file" ]]; then
  exit 0
fi

workflow=$(cat "$workflow_file")

jq -n --arg ctx "$workflow" '{
  hookSpecificOutput: {
    hookEventName: "SessionStart",
    additionalContext: $ctx
  }
}'
