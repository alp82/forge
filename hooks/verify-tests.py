#!/usr/bin/env python3
"""Stop hook: verify tests pass before allowing Claude to finish.

Activates whenever the project has a detectable test command.
Max 1 retry per session to prevent infinite loops.

Gated on a per-session change marker (armed by mark-code-change.py): absent it,
a chat-only turn exits before any command detection or subprocess. A live,
non-converged run-state.json for this session is a further exemption so a
multi-step run verifies exactly once at convergence.

Stdlib only. Always exits 0 (Claude hook contract). A failing suite is signalled
by a single JSON block on stdout; every pass/skip branch prints nothing. Building
the JSON via json.dumps makes the exit-code footgun and the jq-injection class
structurally impossible.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from verify_shared import (
    TESTS_CHANGE_PREFIX,
    live_run_exemption,
    read_marker_count,
    session_marker,
    silent_pass,
)


def main():
    # Completion gate (fail-open bias): unparseable payload -> let Claude finish.
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    session_id = payload.get("session_id") or ""
    cwd = payload.get("cwd") or ""
    stop_hook_active = payload.get("stop_hook_active")

    # Anchor in the working directory (cwd from hook payload, fall back to getcwd).
    project_root = cwd or os.getcwd()
    if not os.path.isdir(project_root):
        sys.exit(0)
    root = Path(project_root)

    # Retry tracking: session-keyed marker so "max 1 retry" survives across
    # invocations in the same Claude session. Fall back to per-invocation when
    # session_id is unavailable.
    marker = session_marker("claude-test-verify", session_id)
    change_marker = session_marker(TESTS_CHANGE_PREFIX, session_id)

    # Avoid re-blocking inside an already-blocked Stop loop.
    if stop_hook_active is True or stop_hook_active == "true":
        silent_pass(marker)

    # Chat-only fast path: no Edit/Write armed the change marker this turn, so
    # exit before the retry-cap read and any command detection or subprocess.
    # Leave both markers untouched.
    if not change_marker.exists():
        sys.exit(0)

    # Mid-run exemption: a live, non-converged run-state for this session means
    # verification waits and runs once at convergence. The change marker survives.
    if live_run_exemption(project_root, session_id):
        sys.exit(0)

    # Already retried once - let Claude finish, the correctness-reviewer catches it.
    if read_marker_count(marker) >= 1:
        silent_pass(marker)

    # Detect a test command. First match wins.
    test_cmd = None
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            pkg_text = pkg.read_text()
        except OSError:
            pkg_text = ""
        if '"test"' in pkg_text:
            try:
                test_script = (json.loads(pkg_text).get("scripts") or {}).get(
                    "test"
                ) or ""
            except (json.JSONDecodeError, ValueError):
                test_script = ""
            # Skip the npm default placeholder (echo "Error: no test specified").
            if test_script and not re.search(r"echo.*Error", test_script):
                test_cmd = ["npm", "test"]

    if test_cmd is None and (root / "pyproject.toml").is_file():
        try:
            has_pytest = "pytest" in (root / "pyproject.toml").read_text()
        except OSError:
            has_pytest = False
        if has_pytest or (root / "tests").is_dir():
            if shutil.which("uv"):
                test_cmd = ["uv", "run", "pytest", "--tb=short", "-q"]
            elif shutil.which("pytest"):
                test_cmd = ["pytest", "--tb=short", "-q"]

    if test_cmd is None and (root / "Cargo.toml").is_file():
        # No which-gate: attempt unconditionally; a missing cargo yields rc 127 -> skip.
        test_cmd = ["cargo", "test"]

    if test_cmd is None and (root / "go.mod").is_file():
        test_cmd = ["go", "test", "./..."]

    # No test command found - don't block.
    if test_cmd is None:
        silent_pass(marker, change_marker)

    # Run tests. capture_output keeps child output off the hook's own stdout
    # (STDOUT PURITY); a non-failing branch must print nothing.
    try:
        completed = subprocess.run(
            test_cmd,
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=120,
        )
        rc = completed.returncode
        out = completed.stdout or ""
    except subprocess.TimeoutExpired:
        rc, out = 124, ""
    except FileNotFoundError:
        rc, out = 127, ""

    # 127 = test runner not resolvable, 124 = timeout - treat as a skip, never block.
    if rc in (124, 127):
        silent_pass(marker, change_marker)

    if rc != 0:
        marker.write_text(str(read_marker_count(marker) + 1))
        last30 = "\n".join(out.splitlines()[-30:])
        reason = (
            "Tests are failing. Fix them before completing.\n\n```\n" + last30 + "\n```"
        )
        print(json.dumps({"decision": "block", "reason": reason}))
        sys.exit(0)

    # Tests passed - clean up.
    silent_pass(marker, change_marker)


if __name__ == "__main__":
    main()
