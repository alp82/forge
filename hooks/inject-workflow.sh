#!/usr/bin/env bash
# SessionStart hook: injects a small workflow-essentials block plus a pointer to
# alp-river's WORKFLOW.md (the full doctrine) into the session as foundational
# context. The agent reads the full file on demand.
# The plugin lives wherever Claude Code mounts it; ${CLAUDE_PLUGIN_ROOT} resolves to that path.

set -euo pipefail

# Self-locate so the dev-tree hook always gets the dev-tree helper, regardless of
# what CLAUDE_PLUGIN_ROOT points at in a session.
hook_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${CLAUDE_PLUGIN_ROOT:="$(cd "${hook_dir}/.." && pwd)"}"

workflow_file="${CLAUDE_PLUGIN_ROOT}/WORKFLOW.md"

if [[ ! -f "$workflow_file" ]]; then
  exit 0
fi

helper="${hook_dir}/workflow-anchor.sh"
[ -f "$helper" ] || exit 0
source "$helper"

context=$(workflow_anchor)

emit_session_context "$context"
