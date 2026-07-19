"""Shared helpers for the AfterAgent stop-gate system (verify-tests.py, verify-build.py,
review-owed.py) - the gemini port.

The verifiers run at AfterAgent (end of turn) and gate on a per-session "code
changed" marker armed by mark-code-change.py: absent the marker they exit
before any command detection or subprocess. run_verify_gate() is the shared
skeleton both verify scripts call; the only per-script differences are the
command detector and the marker/message/timeout parameters. review-owed.py is
a sibling gate on its own marker - it runs no command, so it only borrows the
marker helpers.

CHANGE_MARKER_PREFIXES is the single home for the three marker names - the
AfterTool writer (mark-code-change.py) and every reader import them from
here so they cannot drift. The prefixes are gemini-* (not claude-code-*) so
both harnesses can coexist on one machine with honest, debuggable per-harness
/tmp markers.

Gemini payload notes: session_id and cwd are documented common stdin keys, so
the marker rendezvous and cwd anchoring work unchanged. stop_hook_active is a
Claude field the gemini survey does not mention (RISK-5) - the tolerant read
below treats an absent key as falsy and proceeds; even if gemini offers no
in-block-loop signal, the max-1-retry marker cap makes an infinite AfterAgent loop
structurally impossible (each gate blocks at most once per session).

Stdlib only. session_marker() carries the session-keyed /tmp convention with a
pid-keyed fallback.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

TESTS_CHANGE_PREFIX = "gemini-changed-tests"
BUILD_CHANGE_PREFIX = "gemini-changed-build"
REVIEW_CHANGE_PREFIX = "gemini-changed-review"
CHANGE_MARKER_PREFIXES = (
    TESTS_CHANGE_PREFIX,
    BUILD_CHANGE_PREFIX,
    REVIEW_CHANGE_PREFIX,
)


def session_marker(prefix, session_id):
    """Session-keyed /tmp marker path for a prefix; pid-keyed when session_id is falsy.

    The pid-keyed fallback never rendezvous across sibling hook processes; real
    payloads always carry session_id.

    Load-bearing precondition (rendezvous): the marker armer (mark-code-change.py
    AfterTool) and the stop-gate readers must key off the SAME session_id for
    the armed marker to be found. If a gemini subagent's AfterTool fires with
    its own session_id rather than the main session's, the reader looks at a
    different path and the gate silently no-ops for that AfterAgent turn (RISK-8 - the same
    accepted caveat as Claude Code; review-owed's disk-mtime settling is
    session-agnostic and mitigates the review gate's share of it).

    Precondition (path): the marker home is hardcoded to /tmp and ignores TMPDIR.
    A non-writable or non-shared /tmp means the marker is never armed
    (mark-code-change.py swallows the write failure) and the gates are silently
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


def run_verify_gate(detect_cmd, *, retry_prefix, change_prefix, fail_message, timeout):
    """Shared gate skeleton for the AfterAgent verifiers.

    Fires at AfterAgent (end of turn) whenever code changed. detect_cmd(root)
    returns the command list or None. Max 1 retry per session.
    """
    # Completion gate (fail-open bias): unparseable payload -> let the agent finish.
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

    marker = session_marker(retry_prefix, sid)
    change_marker = session_marker(change_prefix, sid)

    # Avoid re-blocking inside an already-blocked AfterAgent loop (RISK-5: absent on
    # gemini reads as falsy and the retry cap below is the structural loop-breaker).
    if stop_hook_active is True or stop_hook_active == "true":
        silent_pass(marker)

    # Chat-only fast path: no edit-tool call armed the change marker this turn,
    # so exit before the retry-cap read and any command detection or subprocess.
    if not change_marker.exists():
        sys.exit(0)

    # Already retried once - let the agent finish, the review wave catches it.
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
