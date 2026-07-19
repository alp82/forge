#!/usr/bin/env bash
# BeforeAgent hook (gemini port): inject the minimal forge context - the entry
# rule, the flow-skill pointer, and a staleness nag when the installed tier
# agents disagree with the extension version. Deliberately tiny: the flow
# itself lives in skills/forge/SKILL.md and is read on demand, never injected.
#
# Why BeforeAgent, not SessionStart: gemini's SessionStart is advisory-only (no
# context-injection channel documented); the survey records BeforeAgent's
# `hookSpecificOutput.additionalContext` as the injection surface, and it fires
# before every turn INCLUDING the first, so session-start injection is covered.
# The banner reinjects each turn - cheap and idempotent (a few lines).
#
# Output (RISK-1 - the gemini BeforeAgent response schema is documented for
# additionalContext but not pinned field-by-field): the survey-shaped
# hookSpecificOutput/additionalContext JSON on stdout when jq is present, plain
# text stdout otherwise - the install probe (setup § verify (a)) is the arbiter
# of whether either lands in context.
set -euo pipefail

# Self-locate so the dev-tree hook always gets the dev-tree files. No documented
# extension-root env var is guaranteed for a settings.json-wired hook (RISK-7);
# BASH_SOURCE is the only resolver that works under both the extension and the
# settings.json install paths.
hook_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
plugin_root="$(cd "${hook_dir}/../../.." && pwd)"

# The gemini native channel manifest is gemini-extension.json at the repo root.
manifest="${plugin_root}/gemini-extension.json"
plugin_version=""
if [ -f "$manifest" ]; then
  if command -v jq >/dev/null 2>&1; then
    plugin_version=$(jq -r '.version // empty' "$manifest" 2>/dev/null || true)
  else
    plugin_version=$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$manifest" | head -1)
  fi
fi

# Staleness check. setup-forge writes four derived tier-agent files
# ~/.gemini/agents/forge-<tier>.md, each stamped `<!-- forge-version: X.Y.Z -->`
# (that stamp convention is canonical here; the setup skill follows it).
# No forge agent file at all = setup not run = stay silent (tier agents are
# opt-in). Any forge agent file present but the set incomplete, the stamp
# missing, or the stamp differing from the extension version -> nag.
sync_nag=""
agents_dir="$HOME/.gemini/agents"
any_agent=""
for tier in mini standard large ultra; do
  [ -f "${agents_dir}/forge-${tier}.md" ] && any_agent="yes"
done
if [ -n "$any_agent" ]; then
  for tier in mini standard large ultra; do
    agent_file="${agents_dir}/forge-${tier}.md"
    if [ ! -f "$agent_file" ]; then
      sync_nag="- Installed forge tier agents are incomplete - re-run the setup-forge skill."
      break
    fi
    stamp=$(sed -n 's/.*forge-version:[[:space:]]*\([0-9A-Za-z.\-]*\).*/\1/p' "$agent_file" | head -1)
    if [ -z "$stamp" ] || { [ -n "$plugin_version" ] && [ "$stamp" != "$plugin_version" ]; }; then
      sync_nag="- Installed forge tier agents are outdated - re-run the setup-forge skill."
      break
    fi
  done
fi

context="## forge

- Every code-modifying request enters via the forge skill - \"small/mechanical/one-line\" is not a bypass.
- The flow: ${plugin_root}/skills/forge/SKILL.md (stage briefs sit beside it); crossfire is the standalone review verb."
if [ -n "$sync_nag" ]; then
  context="${context}
${sync_nag}"
fi

if command -v jq >/dev/null 2>&1 && \
   encoded=$(jq -cn --arg ctx "$context" \
     '{hookSpecificOutput: {hookEventName: "BeforeAgent", additionalContext: $ctx}}' 2>/dev/null); then
  printf '%s\n' "$encoded"
else
  printf '%s\n' "$context"
fi
