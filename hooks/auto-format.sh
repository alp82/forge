#!/usr/bin/env bash
# PostToolUse hook: auto-format files after Edit/Write.
# Detects project formatter and runs it on the modified file.
# Runs async so it doesn't block Claude.
# Failures are logged to ~/.claude/debug/auto-format.log AND surfaced back to
# the agent via hookSpecificOutput.additionalContext, so unformatted files
# don't accumulate silently when the formatter is broken or misconfigured.

set -euo pipefail

log_file="$HOME/.claude/debug/auto-format.log"
mkdir -p "$HOME/.claude/debug" 2>/dev/null || true

# Accumulates formatter failures for the EXIT trap to emit as additionalContext.
failures=""

# Rotate log if it exceeds 1MB - keep the last 512KB
if [ -f "$log_file" ] && [ "$(stat -c%s "$log_file" 2>/dev/null || echo 0)" -gt 1048576 ]; then
  tail -c 524288 "$log_file" > "${log_file}.tmp" 2>/dev/null && mv "${log_file}.tmp" "$log_file"
fi

log() {
  echo "[$(date -Iseconds)] $*" >> "$log_file" 2>/dev/null || true
}

# Emit collected failures as hookSpecificOutput so the agent sees them on its
# next turn. jq handles JSON escaping; skip if jq is missing (the script needs
# jq to read input, so reaching here without jq means we exited earlier).
emit_failures() {
  [ -z "$failures" ] && return 0
  command -v jq &>/dev/null || return 0
  jq -cn --arg ctx "auto-format: $failures" \
    '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$ctx}}'
}
trap emit_failures EXIT

run_fmt() {
  local name="$1"
  shift
  local output exit_code=0
  output=$("$@" 2>&1) || exit_code=$?
  if [ "$exit_code" -ne 0 ]; then
    log "FAIL $name on $file_path (exit $exit_code)"
    [ -n "$output" ] && echo "$output" >> "$log_file" 2>/dev/null
    echo "---" >> "$log_file" 2>/dev/null
    local tail_output
    tail_output=$(printf '%s' "$output" | tail -n 10)
    failures+="$name failed on $file_path (exit $exit_code) - see ~/.claude/debug/auto-format.log. Tail: $tail_output"
  fi
}

input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // empty')

if [ -z "$file_path" ] || [ ! -f "$file_path" ]; then
  exit 0
fi

# Find project root by walking up to .git
dir=$(dirname "$(realpath "$file_path")")
project_root=""
while [ "$dir" != "/" ]; do
  if [ -d "$dir/.git" ]; then
    project_root="$dir"
    break
  fi
  dir=$(dirname "$dir")
done

if [ -z "$project_root" ]; then
  exit 0
fi

cd "$project_root"
ext="${file_path##*.}"

# JavaScript/TypeScript: Prettier > Biome
if [[ "$ext" =~ ^(js|jsx|ts|tsx|json|css|scss|html|md|yaml|yml)$ ]]; then
  if [ -f ".prettierrc" ] || [ -f ".prettierrc.json" ] || [ -f ".prettierrc.js" ] || [ -f "prettier.config.js" ] || [ -f "prettier.config.mjs" ] || ([ -f "package.json" ] && grep -q '"prettier"' package.json 2>/dev/null); then
    run_fmt prettier npx prettier --write "$file_path"
    # ESLint surfacing (report-only): only when configured AND locally resolvable.
    if [ -f ".eslintrc" ] || [ -f ".eslintrc.json" ] || [ -f ".eslintrc.js" ] || [ -f ".eslintrc.cjs" ] || [ -f ".eslintrc.yaml" ] || [ -f ".eslintrc.yml" ] || [ -f "eslint.config.js" ] || [ -f "eslint.config.mjs" ] || [ -f "eslint.config.cjs" ] || ([ -f "package.json" ] && grep -q '"eslintConfig"' package.json 2>/dev/null); then
      if [ -x "node_modules/.bin/eslint" ]; then
        run_fmt eslint node_modules/.bin/eslint "$file_path"
      elif command -v npx &>/dev/null; then
        run_fmt eslint npx --no-install eslint "$file_path"
      fi
    fi
  elif [ -f "biome.json" ] || [ -f "biome.jsonc" ]; then
    run_fmt biome npx @biomejs/biome format --write "$file_path"
    # Biome lint surfacing (report-only): only when locally resolvable.
    if [ -x "node_modules/.bin/biome" ]; then
      run_fmt "biome lint" node_modules/.bin/biome lint "$file_path"
    elif command -v npx &>/dev/null; then
      run_fmt "biome lint" npx --no-install @biomejs/biome lint "$file_path"
    fi
  fi
fi

# Python: Ruff > Black
if [[ "$ext" == "py" ]]; then
  if command -v ruff &>/dev/null && ([ -f "pyproject.toml" ] || [ -f "ruff.toml" ] || [ -f ".ruff.toml" ]); then
    run_fmt "ruff format" ruff format "$file_path"
    run_fmt "ruff check" ruff check "$file_path"
  elif command -v black &>/dev/null; then
    run_fmt black black --quiet "$file_path"
  fi
fi

# Rust
if [[ "$ext" == "rs" ]] && command -v rustfmt &>/dev/null; then
  run_fmt rustfmt rustfmt "$file_path"
  exit 0
fi

# Go
if [[ "$ext" == "go" ]] && command -v gofmt &>/dev/null; then
  run_fmt gofmt gofmt -w "$file_path"
  exit 0
fi

# Dart
if [[ "$ext" == "dart" ]] && command -v dart &>/dev/null; then
  run_fmt "dart format" dart format "$file_path"
  exit 0
fi

exit 0
