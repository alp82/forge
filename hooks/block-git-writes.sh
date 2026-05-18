#!/usr/bin/env bash
# PreToolUse hook: git write operations are user-only.
# Parses Bash tool input and blocks git commands that modify state.
# Logs blocked attempts to ~/.claude/debug/git-block.log (rotated at ~1MB).

set -euo pipefail

log_file="$HOME/.claude/debug/git-block.log"
mkdir -p "$HOME/.claude/debug" 2>/dev/null || true

if [ -f "$log_file" ] && [ "$(stat -c%s "$log_file" 2>/dev/null || echo 0)" -gt 1048576 ]; then
  tail -c 524288 "$log_file" > "${log_file}.tmp" 2>/dev/null && mv "${log_file}.tmp" "$log_file"
fi

log() {
  echo "[$(date -Iseconds)] $*" >> "$log_file" 2>/dev/null || true
}

# Emit a block decision without relying on jq — used on fail-closed paths
# where jq itself may be unavailable or broken. The reason must be a JSON-safe
# static string (no unescaped quotes, backslashes, or newlines).
block_static() {
  local reason="$1"
  log "BLOCKED (fail-closed): $reason"
  printf '{"decision":"block","reason":"%s"}\n' "$reason"
  exit 0
}

# Fail closed if jq is missing — without it we can't safely distinguish Bash
# from other tool calls, so we don't know whether to inspect the command.
if ! command -v jq &>/dev/null; then
  block_static "git-write guard requires jq (not installed on PATH). Install jq or run git commands yourself."
fi

input=$(cat)

# Fail closed if jq cannot parse the hook input.
if ! tool_name=$(echo "$input" | jq -r '.tool_name // empty' 2>/dev/null); then
  block_static "git-write guard could not parse hook input (jq error). Run the command yourself or report this."
fi

# Only evaluate Bash tool calls
if [ "$tool_name" != "Bash" ]; then
  exit 0
fi

if ! command=$(echo "$input" | jq -r '.tool_input.command // empty' 2>/dev/null); then
  block_static "git-write guard could not parse Bash command from hook input. Run the command yourself or report this."
fi

if [ -z "$command" ]; then
  exit 0
fi

# Match git write verbs at subcommand boundaries.
# The leading class excludes word characters, path separators, and hyphens so
# `echo "git add"` (git after a quote) still matches (intentionally conservative),
# but `foogit add` (no boundary) does not.
blocked_verbs='(^|[^[:alnum:]_/-])git[[:space:]]+(add|commit|push|cherry-pick|rebase|reset|merge|revert|restore|rm|mv|stash|apply|am|clean|pull)([[:space:]]|$)'
# `git tag <name>` (create) and `git tag -d`/`-a`/`-s`/`-f` (create/delete/sign/force)
blocked_tag='(^|[^[:alnum:]_/-])git[[:space:]]+tag[[:space:]]+([^-[:space:]]|-[adsfm])'
# `git branch -D|-d|-m|-M` (delete/rename)
blocked_branch='(^|[^[:alnum:]_/-])git[[:space:]]+branch[[:space:]]+-[DdmM]'
# `git checkout -- <path>` (discard working-tree changes)
blocked_checkout='(^|[^[:alnum:]_/-])git[[:space:]]+checkout[[:space:]]+--[[:space:]]'

if echo "$command" | grep -qE "$blocked_verbs|$blocked_tag|$blocked_branch|$blocked_checkout"; then
  log "BLOCKED: $command"
  reason="Git write operations are user-only (see the alp-river plugin workflow and your project memory feedback). Blocked command: ${command}. If the user explicitly wants this run, surface the exact command for them to execute themselves."
  jq -nc --arg reason "$reason" '{decision:"block", reason:$reason}'
  exit 0
fi

exit 0
