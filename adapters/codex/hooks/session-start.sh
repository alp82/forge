#!/usr/bin/env bash
# SessionStart hook (codex port): inject the minimal forge context - the entry
# rule, the flow-skill pointer, and a staleness nag when the installed tier
# agents disagree with the plugin version. Deliberately tiny: the flow itself
# lives in skills/forge/SKILL.md and is read on demand, never injected.
#
# Output (RISK-1 - the codex SessionStart response schema is undocumented):
# Claude-shaped hookSpecificOutput/additionalContext JSON on stdout when jq is
# present, plain text stdout otherwise - the install probe (setup § verify (a))
# is the arbiter of whether either lands in context.
set -euo pipefail

# Self-locate so the dev-tree hook always gets the dev-tree files. No
# CLAUDE_PLUGIN_ROOT equivalent is documented for codex (RISK-7); BASH_SOURCE
# is the only resolver.
hook_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
plugin_root="$(cd "${hook_dir}/../../.." && pwd)"

plugin_json="${plugin_root}/.codex-plugin/plugin.json"
plugin_version=""
if [ -f "$plugin_json" ]; then
  if command -v jq >/dev/null 2>&1; then
    plugin_version=$(jq -r '.version // empty' "$plugin_json" 2>/dev/null || true)
  else
    plugin_version=$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$plugin_json" | head -1)
  fi
fi

# Staleness check. setup-forge writes four derived tier-agent files
# ~/.codex/agents/forge-<tier>.toml, each stamped `# forge-version: X.Y.Z`
# (that stamp convention is canonical here; the setup skill follows it).
# No forge agent file at all = setup not run = stay silent (tier agents are
# opt-in). Any forge agent file present but the set incomplete, the stamp
# missing, or the stamp differing from the plugin version -> nag.
sync_nag=""
agents_dir="$HOME/.codex/agents"
any_agent=""
for tier in mini standard large ultra; do
  [ -f "${agents_dir}/forge-${tier}.toml" ] && any_agent="yes"
done
if [ -n "$any_agent" ]; then
  for tier in mini standard large ultra; do
    agent_file="${agents_dir}/forge-${tier}.toml"
    if [ ! -f "$agent_file" ]; then
      sync_nag="- Installed forge tier agents are incomplete - re-run \$setup-forge."
      break
    fi
    stamp=$(sed -n 's/^# forge-version:[[:space:]]*//p' "$agent_file" | head -1)
    if [ -z "$stamp" ] || { [ -n "$plugin_version" ] && [ "$stamp" != "$plugin_version" ]; }; then
      sync_nag="- Installed forge tier agents are outdated - re-run \$setup-forge."
      break
    fi
  done
fi

# Host identity line for the worker forwarder (skills/forge/WORKER.md): the
# host-vendor token is defined once in adapters/codex/capabilities.json
# (.vendor) and mirrored here by hand - a bare token that changes at most once
# per harness lifetime. The forge/crossfire dispatcher reads this line to
# forward host-vendor into the worker spawn, so same-vendor second opinions are
# excluded.
context="## forge

- Every code-modifying request enters via the forge skill (\$forge) - \"small/mechanical/one-line\" is not a bypass.
- The flow: ${plugin_root}/skills/forge/SKILL.md (stage briefs sit beside it); \$crossfire is the standalone review verb.
- Host harness: codex, host-vendor: openai - the worker forwarder excludes same-vendor second opinions."
if [ -n "$sync_nag" ]; then
  context="${context}
${sync_nag}"
fi

if command -v jq >/dev/null 2>&1 && \
   encoded=$(jq -cn --arg ctx "$context" \
     '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}' 2>/dev/null); then
  printf '%s\n' "$encoded"
else
  printf '%s\n' "$context"
fi
