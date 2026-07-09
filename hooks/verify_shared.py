"""Shared helpers for the verify gate system (verify-tests.py, verify-build.py).

Both verifiers run at Stop (end of turn) and at SubagentStop (an implementation
stage stops). They gate on a per-session "code changed" marker armed by
mark-code-change.py: absent the marker they exit before any command detection or
subprocess. run_verify_gate() is the shared skeleton both scripts call; the only
per-script differences are the command detector and the marker/message/timeout
parameters.

red_window() decides whether verification must WAIT (True = inside the
pre-implementation window, skip). It has two branches:
  - agent branch (SubagentStop, agent_type given): the window is read off the
    STOPPING stage alone. A code-implementer or fixer stop closes it (verify
    now); every other stage - test-author, reviewers, planners, unknown, or an
    empty agent_type - leaves it open (skip, so deliberately-red TDD tests never
    block). Scope-stripped base-name membership: `alp-river:fixer` reduces to
    `fixer`. Run-state is deliberately NOT consulted: at the instant an
    implementer stops the orchestrator has not yet published #code-written, so
    the state branch would read one stage stale and wrongly skip.
  - state branch (Stop, agent_type is None): a live, fresh, cwd-matching,
    schema-valid, own-session run-state.json opens the window while its `live`
    list has NOT yet published code-written. Every state-validity failure
    (missing/stale/converged/cwd-mismatch/invalid/missing-key/sibling-session)
    fails open toward verification (returns False, verify - the no-pipeline
    direct edit MUST verify). Inside a valid live run a missing or non-list
    `live` reads as an open window (skip - a red-test turn must never block).

The state branch's guards remain the Python twin of recover-run-state.sh
candidate_ok (G1 schema, G2 cwd, G4 mtime, converged-skip); the one deliberate
divergence - a junk RIVER_STATE_MAX_AGE_SECONDS falls back to 86400 here where
the shell defaults only on unset/empty - is preserved. Only the final return
condition (code-written membership) is new.

run_verify_gate() keeps the retry cap EVENT-NAMESPACED: a SubagentStop gate keys
its cap off `<retry_prefix>-sub-<sid>`, the Stop gate off `<retry_prefix>-<sid>`.
A subagent reports the MAIN session_id at SubagentStop and a SubagentStop block
can deliver its feedback while termination proceeds anyway, so a shared retry key
would let one retry burned at SubagentStop push the later Stop gate straight to
its cap and ship red code at end of turn. The change marker stays SHARED across
events - it is the Edit/Write rendezvous and must survive from a subagent's Edit
to the main Stop.

CHANGE_MARKER_PREFIXES is the single home for the two marker names - the
PostToolUse writer and the two readers all read them from here so they cannot
drift.

Residual, named honestly: a run abandoned pre-#code-written still suppresses the
Stop gate until the run-state mtime ceiling lapses (during a milestone loop that
includes turns where increment code HAS landed but the signal is HARD-withheld
until #milestones-complete). The SubagentStop gate is untouched by run-state, and
post-#code-written abandonment no longer suppresses anything - the old 24h
blanket hole is narrowed, not relocated.

Stdlib only. session_marker() carries the session-keyed /tmp convention with a
pid-keyed fallback.
"""

import json
import os
import subprocess
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


IMPLEMENTATION_WRITERS = frozenset({"code-implementer", "fixer"})


def red_window(project_root, session_id, agent_type=None):
    """True means "inside the pre-implementation red window: verification must wait".

    agent branch (agent_type is not None, the SubagentStop site): scope-strip to
    the base name and return `base not in IMPLEMENTATION_WRITERS`. So
    code-implementer/fixer -> False (verify now); test-author, reviewers,
    planners, unknown, or an empty agent_type -> True (skip). Run-state is
    deliberately not consulted.

    state branch (agent_type is None, the Stop site): the Python twin of
    recover-run-state.sh candidate_ok. Every state-validity failure - falsy
    session_id, missing file, stale mtime, bad schema/keys, cwd mismatch,
    converged, or any exception - fails open toward verification (False). Past
    every guard (a valid, fresh, own-session, live run): `live = data.get("live")`,
    a missing or non-list value treated as `[]`, return "code-written" not in
    live (an open window skips, a red-test turn must never block).
    """
    if agent_type is not None:
        base = agent_type.rsplit(":", 1)[-1]
        return base not in IMPLEMENTATION_WRITERS

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
        if not non_converged:
            return False
        live = data.get("live")
        if not isinstance(live, list):
            live = []
        return "code-written" not in live
    except Exception:
        return False


def run_verify_gate(detect_cmd, *, retry_prefix, change_prefix, fail_message, timeout):
    """Shared gate skeleton for the Stop and SubagentStop verifiers.

    Fires at SubagentStop when an implementation stage stops and at Stop at end of
    turn once code has landed (or when no run is live); a deliberately-red TDD
    turn never blocks. detect_cmd(root) returns the command list or None.
    """
    # Completion gate (fail-open bias): unparseable payload -> let Claude finish.
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    sid = payload.get("session_id") or ""
    cwd = payload.get("cwd") or ""
    stop_hook_active = payload.get("stop_hook_active")

    # Anchor in the working directory (cwd from hook payload, fall back to getcwd).
    project_root = cwd or os.getcwd()
    if not os.path.isdir(project_root):
        sys.exit(0)
    root = Path(project_root)

    # Event-namespaced retry marker (derived before the markers so the SubagentStop
    # cap never collides with the Stop cap); the change marker stays shared.
    agent_kind = (
        (payload.get("agent_type") or "")
        if payload.get("hook_event_name") == "SubagentStop"
        else None
    )
    if agent_kind is not None:
        marker = session_marker(retry_prefix + "-sub", sid)
    else:
        marker = session_marker(retry_prefix, sid)
    change_marker = session_marker(change_prefix, sid)

    # Avoid re-blocking inside an already-blocked Stop loop.
    if stop_hook_active is True or stop_hook_active == "true":
        silent_pass(marker)

    # Chat-only fast path: no Edit/Write armed the change marker this turn, so
    # exit before the retry-cap read and any command detection or subprocess.
    if not change_marker.exists():
        sys.exit(0)

    # Red window: inside the pre-implementation window verification waits. The
    # change marker survives untouched, exactly like the old exemption path.
    if red_window(project_root, sid, agent_type=agent_kind):
        sys.exit(0)

    # Already retried once - let Claude finish, the correctness-reviewer catches it.
    if read_marker_count(marker) >= 1:
        silent_pass(marker)

    cmd = detect_cmd(root)
    if cmd is None:
        silent_pass(marker, change_marker)

    # Run the command. capture_output keeps child output off the hook's own stdout
    # (STDOUT PURITY); a non-failing branch must print nothing.
    try:
        completed = subprocess.run(
            cmd,
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
        rc = completed.returncode
        out = completed.stdout or ""
    except subprocess.TimeoutExpired:
        rc, out = 124, ""
    except FileNotFoundError:
        rc, out = 127, ""

    # 127 = tool not resolvable, 124 = timeout - treat as a skip, never block.
    if rc in (124, 127):
        silent_pass(marker, change_marker)

    if rc != 0:
        marker.write_text(str(read_marker_count(marker) + 1))
        last30 = "\n".join(out.splitlines()[-30:])
        reason = fail_message + "\n\n```\n" + last30 + "\n```"
        print(json.dumps({"decision": "block", "reason": reason}))
        sys.exit(0)

    # Green - clean up both markers.
    silent_pass(marker, change_marker)
