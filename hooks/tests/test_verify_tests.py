"""Failing (red) tests for hooks/verify-tests.py.

The script under test does NOT exist yet - these tests are intentionally red.
They define the expected behaviour of verify-tests.py, which reads a JSON
payload from stdin and:

  1. Detects a test command (currently: package.json with a `test` script).
  2. Runs the tests in the directory named by payload["cwd"].
  3. On success / no-test-tool / npm-default-placeholder: exits 0 with no
     stdout (silent pass).
  4. On failure: exits 0 but emits a JSON block to stdout with at least
     {"decision": "block", "reason": "Tests are failing..."}.
  5. Caps retries: a second call with the same session_id after a prior
     failure is a silent pass (prints nothing, exits 0).
  6. Respects stop_hook_active: when true, short-circuits immediately
     (silent pass) before running any tests.
  7. rc-127 from the test runner is treated as a skip (silent pass).

ASSUMPTION on package manager: npm is present in this repo's dev environment.
The failing-test package.json uses a POSIX-shell test script so that node is
NOT required to produce the error output.
"""

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

# Path to the script under test (does not exist yet - tests are red by design)
VERIFY_TESTS_PY = Path(__file__).resolve().parents[1] / "verify-tests.py"


def _run_hook(payload_dict, *, env=None):
    """Mirror of the _run_cli pattern used in test_route.py.

    Passes the JSON-serialised payload on stdin and captures stdout/stderr.
    env overrides the subprocess environment (used to restrict PATH in
    tool-presence tests).
    """
    return subprocess.run(
        ["python3", str(VERIFY_TESTS_PY)],
        input=json.dumps(payload_dict),
        capture_output=True,
        text=True,
        env=env,
    )


def _make_failing_tests_dir():
    """Create a temp dir with a package.json whose test script fails and emits
    both a double-quote (") and a backslash (\\) on stderr.

    The script is pure POSIX sh (run via npm test -> sh -c "...") so node
    is not exercised and the output is deterministic.
    """
    d = tempfile.mkdtemp()
    pkg = {
        "name": "test-failing-tests",
        "version": "0.0.1",
        "scripts": {
            # printf emits: FAIL: "test \\ path"
            "test": r'printf "FAIL: \"test \\ path\"\n" >&2; exit 1'
        },
    }
    (Path(d) / "package.json").write_text(json.dumps(pkg))
    return d


# ---------------------------------------------------------------------------
# TC-VT-1  no test manifest -> silent pass
# ---------------------------------------------------------------------------


def test_no_test_command_is_silent_pass():
    """A bare project dir with no recognised test manifest is a silent pass.

    The script must exit 0 and emit nothing to stdout.
    """
    session_id = str(uuid.uuid4())
    marker = Path(f"/tmp/.claude-test-verify-{session_id}")
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
# TC-VT-2  failing tests with special chars -> valid JSON block
# ---------------------------------------------------------------------------


def test_failing_tests_with_special_chars_emits_valid_json_block():
    """A failing test run whose output contains both " and \\ must produce a
    valid JSON block on stdout with decision=="block" and a reason that starts
    with "Tests are failing".

    Pins jq-injection safety and the mandatory block emission on failure.
    """
    assert shutil.which("npm"), "npm required to drive test output"
    session_id = str(uuid.uuid4())
    marker = Path(f"/tmp/.claude-test-verify-{session_id}")
    test_dir = _make_failing_tests_dir()
    try:
        result = _run_hook(
            {"session_id": session_id, "cwd": test_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, (
            f"hook must always exit 0 (Claude hook contract); "
            f"got {result.returncode}; stderr={result.stderr!r}"
        )
        assert (
            result.stdout.strip() != ""
        ), "stdout must be non-empty when tests fail (block decision expected)"
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
        reason = parsed.get("reason", "")
        assert isinstance(reason, str) and reason.startswith("Tests are failing"), (
            f"reason must be a non-empty string starting with 'Tests are failing', "
            f"got {reason!r}"
        )
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        if marker.exists():
            marker.unlink()


# ---------------------------------------------------------------------------
# TC-VT-NPM  npm default placeholder test script -> silent pass
# ---------------------------------------------------------------------------


def test_npm_default_placeholder_test_script_is_silent_pass():
    """The npm default test placeholder (`echo "Error: no test specified" && exit 1`)
    must be recognised as an absent test suite and treated as a silent pass,
    not a test failure.

    Two sub-cases pin the match as a substring/contains check, not exact equality:
      - scripts.test = `echo "Error: no test specified" && exit 1`
      - scripts.test = `echo "Error"` (shorter; must also be a silent pass)
    """
    assert shutil.which("npm"), "npm required to run the test script"
    for script, label in [
        (r'echo "Error: no test specified" && exit 1', "npm-default-full"),
        (r'echo "Error"', "echo-Error-short"),
    ]:
        session_id = str(uuid.uuid4())
        marker = Path(f"/tmp/.claude-test-verify-{session_id}")
        test_dir = tempfile.mkdtemp()
        try:
            pkg = {
                "name": f"test-npm-placeholder-{label}",
                "version": "0.0.1",
                "scripts": {"test": script},
            }
            (Path(test_dir) / "package.json").write_text(json.dumps(pkg))

            result = _run_hook(
                {
                    "session_id": session_id,
                    "cwd": test_dir,
                    "stop_hook_active": False,
                }
            )
            assert result.returncode == 0, (
                f"[{label}] expected returncode 0; "
                f"got {result.returncode}; stderr={result.stderr!r}"
            )
            assert result.stdout.strip() == "", (
                f"[{label}] expected empty stdout (npm placeholder -> silent pass), "
                f"got {result.stdout!r}"
            )
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)
            if marker.exists():
                marker.unlink()


# ---------------------------------------------------------------------------
# TC-VT-ASYM  Cargo.toml only, cargo absent from PATH -> silent pass via rc-127
# ---------------------------------------------------------------------------


def test_cargo_absent_from_path_is_silent_pass():
    """A project with only Cargo.toml but no cargo binary on PATH is a silent
    pass.

    Unlike the build hook (which gates on tool presence), verify-tests ATTEMPTS
    cargo test, receives rc 127 (command not found), and silently skips via the
    rc-127 arm - a different path to the same silent outcome.
    """
    session_id = str(uuid.uuid4())
    marker = Path(f"/tmp/.claude-test-verify-{session_id}")
    test_dir = tempfile.mkdtemp()
    # A fake-bin dir that has python3 (symlinked) but no cargo, so the hook
    # interpreter is reachable while the test runner is absent.
    fake_bin = tempfile.mkdtemp()
    try:
        (Path(test_dir) / "Cargo.toml").write_text(
            '[package]\nname = "test"\nversion = "0.1.0"\nedition = "2021"\n'
        )
        python3_real = shutil.which("python3") or "/usr/bin/python3"
        (Path(fake_bin) / "python3").symlink_to(python3_real)
        restricted_env = {**os.environ, "PATH": fake_bin}

        result = _run_hook(
            {"session_id": session_id, "cwd": test_dir, "stop_hook_active": False},
            env=restricted_env,
        )
        assert result.returncode == 0, (
            f"expected returncode 0 when cargo absent; "
            f"got {result.returncode}; stderr={result.stderr!r}"
        )
        assert (
            result.stdout.strip() == ""
        ), f"expected empty stdout (rc-127 skip arm), got {result.stdout!r}"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        shutil.rmtree(fake_bin, ignore_errors=True)
        if marker.exists():
            marker.unlink()


# ---------------------------------------------------------------------------
# TC-VT-MARKER  pre-seeded garbage marker does not short-circuit
# ---------------------------------------------------------------------------


def test_garbage_marker_does_not_short_circuit():
    """A marker file containing non-numeric text must not crash the hook and
    must not trigger the retry short-circuit.

    The garbage value is not >= 1 when interpreted numerically, so the hook
    must proceed to run the tests, find them failing, and emit a block decision.
    """
    assert shutil.which("npm"), "npm required to drive the failing tests"
    session_id = str(uuid.uuid4())
    marker = Path(f"/tmp/.claude-test-verify-{session_id}")
    test_dir = _make_failing_tests_dir()
    try:
        marker.write_text("garbage")

        result = _run_hook(
            {"session_id": session_id, "cwd": test_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, (
            f"hook must exit 0 even with a garbage marker; "
            f"got {result.returncode}; stderr={result.stderr!r}"
        )
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"stdout is not valid JSON after garbage marker: {exc}; "
                f"raw stdout={result.stdout!r}"
            )
        assert parsed.get("decision") == "block", (
            f"garbage marker must not trigger retry short-circuit; "
            f"expected decision='block', got {parsed.get('decision')!r}"
        )
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        if marker.exists():
            marker.unlink()


# ---------------------------------------------------------------------------
# TC-VT-3  retry cap: second call on the same session_id is a silent pass
# ---------------------------------------------------------------------------


def test_retry_cap_second_call_is_not_blocked():
    """After one block, a second call with the same session_id is a silent pass.

    Flow:
      1. First call -> block (tests fail).
      2. Marker file /tmp/.claude-test-verify-<session_id> must now exist.
      3. Second call (identical payload) -> silent pass (returncode 0, no stdout).
      4. Marker must be absent after the retry-cap exit so the gate re-arms.
    """
    assert shutil.which("npm"), "npm required to drive the failing tests"
    session_id = str(uuid.uuid4())
    marker = Path(f"/tmp/.claude-test-verify-{session_id}")
    test_dir = _make_failing_tests_dir()
    try:
        payload = {
            "session_id": session_id,
            "cwd": test_dir,
            "stop_hook_active": False,
        }

        first = _run_hook(payload)
        assert first.returncode == 0, (
            f"first call: returncode must be 0, got {first.returncode}; "
            f"stderr={first.stderr!r}"
        )
        assert (
            first.stdout.strip() != ""
        ), "first call: stdout must be non-empty (block expected on failing tests)"
        assert marker.exists(), f"marker {marker} must exist after the first block"

        second = _run_hook(payload)
        assert second.returncode == 0, (
            f"second call: returncode must be 0, got {second.returncode}; "
            f"stderr={second.stderr!r}"
        )
        assert (
            second.stdout.strip() == ""
        ), f"second call: stdout must be empty (retry cap), got {second.stdout!r}"
        assert (
            not marker.exists()
        ), f"marker {marker} must be absent after retry-cap exit"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        if marker.exists():
            marker.unlink()


# ---------------------------------------------------------------------------
# TC-VT-4  stop_hook_active=true -> immediate silent pass
# ---------------------------------------------------------------------------


def test_stop_hook_active_true_is_immediate_pass():
    """When stop_hook_active is true the script must exit 0 with no stdout,
    regardless of whether tests would fail.

    The adversarial setup reuses the failing-tests dir so that a missed guard
    would produce a block and fail this test.
    """
    session_id = str(uuid.uuid4())
    marker = Path(f"/tmp/.claude-test-verify-{session_id}")
    test_dir = _make_failing_tests_dir()
    try:
        result = _run_hook(
            {"session_id": session_id, "cwd": test_dir, "stop_hook_active": True}
        )
        assert result.returncode == 0, (
            f"expected returncode 0, got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert (
            result.stdout.strip() == ""
        ), f"expected empty stdout when stop_hook_active=true, got {result.stdout!r}"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        if marker.exists():
            marker.unlink()


# ---------------------------------------------------------------------------
# TC-VT-5  passing tests -> silent pass and no marker left behind
# ---------------------------------------------------------------------------


def test_passing_tests_is_silent_pass_and_leaves_no_marker():
    """A project whose test script succeeds exits 0 with no stdout and leaves
    no marker file on disk.

    Pins the happy path and the invariant that a non-block exit never leaves
    a marker behind.
    """
    assert shutil.which("npm"), "npm required to run the test script"
    session_id = str(uuid.uuid4())
    marker = Path(f"/tmp/.claude-test-verify-{session_id}")
    test_dir = tempfile.mkdtemp()
    try:
        pkg = {
            "name": "test-passing-tests",
            "version": "0.0.1",
            "scripts": {"test": "exit 0"},
        }
        (Path(test_dir) / "package.json").write_text(json.dumps(pkg))

        result = _run_hook(
            {"session_id": session_id, "cwd": test_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, (
            f"expected returncode 0, got {result.returncode}; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert result.stdout.strip() == "", (
            f"expected empty stdout (silent pass on passing tests), "
            f"got {result.stdout!r}"
        )
        assert (
            not marker.exists()
        ), f"marker {marker} must not exist after a passing (non-block) exit"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        if marker.exists():
            marker.unlink()


# ---------------------------------------------------------------------------
# TC-VT-RC127  test runner exits 127 -> silent pass (rc-127 skip arm)
# ---------------------------------------------------------------------------


def test_test_runner_rc127_is_silent_pass():
    """When the test script resolves but the inner binary is not found (exit
    code 127), the hook must treat this as a skip and exit silently.

    Exercises the rc-127 arm without requiring a timeout.
    """
    assert shutil.which("npm"), "npm required to run the test script"
    session_id = str(uuid.uuid4())
    marker = Path(f"/tmp/.claude-test-verify-{session_id}")
    test_dir = tempfile.mkdtemp()
    try:
        pkg = {
            "name": "test-rc127-tests",
            "version": "0.0.1",
            "scripts": {"test": "nonexistent-runner-xyz"},
        }
        (Path(test_dir) / "package.json").write_text(json.dumps(pkg))

        result = _run_hook(
            {"session_id": session_id, "cwd": test_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, (
            f"expected returncode 0 on rc-127 test exit; "
            f"got {result.returncode}; stderr={result.stderr!r}"
        )
        assert (
            result.stdout.strip() == ""
        ), f"expected empty stdout (rc-127 skip arm), got {result.stdout!r}"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        if marker.exists():
            marker.unlink()
