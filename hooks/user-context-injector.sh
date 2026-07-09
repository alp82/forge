#!/usr/bin/env bash
# PreToolUse(Agent) hook: auto-inject DOCTRINE, USER_CONTEXT, and PROJECT_CONTEXT into subagents.
#
# DOCTRINE: shared review/code-quality rules from the plugin's doctrine/ folder,
#           gated per-agent by DOCTRINE_MAP. Assembled FIRST so it leads the payload.
# USER_CONTEXT: MEMORY.md + every linked markdown file for the current project.
# PROJECT_CONTEXT: docs/INTENT.md, docs/STACK.md, docs/GLOSSARY.md (full bodies)
#                  plus a summary list of docs/adr/*.md, gated per-agent by READ_MAP.
#
# The three axes are independent:
#   Doctrine-aware = agent has a DOCTRINE_MAP entry → receives `## DOCTRINE`, assembled first.
#   User-aware  = agent is listed in the case statement below → receives USER_CONTEXT.
#   Project-aware = agent has an entry in READ_MAP → receives PROJECT_CONTEXT.
#
# An agent can be user-aware only, project-aware only, both, or neither:
#   User-aware Y + Project-aware Y: most agents - clarifier, planner,
#                                   plan-challenger, implementer, design-prototyper,
#                                   ux-prototyper, reviewers, fixer, investigator,
#                                   capture-agent, adr-drafter, discuss, sketch-build
#                                   (see case arms and READ_MAP)
#   User-aware N + Project-aware Y: health-checker, prototype-identifier,
#                                   researcher, code-prototyper, data-prototyper,
#                                   performance-prototyper, explainer-prototyper
#                                   (user_aware=0)
#   User-aware Y + Project-aware N: setup-agent
#   User-aware N + Project-aware N: test-verifier, accessibility-reviewer, and
#                                   test-gap are user_aware=0 arms that fall
#                                   through for a doctrine-only payload
#                                   (DOCTRINE_MAP entries). unknown agent types
#                                   still exit at the terminal `*)`.
#
# Behavioral invariant: test-verifier, accessibility-reviewer, and test-gap emit
# a DOCTRINE-only block from an otherwise-silent exit - they carry no user or
# project context, so the `## DOCTRINE` block is their whole payload (test-gap
# newly joins the doctrine-only fall-through arm below). Every other
# doctrine-aware agent was already user- or project-aware (the 10 reviewer
# rows), so it just gains a leading `## DOCTRINE` block ahead of the context
# it already received.
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
  # User-aware: yes. Project-aware: depends on READ_MAP.
  clarifier|code-planner|plan-challenger|plan-arbiter|code-implementer|fixer|code-investigator|setup-agent|capture-agent|adr-drafter|design-prototyper|ux-prototyper|discuss|sketch-build|system-planner|system-executor|system-investigator|system-verifier|safety-gate)
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
  # User-aware: no. Project-aware: yes (READ_MAP entries below).
  health-checker|prototype-identifier|researcher|code-prototyper|data-prototyper|performance-prototyper|explainer-prototyper)
    user_aware=0
    ;;
  # User-aware: no. Project-aware: no. They cite doctrine, so they fall through
  # for a doctrine-only payload instead of hitting the terminal exit.
  test-verifier|accessibility-reviewer|test-gap)
    user_aware=0
    ;;
  # User-aware: no. Project-aware: no (not in READ_MAP either). Silent skip.
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

# READ_MAP: per-agent token list resolving to docs/ files.
# Tokens (lowercase) → INTENT/STACK/GLOSSARY/adr (UPPERCASE filenames, singular adr/).
# Single source of truth for project-context routing. Agent files do not carry
# a reads: field - what runs is what's in this map.
declare -A READ_MAP=(
  [clarifier]="intent stack glossary adrs"
  [reuse-scanner]="glossary"
  [health-checker]="stack"
  [prototype-identifier]="stack"
  [researcher]="stack"
  [code-prototyper]="stack"
  [data-prototyper]="stack"
  [performance-prototyper]="stack"
  [explainer-prototyper]="stack"
  [code-planner]="intent stack glossary adrs"
  [system-planner]="stack glossary adrs"
  [system-executor]="stack glossary"
  [system-investigator]="stack glossary"
  [system-verifier]="stack"
  [safety-gate]="stack"
  [plan-challenger]="intent stack glossary adrs"
  [plan-arbiter]="intent stack glossary adrs"
  [design-prototyper]="intent stack glossary adrs"
  [ux-prototyper]="intent stack glossary adrs"
  [code-implementer]="stack glossary adrs"
  [correctness-reviewer]="stack glossary"
  [simplicity-reviewer]="stack glossary"
  [acceptance-reviewer]="intent glossary"
  [shape-reviewer]="stack glossary adrs"
  [conventions-reviewer]="glossary"
  [security-reviewer]="stack adrs"
  [performance-reviewer]="stack"
  [ux-reviewer]="intent"
  [design-consistency-reviewer]="intent stack"
  [fixer]="stack glossary adrs"
  [code-investigator]="stack glossary adrs"
  [capture-agent]="intent stack glossary"
  [adr-drafter]="intent stack glossary adrs"
  [discuss]="intent stack glossary adrs"
  [sketch-build]="stack glossary"
)

# DOCTRINE_MAP: per-agent doctrine slices, resolved to doctrine/<token>.md.
# Single source of truth for doctrine routing - an agent appears here only if its
# definition cites that doctrine. Independent of the user-aware and project-aware
# axes (see the header).
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

# Summarize active ADRs as a markdown bullet list. Empty string when nothing
# qualifies (no adr/ dir, no .md files, all filtered out).
summarize_adrs() {
  local adr_dir="$1"
  [ -d "$adr_dir" ] || return 0

  local files=()
  local f base
  for f in "$adr_dir"/*.md; do
    [ -e "$f" ] || continue
    base="${f##*/}"
    case "$base" in
      0000-*.md)
        continue
        ;;
    esac
    files+=("$f")
  done
  [ "${#files[@]}" -gt 0 ] || return 0

  # Single awk pass over all ADR files: a per-file state machine extracts
  # status, title, and a short summary (first paragraph under `## Summary`,
  # falling back to the first paragraph after the H1 title), flushing one
  # bullet per file at the next FNR==1 boundary and at END. Portable POSIX
  # awk: a zero-length file never fires FNR==1 and yields no bullet.
  awk '
    function reset_state() {
      fm = 0; fm_done = 0
      status = ""; title = ""
      pre = ""; pre_lines = 0; pre_done = 0
      post = ""; post_lines = 0; in_summary = 0
    }
    function flush_record() {
      if (!seen) return
      if (status == "deprecated" || status == "superseded") return
      summary_final = (post != "") ? post : pre
      gsub(/[[:space:]]+/, " ", summary_final)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", summary_final)
      if (index(summary_final, "_TODO:_")) return
      if (status == "") status = "unknown status"
      if (title == "") title = stem
      idx = index(stem, "-")
      num = idx ? substr(stem, 1, idx - 1) : stem
      line = "- ADR-" num ": " title " [" status "]"
      if (summary_final != "") line = line " - " summary_final
      print line " (docs/adr/" base ")"
    }
    BEGIN { seen = 0 }
    FNR == 1 {
      if (seen) flush_record()
      reset_state()
      seen = 1
      n = split(FILENAME, parts, "/")
      base = parts[n]
      stem = base
      sub(/\.md$/, "", stem)
    }
    FNR == 1 && /^---[[:space:]]*$/ { fm = 1; next }
    fm && !fm_done && /^---[[:space:]]*$/ { fm_done = 1; next }
    fm && !fm_done {
      if (match($0, /^[[:space:]]*status[[:space:]]*:[[:space:]]*/)) {
        status = substr($0, RSTART + RLENGTH)
        gsub(/^["'"'"']|["'"'"']$/, "", status)
        gsub(/[[:space:]]+$/, "", status)
      }
      next
    }
    title == "" && /^#[[:space:]]+/ {
      title = $0
      sub(/^#[[:space:]]+/, "", title)
      sub(/^[0-9]+[.\-][[:space:]]+/, "", title)
      sub(/^[0-9]+[[:space:]]+-[[:space:]]+/, "", title)
      gsub(/[[:space:]]+$/, "", title)
      next
    }
    title == "" { next }
    /^##[[:space:]]+[Ss]ummary[[:space:]]*$/ {
      in_summary = 1
      post = ""; post_lines = 0
      next
    }
    in_summary {
      if ($0 ~ /^#/) { in_summary = 0 }
      else if ($0 ~ /^[[:space:]]*$/) {
        if (post_lines > 0) in_summary = 0
      }
      else if (post_lines < 3) {
        if (post == "") post = $0
        else post = post " " $0
        post_lines++
      }
    }
    !pre_done && pre_lines < 3 {
      if ($0 ~ /^[[:space:]]*$/) {
        if (pre_lines > 0) pre_done = 1
      }
      else if ($0 ~ /^#/) { pre_done = 1 }
      else {
        if (pre == "") pre = $0
        else pre = pre " " $0
        pre_lines++
      }
    }
    END { flush_record() }
  ' "${files[@]}"
}

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

# Build PROJECT_CONTEXT from docs/ per the READ_MAP entry for this agent.
project_context=""
docs_dir="$project_cwd/docs"
tokens="${READ_MAP[$subagent_type]:-}"

if [ -n "$tokens" ] && [ -d "$docs_dir" ]; then
  body=""
  for token in $tokens; do
    case "$token" in
      intent)
        if [ -f "$docs_dir/INTENT.md" ]; then
          body+="### INTENT.md

"
          body+=$(cat "$docs_dir/INTENT.md")
          body+="

"
        fi
        ;;
      stack)
        if [ -f "$docs_dir/STACK.md" ]; then
          body+="### STACK.md

"
          body+=$(cat "$docs_dir/STACK.md")
          body+="

"
        fi
        ;;
      glossary)
        if [ -f "$docs_dir/GLOSSARY.md" ]; then
          body+="### GLOSSARY.md

"
          body+=$(cat "$docs_dir/GLOSSARY.md")
          body+="

"
        fi
        ;;
      adrs)
        adr_summary=$(summarize_adrs "$docs_dir/adr")
        if [ -n "$adr_summary" ]; then
          body+="### ADRs

"
          body+="$adr_summary"
          body+="
"
        fi
        ;;
    esac
  done

  if [ -n "$body" ]; then
    project_context="## PROJECT_CONTEXT
${body}"
  fi
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

# Combine DOCTRINE, USER_CONTEXT, and PROJECT_CONTEXT into one
# additionalContext payload by sequential-append (doctrine first). Non-empty
# blocks join with "\n\n---\n\n".
assembled=""
for block in "$doctrine_context" "$user_context" "$project_context"; do
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
