#!/usr/bin/env bash
# Stop hook: verify the project still builds / typechecks before allowing Claude to finish.
# Activates whenever a build/typecheck tool resolves locally for the project.
# Max 1 retry per session to prevent infinite loops.
#
# Conservative by construction: the build/typecheck runs ONLY when its tool is
# locally present (no npx-on-miss downloads/hangs). A timeout is treated as a
# non-blocking pass-through. For rust/go this checks the compile-error class
# (cargo check / go build -o /dev/null) - it does not assert artifact parity.

set -euo pipefail

# This is a completion gate (fail-open bias): if jq is absent we cannot parse
# the payload, so let Claude finish rather than blocking on a tooling gap.
command -v jq &>/dev/null || exit 0

# Read hook payload from stdin (Claude Code passes JSON with session_id, transcript_path, cwd)
input=$(cat)
session_id=$(echo "$input" | jq -r '.session_id // empty' 2>/dev/null)
cwd=$(echo "$input" | jq -r '.cwd // empty' 2>/dev/null)
stop_hook_active=$(echo "$input" | jq -r '.stop_hook_active // empty' 2>/dev/null)

# Anchor in the working directory (cwd from hook payload, fall back to $PWD)
project_root="${cwd:-$PWD}"
cd "$project_root" || exit 0

# Retry tracking: session-keyed marker so "max 1 retry" actually survives across hook invocations
# in the same Claude session.
if [ -n "$session_id" ]; then
  session_marker="/tmp/.claude-build-verify-${session_id}"
else
  # Fallback when session_id is unavailable - degrades to per-invocation (no retry limit guarantee)
  session_marker="/tmp/.claude-build-verify-fallback-$$"
fi

# Avoid re-blocking inside an already-blocked Stop loop: clear the marker and let Claude finish.
if [ "$stop_hook_active" = "true" ]; then
  rm -f "$session_marker"
  exit 0
fi

if [ -f "$session_marker" ]; then
  retry_count=$(cat "$session_marker")
  if [ "$retry_count" -ge 1 ]; then
    # Already retried once - let Claude finish, the correctness-reviewer will catch it
    rm -f "$session_marker"
    exit 0
  fi
fi

# Detect the package manager from the lockfile present.
detect_pm() {
  if [ -f "pnpm-lock.yaml" ]; then
    echo "pnpm"
  elif [ -f "yarn.lock" ]; then
    echo "yarn"
  else
    echo "npm"
  fi
}

# Detect a build/typecheck command. First match wins; the tool must resolve
# locally or the row is skipped (silent pass), never an npx-on-miss download.
build_cmd=""
if [ -f "package.json" ] && [ -n "$(jq -r '.scripts.build // empty' package.json 2>/dev/null)" ]; then
  pm=$(detect_pm)
  build_cmd="$pm run build 2>&1"
elif [ -f "tsconfig.json" ]; then
  if [ -x "node_modules/.bin/tsc" ]; then
    build_cmd="node_modules/.bin/tsc --noEmit 2>&1"
  elif command -v npx &>/dev/null; then
    # --no-install: never download; exit 127 (tool absent) is handled below as a skip.
    build_cmd="npx --no-install tsc --noEmit 2>&1"
  fi
elif [ -f "Cargo.toml" ] && command -v cargo &>/dev/null; then
  build_cmd="cargo check 2>&1"
elif [ -f "go.mod" ] && command -v go &>/dev/null; then
  build_cmd="go build -o /dev/null ./... 2>&1"
elif grep -q '\[tool.mypy\]' pyproject.toml 2>/dev/null || [ -f "mypy.ini" ] || grep -q '\[mypy\]' setup.cfg 2>/dev/null; then
  # mypy only when configured AND resolvable; otherwise silent skip (no compileall).
  if command -v mypy &>/dev/null; then
    build_cmd="mypy . 2>&1"
  fi
fi

# No build command found / tool absent - don't block
if [ -z "$build_cmd" ]; then
  rm -f "$session_marker"
  exit 0
fi

# Run the build/typecheck with timeout
exit_code=0
result=$(timeout 150 bash -c "$build_cmd" 2>&1) || exit_code=$?

# 127 = tool not resolvable (e.g. npx --no-install miss) - treat as a skip, never block.
if [ "$exit_code" -eq 127 ]; then
  rm -f "$session_marker"
  exit 0
fi

# 124 = timeout - non-blocking pass-through.
if [ "$exit_code" -eq 124 ]; then
  rm -f "$session_marker"
  exit 0
fi

if [ "$exit_code" -ne 0 ]; then
  # Track retry
  current=$(($(cat "$session_marker" 2>/dev/null || echo 0) + 1))
  echo "$current" > "$session_marker" || true

  # Truncate output to last 30 lines to keep context clean
  tail_output=$(echo "$result" | tail -30)
  reason=$(printf 'Build is failing. Fix it before completing.\n\n```\n%s\n```' "$tail_output")

  jq -nc --arg reason "$reason" '{decision:"block",reason:$reason}'
  exit 0
fi

# Build passed - clean up
rm -f "$session_marker"
exit 0
