#!/usr/bin/env bash
# SessionStart hook: inject the minimal forge context - the entry rule, the
# flow-skill pointer, and a skill-sync nag when an installed skill copy is
# stale. Deliberately tiny: the flow itself lives in skills/forge/SKILL.md and
# is read on demand, never injected.
set -euo pipefail

# Self-locate so the dev-tree hook always gets the dev-tree files, regardless
# of what CLAUDE_PLUGIN_ROOT points at in a session.
hook_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${CLAUDE_PLUGIN_ROOT:="$(cd "${hook_dir}/.." && pwd)"}"

plugin_json="${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json"
plugin_version=""
if [ -f "$plugin_json" ]; then
  if command -v jq >/dev/null 2>&1; then
    plugin_version=$(jq -r '.version // empty' "$plugin_json" 2>/dev/null || true)
  else
    plugin_version=$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$plugin_json" | head -1)
  fi
fi

# Sync check. /setup-forge symlinks the bare skill names in ~/.claude/skills to
# the installed plugin's skill dirs - a symlink is always current. Where a
# symlink failed and a COPY was made, setup stamps the copy with a
# .forge-version file; a stamp that differs from the plugin version (or is
# missing on a copy) means the copy is stale. No dir at all = setup not run =
# stay silent (bare names are opt-in). This stamp convention is canonical here;
# the setup skill follows it.
sync_nag=""
for skill_dir in "${CLAUDE_PLUGIN_ROOT}"/skills/*/; do
  [ -f "${skill_dir}SKILL.md" ] || continue
  name=$(sed -n 's/^name:[[:space:]]*//p' "${skill_dir}SKILL.md" | head -1)
  [ -n "$name" ] || name=$(basename "$skill_dir")
  target="$HOME/.claude/skills/$name"
  [ -e "$target" ] || continue
  [ -L "$target" ] && continue
  stamp=$(cat "$target/.forge-version" 2>/dev/null || true)
  if [ -n "$plugin_version" ] && [ "$stamp" != "$plugin_version" ]; then
    sync_nag="- Installed skill copies are outdated - re-run /setup-forge."
    break
  fi
done

context="## forge

- Every code-modifying request enters via the forge skill (/forge) - \"small/mechanical/one-line\" is not a bypass.
- The flow: ${CLAUDE_PLUGIN_ROOT}/skills/forge/SKILL.md (stage briefs sit beside it); /crossfire is the standalone review verb."
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
