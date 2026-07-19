#!/usr/bin/env python3
"""Verify gate: run the project's tests before allowing a stop (gemini port).

Activates whenever the project has a detectable test command and a per-session
change marker (armed by mark-code-change.py) is present - a chat-only turn exits
before any command detection or subprocess. Fires at AfterAgent (end of turn)
whenever code changed. Max 1 retry per session.

Stdlib only. Always exits 0 (a failing suite is a block decision, not a hook
error). A failing suite is signalled by a single {"decision":"block"} JSON
object on stdout - gemini's documented AfterAgent block channel; every pass/skip
branch prints nothing. Building the JSON via json.dumps makes the exit-code
footgun and the jq-injection class structurally impossible.
"""

import json
import re
import shutil

from verify_shared import TESTS_CHANGE_PREFIX, run_verify_gate


def detect_test_cmd(root):
    """First matching test command for the project, or None. First match wins."""
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

    return test_cmd


def main():
    run_verify_gate(
        detect_test_cmd,
        retry_prefix="gemini-test-verify",
        change_prefix=TESTS_CHANGE_PREFIX,
        fail_message="Tests are failing. Fix them before completing.",
        timeout=120,
    )


if __name__ == "__main__":
    main()
