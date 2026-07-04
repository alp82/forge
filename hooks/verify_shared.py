"""Shared helpers for the Stop-hook verify gate system (verify-tests.py, verify-build.py).

Both verifiers gate on a per-session "code changed" marker armed by
mark-code-change.py: absent the marker they exit before any command detection or
subprocess. A live, non-converged, cwd-matching, fresh run-state.json for this
session is a further exemption (the change marker survives it), so a multi-step
run pays verification exactly once at convergence.

CHANGE_MARKER_PREFIXES is the single home for the two marker names - the
PostToolUse writer and the two Stop readers all read them from here so they
cannot drift.

Stdlib only. session_marker() carries the session-keyed /tmp convention with a
pid-keyed fallback; live_run_exemption() is the Python twin of
recover-run-state.sh candidate_ok (G1 schema, G2 cwd, G4 mtime, converged-skip),
with one deliberate divergence noted in that function.
"""

import json
import os
import sys
import time
from pathlib import Path

TESTS_CHANGE_PREFIX = "claude-code-changed-tests"
BUILD_CHANGE_PREFIX = "claude-code-changed-build"
CHANGE_MARKER_PREFIXES = (TESTS_CHANGE_PREFIX, BUILD_CHANGE_PREFIX)


def session_marker(prefix, session_id):
    """Session-keyed /tmp marker path for a prefix; pid-keyed when session_id is falsy.

    The pid-keyed fallback never rendezvous across sibling hook processes; real
    payloads always carry session_id.

    Load-bearing precondition (rendezvous): the marker armer (mark-code-change.py
    PostToolUse) and the readers (verify-tests.py / verify-build.py Stop) must key
    off the SAME session_id for the armed marker to be found. If a subagent's
    PostToolUse(Edit|Write) fires with a different session_id than the main
    session's end-of-turn Stop, the reader looks at a different path and
    verification silently no-ops for that Stop.

    Precondition (path): the marker home is hardcoded to /tmp and ignores TMPDIR.
    A non-writable or non-shared /tmp means the marker is never armed
    (mark-code-change.py swallows the write failure) and verification is silently
    skipped - the failure direction is fail-toward-skip, not fail-toward-block.
    """
    if session_id:
        return Path(f"/tmp/.{prefix}-{session_id}")
    return Path(f"/tmp/.{prefix}-fallback-{os.getpid()}")


def silent_pass(*markers):
    """Clear each non-None marker (gate re-arms) and exit 0 with no stdout."""
    for marker in markers:
        if marker is not None:
            marker.unlink(missing_ok=True)
    sys.exit(0)


def read_marker_count(marker):
    """Read the marker as an int retry counter; junk/missing reads as 0 (fresh)."""
    try:
        return int(marker.read_text().strip())
    except (ValueError, OSError):
        return 0


def live_run_exemption(project_root, session_id):
    """True when this session has a fresh, cwd-matching, non-converged run-state.json.

    Python twin of recover-run-state.sh candidate_ok: G1 (schema_version==1 plus
    required route/cwd/mid_run_stage keys), G2 (cwd exact match), G4 (mtime within
    max-age), converged-skip (route empty AND pending_gate empty -> not live). Reads
    ONLY this session's own file (no freshest-scan), so another session's live run
    never suppresses this session's verification.

    One deliberate divergence from candidate_ok: a junk RIVER_STATE_MAX_AGE_SECONDS
    falls back to 86400 here (the shell's :-86400 defaults only on unset/empty), so
    the exemption still evaluates instead of the whole-body except swallowing the
    ValueError. Every failure path fails open toward verification (returns False).

    Exit condition is convergence-OR-age-out, not "runs once at convergence": a run
    abandoned mid-flight never converges, so this keeps returning True (suppressing
    verification for that session) bounded only by the RIVER_STATE_MAX_AGE_SECONDS
    mtime ceiling - once the run-state file ages past that ceiling the exemption
    lapses and verification resumes.
    """
    if not session_id:
        return False
    try:
        state_file = (
            Path(project_root) / ".alp-river" / "runs" / session_id / "run-state.json"
        )
        if not state_file.exists():
            return False
        try:
            max_age = int(os.environ.get("RIVER_STATE_MAX_AGE_SECONDS", "86400"))
        except ValueError:
            max_age = 86400
        if time.time() - state_file.stat().st_mtime > max_age:
            return False
        data = json.loads(state_file.read_text())
        if data.get("schema_version") != 1:
            return False
        if not all(key in data for key in ("route", "cwd", "mid_run_stage")):
            return False
        if data["cwd"] != project_root:
            return False
        route = data.get("route")
        non_converged = (
            any(route) if isinstance(route, list) else bool(route)
        ) or bool(data.get("pending_gate"))
        return non_converged
    except Exception:
        return False
