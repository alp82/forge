#!/usr/bin/env bash
# SessionStart hook (startup / resume / compact): the single recovery hook.
# It unifies what inject-workflow.sh (anchor) and the retired
# reinject-canonical-state.sh (post-compact re-anchor) used to split.
#
# - startup / resume: ALWAYS injects the per-run WRITE PATH so the orchestrator
#   knows where to persist run-state each turn. If a valid, fresh, non-converged
#   prior run-state.json exists (resume: its own dir; startup: freshest in a scan
#   of all runs/ dirs, since a brand-new session_id matches no dir), it ALSO
#   injects a recovery offer phrased as a turn-1 instruction to surface a
#   confirm-first gate.
# - compact: inject-workflow.sh does NOT fire on compact, so this emits the
#   workflow anchor here, re-anchoring route/live/available/premises file-first
#   from run-state.json; when the file is absent or invalid it emits the anchor
#   plus a preserve-manually note (the on-disk file is the sole state source).
#
# STDOUT-PURE: emits only the legal hookSpecificOutput JSON (via the sourced
# emit_session_context) or nothing. ALWAYS exits 0; never crashes, never
# non-zero, never rejects with output.

set -uo pipefail  # -e omitted: this hook MUST exit 0; IO failures are guarded per-call (|| true / return 1).

# Source the co-located workflow-anchor.sh so the dev-tree hook always gets the
# dev-tree helper, regardless of what CLAUDE_PLUGIN_ROOT points at in a session.
hook_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
helper="${hook_dir}/workflow-anchor.sh"
[ -f "$helper" ] || exit 0
source "$helper"

# workflow_anchor() internally references ${CLAUDE_PLUGIN_ROOT}/WORKFLOW.md; keep
# the same default so it resolves correctly when running directly (tests).
: "${CLAUDE_PLUGIN_ROOT:="$(cd "${hook_dir}/.." && pwd)"}"

input=$(cat 2>/dev/null || true)

# Use the .cwd // empty with $PWD fallback pattern from inject-workflow.sh:22-23.
source_type=$(echo "$input" | jq -r '.source // empty' 2>/dev/null || true)
session_id=$(echo "$input" | jq -r '.session_id // empty' 2>/dev/null || true)
project_cwd=$(echo "$input" | jq -r '.cwd // empty' 2>/dev/null || true)
[ -z "$project_cwd" ] && project_cwd="$PWD"
transcript_path=$(echo "$input" | jq -r '.transcript_path // empty' 2>/dev/null || true)

max_age="${RIVER_STATE_MAX_AGE_SECONDS:-86400}"
runs_dir="${project_cwd}/.alp-river/runs"

# Guards on a candidate run-state.json: G1 (jq-parseable + schema_version==1 +
# validate-on-read required fields), G2 (cwd matches payload), G4 (mtime within
# max-age), CONVERGED-SKIP (route empty AND pending_gate empty/absent). Returns 0
# only when every guard passes and the state is a live recovery candidate.
# G3 is not here - it is the resume-vs-startup dispatch at the call site that
# decides WHICH file to pass in (own dir vs. freshest-scan).
candidate_ok() {
  # Twin: hooks/verify_shared.py red_window() (run-state branch) applies these
  # guards in Python; change both together. One divergence: junk
  # RIVER_STATE_MAX_AGE_SECONDS - this shell defaults only on unset/empty, the
  # Python side also falls back to 86400 on junk.
  local f="$1"
  [ -f "$f" ] || return 1
  jq -e '.schema_version == 1 and has("route") and has("cwd") and has("mid_run_stage")' "$f" >/dev/null 2>&1 || return 1
  local cwd_field
  cwd_field=$(jq -r '.cwd // empty' "$f" 2>/dev/null) || return 1
  [ "$cwd_field" = "$project_cwd" ] || return 1
  local mtime now age
  mtime=$(stat -c %Y "$f" 2>/dev/null || echo 0)
  now=$(date +%s)
  age=$(( now - mtime ))
  (( age <= max_age )) || return 1
  local r pg
  r=$(jq -r 'if (.route|type)=="array" then (.route|join(", ")) else (.route // "") end' "$f" 2>/dev/null)
  pg=$(jq -r '.pending_gate // empty' "$f" 2>/dev/null)
  [ -z "$r" ] && [ -z "$pg" ] && return 1
  return 0
}

# Delete runs/<id>/ dirs whose run-state.json mtime is older than the max-age.
# Runs during the read pass; freshness is the file's mtime, same signal as G4.
prune_stale() {
  [ -d "$runs_dir" ] || return 0
  local now mtime age f d
  now=$(date +%s)
  for f in "$runs_dir"/*/run-state.json; do
    [ -f "$f" ] || continue
    mtime=$(stat -c %Y "$f" 2>/dev/null || echo "$now")
    age=$(( now - mtime ))
    if (( age > max_age )); then
      d=$(dirname "$f")
      rm -rf "$d" 2>/dev/null || true
    fi
  done
}

# Build the recovery offer: a turn-1 instruction naming the mid-run stage and
# route. SessionStart additionalContext injects silently (no picker renders), so
# the offer is phrased as an explicit instruction to surface a confirm-first gate.
build_offer() {
  local f="$1" stage route pending plan_path
  stage=$(jq -r '.mid_run_stage // empty' "$f" 2>/dev/null)
  route=$(jq -r 'if (.route|type)=="array" then (.route|join(", ")) else (.route // "") end' "$f" 2>/dev/null)
  pending=$(jq -r '.pending_gate // empty' "$f" 2>/dev/null)
  printf '## Recovery offer (prior in-flight run found)\n\n'
  printf 'A prior run-state.json for this project shows a mid-run stage "%s" on route "%s". ' "$stage" "$route"
  printf 'On turn 1, before anything else, surface a confirm-first gate to the user: '
  printf '"Resume at %s on route %s, or start fresh?" ' "$stage" "$route"
  printf 'Do not silently resume; let the user choose. If this context was compacted away, ignore it silently.\n'
  if [ "$pending" = "plan-approval" ]; then
    plan_path=$(jq -r '.artifact_index["@approved-plan"] // empty' "$f" 2>/dev/null)
    if [ -n "$plan_path" ]; then
      printf '\nA plan-approval gate is pending; the plan handle is at %s. Re-emit the plan-approval gate on resume.\n' "$plan_path"
    fi
  fi
}

# Re-anchor the canonical run state file-first from run-state.json on compact.
# Returns 0 when the file was present and valid, 1 when the caller must fall back
# to the anchor-only preserve-manually note.
reanchor_from_file() {
  local f="$1"
  [ -f "$f" ] || return 1
  jq -e '.schema_version == 1' "$f" >/dev/null 2>&1 || return 1
  local cwd_field
  cwd_field=$(jq -r '.cwd // empty' "$f" 2>/dev/null) || return 1
  [ "$cwd_field" = "$project_cwd" ] || return 1
  local route live available premises mid pending
  route=$(jq -r 'if (.route|type)=="array" then (.route|join(", ")) else (.route // "") end' "$f" 2>/dev/null || true)
  live=$(jq -r '(.live // []) | join(", ")' "$f" 2>/dev/null || true)
  available=$(jq -r '(.available // []) | join(", ")' "$f" 2>/dev/null || true)
  premises=$(jq -r '.premises // empty' "$f" 2>/dev/null || true)
  mid=$(jq -r '.mid_run_stage // empty' "$f" 2>/dev/null || true)
  pending=$(jq -r '.pending_gate // empty' "$f" 2>/dev/null || true)
  append_block "### Current route (from run-state.json)" "$route"
  append_block "### Live signals (from run-state.json)" "$live"
  append_block "### Available artifacts (from run-state.json)" "$available"
  append_block "### Route premises (from run-state.json)" "$premises"
  append_block "" "Mid-run stage: ${mid:-none}. Pending gate: ${pending:-none}. The router recomputes the route from the blocks above."
  return 0
}

case "$source_type" in
  compact)
    # inject-workflow.sh does not fire on compact, so emit the workflow anchor
    # here. File-first re-anchor from run-state.json; when the file is absent
    # or invalid, emit the anchor plus the preserve-manually note. The on-disk
    # file is the sole state source; there is no transcript recovery.
    truncated=0
    out="$(workflow_anchor)"
    out+=$'\n\n'"## Post-compaction anchor"$'\n\n'"Resume at the current workflow step."

    state_file="${runs_dir}/${session_id}/run-state.json"
    if ! reanchor_from_file "$state_file"; then
      append_block "" "Preserve manually: the stage currently mid-run and any gate awaiting the user. The router recomputes the route from the blocks above."
    fi

    if (( truncated )); then
      out+=$'\n\n'"$TRUNC_MARKER"
    fi
    emit_session_context "$out"
    ;;

  startup|resume)
    # Maintenance read pass: prune stale run dirs.
    prune_stale

    write_path="${project_cwd}/.alp-river/runs/${session_id}/run-state.json"
    context="## Run-state write path"$'\n\n'"Each turn (loop step 4), write the canonical run-state snapshot with your own Write tool to:"$'\n'"${write_path}"$'\n'"This per-run file is where durability and recovery read from."

    candidate=""
    if [ "$source_type" = "resume" ]; then
      # resume: look ONLY at its own session dir; never scan.
      cf="${runs_dir}/${session_id}/run-state.json"
      candidate_ok "$cf" && candidate="$cf"
    else
      # startup: the session_id is brand-new and matches no dir, so SCAN all
      # runs/ dirs and pick the freshest that passes the guards - selection is by
      # cwd + age + freshest-scan, NEVER session-equality.
      best=""
      best_mtime=-1
      for f in "$runs_dir"/*/run-state.json; do
        [ -f "$f" ] || continue
        if candidate_ok "$f"; then
          m=$(stat -c %Y "$f" 2>/dev/null || echo 0)
          if (( m > best_mtime )); then
            best_mtime=$m
            best="$f"
          fi
        fi
      done
      candidate="$best"
    fi

    if [ -n "$candidate" ]; then
      offer=$(build_offer "$candidate")
      context="${context}"$'\n\n'"${offer}"
    fi

    emit_session_context "$context"
    ;;

  *)
    : # not registered on any other source; emit nothing.
    ;;
esac

exit 0
