#!/usr/bin/env python3
"""Stop gate: code changed this session, so a review wave is owed (codex port).

The one duty of the old deterministic router that no prose flow can replace:
knowing the session isn't done. mark-code-change.py arms the review marker on
every real project edit; the debt is settled here, at Stop, when a lens
findings file (`findings-<lens>.md` in a `.forge/` run dir) postdates that last
edit - both the forge review wave and standalone crossfire write those.

Settling is checked here, not at write time, on purpose. The findings files are
written by review *subagents*, usually via the shell tool and always under a
subagent session_id - so a PostToolUse clearer neither fires nor rendezvous
with the main session's marker. This Stop gate runs under the main session_id
and reads the files off disk, so it is agnostic to both how the findings were
written and by whom. The mtime comparison (findings newer than the marker) is
what keeps "review then edit again" honest: stale findings from before the
last change do not settle.

If no findings postdate the change, it was never reviewed: block once and say
so. No command runs here - the block message IS the enforcement. Max 1 block
per session: at the cap the gate clears both markers and stands down (new edits
re-arm it). Respects stop_hook_active so an already-blocked Stop loop is never
re-blocked (RISK-5: codex may never send it; the retry cap is the structural
loop-breaker either way).

Stdlib only. Always exits 0 (a block is a decision, not a hook error). The
block is a single {"decision":"block"} JSON object on stdout - codex's
documented Stop block channel; every pass/skip branch prints nothing.
"""

import json
import sys
from pathlib import Path

from verify_shared import (
    REVIEW_CHANGE_PREFIX,
    read_marker_count,
    session_marker,
    silent_pass,
)

RETRY_PREFIX = "codex-review-owed"

BLOCK_REASON = (
    "Code changed this session but no review ran over it. Fire the review wave "
    "- crossfire over the change, or finish the forge run's review stage - "
    "before completing. If a review truly does not apply, tell the user why "
    "instead of stopping silently."
)


def review_ran_since(review_marker, cwd):
    """True when a lens findings file postdates the last code change.

    The review marker's mtime is the time of the last armed edit (mark-code-
    change.py rewrites it on every project edit). A `findings-<lens>.md` under a
    `.forge/` run dir with a newer mtime is the deterministic "a wave ran after
    the change" signal - written by the forge wave or standalone crossfire,
    regardless of tool or session_id.

    Scoping is by mtime ordering alone: the scan sweeps the whole `.forge/` tree
    (gitignored, so a branch checkout never resets these mtimes) and any findings
    newer than the marker counts. Honest for the normal case (a wave spans
    seconds after the edit) and for review-then-edit-again (a later edit re-arms
    the marker past the old findings). The one gap left open: an edit made *while
    a prior wave is still running* can be settled by that wave's just-later
    findings - acceptable, as it needs an interleaved edit-during-review and only
    skips one extra wave.

    Every failure path declines to settle so the gate stays fail-toward-block:
    a bad marker, a missing `.forge/`, or any error walking the tree or stat-ing
    a findings file (unreadable subdir, symlink loop, dangling link) all return
    False - block and ask for re-review rather than settle on shaky evidence.
    """
    try:
        marker_mtime = review_marker.stat().st_mtime
        forge = (Path(cwd) if cwd else Path.cwd()) / ".forge"
        if not forge.is_dir():
            return False
        for findings in forge.rglob("findings-*.md"):
            if findings.stat().st_mtime > marker_mtime:
                return True
    except OSError:
        return False
    return False


def main():
    # Fail-open bias: unparseable payload -> let the agent finish.
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    sid = payload.get("session_id") or ""
    cwd = payload.get("cwd") or ""
    stop_hook_active = payload.get("stop_hook_active")

    retry_marker = session_marker(RETRY_PREFIX, sid)
    review_marker = session_marker(REVIEW_CHANGE_PREFIX, sid)

    # Inside an already-blocked Stop loop: stand down for this turn, keep the
    # review debt armed for the next one.
    if stop_hook_active is True or stop_hook_active == "true":
        silent_pass(retry_marker)

    if not review_marker.exists():
        sys.exit(0)

    # A review wave whose findings postdate the change settles the debt.
    if review_ran_since(review_marker, cwd):
        silent_pass(retry_marker, review_marker)

    # Already blocked once this session - give up cleanly, clear the debt.
    if read_marker_count(retry_marker) >= 1:
        silent_pass(retry_marker, review_marker)

    retry_marker.write_text("1")
    print(json.dumps({"decision": "block", "reason": BLOCK_REASON}))
    sys.exit(0)


if __name__ == "__main__":
    main()
