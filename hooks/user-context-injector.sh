#!/usr/bin/env bash
# PreToolUse(Agent) hook: auto-inject DOCTRINE, USER_CONTEXT, PROJECT_CONTEXT, and PSYCHOLOGY into subagents.
#
# DOCTRINE: shared review/code-quality rules from the plugin's doctrine/ folder,
#           gated per-agent by DOCTRINE_MAP. Assembled FIRST so it leads the payload.
# USER_CONTEXT: MEMORY.md + every linked markdown file for the current project.
# PROJECT_CONTEXT: docs/INTENT.md, docs/STACK.md, docs/GLOSSARY.md (full bodies)
#                  plus a summary list of docs/adr/*.md, gated per-agent by READ_MAP.
# PSYCHOLOGY: opt-in persona block resolved per-agent via psychology/agent-map.json.
#             Per-project overrides are read from .claude/settings.local.json under
#             alpRiver.psychologyOverrides.<agent>; set to a persona name to swap, or
#             omit to accept the sidecar default. Fails open on missing/corrupted files.
#
# The four axes are independent:
#   Doctrine-aware = agent has a DOCTRINE_MAP entry → receives `## DOCTRINE`, assembled first.
#   User-aware  = agent is listed in the case statement below → receives USER_CONTEXT.
#   Project-aware = agent has an entry in READ_MAP → receives PROJECT_CONTEXT.
#   Psychology = agent has an entry in psychology/agent-map.json (or a project override)
#               → receives PSYCHOLOGY block.
#
# An agent can be user-aware only, project-aware only, both, or neither:
#   User-aware Y + Project-aware Y: most agents - interviewer, planner,
#                                   plan-challenger, implementer, design-prototyper,
#                                   ux-prototyper, reviewers, fixer, investigator,
#                                   capture-agent, adr-drafter, discuss, sketch-build
#                                   (see case arms and READ_MAP)
#   User-aware N + Project-aware Y: health-checker, prototype-identifier,
#                                   researcher, code-prototyper, data-prototyper,
#                                   performance-prototyper  (user_aware=0)
#   User-aware Y + Project-aware N: plan-adherence-reviewer,
#                                   setup-agent
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
# doctrine-aware agent was already user- or project-aware (the 15 reviewer rows
# and plan-adherence-reviewer), so it just gains a leading `## DOCTRINE` block
# ahead of the context it already received.
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
  interviewer|code-planner|plan-challenger|plan-arbiter|code-implementer|fixer|code-investigator|setup-agent|capture-agent|adr-drafter|design-prototyper|ux-prototyper|discuss|sketch-build|system-planner|system-executor|system-investigator|system-verifier|safety-gate)
    ;;
  requirements-clarifier|reuse-scanner)
    ;;
  correctness-reviewer|quality-reviewer|simplicity-reviewer|acceptance-reviewer|plan-adherence-reviewer)
    ;;
  structure-reviewer|architecture-reviewer|consistency-reviewer|reuse-reviewer|naming-clarity|assumptions)
    ;;
  security-reviewer|performance-reviewer)
    ;;
  design-consistency-reviewer|ux-reviewer)
    ;;
  # User-aware: no. Project-aware: yes (READ_MAP entries below).
  health-checker|prototype-identifier|researcher|code-prototyper|data-prototyper|performance-prototyper)
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
  [interviewer]="intent glossary adrs"
  [requirements-clarifier]="intent stack glossary adrs"
  [reuse-scanner]="glossary"
  [health-checker]="stack"
  [prototype-identifier]="stack"
  [researcher]="stack"
  [code-prototyper]="stack"
  [data-prototyper]="stack"
  [performance-prototyper]="stack"
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
  [quality-reviewer]="intent stack glossary"
  [acceptance-reviewer]="intent glossary"
  [structure-reviewer]="glossary adrs"
  [architecture-reviewer]="stack glossary adrs"
  [consistency-reviewer]="glossary"
  [naming-clarity]="glossary"
  [assumptions]="stack glossary"
  [reuse-reviewer]="glossary"
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
# definition cites that doctrine. Independent of the user-aware, project-aware, and
# psychology axes (see the header).
declare -A DOCTRINE_MAP=(
  [correctness-reviewer]="reviewer-contract confidence-tagging discoveries communication"
  [simplicity-reviewer]="reviewer-contract confidence-tagging discoveries communication"
  [quality-reviewer]="reviewer-contract confidence-tagging discoveries communication"
  [architecture-reviewer]="reviewer-contract confidence-tagging discoveries communication"
  [security-reviewer]="reviewer-contract confidence-tagging discoveries communication"
  [performance-reviewer]="reviewer-contract confidence-tagging discoveries communication"
  [consistency-reviewer]="reviewer-contract confidence-tagging discoveries communication"
  [structure-reviewer]="reviewer-contract confidence-tagging discoveries communication"
  [naming-clarity]="reviewer-contract confidence-tagging discoveries communication"
  [assumptions]="reviewer-contract confidence-tagging discoveries communication"
  [reuse-reviewer]="reviewer-contract confidence-tagging communication"
  [acceptance-reviewer]="reviewer-contract confidence-tagging communication"
  [test-verifier]="reviewer-contract confidence-tagging communication"
  [accessibility-reviewer]="reviewer-contract confidence-tagging communication"
  [ux-reviewer]="reviewer-contract confidence-tagging communication"
  [design-consistency-reviewer]="reviewer-contract confidence-tagging communication"
  # communication-only by design - fact-reporter, no reviewer-contract scope
  [plan-adherence-reviewer]="communication"
  [code-implementer]="code-doctrine discoveries"
  [code-planner]="code-doctrine"
  [plan-challenger]="code-doctrine briefs"
  [plan-arbiter]="code-doctrine briefs"
  [discuss]="briefs"
  [interviewer]="briefs"
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

  local out=""
  local f
  for f in "$adr_dir"/*.md; do
    [ -e "$f" ] || continue
    local base
    base=$(basename "$f")
    case "$base" in
      0000-*.md)
        continue
        ;;
    esac

    # Single awk pass extracts status, title, and a short summary. Prefers the
    # first paragraph under `## Summary`; falls back to the first paragraph after
    # the H1 title when no Summary heading is present.
    local extracted
    extracted=$(awk '
      BEGIN {
        fm = 0; fm_done = 0
        status = ""; title = ""
        pre = ""; pre_lines = 0; pre_done = 0
        post = ""; post_lines = 0; in_summary = 0
      }
      NR == 1 && /^---[[:space:]]*$/ { fm = 1; next }
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
      END {
        summary = (post != "") ? post : pre
        gsub(/[[:space:]]+/, " ", summary)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", summary)
        printf "%s\t%s\t%s", status, title, summary
      }
    ' "$f")

    local status title summary
    status=$(printf '%s' "$extracted" | cut -f1)
    title=$(printf '%s' "$extracted" | cut -f2)
    summary=$(printf '%s' "$extracted" | cut -f3)

    case "$status" in
      deprecated|superseded)
        continue
        ;;
    esac

    case "$summary" in
      *_TODO:_*)
        continue
        ;;
    esac

    [ -z "$status" ] && status="unknown status"
    if [ -z "$title" ]; then
      title="${base%.md}"
    fi

    local stem="${base%.md}"
    local num="${stem%%-*}"

    out+="- ADR-${num}: ${title} [${status}]"
    [ -n "$summary" ] && out+=" - ${summary}"
    out+=" (docs/adr/${base})"$'\n'
  done

  printf '%s' "$out"
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

# Resolve the optional psychology block for this agent.
# Returns the rendered block on stdout, or empty when the agent is unmapped,
# the override resolves to nothing, or the persona file is missing (fail open).
# The block is the persona file body followed by a generic directive telling the
# agent to vocalize its Anchor line.
resolve_persona() {
  local agent="$1"
  local cwd="$2"

  local map_file="$plugin_root/psychology/agent-map.json"
  local settings_file="$cwd/.claude/settings.local.json"

  # Per-project override. Type guard discards non-string values; "none"/empty
  # fall through to the sidecar default (no per-project suppression).
  local persona_name=""
  if [ -f "$settings_file" ]; then
    persona_name=$(jq -r --arg a "$agent" \
      '.alpRiver.psychologyOverrides[$a] | select(type == "string") // empty' \
      "$settings_file" 2>/dev/null || true)
    if [ "$persona_name" = "none" ]; then
      persona_name=""
    fi
  fi

  # Fall back to the sidecar default when no usable override was found.
  if [ -z "$persona_name" ]; then
    if [ -f "$map_file" ]; then
      if ! persona_name=$(jq -r --arg a "$agent" '.[$a] // empty' "$map_file" 2>/dev/null); then
        echo "alp-river: warning: failed to parse psychology/agent-map.json" >&2
        return 0
      fi
    fi
  fi

  [ -z "$persona_name" ] && return 0

  local persona_file="$plugin_root/psychology/${persona_name}.md"
  [ -f "$persona_file" ] || return 0

  # Display name: hyphens-to-spaces, lowercase whole string, then uppercase first character.
  local lowered first rest display_name
  lowered=$(echo "$persona_name" | tr '-' ' ' | tr '[:upper:]' '[:lower:]')
  first="${lowered:0:1}"
  rest="${lowered:1}"
  display_name="${first^^}${rest}"

  printf '## PSYCHOLOGY: %s\n' "$display_name"
  cat "$persona_file"
  printf '\nBefore acting, restate your Anchor above in your own voice as the opening line of your response, then proceed.\n'
}

psychology_context=$(resolve_persona "$subagent_type" "$project_cwd")

# Combine DOCTRINE, USER_CONTEXT, PROJECT_CONTEXT, and PSYCHOLOGY into one
# additionalContext payload by sequential-append (doctrine first). Non-empty
# blocks join with "\n\n---\n\n".
assembled=""
for block in "$doctrine_context" "$user_context" "$project_context" "$psychology_context"; do
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
