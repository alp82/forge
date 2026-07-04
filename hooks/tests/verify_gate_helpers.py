"""Shared test helpers for the Stop-hook verify gates (verify-tests.py,
verify-build.py).

The two gate suites (test_verify_tests.py, test_verify_build.py) drive their
hook the same way: arm a per-session change marker, optionally write a
run-state.json fixture, then run the hook with a JSON payload on stdin. The
only differences are the change-marker prefix and the hook script path, so
those are parameters here. This is a pure DRY extraction - behaviour is
identical to the per-suite copies these replaced.
"""

import json
import subprocess
from pathlib import Path


def change_marker_path(prefix, session_id):
    """PostToolUse change-marker path for a prefix and session."""
    return Path(f"/tmp/.{prefix}-{session_id}")


def arm_change_marker(prefix, session_id):
    """Create the PostToolUse change marker so the gate treats this session as
    having code changes to verify since the last check.
    """
    marker = change_marker_path(prefix, session_id)
    marker.write_text("1")
    return marker


def write_run_state(cwd_str, session_id, **overrides):
    """Write <cwd>/.alp-river/runs/<session_id>/run-state.json for live-run
    exemption tests.

    Canonical defaults: schema_version=1, cwd=cwd_str, route=["code"],
    mid_run_stage="code-implementer", no pending_gate. Mirrors write_state in
    test_recover_run_state.py; mtime (freshness) is set by the caller via
    os.utime, not a written_at field.
    """
    runs_dir = Path(cwd_str) / ".alp-river" / "runs" / session_id
    runs_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "schema_version": 1,
        "run_id": session_id,
        "cwd": cwd_str,
        "route": ["code"],
        "mid_run_stage": "code-implementer",
    }
    state.update(overrides)
    state_file = runs_dir / "run-state.json"
    state_file.write_text(json.dumps(state), encoding="utf-8")
    return state_file


def run_hook(hook_path, payload_dict, *, env=None):
    """Mirror of the _run_cli pattern used in test_route.py.

    Passes the JSON-serialised payload on stdin and captures stdout/stderr.
    env overrides the subprocess environment (used to restrict PATH in
    tool-presence tests).
    """
    return subprocess.run(
        ["python3", str(hook_path)],
        input=json.dumps(payload_dict),
        capture_output=True,
        text=True,
        env=env,
    )
