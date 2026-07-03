#!/usr/bin/env bash
# PreToolUse hook: block the dangerous, allow the forward.
# Parses Bash tool input and blocks git commands that rewrite or destroy
# history/state, while letting the forward ship ops (add/commit/plain push)
# through. Logs blocked attempts to ~/.claude/debug/git-block.log (rotated at ~1MB).

set -euo pipefail

log_file="$HOME/.claude/debug/git-block.log"
mkdir -p "$HOME/.claude/debug" 2>/dev/null || true

if [ -f "$log_file" ] && [ "$(stat -c%s "$log_file" 2>/dev/null || echo 0)" -gt 1048576 ]; then
  tail -c 524288 "$log_file" > "${log_file}.tmp" 2>/dev/null && mv "${log_file}.tmp" "$log_file"
fi

log() {
  echo "[$(date -Iseconds)] $*" >> "$log_file" 2>/dev/null || true
}

# Emit a block decision without relying on jq - used on fail-closed paths
# where jq itself may be unavailable or broken. The reason must be a JSON-safe
# static string (no unescaped quotes, backslashes, or newlines).
block_static() {
  local reason="$1"
  log "BLOCKED (fail-closed): $reason"
  printf '{"decision":"block","reason":"%s"}\n' "$reason"
  exit 0
}

# Fail closed if jq is missing - without it we can't safely distinguish Bash
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

# Shared optional run of git global options between `git` and its subcommand.
# Generic consumer: -c and -C are listed first (arg-taking shorts, consume one
# extra token); every other long option is arg-less or =value form; every other
# short is treated as arg-less. This means an unknown future global option
# cannot break verb adjacency - it is absorbed without consuming the verb token.
# Rationale: git's ONLY separate-token short global options are -c and -C;
# every other short is arg-less, and every long option is arg-less or =value.
gopt='([[:space:]]+(-c[[:space:]]+[^[:space:]]+|-C[[:space:]]+[^[:space:]]+|--[A-Za-z][A-Za-z-]*(=[^[:space:]]*)?|-[A-Za-z]))*'

# Match git write verbs at subcommand boundaries.
# The leading class excludes word characters, path separators, and hyphens so
# `echo "git add"` (git after a quote) still matches (intentionally conservative),
# but `foogit add` (no boundary) does not.
blocked_verbs="(^|[^[:alnum:]_/-])git${gopt}[[:space:]]+(cherry-pick|rebase|reset|merge|revert|restore|rm|mv|stash|apply|am|clean|pull|filter-branch)([[:space:]]|$)"
# Destructive `git push` forms the narrowed verb list now lets through:
# force/delete flags (long forms, bundled short clusters containing f/d),
# whitespace-led `+` refspecs (force-push, with or without colon), and
# whitespace-led `:` empty-source refspecs (remote-branch delete).
blocked_push_destructive="(^|[^[:alnum:]_/-])git${gopt}[[:space:]]+push([[:space:]][^;&|]*)?([[:space:]](--force|--force-with-lease|--delete|--mirror|--prune)(=[^[:space:]]*)?([[:space:]]|$)|(^|[[:space:]])-[[:alnum:]]*[fd][[:alnum:]]*([[:space:]]|$)|[[:space:]][+][^[:space:]]|[[:space:]]:[^[:space:]])"
# `git tag <name>` (create) and `git tag -d`/`-a`/`-s`/`-f` (create/delete/sign/force)
blocked_tag="(^|[^[:alnum:]_/-])git${gopt}[[:space:]]+tag[[:space:]]+([^-[:space:]]|-[adsfm])"
# `git branch -D|-d|-m|-M` (delete/rename)
blocked_branch="(^|[^[:alnum:]_/-])git${gopt}[[:space:]]+branch[[:space:]]+-[DdmM]"
# `git checkout` forms that discard working-tree changes: `[<ref>] -- <path>`
# (a ref before the pathspec separator still discards edits), force checkout
# (`-f`/`--force` as its own token; `-b` stays allowed), a bare `.` pathspec,
# and `--pathspec-from-file` (pathspecs smuggled via a file or stdin). The
# `[^;&|]*` keeps the match inside one shell segment, same idiom as
# blocked_push_destructive.
blocked_checkout="(^|[^[:alnum:]_/-])git${gopt}[[:space:]]+checkout([[:space:]][^;&|]*)?[[:space:]](--[[:space:]]|(-f|--force|[.])([[:space:]]|$)|--pathspec-from-file(=|[[:space:]]|$))"
# Ref surgery: `git reflog expire|delete`, `git update-ref` (blocked
# unconditionally - it has no read-only form, so this covers -d, the two-arg
# overwrite, and --stdin), and `git worktree remove --force|-f` (including
# bundled short clusters like -ff).
blocked_ref_surgery="(^|[^[:alnum:]_/-])git${gopt}[[:space:]]+(reflog[[:space:]]+(expire|delete)|update-ref([[:space:]]|$)|worktree[[:space:]]+remove([[:space:]][^;&|]*)?[[:space:]](--force|-[A-Za-z]*f[A-Za-z]*)([[:space:]]|$))"

if echo "$command" | grep -qE "$blocked_verbs|$blocked_tag|$blocked_branch|$blocked_checkout|$blocked_ref_surgery|$blocked_push_destructive"; then
  log "BLOCKED: $command"
  reason="This git command rewrites or destroys history/state and is user-only. Forward ops (add/commit/push) are allowed; this one is blocked: ${command}. If you explicitly want it, surface the exact command for the user to run."
  jq -nc --arg reason "$reason" '{decision:"block", reason:$reason}'
  exit 0
fi

exit 0
