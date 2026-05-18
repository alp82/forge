#!/usr/bin/env bash
# SessionStart:compact hook: re-anchor workflow + canonical pipeline state
# from the transcript after compaction. PreCompact stdout only reaches the
# debug log, so re-injection has to happen on the post-compact SessionStart
# fire, which does inject stdout/additionalContext into the conversation.
# Re-emits WORKFLOW.md alongside the structured workflow state
# (last APPROVED_PLAN, CONFIRMED_INTENT, CLARIFY_OUTPUT, CLASSIFICATION)
# extracted from the transcript.

set -euo pipefail

input=$(cat 2>/dev/null || echo '{}')

# Load the plugin's workflow — same content SessionStart injects.
workflow=""
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -f "${CLAUDE_PLUGIN_ROOT}/WORKFLOW.md" ]; then
  workflow=$(cat "${CLAUDE_PLUGIN_ROOT}/WORKFLOW.md")
fi

# Fallback anchor when jq missing or transcript unreachable — always emit
# something useful.
print_fallback() {
  if [ -n "$workflow" ]; then
    printf '%s\n\n' "$workflow"
  fi
  cat <<'EOF'
## Post-compaction anchor

Resume at the current workflow step. Preserve:
- Confirmed intent
- Classification (S/M/L/XL)
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
      line = $0
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

# Build the anchor message: workflow first, then canonical state.
out=""
if [ -n "$workflow" ]; then
  out="$workflow

"
fi
out+="## Post-compaction anchor

Resume at the current workflow step."

if [ -n "$intent" ]; then
  out+="

### Canonical intent (from transcript)
$intent"
fi

if [ -n "$classification" ]; then
  out+="

### Canonical classification (from transcript)
$classification"
fi

if [ -n "$clarify" ]; then
  out+="

### Canonical clarify output (from transcript)
$clarify"
fi

if [ -n "$plan" ]; then
  out+="

### Canonical approved plan (highest version, from transcript)
$plan"
fi

out+="

Preserve manually: current workflow step, gate results so far, unresolved self-heal findings, backward edges used."

# Emit as additionalContext; fall back to plain stdout if jq encoding fails.
if encoded=$(jq -cn --arg ctx "$out" \
  '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}' 2>/dev/null); then
  printf '%s\n' "$encoded"
else
  printf '%s\n' "$out"
fi
