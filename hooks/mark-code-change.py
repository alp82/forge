#!/usr/bin/env python3
"""PostToolUse(Edit|Write) hook: arm the per-session "code changed" markers.

Drops all three change markers (tests + build + review) when the edited file
is a real project file - inside the payload's cwd and not under a run scratch
dir (.forge/, or the pre-2.0 .alp-river/). The Stop gates (verify-tests,
verify-build, review-owed) gate on these markers, so a chat-only turn (no
Edit/Write) leaves them absent and the end-of-turn checks skip.

The review marker is also CLEARED here: a write of `findings-<lens>.md` inside
a `.forge/` run dir is the deterministic evidence that a review lens ran over
the change (both the forge wave and standalone /crossfire write these), so it
settles the review debt for the session.

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
    REVIEW_CHANGE_PREFIX,
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


def settles_review(file_path):
    """True when the write is a lens findings file in a .forge run dir - the
    deterministic "a review ran" signal that clears the review debt."""
    path = Path(file_path)
    return ".forge" in path.parts and (
        path.name.startswith("findings-") and path.name.endswith(".md")
    )


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
        if settles_review(file_path):
            session_marker(REVIEW_CHANGE_PREFIX, session_id).unlink(missing_ok=True)
            return
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
