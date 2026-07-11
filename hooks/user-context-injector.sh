#!/usr/bin/env bash
# PreToolUse(Agent) hook: auto-inject DOCTRINE and USER_CONTEXT into subagents.
#
# DOCTRINE: shared review/code-quality rules from the plugin's doctrine/ folder,
#           gated per-agent by DOCTRINE_MAP. Assembled FIRST so it leads the payload.
# USER_CONTEXT: MEMORY.md + every linked markdown file for the current project.
#
# The two axes are independent:
#   Doctrine-aware = agent has a DOCTRINE_MAP entry → receives `## DOCTRINE`, assembled first.
#   User-aware  = agent is listed in the case statement below → receives USER_CONTEXT.
#
# An agent can be user-aware, doctrine-aware, both, or neither:
#   User-aware: clarifier, planner, plan-challenger, plan-arbiter, implementer,
#               design-prototyper, ux-prototyper, reviewers, fixer, investigator,
#               discuss, sketch-build, the system-* stages (see case arms)
#   Doctrine-aware only: test-verifier, accessibility-reviewer, and test-gap are
#               user_aware=0 arms that fall through for a doctrine-only payload
#               (DOCTRINE_MAP entries). Unknown agent types still exit at the
#               terminal `*)`.
#
# Behavioral invariant: test-verifier, accessibility-reviewer, and test-gap emit
# a DOCTRINE-only block from an otherwise-silent exit - they carry no user
# context, so the `## DOCTRINE` block is their whole payload. Every other
# doctrine-aware agent is also user-aware, so it just gains a leading
# `## DOCTRINE` block ahead of the context it already received.
#
# Non-Agent tool calls also exit silently. Fails open on any error - missing
# files are normal.

set -euo pipefail

# Fail open if jq missing
if ! command -v jq &>/dev/null; then
  exit 0
fi

input=$(cat)

tool_name=$(echo "$input" | jq -r '.tool_name // empty' 2>/dev/null) || exit 0
if [ "$tool_name" != "Agent" ]; then
  exit 0
fi

subagent_type=$(echo "$input" | jq -r '.tool_input.subagent_type // empty' 2>/dev/null)
if [ -z "$subagent_type" ]; then
  exit 0
fi

# Plugin root: prefer CLAUDE_PLUGIN_ROOT, fall back to two dirnames up from this script.
plugin_root="${CLAUDE_PLUGIN_ROOT:-}"
if [ -z "$plugin_root" ]; then
  plugin_root="$(dirname "$(dirname "${BASH_SOURCE[0]}")")"
fi

user_aware=1
case "$subagent_type" in
  # User-aware: yes.
  clarifier|code-planner|plan-challenger|plan-arbiter|code-implementer|fixer|code-investigator|design-prototyper|ux-prototyper|discuss|sketch-build|system-planner|system-executor|system-investigator|system-verifier|safety-gate)
    ;;
  reuse-scanner)
    ;;
  correctness-reviewer|simplicity-reviewer|acceptance-reviewer)
    ;;
  shape-reviewer|conventions-reviewer)
    ;;
  security-reviewer|performance-reviewer)
    ;;
  design-consistency-reviewer|ux-reviewer)
    ;;
  # User-aware: no. They cite doctrine, so they fall through for a
  # doctrine-only payload instead of hitting the terminal exit.
  test-verifier|accessibility-reviewer|test-gap)
    user_aware=0
    ;;
  # User-aware: no. Not doctrine-aware either. Silent skip.
  *)
    exit 0
    ;;
esac

# Resolve project cwd → memory directory.
# Claude Code stores per-project memory under ~/.claude/projects/<encoded-cwd>/memory/
# where encoded-cwd replaces "/" with "-", so "/home/alp" becomes "-home-alp".
project_cwd=$(echo "$input" | jq -r '.cwd // empty' 2>/dev/null)
[ -z "$project_cwd" ] && project_cwd="$PWD"

encoded_cwd=$(echo "$project_cwd" | sed 's|/|-|g')
memory_dir="$HOME/.claude/projects/${encoded_cwd}/memory"
memory_file="$memory_dir/MEMORY.md"

# DOCTRINE_MAP: per-agent doctrine slices, resolved to doctrine/<token>.md.
# Single source of truth for doctrine routing - an agent appears here only if its
# definition cites that doctrine. Independent of the user-aware axis (see the
# header).
declare -A DOCTRINE_MAP=(
  [correctness-reviewer]="reviewer-contract confidence-tagging discoveries communication"
  [simplicity-reviewer]="reviewer-contract confidence-tagging discoveries communication"
  [shape-reviewer]="reviewer-contract confidence-tagging discoveries communication"
  [conventions-reviewer]="reviewer-contract confidence-tagging discoveries communication"
  [security-reviewer]="reviewer-contract confidence-tagging discoveries communication"
  [performance-reviewer]="reviewer-contract confidence-tagging discoveries communication"
  [acceptance-reviewer]="reviewer-contract confidence-tagging communication"
  [test-verifier]="reviewer-contract confidence-tagging communication"
  [accessibility-reviewer]="reviewer-contract confidence-tagging communication"
  [ux-reviewer]="reviewer-contract confidence-tagging communication"
  [design-consistency-reviewer]="reviewer-contract confidence-tagging communication"
  [code-implementer]="code-doctrine discoveries"
  [code-planner]="code-doctrine"
  [plan-challenger]="code-doctrine"
  [plan-arbiter]="code-doctrine"
  [fixer]="discoveries"
  [code-investigator]="discoveries"
  [system-planner]="code-doctrine"
  [system-executor]="code-doctrine discoveries"
  [system-investigator]="discoveries"
  # communication-only by design - coverage fact-reporter, case arm added below
  [test-gap]="communication"
)

# Build USER_CONTEXT from MEMORY.md and its linked .md files.
# Skipped for agents that are not user-aware.
user_context=""
if [ "$user_aware" -eq 1 ] && [ -f "$memory_file" ]; then
  user_context="## USER_CONTEXT
"
  user_context+=$(cat "$memory_file")

  # Parse markdown links [Title](file.md) - only .md links, only within the memory dir.
  while IFS= read -r link_path; do
    [ -z "$link_path" ] && continue
    case "$link_path" in
      http://*|https://*|/*|*..*)
        continue
        ;;
    esac
    full_path="$memory_dir/$link_path"
    if [ -f "$full_path" ]; then
      user_context+="

---

### $link_path

"
      user_context+=$(cat "$full_path")
    fi
  done < <(grep -oE '\[[^]]*\]\([^)]+\.md\)' "$memory_file" | sed -E 's/.*\(([^)]*\.md)\).*/\1/')
fi

# Build DOCTRINE from the plugin's doctrine/ folder per the DOCTRINE_MAP entry.
# Concatenates the agent's cited slices under one "## DOCTRINE" header.
# Fails open: a missing dir or slice file just omits that part.
doctrine_dir="$plugin_root/doctrine"
doctrine_context=""
doctrine_tokens="${DOCTRINE_MAP[$subagent_type]:-}"
if [ -n "$doctrine_tokens" ] && [ -d "$doctrine_dir" ]; then
  dbody=""
  for dtoken in $doctrine_tokens; do
    dfile="$doctrine_dir/${dtoken}.md"
    if [ -f "$dfile" ]; then
      [ -n "$dbody" ] && dbody+="

"
      dbody+=$(cat "$dfile")
    fi
  done
  if [ -n "$dbody" ]; then
    doctrine_context="## DOCTRINE
${dbody}"
  fi
fi

# Combine DOCTRINE and USER_CONTEXT into one additionalContext payload by
# sequential-append (doctrine first). Non-empty blocks join with "\n\n---\n\n".
assembled=""
for block in "$doctrine_context" "$user_context"; do
  [ -z "$block" ] && continue
  if [ -z "$assembled" ]; then
    assembled="$block"
  else
    assembled="${assembled}

---

${block}"
  fi
done

if [ -z "$assembled" ]; then
  exit 0
fi

jq -cn --arg ctx "$assembled" \
  '{hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext: $ctx}}'
