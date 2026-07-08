#!/usr/bin/env bash
# Notification hook: desktop notification when Claude needs attention.
# Works on Linux (notify-send), macOS (osascript), and falls back to terminal bell.

set -euo pipefail

input=$(cat)
title="Claude Code"

# Extract message from hook input; jq's // covers missing/null, the || covers
# non-JSON input (parse failure), and a present-but-empty message stays empty.
body=$(echo "$input" | jq -r '.message // "Needs your attention"' 2>/dev/null) || body="Needs your attention"

# Linux
if command -v notify-send &>/dev/null; then
  notify-send -u normal -t 5000 "$title" "$body" 2>/dev/null
  exit 0
fi

# macOS. AppleScript string literals escape exactly two characters, so escape
# backslashes first, then double quotes; then flatten newlines because a raw
# newline would split the single-line -e source.
if command -v osascript &>/dev/null; then
  esc_body="${body//\\/\\\\}"
  esc_body="${esc_body//\"/\\\"}"
  esc_body="${esc_body//$'\n'/ }"
  esc_title="${title//\\/\\\\}"
  esc_title="${esc_title//\"/\\\"}"
  esc_title="${esc_title//$'\n'/ }"
  osascript -e "display notification \"$esc_body\" with title \"$esc_title\"" 2>/dev/null
  exit 0
fi

# Fallback: terminal bell
printf '\a'
exit 0
