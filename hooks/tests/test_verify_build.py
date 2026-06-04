"""Failing (red) tests for hooks/verify-build.sh.

The script under test does NOT exist yet - these tests are intentionally red.
They define the expected behaviour of verify-build.sh, which reads a JSON
payload from stdin and:

  1. Detects a build command (currently: package.json with a `build` script).
  2. Runs the build in the directory named by payload["cwd"].
  3. On success / no-build-tool: exits 0 with no stdout (silent pass).
  4. On failure: exits 0 but emits a JSON block to stdout with at least
     {"decision": "block", "reason": "<...>"}.
  5. Caps retries: a second call with the same session_id after a prior
     failure is a silent pass (prints nothing, exits 0).
  6. Respects stop_hook_active: when true, short-circuits immediately
     (silent pass) before running any build.

ASSUMPTION on package manager: npm is present in this repo's dev environment
(confirmed: `which npm` resolves in CI / local). The failing-build package.json
uses a POSIX-shell build script so that node is NOT required to produce the
error output - `npm run build` invokes sh to execute the script, which uses
`printf` to emit special characters (double-quote and backslash) and then
`exit 1`.  This drives the jq-injection-safety path without depending on node.
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

# Path to the script under test (does not exist yet - tests are red by design)
VERIFY_BUILD_SH = Path(__file__).resolve().parents[1] / "verify-build.sh"


def _run_hook(payload_dict):
    """Mirror of the _run_cli pattern used in test_route.py.

    Passes the JSON-serialised payload on stdin and captures stdout/stderr.
    """
    return subprocess.run(
        ["bash", str(VERIFY_BUILD_SH)],
        input=json.dumps(payload_dict),
        capture_output=True,
        text=True,
    )


def _make_failing_build_dir():
    """Create a temp dir with a package.json whose build script fails and emits
    both a double-quote (") and a backslash (\\) on stderr.

    The script is pure POSIX sh (run via npm run build -> sh -c "...") so node
    is not exercised and the output is deterministic regardless of the Node
    version present.
    """
    d = tempfile.mkdtemp()
    pkg = {
        "name": "test-failing-build",
        "version": "0.0.1",
        "scripts": {
            # printf emits: oops: " \\ /a/b
            # The \" and \\ in the JSON string become literal " and \ in the script text.
            # npm run build executes this via sh, so no node binary is needed.
            "build": r'printf "oops: \" \\ /a/b\n" >&2; exit 1'
        },
    }
    (Path(d) / "package.json").write_text(json.dumps(pkg))
    return d


# ---------------------------------------------------------------------------
# TC-VB-1  no build command -> silent pass
# ---------------------------------------------------------------------------


def test_no_build_command_is_silent_pass():
    """A bare project dir with no recognised build manifest is a silent pass.

    Precondition: temp dir contains none of package.json / tsconfig.json /
    Cargo.toml / go.mod / pyproject.toml, so no build command is detected.
    The script must exit 0 and emit nothing to stdout.
    """
    session_id = "test-vb-1"
    marker = Path(f"/tmp/.claude-build-verify-{session_id}")
    bare_dir = tempfile.mkdtemp()
    try:
        result = _run_hook(
            {"session_id": session_id, "cwd": bare_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, (
            f"expected returncode 0, got {result.returncode}; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert (
            result.stdout.strip() == ""
        ), f"expected empty stdout (silent pass), got {result.stdout!r}"
    finally:
        shutil.rmtree(bare_dir, ignore_errors=True)
        if marker.exists():
            marker.unlink()


# ---------------------------------------------------------------------------
# TC-VB-2  failing build with special chars -> valid JSON block  [PINS BOTH BUGS]
# ---------------------------------------------------------------------------


def test_failing_build_with_special_chars_emits_valid_json_block():
    """A failing build whose output contains both " and \\ must produce a valid
    JSON block on stdout with decision==\"block\".

    This test pins two bugs simultaneously:
      - Bug A (jq injection): unescaped " or \\ in build output breaks the
        jq command the hook uses to construct the JSON reason string, making
        stdout unparseable.
      - Bug B (missing block): the script must actually emit JSON when the
        build fails, not stay silent.

    The package.json build script uses printf so node is not needed to produce
    the special-char output.
    """
    assert shutil.which(
        "npm"
    ), "npm required to drive build output through the jq reason path"
    session_id = "test-vb-2"
    marker = Path(f"/tmp/.claude-build-verify-{session_id}")
    build_dir = _make_failing_build_dir()
    try:
        result = _run_hook(
            {"session_id": session_id, "cwd": build_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, (
            f"hook must always exit 0 (Claude hook contract); "
            f"got {result.returncode}; stderr={result.stderr!r}"
        )
        assert (
            result.stdout.strip() != ""
        ), "stdout must be non-empty when build fails (block decision expected)"
        # This is the jq-injection-safety assertion: json.loads must not raise
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"stdout is not valid JSON (jq-injection bug): {exc}; "
                f"raw stdout={result.stdout!r}"
            )
        assert (
            parsed.get("decision") == "block"
        ), f"parsed[\"decision\"] must be 'block', got {parsed.get('decision')!r}"
        assert (
            isinstance(parsed.get("reason"), str) and parsed["reason"]
        ), f"parsed[\"reason\"] must be a non-empty string, got {parsed.get('reason')!r}"
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)
        if marker.exists():
            marker.unlink()


# ---------------------------------------------------------------------------
# TC-VB-3  retry cap: second call on the same session_id is a silent pass
# ---------------------------------------------------------------------------


def test_retry_cap_second_call_is_not_blocked():
    """After one block, a second call with the same session_id is a silent pass.

    Flow:
      1. First call -> block (build fails).
      2. Marker file /tmp/.claude-build-verify-<session_id> must now exist,
         proving the failure was registered.
      3. Second call (identical payload) -> silent pass (returncode 0, no stdout).
    """
    assert shutil.which(
        "npm"
    ), "npm required to drive build output through the jq reason path"
    session_id = "test-vb-3"
    marker = Path(f"/tmp/.claude-build-verify-{session_id}")
    build_dir = _make_failing_build_dir()
    try:
        payload = {
            "session_id": session_id,
            "cwd": build_dir,
            "stop_hook_active": False,
        }

        # First call: expect a block
        first = _run_hook(payload)
        assert first.returncode == 0, (
            f"first call: returncode must be 0, got {first.returncode}; "
            f"stderr={first.stderr!r}"
        )
        assert (
            first.stdout.strip() != ""
        ), "first call: stdout must be non-empty (block expected on failing build)"

        # Marker must exist after the first block
        assert (
            marker.exists()
        ), f"marker {marker} must exist after the first block, proving the failure registered"

        # Second call: retry cap engaged, must be silent pass
        second = _run_hook(payload)
        assert second.returncode == 0, (
            f"second call: returncode must be 0, got {second.returncode}; "
            f"stderr={second.stderr!r}"
        )
        assert (
            second.stdout.strip() == ""
        ), f"second call: stdout must be empty (retry cap), got {second.stdout!r}"
        # Marker must be cleared on the retry-cap (non-block) exit so the gate re-arms
        assert (
            not marker.exists()
        ), f"marker {marker} must be absent after retry-cap exit (non-block exit must clear marker)"
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)
        if marker.exists():
            marker.unlink()


# ---------------------------------------------------------------------------
# TC-VB-4  stop_hook_active=true -> immediate silent pass
# ---------------------------------------------------------------------------


def test_stop_hook_active_true_is_immediate_pass():
    """When stop_hook_active is true the script must exit 0 with no stdout,
    regardless of whether a build would fail.

    The adversarial setup reuses the failing-build dir: if the guard is
    ignored the build fires, the block JSON appears on stdout, and the test
    fails - proving the guard is load-bearing.
    """
    session_id = "test-vb-4"
    marker = Path(f"/tmp/.claude-build-verify-{session_id}")
    build_dir = _make_failing_build_dir()
    try:
        result = _run_hook(
            {"session_id": session_id, "cwd": build_dir, "stop_hook_active": True}
        )
        assert result.returncode == 0, (
            f"expected returncode 0, got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert (
            result.stdout.strip() == ""
        ), f"expected empty stdout when stop_hook_active=true, got {result.stdout!r}"
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)
        if marker.exists():
            marker.unlink()


# ---------------------------------------------------------------------------
# TC-VB-5  passing build -> silent pass and no marker left behind
# ---------------------------------------------------------------------------


def test_passing_build_is_silent_pass_and_leaves_no_marker():
    """A project whose build script succeeds exits 0 with no stdout and leaves
    no marker file on disk.

    This pins the happy path (build runs AND succeeds) and the invariant that a
    non-block exit never leaves a marker behind.  No other test exercises a
    successful build run.
    """
    assert shutil.which("npm"), "npm required to run the build script"
    session_id = "test-vb-5"
    marker = Path(f"/tmp/.claude-build-verify-{session_id}")
    build_dir = tempfile.mkdtemp()
    try:
        pkg = {
            "name": "test-passing-build",
            "version": "0.0.1",
            "scripts": {"build": "exit 0"},
        }
        (Path(build_dir) / "package.json").write_text(json.dumps(pkg))

        result = _run_hook(
            {"session_id": session_id, "cwd": build_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, (
            f"expected returncode 0, got {result.returncode}; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert result.stdout.strip() == "", (
            f"expected empty stdout (silent pass on successful build), "
            f"got {result.stdout!r}"
        )
        assert (
            not marker.exists()
        ), f"marker {marker} must not exist after a passing (non-block) exit"
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)
        if marker.exists():
            marker.unlink()
