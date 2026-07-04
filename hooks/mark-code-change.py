#!/usr/bin/env python3
"""PostToolUse(Edit|Write) hook: arm the per-session "code changed" markers.

Drops both change markers (tests + build) when the edited file is a real project
file - inside the payload's cwd and not under the workflow's own .alp-river/
scratch dir. The Stop verifiers gate on these markers, so a chat-only turn (no
Edit/Write) leaves them absent and the end-of-turn checks skip.

Marker existence is the whole signal; content is irrelevant. Always exits 0 and
never prints (PostToolUse stdout would be parsed). Fail-open: any unparseable
payload, missing file_path, non-Edit/Write tool, or path outside cwd is a silent
no-op that arms nothing.
"""

import json
import sys
from pathlib import Path

from verify_shared import CHANGE_MARKER_PREFIXES, session_marker


def should_arm(file_path, cwd):
    """True only for a real project file: inside cwd and not under .alp-river/.

    Resolves symlinks so a link inside cwd pointing outside cwd is excluded, and
    matches ".alp-river" as an exact path component (never a substring).
    """
    try:
        rel = Path(file_path).resolve().relative_to(Path(cwd).resolve())
    except ValueError:
        return False
    return ".alp-river" not in rel.parts


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
        if not should_arm(file_path, cwd):
            return
        session_id = payload.get("session_id") or ""
        # Rendezvous precondition: this session_id must equal the end-of-turn Stop
        # payload's session_id or the reader looks at a different marker path and
        # verification silently no-ops (see session_marker in verify_shared.py). A
        # subagent PostToolUse firing under a different session_id arms the wrong
        # marker.
        for prefix in CHANGE_MARKER_PREFIXES:
            session_marker(prefix, session_id).write_text("1")
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
