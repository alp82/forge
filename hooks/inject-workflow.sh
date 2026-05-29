#!/usr/bin/env bash
# SessionStart hook: injects a small workflow-essentials block plus a pointer to
# alp-river's WORKFLOW.md (the full doctrine) into the session as foundational
# context. The agent reads the full file on demand. Also injects a setup nudge
# when the project lacks docs/INTENT.md and the user hasn't opted out via
# alpRiver.skipSetup in .claude/settings.local.json.
# The plugin lives wherever Claude Code mounts it; ${CLAUDE_PLUGIN_ROOT} resolves to that path.

set -euo pipefail

workflow_file="${CLAUDE_PLUGIN_ROOT}/WORKFLOW.md"

if [[ ! -f "$workflow_file" ]]; then
  exit 0
fi

helper="${CLAUDE_PLUGIN_ROOT}/hooks/workflow-anchor.sh"
[ -f "$helper" ] || exit 0
source "$helper"

input=$(cat 2>/dev/null || true)
project_cwd=$(echo "$input" | jq -r '.cwd // empty' 2>/dev/null || true)
[ -z "$project_cwd" ] && project_cwd="$PWD"

context=$(workflow_anchor)

# Setup nudge: project lacks docs/INTENT.md and user hasn't opted out.
intent_file="$project_cwd/docs/INTENT.md"
settings_file="$project_cwd/.claude/settings.local.json"

skip_setup="false"
if [ -f "$settings_file" ]; then
  skip_setup=$(jq -r '.alpRiver.skipSetup // false' "$settings_file" 2>/dev/null || echo "false")
fi

if [ ! -f "$intent_file" ] && [ "$skip_setup" != "true" ]; then
  nudge=$(cat <<'EOF'


## Setup nudge

Project context missing: no `docs/INTENT.md` in this project. Consider running `/alp-river:setup` before kicking off work - planning and review run with your intent, stack, and glossary loaded. Dismiss permanently with `"alpRiver": {"skipSetup": true}` in `.claude/settings.local.json`.
EOF
)
  context+="$nudge"
fi

emit_session_context "$context"
