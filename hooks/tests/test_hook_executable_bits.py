"""Guard: every hook script invoked DIRECTLY by hooks.json must be executable.

CONTRACT:
  - A hook whose command runs the script itself (first token is
    ${CLAUDE_PLUGIN_ROOT}/hooks/<name>.sh) is exec'd by the OS, so the file
    needs the executable bit. The bit that matters is the one git TRACKS
    (mode 100755), because that is what propagates into the plugin cache on
    install - a working-tree chmod that never reaches the index still ships a
    non-executable file and fails at SessionStart with "Permission denied".
  - A command that passes a script TO an interpreter (python3 .../x.py,
    bash .../x.sh) does not need the bit; the interpreter is the executable.
    Those are correctly skipped here.

This is the cheap canary for the class of bug where recover-run-state.sh
shipped as 100644 and the SessionStart recovery hook silently never ran.
Against that state this test is RED for recover-run-state.sh; flipping the
tracked mode to 100755 makes it GREEN.
"""

import json
import re
import subprocess
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = HOOKS_DIR.parent
HOOKS_JSON = HOOKS_DIR / "hooks.json"

# First token of a command that runs a repo hook script directly (no interpreter).
DIRECT_SCRIPT = re.compile(r"^\$\{CLAUDE_PLUGIN_ROOT\}/hooks/([^\s]+\.sh)$")


def _iter_commands(node):
    """Yield every command string under any {"type":"command"} entry."""
    if isinstance(node, dict):
        if node.get("type") == "command" and isinstance(node.get("command"), str):
            yield node["command"]
        for value in node.values():
            yield from _iter_commands(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_commands(item)


def _directly_invoked_scripts():
    """Return sorted basenames of hooks/*.sh that hooks.json execs directly."""
    config = json.loads(HOOKS_JSON.read_text())
    scripts = set()
    for command in _iter_commands(config):
        first_token = command.strip().split()[0]
        match = DIRECT_SCRIPT.match(first_token)
        if match:
            scripts.add(match.group(1))
    return sorted(scripts)


def _git_mode(rel_path):
    """The mode git tracks for rel_path (relative to repo root), or '' if untracked."""
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-s", rel_path],
        capture_output=True,
        text=True,
    )
    line = result.stdout.strip()
    return line.split()[0] if line else ""


def test_some_scripts_are_directly_invoked():
    """Sanity: the discovery actually finds direct-exec hooks (catches a parser regression)."""
    assert (
        _directly_invoked_scripts()
    ), "expected hooks.json to invoke at least one .sh directly"


def test_directly_invoked_hooks_are_executable():
    """Every directly-invoked hook script is git-tracked as executable (100755)."""
    offenders = {}
    for name in _directly_invoked_scripts():
        rel = f"hooks/{name}"
        mode = _git_mode(rel)
        if mode != "100755":
            offenders[rel] = mode or "untracked"
    assert not offenders, (
        "directly-invoked hook scripts must be git-tracked as executable (100755); "
        f"offenders (path -> tracked mode): {offenders}"
    )
