#!/usr/bin/env bash
# Sourced by inject-workflow.sh and reinject-canonical-state.sh - not run directly.
# Provides the small SessionStart context (essentials + a pointer to WORKFLOW.md)
# and the shared hookSpecificOutput emitter. WORKFLOW.md holds the full doctrine;
# this anchor stays well under the harness 10k-char per-output cap so it is never
# truncated, and points the agent at the full file to read on demand.

workflow_anchor() {
  cat <<EOF
## alp-river workflow

This is a pointer, not the spec. Before running the route loop (triage, route, run a stage, recompose) you MUST read the doctrine file below - the loop, the signal vocabulary, the convergence rule, and the Concise Surfacing Contract are NOT reproduced here. Read it; do not infer them. (The shared review and code-quality doctrine now ships per-agent via the Agent hook; the WORKFLOW.md pointer stays authoritative for you.)

Stable meta-rules (the file is authoritative on everything else):
- Pipeline entry: every code-modifying request enters the pipeline via /alp-river:go (or plain chat - same pipeline) first. "Small/mechanical/one-line" is not a bypass.
- Intent first: confirm the outcome at user-observable level before any work. No file paths or function names in the restate.
- Read before acting: ground every change in files you have actually read.
- Context discipline: the main agent orchestrates and spawns subagents; it does not read whole codebases or implement large changes itself.
- House style: no em-dashes (use a hyphen); no preamble; leave touched code better than you found it; no TODOs, no backwards-compat scaffolding.

Full doctrine (read on demand): ${CLAUDE_PLUGIN_ROOT}/WORKFLOW.md
EOF
}

emit_session_context() {
  local ctx="$1"
  if command -v jq >/dev/null 2>&1 && \
     encoded=$(jq -cn --arg ctx "$ctx" \
       '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}' 2>/dev/null); then
    printf '%s\n' "$encoded"
  else
    printf '%s\n' "$ctx"
  fi
}
