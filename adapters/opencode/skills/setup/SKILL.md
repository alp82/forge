---
name: setup-forge
description: Re-run forge's opencode install/update - refreshes the installed skills, plugin, and tier agents, then re-verifies every declared capability. Run when the startup nag says the installed forge surfaces disagree, or to update forge.
---

# setup-forge — re-run the opencode install

Fetch `https://raw.githubusercontent.com/alp82/forge/main/adapters/opencode/INSTALL.md`
and follow it. That document is the one home for the whole install-and-verify
procedure — it is idempotent, so re-following it refreshes current copies and re-runs
verification by construction.
