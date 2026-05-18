# alp-river

Project-specific rules for this plugin repo. The pipeline workflow lives in `WORKFLOW.md`. Global rules live in `~/.claude/CLAUDE.md`. This file does not ship to consumers - Claude Code only loads CLAUDE.md from the user's working directory.

## Versioning

Plugin version lives in `.claude-plugin/plugin.json`. The same version is mirrored in `.claude-plugin/marketplace.json` - bump both together.

- **Patch bump** after a successful task when the workflow itself changes: anything under `agents/`, `commands/`, `hooks/`, or `WORKFLOW.md`. Same trigger: add a `CHANGELOG.md` entry, and update `README.md` if the public surface description shifts.
- **No bump** for doc-only changes (README, CHANGELOG, CLAUDE.md, comment polish). `marketplace.json` listing edits (description, keywords) are metadata, not workflow.
- **Minor and major** are manual. Don't auto-bump.

## CHANGELOG style

See `WORKFLOW.md` § "Changelog Style" - one canonical home for the rules.
