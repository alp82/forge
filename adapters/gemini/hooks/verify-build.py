#!/usr/bin/env python3
"""Verify gate: build / typecheck the project before allowing a stop (gemini port).

Activates whenever a build/typecheck tool resolves locally for the project and a
per-session change marker (armed by mark-code-change.py) is present - a chat-only
turn exits before any command detection or subprocess. Fires at AfterAgent, end of
turn whenever code changed. Max 1 retry per session.

Conservative by construction: the build/typecheck runs ONLY when its tool is
locally present (no npx-on-miss downloads/hangs). A timeout is treated as a
non-blocking pass-through. For rust/go this checks the compile-error class
(cargo check / go build -o /dev/null) - it does not assert artifact parity.

Stdlib only. Always exits 0 (a failing build is a block decision, not a hook
error). A failing build is signalled by a single {"decision":"block"} JSON
object on stdout - gemini's documented AfterAgent block channel; every pass/skip
branch prints nothing. Building the JSON via json.dumps makes the exit-code
footgun and the jq-injection class structurally impossible.
"""

import json
import os
import shutil

from verify_shared import BUILD_CHANGE_PREFIX, run_verify_gate


def detect_build_cmd(root):
    """First matching build/typecheck command for the project, or None.

    First match wins; the tool must resolve locally or the row is skipped, never
    an npx-on-miss download.
    """
    build_cmd = None
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            scripts = json.loads(pkg.read_text()).get("scripts") or {}
        except (json.JSONDecodeError, OSError):
            scripts = {}
        if scripts.get("build"):
            if (root / "pnpm-lock.yaml").is_file():
                pm = "pnpm"
            elif (root / "yarn.lock").is_file():
                pm = "yarn"
            else:
                pm = "npm"
            build_cmd = [pm, "run", "build"]

    if build_cmd is None and (root / "tsconfig.json").is_file():
        local_tsc = root / "node_modules" / ".bin" / "tsc"
        if os.access(local_tsc, os.X_OK):
            build_cmd = [str(local_tsc), "--noEmit"]
        elif shutil.which("npx"):
            # --no-install: never download; a 127 (tool absent) is a skip below.
            build_cmd = ["npx", "--no-install", "tsc", "--noEmit"]

    if build_cmd is None and (root / "Cargo.toml").is_file() and shutil.which("cargo"):
        build_cmd = ["cargo", "check"]

    if build_cmd is None and (root / "go.mod").is_file() and shutil.which("go"):
        build_cmd = ["go", "build", "-o", "/dev/null", "./..."]

    if build_cmd is None and mypy_configured(root) and shutil.which("mypy"):
        build_cmd = ["mypy", "."]

    return build_cmd


def mypy_configured(root):
    """True when mypy config is present: [tool.mypy] in pyproject, mypy.ini, or [mypy] in setup.cfg."""
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            if "[tool.mypy]" in pyproject.read_text():
                return True
        except OSError:
            pass
    if (root / "mypy.ini").is_file():
        return True
    setup_cfg = root / "setup.cfg"
    if setup_cfg.is_file():
        try:
            if "[mypy]" in setup_cfg.read_text():
                return True
        except OSError:
            pass
    return False


def main():
    run_verify_gate(
        detect_build_cmd,
        retry_prefix="gemini-build-verify",
        change_prefix=BUILD_CHANGE_PREFIX,
        fail_message="Build is failing. Fix it before completing.",
        timeout=150,
    )


if __name__ == "__main__":
    main()
