#!/usr/bin/env python3
"""PostToolUse(Edit|Write) hook: arm the per-session "code changed" markers.

Drops all three change markers (tests + build + review) when the edited file
is a real project file - inside the payload's cwd and not under a run scratch
dir (.forge/, or the pre-2.0 .alp-river/). The Stop gates (verify-tests,
verify-build, review-owed) gate on these markers, so a chat-only turn (no
Edit/Write) leaves them absent and the end-of-turn checks skip.

This hook only ARMS. The review debt is settled at Stop by review-owed.py - see
its module docstring for why settling has to happen there, not at write time. So
a `.forge/` write is inert here: it arms nothing and settles nothing.

Marker existence is the whole signal; content is irrelevant. Always exits 0
and never prints (PostToolUse stdout would be parsed). Fail-open: any
unparseable payload, missing file_path, non-Edit/Write tool, or path outside
cwd is a silent no-op that arms nothing.
"""

import json
import sys
from pathlib import Path

from verify_shared import (
    CHANGE_MARKER_PREFIXES,
    session_marker,
)

# Run scratch dirs whose writes are process debris, never project changes.
# .alp-river is the pre-2.0 run dir; drop it when the old pipeline dies.
SCRATCH_DIRS = frozenset({".forge", ".alp-river"})


def should_arm(file_path, cwd):
    """True only for a real project file: inside cwd and not under a scratch dir.

    Resolves symlinks so a link inside cwd pointing outside cwd is excluded, and
    matches scratch dirs as exact path components (never a substring).
    """
    try:
        rel = Path(file_path).resolve().relative_to(Path(cwd).resolve())
    except ValueError:
        return False
    return not SCRATCH_DIRS.intersection(rel.parts)


def main():
    try:
        if sys.stdin.isatty():
            return
        raw = sys.stdin.read().strip()
        if not raw:
            return
        payload = json.loads(raw)
        if payload.get("tool_name") not in ("Edit", "Write"):
            return
        file_path = (payload.get("tool_input") or {}).get("file_path")
        cwd = payload.get("cwd")
        if not file_path or not cwd:
            return
        session_id = payload.get("session_id") or ""
        if not should_arm(file_path, cwd):
            return
        # Rendezvous precondition: this session_id must equal the end-of-turn Stop
        # payload's session_id or the reader looks at a different marker path and
        # the gate silently no-ops (see session_marker in verify_shared.py). A
        # subagent PostToolUse firing under a different session_id arms the wrong
        # marker.
        for prefix in CHANGE_MARKER_PREFIXES:
            session_marker(prefix, session_id).write_text("1")
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
