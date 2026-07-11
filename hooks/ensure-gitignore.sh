#!/usr/bin/env bash
# SessionStart hook (startup / resume): keep the plugin's transient .alp-river/
# artifacts directory out of version control. It does two independent things:
#   1. Idempotently appends ".alp-river/" to the repo-root .gitignore when no
#      matching line exists (creating the file if absent).
#   2. If .alp-river is already tracked by git, it injects a turn-1 instruction
#      telling the agent to surface the exact untrack command for the user to
#      run - it NEVER runs `git rm` itself (git rm is user-only, per the
#      git-write guard in block-git-writes.sh).
#
# STDOUT-PURE: emits only the legal hookSpecificOutput JSON (via the sourced
# emit_session_context) or nothing. ALWAYS exits 0; never crashes, never
# non-zero. All writes are guarded with || true.

set -uo pipefail  # -e omitted: this hook MUST exit 0; grep/git ls-files non-zero exits are normal control flow.

# Source the co-located workflow-anchor.sh so the dev-tree hook always gets the
# dev-tree helper, regardless of what CLAUDE_PLUGIN_ROOT points at in a session.
hook_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
helper="${hook_dir}/workflow-anchor.sh"
[ -f "$helper" ] || exit 0
source "$helper"

# Default CLAUDE_PLUGIN_ROOT so it resolves correctly when running directly (tests).
: "${CLAUDE_PLUGIN_ROOT:="$(cd "${hook_dir}/.." && pwd)"}"

input=$(cat 2>/dev/null || true)

# .cwd // empty with $PWD fallback.
project_cwd=$(echo "$input" | jq -r '.cwd // empty' 2>/dev/null || true)
[ -z "$project_cwd" ] && project_cwd="$PWD"

# Not a git work tree -> exit 0, silent.
git -C "$project_cwd" rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
root=$(git -C "$project_cwd" rev-parse --show-toplevel 2>/dev/null || true)
[ -n "$root" ] || exit 0

context=""

# Block 1: idempotent .gitignore append.
gitignore="${root}/.gitignore"
if [ -f "$gitignore" ] && grep -qE '^[[:space:]]*/?\.alp-river/?[[:space:]]*$' "$gitignore"; then
  : # already present; do nothing.
else
  # Trailing-newline safety: if the file exists, is non-empty, and its last byte
  # is not a newline, add a newline before appending the standalone line.
  if [ -s "$gitignore" ] && [ -n "$(tail -c 1 "$gitignore" 2>/dev/null || true)" ]; then
    printf '\n' >> "$gitignore" || true
  fi
  printf '.alp-river/\n' >> "$gitignore" || true
  context="## .gitignore updated"$'\n\n'"Added \`.alp-river/\` to \`${gitignore}\` so this tool's transient artifacts directory stays out of version control."
fi

# Block 2: tracked detection.
if [ -n "$(git -C "$root" ls-files -- .alp-river 2>/dev/null || true)" ]; then
  instruction="## .alp-river is tracked by git"$'\n\n'"The \`.alp-river\` directory holds transient plan artifacts and should not be committed. On turn 1, before anything else, tell the user and surface this exact command for them to run (do not run it yourself; git rm is user-only): \`git rm -r --cached .alp-river && git commit -m \"chore: stop tracking .alp-river artifacts\"\`. If this context was compacted away, ignore it silently."
  if [ -n "$context" ]; then
    context="${context}"$'\n\n'"${instruction}"
  else
    context="$instruction"
  fi
fi

[ -n "$context" ] && emit_session_context "$context"
exit 0
