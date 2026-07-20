#!/usr/bin/env python3
"""Install forge's enforcement hooks into codex's own hooks file.

Codex does NOT load hooks carried by a plugin - `plugin_hooks` is a removed
feature (`codex features list`), so the `hooks` pointer in `.codex-plugin/
plugin.json` is inert. Real codex hooks live in `$CODEX_HOME/hooks.json`
(default `~/.codex/hooks.json`) under a per-hook trust mechanism. This script is
the writer the setup-forge skill runs: it reads the shipped nested-schema
template beside it, resolves every command to an ABSOLUTE path (there is no
plugin-root variable codex substitutes at runtime), and merges forge's entries
into `$CODEX_HOME/hooks.json` - owning only its own, never touching a user's or
Orca's hooks.

Idempotent: re-running replaces forge's own entries and leaves everything else
byte-for-byte. Ownership is by command basename - any MatcherGroup whose inner
commands are all forge scripts (FORGE_SCRIPTS) is forge's, and is dropped before
the freshly-resolved groups are appended. That re-owns correctly even when the
installed plugin path changes between versions.

Trust: codex will not run a newly written hook until it is trusted. On the next
interactive codex start the user is prompted to trust forge's hooks; automation
passes `--dangerously-bypass-hook-trust`. This script only writes the config -
it never edits trust state.

Stdlib only. Exits non-zero with a message on any write failure so the setup
skill can report a loud failure rather than a silent half-install.
"""

import json
import os
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
TEMPLATE = HOOKS_DIR / "hooks.json"

# The forge hook scripts, by basename. A MatcherGroup is forge-owned iff every
# inner command's script basename is in this set - the ownership key that lets a
# re-install replace forge's groups without disturbing foreign ones.
FORGE_SCRIPTS = frozenset(
    {
        "session-start.sh",
        "block-git-writes.sh",
        "mark-code-change.py",
        "verify-tests.py",
        "verify-build.py",
        "review-owed.py",
    }
)


def codex_home() -> Path:
    """Codex's config dir: $CODEX_HOME, else ~/.codex (codex's own default)."""
    env = os.environ.get("CODEX_HOME")
    return Path(env).expanduser() if env else Path.home() / ".codex"


def _script_basename(command: str) -> str:
    """The hook script a command runs, ignoring a leading interpreter.

    `python3 /abs/mark-code-change.py foo` -> `mark-code-change.py`;
    `/abs/session-start.sh` -> `session-start.sh`. Interpreter-agnostic so the
    ownership test matches whether or not the command is prefixed with python3.
    """
    tokens = command.split()
    for tok in tokens:
        base = os.path.basename(tok)
        if base in FORGE_SCRIPTS:
            return base
    # Fall back to the last path-like token's basename.
    return os.path.basename(tokens[-1]) if tokens else ""


def _resolve(command: str) -> str:
    """Rewrite a template command's script reference to an absolute path.

    Template commands name scripts by basename (`session-start.sh`,
    `python3 mark-code-change.py`); this joins them to HOOKS_DIR so codex - which
    substitutes no plugin-root variable - runs them by absolute path.
    """
    tokens = command.split(" ", 1)
    if tokens[0] == "python3":
        return f"python3 {HOOKS_DIR / tokens[1]}"
    rest = f" {tokens[1]}" if len(tokens) > 1 else ""
    return f"{HOOKS_DIR / tokens[0]}{rest}"


def _is_forge_group(group: dict) -> bool:
    """True when every inner command in the group runs a forge script."""
    inner = group.get("hooks") or []
    if not inner:
        return False
    return all(_script_basename(h.get("command", "")) in FORGE_SCRIPTS for h in inner)


def build_forge_hooks() -> dict:
    """The template's event map with every command resolved to an absolute path."""
    template = json.loads(TEMPLATE.read_text())
    forge_hooks = {}
    for event, groups in template["hooks"].items():
        resolved_groups = []
        for group in groups:
            resolved = dict(group)
            resolved["hooks"] = [
                {**h, "command": _resolve(h["command"])} for h in group["hooks"]
            ]
            resolved_groups.append(resolved)
        forge_hooks[event] = resolved_groups
    return forge_hooks


def merge(existing: dict, forge_hooks: dict) -> dict:
    """Merge forge's event groups into an existing hooks config.

    Preserves the top-level `description` (and any other top-level keys) and every
    non-forge MatcherGroup. For each event forge owns, foreign groups keep their
    order and forge's freshly-resolved groups are appended after them; a re-install
    first strips the previous forge groups so they never accumulate.
    """
    merged = dict(existing)
    events = dict(merged.get("hooks") or {})
    for event, forge_groups in forge_hooks.items():
        foreign = [g for g in events.get(event, []) if not _is_forge_group(g)]
        events[event] = foreign + forge_groups
    merged["hooks"] = events
    return merged


def main() -> int:
    home = codex_home()
    target = home / "hooks.json"
    try:
        home.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"forge hook install FAILED: cannot create {home}: {exc}", file=sys.stderr)
        return 1

    existing = {}
    if target.exists():
        try:
            existing = json.loads(target.read_text())
        except (json.JSONDecodeError, ValueError) as exc:
            print(
                f"forge hook install FAILED: {target} exists but is not valid JSON "
                f"({exc}). Fix or remove it, then re-run - refusing to clobber it.",
                file=sys.stderr,
            )
            return 1

    merged = merge(existing, build_forge_hooks())
    try:
        target.write_text(json.dumps(merged, indent=2) + "\n")
    except OSError as exc:
        print(f"forge hook install FAILED: cannot write {target}: {exc}", file=sys.stderr)
        return 1

    events = ", ".join(merged["hooks"].keys())
    print(f"forge hooks written to {target} (events: {events})")
    print(
        "Trust: on the next interactive codex start, approve forge's hooks when "
        "prompted; automation runs with --dangerously-bypass-hook-trust."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
