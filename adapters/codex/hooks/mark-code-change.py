#!/usr/bin/env python3
"""PostToolUse(edit tools) hook: arm the per-session "code changed" markers
(codex port).

Drops all three change markers (tests + build + review) when an edit tool
touched a real project file - inside the payload's cwd and not under a run
scratch dir (.forge/, or the pre-2.0 .alp-river/). The Stop gates
(verify-tests, verify-build, review-owed) gate on these markers, so a
chat-only turn (no edit-tool call) leaves them absent and the end-of-turn
checks skip.

Codex I/O (RISK-4 - the survey never names codex's edit tools or their input
fields, so this reads tolerantly):
  - Matched tool names: apply_patch / edit / write / str_replace / create_file
    plus the Claude-shaped Edit / Write.
  - Path derivation tries tool_input.file_path, then tool_input.path, then -
    for apply_patch - scans the patch body (tool_input.patch / tool_input.input)
    for `*** Update File:` / `*** Add File:` paths; arming fires when ANY
    derived path passes should_arm.
  - A matched edit tool with NO derivable path arms anyway (fail-toward-arm):
    worst case the gates run once on a chat-ish turn; failing toward skip would
    silently disarm the whole gated tier.

This hook only ARMS. The review debt is settled at Stop by review-owed.py - see
its module docstring for why settling has to happen there, not at write time. So
a `.forge/` write is inert here: it arms nothing and settles nothing.

Marker existence is the whole signal; content is irrelevant. Always exits 0
and never prints (PostToolUse stdout would be parsed). Fail-open on the outer
frame: an unparseable payload or a non-edit tool is a silent no-op.
"""

import json
import re
import sys
from pathlib import Path

from verify_shared import (
    CHANGE_MARKER_PREFIXES,
    session_marker,
)

# Run scratch dirs whose writes are process debris, never project changes.
# .alp-river is the pre-2.0 run dir; drop it when the old pipeline dies.
SCRATCH_DIRS = frozenset({".forge", ".alp-river"})

# RISK-4: codex edit-tool names are undocumented - match broadly.
EDIT_TOOLS = frozenset(
    {"apply_patch", "edit", "write", "str_replace", "create_file", "Edit", "Write"}
)

# apply_patch body headers naming the touched files.
PATCH_PATH_RE = re.compile(r"^\*\*\* (?:Update|Add) File:\s*(.+?)\s*$", re.MULTILINE)


def should_arm(file_path, cwd):
    """True only for a real project file: inside cwd and not under a scratch dir.

    Relative paths (apply_patch bodies use them) are joined to cwd first.
    Resolves symlinks so a link inside cwd pointing outside cwd is excluded, and
    matches scratch dirs as exact path components (never a substring).
    """
    try:
        p = Path(file_path)
        if not p.is_absolute():
            p = Path(cwd) / p
        rel = p.resolve().relative_to(Path(cwd).resolve())
    except (ValueError, OSError):
        return False
    return not SCRATCH_DIRS.intersection(rel.parts)


def derive_paths(tool_input):
    """Every file path derivable from the tool input, in preference order."""
    paths = []
    for key in ("file_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            paths.append(value)
    for key in ("patch", "input"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            paths.extend(PATCH_PATH_RE.findall(value))
    return paths


def main():
    try:
        if sys.stdin.isatty():
            return
        raw = sys.stdin.read().strip()
        if not raw:
            return
        payload = json.loads(raw)
        if payload.get("tool_name") not in EDIT_TOOLS:
            return
        tool_input = payload.get("tool_input") or {}
        cwd = payload.get("cwd")
        session_id = payload.get("session_id") or ""
        paths = derive_paths(tool_input)
        if paths and cwd:
            # Judged path(s): arm iff any derived path is a real project file.
            if not any(should_arm(p, cwd) for p in paths):
                return
        # No derivable path (or no cwd to judge against): arm anyway
        # (fail-toward-arm - see module docstring).
        # Rendezvous precondition: this session_id must equal the end-of-turn Stop
        # payload's session_id or the reader looks at a different marker path and
        # the gate silently no-ops (see session_marker in verify_shared.py). A
        # subagent PostToolUse firing under a different session_id arms the wrong
        # marker (RISK-8).
        for prefix in CHANGE_MARKER_PREFIXES:
            session_marker(prefix, session_id).write_text("1")
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
