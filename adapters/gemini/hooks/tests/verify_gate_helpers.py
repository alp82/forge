"""Shared test helpers for the Stop-hook verify gates (verify-tests.py,
verify-build.py).

The two gate suites (test_verify_tests.py, test_verify_build.py) drive their
hook the same way: arm a per-session change marker, then run the hook with a
JSON payload on stdin. The only differences are the change-marker prefix and
the hook script path, so those are parameters here. This is a pure DRY
extraction - behaviour is identical to the per-suite copies these replaced.
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
