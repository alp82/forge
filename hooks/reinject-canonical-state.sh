#!/usr/bin/env bash
# SessionStart:compact hook: re-anchor the workflow pointer + canonical pipeline
# state from the transcript after compaction. PreCompact stdout only reaches the
# debug log, so re-injection has to happen on the post-compact SessionStart
# fire, which does inject stdout/additionalContext into the conversation.
# Re-emits the workflow-essentials anchor (a pointer to WORKFLOW.md, read on
# demand) alongside the structured run state (last ROUTE, LIVE_SIGNALS,
# AVAILABLE_ARTIFACTS, PREMISES) extracted from the transcript.

set -euo pipefail

helper="${CLAUDE_PLUGIN_ROOT}/hooks/workflow-anchor.sh"
[ -f "$helper" ] || exit 0
source "$helper"

input=$(cat 2>/dev/null || echo '{}')

# Fallback anchor when jq missing or transcript unreachable - always emit
# something useful.
print_fallback() {
  printf '%s\n\n' "$(workflow_anchor)"
  cat <<'EOF'
## Post-compaction anchor

Resume the route loop. Preserve:
- Current route (ordered stages)
- Live signals + available artifacts
- Route premises
- The stage currently mid-run
- Any gate awaiting the user
EOF
}

if ! command -v jq &>/dev/null; then
  print_fallback
  exit 0
fi

transcript_path=$(echo "$input" | jq -r '.transcript_path // empty' 2>/dev/null)

if [ -z "$transcript_path" ] || [ ! -f "$transcript_path" ]; then
  print_fallback
  exit 0
fi

# Pull assistant text from the transcript as a single plain stream.
transcript_text=$(jq -r '
  select((.type? // "") == "assistant" or (.role? // "") == "assistant")
  | (.message.content? // .content? // [])
  | if type == "array" then
      map(select((.type? // "") == "text") | .text) | join("\n")
    elif type == "string" then .
    else ""
    end
' "$transcript_path" 2>/dev/null) || transcript_text=""

if [ -z "$transcript_text" ]; then
  print_fallback
  exit 0
fi

# Extract the LAST complete <TAG>...</TAG> block from the transcript stream.
# Case-sensitive; tag must appear on a line that includes the open marker.
extract_last_block() {
  local tag="$1"
  local text="$2"
  printf '%s\n' "$text" | awk -v tag="$tag" '
    BEGIN { capture = 0; last = ""; buf = "" }
    {
      sub(/\r$/, "", $0); line = $0
      open_pattern = "<" tag "[ >]"
      close_pattern = "</" tag ">"
      if (match(line, open_pattern)) {
        capture = 1
        buf = line
        if (match(line, close_pattern)) {
          last = buf
          capture = 0
          buf = ""
        }
        next
      }
      if (capture) {
        buf = buf "\n" line
        if (match(line, close_pattern)) {
          last = buf
          capture = 0
          buf = ""
        }
      }
    }
    END { print last }
  '
}

route=$(extract_last_block "ROUTE" "$transcript_text")
signals=$(extract_last_block "LIVE_SIGNALS" "$transcript_text")
artifacts=$(extract_last_block "AVAILABLE_ARTIFACTS" "$transcript_text")
premises=$(extract_last_block "PREMISES" "$transcript_text")

# Build the anchor message: workflow pointer first, then canonical state.
# Bounded to stay under the session-start per-output size limit. The anchor is
# mandatory and goes first; canonical blocks follow in priority order. Room for
# the truncation marker is reserved up front (EFFECTIVE_CEILING), so whenever any
# block is dropped or shortened we set `truncated` and append the marker exactly
# once at the end - it always fits. The marker therefore appears when, and only
# when, something was truncated (never silently dropped), and total output stays
# under CEILING.
CEILING=9000
TRUNC_MARKER='[canonical state truncated to fit the session-start size limit - the full version is in the pre-compaction transcript]'
# Reserve room for the marker plus its leading blank-line separator, with a small
# slack so the marker always fits when appended at the end.
MARKER_SLACK=8
EFFECTIVE_CEILING=$(( CEILING - ${#TRUNC_MARKER} - 2 - MARKER_SLACK ))
truncated=0

append_block() {
  local heading="$1" body="$2"
  [ -z "$body" ] && return 0
  local sep=""
  [ -n "$out" ] && sep=$'\n\n'
  # Empty heading: append the body sentence directly (no heading line, no extra
  # blank lines) so the separator alone divides it from the prior block.
  local prefix="${sep}"
  [ -n "$heading" ] && prefix="${sep}${heading}"$'\n'
  local candidate="${prefix}${body}"
  local remaining=$(( EFFECTIVE_CEILING - ${#out} ))
  if (( ${#candidate} <= remaining )); then
    out+="$candidate"
    return 0
  fi
  # Does not fit whole: emit as much body as the prefix leaves room for and flag
  # truncation so the marker is appended once at the end.
  truncated=1
  local budget_for_body=$(( remaining - ${#prefix} ))
  if (( budget_for_body > 0 )); then
    out+="${prefix}${body:0:budget_for_body}"
  fi
}

out="$(workflow_anchor)"
out+=$'\n\n'"## Post-compaction anchor"$'\n\n'"Resume at the current workflow step."

append_block "### Current route (from transcript)" "$route"
append_block "### Live signals (from transcript)" "$signals"
append_block "### Available artifacts (from transcript)" "$artifacts"
append_block "### Route premises (from transcript)" "$premises"
append_block "" "Preserve manually: the stage currently mid-run and any gate awaiting the user. The router recomputes the route from the blocks above."

# Marker room was reserved against CEILING, so this always fits.
if (( truncated )); then
  out+=$'\n\n'"$TRUNC_MARKER"
fi

emit_session_context "$out"
