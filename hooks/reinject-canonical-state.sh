#!/usr/bin/env bash
# SessionStart:compact hook: re-anchor the workflow pointer + canonical pipeline
# state from the transcript after compaction. PreCompact stdout only reaches the
# debug log, so re-injection has to happen on the post-compact SessionStart
# fire, which does inject stdout/additionalContext into the conversation.
# Re-emits the workflow-essentials anchor (a pointer to WORKFLOW.md, read on
# demand) alongside the structured workflow state (last APPROVED_PLAN,
# CONFIRMED_INTENT, CLARIFY_OUTPUT, CLASSIFICATION) extracted from the transcript.

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

Resume at the current workflow step. Preserve:
- Confirmed intent
- Classification (S/M/L/XL/XXL)
- Approved plan (if any)
- Current workflow step
- Gate results so far
- Unresolved self-heal findings
- Backward edges used: N/2
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

intent=$(extract_last_block "CONFIRMED_INTENT" "$transcript_text")
classification=$(extract_last_block "CLASSIFICATION" "$transcript_text")
clarify=$(extract_last_block "CLARIFY_OUTPUT" "$transcript_text")
plan=$(extract_last_block "APPROVED_PLAN" "$transcript_text")

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

append_block "### Canonical intent (from transcript)" "$intent"
append_block "### Canonical classification (from transcript)" "$classification"
append_block "### Canonical clarify output (from transcript)" "$clarify"
append_block "### Canonical approved plan (highest version, from transcript)" "$plan"
append_block "" "Preserve manually: current workflow step, gate results so far, unresolved self-heal findings, backward edges used."

# Marker room was reserved against CEILING, so this always fits.
if (( truncated )); then
  out+=$'\n\n'"$TRUNC_MARKER"
fi

emit_session_context "$out"
