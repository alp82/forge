"""Failing (red) tests for hooks/verify-tests.py.

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

CHANGE-MARKER GATE (RED - the gate does not exist yet in hooks/verify-tests.py):
verification only RUNS when a PostToolUse change marker
/tmp/.claude-code-changed-tests-<session_id> is present (armed by
hooks/mark-code-change.py, which also does not exist yet - see
test_mark_code_change.py). Absent the marker, the hook must silently pass
before even detecting a test command, regardless of whether tests would fail.
A block leaves the change marker in place (re-verification stays armed); any
silent-pass branch that actually ran verification (or determined there was
nothing to verify) CLEARS the change marker.

At Stop the armed change marker alone decides - verification always runs.

Pre-existing tests below arm the tests change marker in setup (via
_arm_change_marker) and clean it up in finally; the bare-dir / no-test-command
test is left unarmed since a silent pass is the correct outcome either way.
"""

import json
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path

from verify_gate_helpers import arm_change_marker, change_marker_path, run_hook

# Path to the script under test (does not exist yet - tests are red by design)
VERIFY_TESTS_PY = Path(__file__).resolve().parents[1] / "verify-tests.py"

# The tests-gate change-marker prefix; the shared helpers are parametrized by it.
CHANGE_PREFIX = "claude-code-changed-tests"


def _change_marker_path(session_id):
    return change_marker_path(CHANGE_PREFIX, session_id)


def _arm_change_marker(session_id):
    return arm_change_marker(CHANGE_PREFIX, session_id)


def _run_hook(payload_dict, *, env=None):
    return run_hook(VERIFY_TESTS_PY, payload_dict, env=env)


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
    change_marker = _arm_change_marker(session_id)
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
        if change_marker.exists():
            change_marker.unlink()


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
        change_marker = _arm_change_marker(session_id)
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
            if change_marker.exists():
                change_marker.unlink()


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
    change_marker = _arm_change_marker(session_id)
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
        if change_marker.exists():
            change_marker.unlink()


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
    change_marker = _arm_change_marker(session_id)
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
        if change_marker.exists():
            change_marker.unlink()


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
    change_marker = _arm_change_marker(session_id)
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
        if change_marker.exists():
            change_marker.unlink()


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
    change_marker = _arm_change_marker(session_id)
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
        if change_marker.exists():
            change_marker.unlink()


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
    change_marker = _arm_change_marker(session_id)
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
        assert (
            not change_marker.exists()
        ), f"change marker {change_marker} must be cleared after a passing verification run"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        if marker.exists():
            marker.unlink()
        if change_marker.exists():
            change_marker.unlink()


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
    change_marker = _arm_change_marker(session_id)
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
        assert (
            not change_marker.exists()
        ), f"change marker {change_marker} must be cleared after the rc-127 skip arm"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        if marker.exists():
            marker.unlink()
        if change_marker.exists():
            change_marker.unlink()


# ---------------------------------------------------------------------------
# Group B: change-marker gate (TC-VT-G01..G11, skip G08)
# ---------------------------------------------------------------------------


def test_vt_g01_change_marker_absent_failing_dir_is_silent_pass():
    """TC-VT-G01: failing dir; change marker ABSENT -> silent pass.

    Proves the fast exit happens before test-command detection/subprocess -
    a failing dir would otherwise block.
    """
    assert shutil.which("npm"), "npm required to drive the failing tests"
    session_id = str(uuid.uuid4())
    verify_marker = Path(f"/tmp/.claude-test-verify-{session_id}")
    test_dir = _make_failing_tests_dir()
    try:
        result = _run_hook(
            {"session_id": session_id, "cwd": test_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, (
            f"expected returncode 0, got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert result.stdout.strip() == "", (
            "no change marker armed -> must be a silent pass even though the "
            f"tests would fail; got stdout={result.stdout!r}"
        )
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        if verify_marker.exists():
            verify_marker.unlink()


def test_vt_g02_change_marker_absent_bare_dir_creates_no_marker():
    """TC-VT-G02: bare dir; change marker absent -> silent pass; no change
    marker gets created."""
    session_id = str(uuid.uuid4())
    change_marker = _change_marker_path(session_id)
    bare_dir = tempfile.mkdtemp()
    try:
        result = _run_hook(
            {"session_id": session_id, "cwd": bare_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, (
            f"expected returncode 0, got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert not change_marker.exists(), (
            f"change marker {change_marker} must not be created by verify-tests.py "
            "itself (only mark-code-change.py arms it)"
        )
    finally:
        shutil.rmtree(bare_dir, ignore_errors=True)
        if change_marker.exists():
            change_marker.unlink()


def test_vt_g03_change_marker_armed_failing_dir_blocks_and_marker_persists():
    """TC-VT-G03: failing dir; change marker armed -> block emitted; change
    marker STILL EXISTS after (re-verification stays armed); retry marker
    written/incremented."""
    assert shutil.which("npm"), "npm required to drive the failing tests"
    session_id = str(uuid.uuid4())
    change_marker = _arm_change_marker(session_id)
    verify_marker = Path(f"/tmp/.claude-test-verify-{session_id}")
    test_dir = _make_failing_tests_dir()
    try:
        result = _run_hook(
            {"session_id": session_id, "cwd": test_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, (
            f"expected returncode 0, got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        parsed = json.loads(result.stdout)
        assert parsed.get("decision") == "block", f"got {parsed!r}"
        assert (
            change_marker.exists()
        ), "change marker must persist after a block so re-verification stays armed"
        assert verify_marker.exists(), "retry marker must be written after a block"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        if verify_marker.exists():
            verify_marker.unlink()
        if change_marker.exists():
            change_marker.unlink()


def test_vt_g04_change_marker_armed_passing_dir_clears_marker():
    """TC-VT-G04: passing dir; change marker armed -> silent pass; change
    marker CLEARED after."""
    assert shutil.which("npm"), "npm required to run the test script"
    session_id = str(uuid.uuid4())
    change_marker = _arm_change_marker(session_id)
    test_dir = tempfile.mkdtemp()
    try:
        pkg = {
            "name": "test-vt-g04-passing",
            "version": "0.0.1",
            "scripts": {"test": "exit 0"},
        }
        (Path(test_dir) / "package.json").write_text(json.dumps(pkg))
        result = _run_hook(
            {"session_id": session_id, "cwd": test_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, f"got {result.returncode}"
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert not change_marker.exists(), "change marker must be cleared on pass"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        if change_marker.exists():
            change_marker.unlink()


def test_vt_g05_change_marker_armed_bare_dir_clears_marker():
    """TC-VT-G05: bare dir (no test command detected); change marker armed ->
    silent pass; change marker cleared (explicit marker-state assertion
    pinning the no-command clear)."""
    session_id = str(uuid.uuid4())
    change_marker = _arm_change_marker(session_id)
    bare_dir = tempfile.mkdtemp()
    try:
        result = _run_hook(
            {"session_id": session_id, "cwd": bare_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, f"got {result.returncode}"
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert (
            not change_marker.exists()
        ), "change marker must be cleared when no test command is detected"
    finally:
        shutil.rmtree(bare_dir, ignore_errors=True)
        if change_marker.exists():
            change_marker.unlink()


def test_vt_g06_change_marker_armed_npm_placeholder_clears_marker():
    """TC-VT-G06: npm placeholder script; change marker armed -> silent pass;
    change marker cleared."""
    assert shutil.which("npm"), "npm required to run the test script"
    session_id = str(uuid.uuid4())
    change_marker = _arm_change_marker(session_id)
    test_dir = tempfile.mkdtemp()
    try:
        pkg = {
            "name": "test-vt-g06-npm-placeholder",
            "version": "0.0.1",
            "scripts": {"test": r'echo "Error: no test specified" && exit 1'},
        }
        (Path(test_dir) / "package.json").write_text(json.dumps(pkg))
        result = _run_hook(
            {"session_id": session_id, "cwd": test_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, f"got {result.returncode}"
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert (
            not change_marker.exists()
        ), "change marker must be cleared on the npm-placeholder skip arm"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        if change_marker.exists():
            change_marker.unlink()


def test_vt_g07_change_marker_armed_rc127_clears_marker():
    """TC-VT-G07: rc-127 dir (detected command names an absent binary);
    change marker armed -> silent pass; change marker cleared (pins the
    shared rc-in-(124,127) branch by code-path equivalence; no forced
    120s timeout for rc-124 here)."""
    assert shutil.which("npm"), "npm required to run the test script"
    session_id = str(uuid.uuid4())
    change_marker = _arm_change_marker(session_id)
    test_dir = tempfile.mkdtemp()
    try:
        pkg = {
            "name": "test-vt-g07-rc127",
            "version": "0.0.1",
            "scripts": {"test": "nonexistent-runner-xyz"},
        }
        (Path(test_dir) / "package.json").write_text(json.dumps(pkg))
        result = _run_hook(
            {"session_id": session_id, "cwd": test_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, f"got {result.returncode}"
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert (
            not change_marker.exists()
        ), "change marker must be cleared on the rc-127 skip arm"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        if change_marker.exists():
            change_marker.unlink()


def test_vt_g09_garbage_retry_marker_with_armed_change_marker_still_blocks():
    """TC-VT-G09: garbage retry-marker text + failing dir; change marker
    armed -> block still emitted; change marker still exists."""
    assert shutil.which("npm"), "npm required to drive the failing tests"
    session_id = str(uuid.uuid4())
    verify_marker = Path(f"/tmp/.claude-test-verify-{session_id}")
    change_marker = _arm_change_marker(session_id)
    test_dir = _make_failing_tests_dir()
    try:
        verify_marker.write_text("garbage")
        result = _run_hook(
            {"session_id": session_id, "cwd": test_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, f"got {result.returncode}"
        parsed = json.loads(result.stdout)
        assert parsed.get("decision") == "block", f"got {parsed!r}"
        assert change_marker.exists(), "change marker must still exist after the block"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        if verify_marker.exists():
            verify_marker.unlink()
        if change_marker.exists():
            change_marker.unlink()


def test_vt_g10_retry_cap_with_armed_change_marker_does_not_clear_it():
    """TC-VT-G10: failing dir; change marker armed; retry marker count already
    1 -> retry-cap silent pass; change marker STILL EXISTS (retry-cap path
    does not clear it)."""
    assert shutil.which("npm"), "npm required to drive the failing tests"
    session_id = str(uuid.uuid4())
    verify_marker = Path(f"/tmp/.claude-test-verify-{session_id}")
    change_marker = _arm_change_marker(session_id)
    test_dir = _make_failing_tests_dir()
    try:
        verify_marker.write_text("1")
        result = _run_hook(
            {"session_id": session_id, "cwd": test_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, f"got {result.returncode}"
        assert (
            result.stdout.strip() == ""
        ), f"retry cap already at 1 -> expected silent pass, got {result.stdout!r}"
        assert (
            change_marker.exists()
        ), "the retry-cap silent-pass path must not clear the change marker"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        if verify_marker.exists():
            verify_marker.unlink()
        if change_marker.exists():
            change_marker.unlink()


def test_vt_g11_stop_hook_active_with_armed_change_marker_does_not_clear_it():
    """TC-VT-G11: failing dir; change marker armed; stop_hook_active=true ->
    silent pass; change marker STILL EXISTS."""
    session_id = str(uuid.uuid4())
    change_marker = _arm_change_marker(session_id)
    test_dir = _make_failing_tests_dir()
    try:
        result = _run_hook(
            {"session_id": session_id, "cwd": test_dir, "stop_hook_active": True}
        )
        assert result.returncode == 0, f"got {result.returncode}"
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert (
            change_marker.exists()
        ), "the stop_hook_active short-circuit must not clear the change marker"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        if change_marker.exists():
            change_marker.unlink()


def test_vt_no_run_state_exemption_stop_blocks_on_failing_tests():
    """No-exemption contract (removes docs/ADR/run-state subsystems, AC3):
    the Stop-site run-state exemption is gone entirely, not merely narrowed.

    Reproduces the exact scenario the old code exempted (test_vt_g12: fresh,
    cwd-matching, non-converged run-state.json for THIS session, no `live`
    key, which used to read as an open red window) against a failing test
    dir with the change marker armed. With the state branch removed there is
    no window to read: the Stop site must run verification and block, the
    same as any marker-gated call with no run-state file at all - agent_type
    is None here (no hook_event_name in the payload), so there is no
    SubagentStop branch to fall back on either.
    """
    assert shutil.which("npm"), "npm required to drive the failing tests"
    session_id = str(uuid.uuid4())
    verify_marker = Path(f"/tmp/.claude-test-verify-{session_id}")
    change_marker = _arm_change_marker(session_id)
    test_dir = _make_failing_tests_dir()
    try:
        # Inline leftover-file fixture: a stale run-state.json shaped like the
        # removed subsystem's snapshot, proving its presence has zero effect.
        runs_dir = Path(test_dir) / ".alp-river" / "runs" / session_id
        runs_dir.mkdir(parents=True, exist_ok=True)
        state_file = runs_dir / "run-state.json"
        state_file.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "run_id": session_id,
                    "cwd": test_dir,
                    "route": ["code"],
                    "mid_run_stage": "code-implementer",
                }
            ),
            encoding="utf-8",
        )
        t = time.time()
        os.utime(state_file, (t, t))
        result = _run_hook(
            {"session_id": session_id, "cwd": test_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, f"got {result.returncode}"
        parsed = json.loads(result.stdout)
        assert parsed.get("decision") == "block", (
            "the run-state exemption no longer exists; a live run-state file "
            "that used to open the red window must not suppress verification "
            f"on a failing dir; got {result.stdout!r}"
        )
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        if verify_marker.exists():
            verify_marker.unlink()
        if change_marker.exists():
            change_marker.unlink()
