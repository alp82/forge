#!/usr/bin/env python3
"""Stop gate: code changed this session, so a review wave is owed.

The one duty of the old deterministic router that no prose flow can replace:
knowing the session isn't done. mark-code-change.py arms the review marker on
every real project edit and clears it when a lens findings file
(`findings-<lens>.md` in a `.forge/` run dir) is written - both the forge
review wave and standalone /crossfire write those. If the marker is still
armed at Stop, the change was never reviewed: block once and say so.

No command runs here - the block message IS the enforcement. Max 1 block per
session: at the cap the gate clears both markers and stands down (new edits
re-arm it). Respects stop_hook_active so an already-blocked Stop loop is never
re-blocked.

Stdlib only. Always exits 0 (Claude hook contract). The block is a single JSON
object on stdout; every pass/skip branch prints nothing.
"""

import json
import sys

from verify_shared import (
    REVIEW_CHANGE_PREFIX,
    read_marker_count,
    session_marker,
    silent_pass,
)

RETRY_PREFIX = "claude-review-owed"

BLOCK_REASON = (
    "Code changed this session but no review ran over it. Fire the review wave "
    "- /crossfire over the change, or finish the forge run's review stage - "
    "before completing. If a review truly does not apply, tell the user why "
    "instead of stopping silently."
)


def main():
    # Fail-open bias: unparseable payload -> let Claude finish.
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    sid = payload.get("session_id") or ""
    stop_hook_active = payload.get("stop_hook_active")

    retry_marker = session_marker(RETRY_PREFIX, sid)
    review_marker = session_marker(REVIEW_CHANGE_PREFIX, sid)

    # Inside an already-blocked Stop loop: stand down for this turn, keep the
    # review debt armed for the next one.
    if stop_hook_active is True or stop_hook_active == "true":
        silent_pass(retry_marker)

    if not review_marker.exists():
        sys.exit(0)

    # Already blocked once this session - give up cleanly, clear the debt.
    if read_marker_count(retry_marker) >= 1:
        silent_pass(retry_marker, review_marker)

    retry_marker.write_text("1")
    print(json.dumps({"decision": "block", "reason": BLOCK_REASON}))
    sys.exit(0)


if __name__ == "__main__":
    main()
