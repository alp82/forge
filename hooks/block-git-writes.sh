#!/usr/bin/env bash
# PreToolUse hook: block the dangerous, allow the forward.
# Parses Bash tool input, splits the command into pipeline segments, and blocks
# segments that actually run a git command which rewrites or destroys
# history/state, while letting the forward ship ops (add/commit/plain push)
# through. Verbs match at command position per segment, so text that merely
# mentions a blocked command (commit messages, echo strings, grep arguments)
# passes. Logs blocked attempts to ~/.claude/debug/git-block.log (rotated at ~1MB).

set -euo pipefail

log_file="$HOME/.claude/debug/git-block.log"
mkdir -p "$HOME/.claude/debug" 2>/dev/null || true

if [ -f "$log_file" ] && [ "$(stat -c%s "$log_file" 2>/dev/null || echo 0)" -gt 1048576 ]; then
  tail -c 524288 "$log_file" > "${log_file}.tmp" 2>/dev/null && mv "${log_file}.tmp" "$log_file"
fi

log() {
  echo "[$(date -Iseconds)] $*" >> "$log_file" 2>/dev/null || true
}

# Emit a block decision without relying on jq - used on the fail-closed
# jq-parse-failure paths below (jq present but the payload unparseable is a
# genuine anomaly). The reason must be a JSON-safe static string (no unescaped
# quotes, backslashes, or newlines).
block_static() {
  local reason="$1"
  log "BLOCKED (fail-closed): $reason"
  printf '{"decision":"block","reason":"%s"}\n' "$reason"
  exit 0
}

# Fail open if jq is missing: warn and allow, matching the sibling-hook
# convention (user-context-injector.sh, auto-format.sh). The prior fail-closed
# choice turned a missing jq into a total block of every Bash call.
if ! command -v jq &>/dev/null; then
  jq_warning="WARN: jq not found on PATH - git-write guard skipped (fail-open)"
  log "$jq_warning"
  echo "$jq_warning" >&2
  exit 0
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

# Every pattern below is anchored at ^git and applied to a normalized pipeline
# segment whose first real token resolved to git (segment splitting happens in
# the loop further down; leading shell reserved words - if/then/elif/else/do/
# while/until/!/time/exec - are stripped first, so `if git pull; then ...` and
# `exec git reset --hard` still resolve to git). Splitting is also quote-blind
# on parens/braces/backticks/`;`/`|`/`&`/newline, which cuts both ways:
# false-positive direction (errs safe, accepted) - a quoted string containing
# a separator plus a git command still blocks, e.g. a commit message
# containing `; git push --force`, a heredoc commit-body line starting with a
# git phrase (the `\n` separator), or a commit message containing a literal
# `(`/backtick immediately before a blocked verb; false-negative direction
# (accepted residual, not fixed) - a quoted separator argument can split a
# destructive command's own flags into a non-git segment, e.g. a quoted `;`
# inside an otherwise-git-anchored argument list. Accepted bypasses (a
# shell-aware tokenizer is out of scope): quote-splitting (`"git" push`), IFS
# tricks, and interpreter/wrapper indirection - `bash x.sh`, `env git ...`,
# `command git ...`, `timeout ...`, `nohup ...`, `nice ...`, `sudo ...`, and
# `xargs git ...` resolve their first token to the wrapper, not git, and pass.
blocked_verbs="^git${gopt}[[:space:]]+(cherry-pick|rebase|reset|merge|revert|restore|rm|mv|apply|am|clean|pull|filter-branch)([[:space:]]|$)"
# Destructive `git push` forms the narrowed verb list now lets through:
# force/delete flags (long forms, bundled short clusters containing f/d),
# whitespace-led `+` refspecs (force-push, with or without colon), and
# whitespace-led `:` empty-source refspecs (remote-branch delete). The
# `[^;&|]*` idiom predates segment pre-splitting - segments can no longer
# contain `;`, `&`, or `|`, so it now reads as `.*`; kept as defense in depth.
blocked_push_destructive="^git${gopt}[[:space:]]+push([[:space:]][^;&|]*)?([[:space:]](--force|--force-with-lease|--delete|--mirror|--prune)(=[^[:space:]]*)?([[:space:]]|$)|(^|[[:space:]])-[[:alnum:]]*[fd][[:alnum:]]*([[:space:]]|$)|[[:space:]][+][^[:space:]]|[[:space:]]:[^[:space:]])"
# `git tag <name>` (create) and `git tag -d`/`-a`/`-s`/`-f` (create/delete/sign/force)
blocked_tag="^git${gopt}[[:space:]]+tag[[:space:]]+([^-[:space:]]|-[adsfm])"
# `git branch -D|-d|-m|-M` (delete/rename)
blocked_branch="^git${gopt}[[:space:]]+branch[[:space:]]+-[DdmM]"
# `git checkout` forms that discard working-tree changes: `[<ref>] -- <path>`
# (a ref before the pathspec separator still discards edits), force checkout
# (`-f`/`--force` as its own token; `-b` stays allowed), a bare `.` pathspec,
# and `--pathspec-from-file` (pathspecs smuggled via a file or stdin). The
# `[^;&|]*` is the same pre-splitting-era idiom noted on
# blocked_push_destructive - now redundant, kept as defense in depth.
blocked_checkout="^git${gopt}[[:space:]]+checkout([[:space:]][^;&|]*)?[[:space:]](--[[:space:]]|(-f|--force|[.])([[:space:]]|$)|--pathspec-from-file(=|[[:space:]]|$))"
# Ref surgery: `git reflog expire|delete`, `git update-ref` (blocked
# unconditionally - it has no read-only form, so this covers -d, the two-arg
# overwrite, and --stdin), and `git worktree remove --force|-f` (including
# bundled short clusters like -ff).
blocked_ref_surgery="^git${gopt}[[:space:]]+(reflog[[:space:]]+(expire|delete)|update-ref([[:space:]]|$)|worktree[[:space:]]+remove([[:space:]][^;&|]*)?[[:space:]](--force|-[A-Za-z]*f[A-Za-z]*)([[:space:]]|$))"
# Mutating stash (bare `git stash`, push/pop/drop/clear/-u, ...) stays blocked;
# POSIX ERE has no lookahead, so read-only `git stash list|show` is a separate
# allow-pattern checked first in the loop below.
blocked_stash="^git${gopt}[[:space:]]+stash([[:space:]]|$)"
stash_readonly="^git${gopt}[[:space:]]+stash[[:space:]]+(list|show)([[:space:]]|$)"

blocked_all="$blocked_verbs|$blocked_tag|$blocked_branch|$blocked_checkout|$blocked_ref_surgery|$blocked_push_destructive|$blocked_stash"

# Quote-tolerant leading env-assignment (`FOO="a b" git ...`), stripped before
# quotes are dropped so the value's spaces cannot break first-token resolution.
env_assign_re="^[A-Za-z_][A-Za-z0-9_]*=(\"[^\"]*\"|'[^']*'|[^[:space:]])*[[:space:]]+"

# Shell reserved words that can prefix a git invocation without being its own
# command (`if git pull; then ...`, `exec git reset --hard`, `! git reset
# --hard`): stripped iteratively so `if FOO=x git ...` still resolves.
reserved_word_re="^(if|then|elif|else|do|while|until|!|time|exec|coproc)[[:space:]]+"

# Split into pipeline segments (covers `;`, `|`, `&&`, `||`, `$(`, backticks,
# brace/paren groups, and newlines) and judge each by its first real token.
segments=$(printf '%s\n' "$command" | tr '|&;(){}`\n' '\n')

while IFS= read -r seg; do
  seg="${seg#"${seg%%[![:space:]]*}"}"
  while true; do
    if [[ $seg =~ $env_assign_re ]]; then
      seg="${seg:${#BASH_REMATCH[0]}}"
    elif [[ $seg =~ $reserved_word_re ]]; then
      seg="${seg:${#BASH_REMATCH[0]}}"
    else
      break
    fi
  done
  first="${seg%%[[:space:]]*}"
  case "$first" in
    git) ;;
    # Path invocation: normalize `/usr/bin/git push` to `git push`.
    */git) seg="git${seg#"$first"}" ;;
    *) continue ;;
  esac
  # Drop quote characters so a blocked flag directly followed by a closing
  # quote (the quote-blind-split residual above) still matches its pattern.
  seg="${seg//\"/}"
  seg="${seg//\'/}"
  if [[ $seg =~ $stash_readonly ]]; then
    continue
  fi
  if [[ $seg =~ $blocked_all ]]; then
    log "BLOCKED: $command"
    reason="This git command rewrites or destroys history/state and is user-only. Forward ops (add/commit/push) are allowed; this one is blocked: ${command}. If you explicitly want it, surface the exact command for the user to run."
    jq -nc --arg reason "$reason" '{decision:"block", reason:$reason}'
    exit 0
  fi
done <<< "$segments"

exit 0
