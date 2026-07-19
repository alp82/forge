"""Failing (red) tests for hooks/verify-build.py.

They define the expected behaviour of verify-build.py, which reads a JSON
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

CHANGE-MARKER GATE (RED - the gate does not exist yet in hooks/verify-build.py):
verification only RUNS when a PostToolUse change marker
/tmp/.codex-changed-build-<session_id> is present (armed by
hooks/mark-code-change.py, which also does not exist yet - see
test_mark_code_change.py). Absent the marker, the hook must silently pass
before even detecting a build command, regardless of whether the build would
fail. A block leaves the change marker in place (re-verification stays
armed); any silent-pass branch that actually ran verification (or determined
there was nothing to verify, INCLUDING the tool-absent `build_cmd is None`
branch) CLEARS the change marker.

At Stop the armed change marker alone decides - verification always runs.

Pre-existing tests below arm the build change marker in setup (via
_arm_change_marker) and clean it up in finally; the bare-dir / no-build-command
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
VERIFY_BUILD_PY = Path(__file__).resolve().parents[1] / "verify-build.py"

# The build-gate change-marker prefix; the shared helpers are parametrized by it.
CHANGE_PREFIX = "codex-changed-build"


def _change_marker_path(session_id):
    return change_marker_path(CHANGE_PREFIX, session_id)


def _arm_change_marker(session_id):
    return arm_change_marker(CHANGE_PREFIX, session_id)


def _run_hook(payload_dict, *, env=None):
    return run_hook(VERIFY_BUILD_PY, payload_dict, env=env)


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
    session_id = str(uuid.uuid4())
    marker = Path(f"/tmp/.codex-build-verify-{session_id}")
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
    session_id = str(uuid.uuid4())
    marker = Path(f"/tmp/.codex-build-verify-{session_id}")
    change_marker = _arm_change_marker(session_id)
    build_dir = _make_failing_build_dir()
    try:
        result = _run_hook(
            {"session_id": session_id, "cwd": build_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, (
            f"hook must always exit 0 (codex hook contract); "
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
        if change_marker.exists():
            change_marker.unlink()


# ---------------------------------------------------------------------------
# TC-VB-3  retry cap: second call on the same session_id is a silent pass
# ---------------------------------------------------------------------------


def test_retry_cap_second_call_is_not_blocked():
    """After one block, a second call with the same session_id is a silent pass.

    Flow:
      1. First call -> block (build fails).
      2. Marker file /tmp/.codex-build-verify-<session_id> must now exist,
         proving the failure was registered.
      3. Second call (identical payload) -> silent pass (returncode 0, no stdout).
    """
    assert shutil.which(
        "npm"
    ), "npm required to drive build output through the jq reason path"
    session_id = str(uuid.uuid4())
    marker = Path(f"/tmp/.codex-build-verify-{session_id}")
    change_marker = _arm_change_marker(session_id)
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
        if change_marker.exists():
            change_marker.unlink()


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
    session_id = str(uuid.uuid4())
    marker = Path(f"/tmp/.codex-build-verify-{session_id}")
    change_marker = _arm_change_marker(session_id)
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
        if change_marker.exists():
            change_marker.unlink()


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
    session_id = str(uuid.uuid4())
    marker = Path(f"/tmp/.codex-build-verify-{session_id}")
    change_marker = _arm_change_marker(session_id)
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
        assert (
            not change_marker.exists()
        ), f"change marker {change_marker} must be cleared after a passing verification run"
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)
        if marker.exists():
            marker.unlink()
        if change_marker.exists():
            change_marker.unlink()


# ---------------------------------------------------------------------------
# TC-VB-MARKER  pre-seeded garbage marker is not treated as a retry counter
# ---------------------------------------------------------------------------


def test_garbage_marker_does_not_short_circuit():
    """A marker file containing non-numeric text must not crash the hook and
    must not trigger the retry short-circuit (which would cause a silent pass).

    The garbage value is not >= 1 when interpreted numerically, so the hook
    must proceed to run the build, find it failing, and emit a block decision.
    """
    assert shutil.which("npm"), "npm required to drive the failing build"
    session_id = str(uuid.uuid4())
    marker = Path(f"/tmp/.codex-build-verify-{session_id}")
    change_marker = _arm_change_marker(session_id)
    build_dir = _make_failing_build_dir()
    try:
        # Pre-seed the marker with non-numeric garbage
        marker.write_text("garbage")

        result = _run_hook(
            {"session_id": session_id, "cwd": build_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, (
            f"hook must exit 0 even with a garbage marker; "
            f"got {result.returncode}; stderr={result.stderr!r}"
        )
        # Must not crash -> stdout must be valid JSON (not empty, not a traceback)
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
        shutil.rmtree(build_dir, ignore_errors=True)
        if marker.exists():
            marker.unlink()
        if change_marker.exists():
            change_marker.unlink()


# ---------------------------------------------------------------------------
# TC-VB-ASYM  Cargo.toml only, cargo absent from PATH -> silent pass
# ---------------------------------------------------------------------------


def test_cargo_absent_from_path_is_silent_pass():
    """A project with only Cargo.toml but no cargo binary on PATH is a silent
    pass.

    verify-build.py gates the Rust build on cargo being present; when the
    tool is absent it must silently skip rather than error.
    """
    session_id = str(uuid.uuid4())
    marker = Path(f"/tmp/.codex-build-verify-{session_id}")
    change_marker = _arm_change_marker(session_id)
    build_dir = tempfile.mkdtemp()
    # A fake-bin dir that has python3 (symlinked) but no cargo, so the hook
    # interpreter is reachable while the build tool is absent.
    fake_bin = tempfile.mkdtemp()
    try:
        (Path(build_dir) / "Cargo.toml").write_text(
            '[package]\nname = "test"\nversion = "0.1.0"\nedition = "2021"\n'
        )
        python3_real = shutil.which("python3") or "/usr/bin/python3"
        (Path(fake_bin) / "python3").symlink_to(python3_real)
        restricted_env = {**os.environ, "PATH": fake_bin}

        result = _run_hook(
            {"session_id": session_id, "cwd": build_dir, "stop_hook_active": False},
            env=restricted_env,
        )
        assert result.returncode == 0, (
            f"expected returncode 0 when cargo absent; "
            f"got {result.returncode}; stderr={result.stderr!r}"
        )
        assert result.stdout.strip() == "", (
            f"expected empty stdout (silent skip when cargo absent), "
            f"got {result.stdout!r}"
        )
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)
        shutil.rmtree(fake_bin, ignore_errors=True)
        if marker.exists():
            marker.unlink()
        if change_marker.exists():
            change_marker.unlink()


# ---------------------------------------------------------------------------
# TC-VB-RC127  build command exits 127 -> silent pass (rc-127 skip arm)
# ---------------------------------------------------------------------------


def test_build_command_rc127_is_silent_pass():
    """When the build script resolves but the inner binary is not found (exit
    code 127), the hook must treat this as a skip and exit silently.

    This exercises the rc-127 arm without requiring a 150-second timeout.
    """
    assert shutil.which("npm"), "npm required to run the build script"
    session_id = str(uuid.uuid4())
    marker = Path(f"/tmp/.codex-build-verify-{session_id}")
    change_marker = _arm_change_marker(session_id)
    build_dir = tempfile.mkdtemp()
    try:
        pkg = {
            "name": "test-rc127-build",
            "version": "0.0.1",
            "scripts": {"build": "nonexistent-binary-xyz"},
        }
        (Path(build_dir) / "package.json").write_text(json.dumps(pkg))

        result = _run_hook(
            {"session_id": session_id, "cwd": build_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, (
            f"expected returncode 0 on rc-127 build exit; "
            f"got {result.returncode}; stderr={result.stderr!r}"
        )
        assert (
            result.stdout.strip() == ""
        ), f"expected empty stdout (rc-127 skip arm), got {result.stdout!r}"
        assert (
            not change_marker.exists()
        ), f"change marker {change_marker} must be cleared after the rc-127 skip arm"
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)
        if marker.exists():
            marker.unlink()
        if change_marker.exists():
            change_marker.unlink()


# ---------------------------------------------------------------------------
# Group C: change-marker gate (TC-VB-G01..G11 minus G08, mirroring Group B in
# test_verify_tests.py) + build-specific TC-VB-G07'
# ---------------------------------------------------------------------------


def test_vb_g01_change_marker_absent_failing_dir_is_silent_pass():
    """TC-VB-G01: failing build dir; change marker ABSENT -> silent pass."""
    assert shutil.which(
        "npm"
    ), "npm required to drive build output through the jq reason path"
    session_id = str(uuid.uuid4())
    verify_marker = Path(f"/tmp/.codex-build-verify-{session_id}")
    build_dir = _make_failing_build_dir()
    try:
        result = _run_hook(
            {"session_id": session_id, "cwd": build_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, f"got {result.returncode}"
        assert result.stdout.strip() == "", (
            "no change marker armed -> must be a silent pass even though the "
            f"build would fail; got stdout={result.stdout!r}"
        )
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)
        if verify_marker.exists():
            verify_marker.unlink()


def test_vb_g02_change_marker_absent_bare_dir_creates_no_marker():
    """TC-VB-G02: bare dir; change marker absent -> silent pass; no change
    marker gets created."""
    session_id = str(uuid.uuid4())
    change_marker = _change_marker_path(session_id)
    bare_dir = tempfile.mkdtemp()
    try:
        result = _run_hook(
            {"session_id": session_id, "cwd": bare_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, f"got {result.returncode}"
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert (
            not change_marker.exists()
        ), f"change marker {change_marker} must not be created by verify-build.py itself"
    finally:
        shutil.rmtree(bare_dir, ignore_errors=True)
        if change_marker.exists():
            change_marker.unlink()


def test_vb_g03_change_marker_armed_failing_dir_blocks_and_marker_persists():
    """TC-VB-G03: failing dir; change marker armed -> block emitted; change
    marker STILL EXISTS after; retry marker written/incremented."""
    assert shutil.which(
        "npm"
    ), "npm required to drive build output through the jq reason path"
    session_id = str(uuid.uuid4())
    change_marker = _arm_change_marker(session_id)
    verify_marker = Path(f"/tmp/.codex-build-verify-{session_id}")
    build_dir = _make_failing_build_dir()
    try:
        result = _run_hook(
            {"session_id": session_id, "cwd": build_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, f"got {result.returncode}"
        parsed = json.loads(result.stdout)
        assert parsed.get("decision") == "block", f"got {parsed!r}"
        assert (
            change_marker.exists()
        ), "change marker must persist after a block so re-verification stays armed"
        assert verify_marker.exists(), "retry marker must be written after a block"
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)
        if verify_marker.exists():
            verify_marker.unlink()
        if change_marker.exists():
            change_marker.unlink()


def test_vb_g04_change_marker_armed_passing_dir_clears_marker():
    """TC-VB-G04: passing dir; change marker armed -> silent pass; change
    marker CLEARED after."""
    assert shutil.which("npm"), "npm required to run the build script"
    session_id = str(uuid.uuid4())
    change_marker = _arm_change_marker(session_id)
    build_dir = tempfile.mkdtemp()
    try:
        pkg = {
            "name": "test-vb-g04-passing",
            "version": "0.0.1",
            "scripts": {"build": "exit 0"},
        }
        (Path(build_dir) / "package.json").write_text(json.dumps(pkg))
        result = _run_hook(
            {"session_id": session_id, "cwd": build_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, f"got {result.returncode}"
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert not change_marker.exists(), "change marker must be cleared on pass"
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)
        if change_marker.exists():
            change_marker.unlink()


def test_vb_g05_change_marker_armed_bare_dir_clears_marker():
    """TC-VB-G05: bare dir (no build command detected); change marker armed ->
    silent pass; change marker cleared."""
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
        ), "change marker must be cleared when no build command is detected"
    finally:
        shutil.rmtree(bare_dir, ignore_errors=True)
        if change_marker.exists():
            change_marker.unlink()


def test_vb_g06_change_marker_armed_tool_absent_clears_marker():
    """TC-VB-G06 (build analogue of the npm-placeholder skip): a tsconfig.json
    project with npx absent from PATH resolves build_cmd to None; change
    marker armed -> silent pass; change marker cleared."""
    session_id = str(uuid.uuid4())
    change_marker = _arm_change_marker(session_id)
    build_dir = tempfile.mkdtemp()
    fake_bin = tempfile.mkdtemp()
    try:
        (Path(build_dir) / "tsconfig.json").write_text("{}")
        python3_real = shutil.which("python3") or "/usr/bin/python3"
        (Path(fake_bin) / "python3").symlink_to(python3_real)
        restricted_env = {**os.environ, "PATH": fake_bin}
        result = _run_hook(
            {"session_id": session_id, "cwd": build_dir, "stop_hook_active": False},
            env=restricted_env,
        )
        assert result.returncode == 0, f"got {result.returncode}"
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert (
            not change_marker.exists()
        ), "change marker must be cleared on the build_cmd-is-None skip arm"
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)
        shutil.rmtree(fake_bin, ignore_errors=True)
        if change_marker.exists():
            change_marker.unlink()


def test_vb_g07_prime_tool_absent_build_cmd_none_clears_marker():
    """TC-VB-G07': verify-build gates on tool presence before running - the
    "no build tool resolvable" case is a build_cmd is None silent pass;
    confirm it also clears the change marker (Cargo.toml present, cargo
    absent from PATH)."""
    session_id = str(uuid.uuid4())
    change_marker = _arm_change_marker(session_id)
    build_dir = tempfile.mkdtemp()
    fake_bin = tempfile.mkdtemp()
    try:
        (Path(build_dir) / "Cargo.toml").write_text(
            '[package]\nname = "test"\nversion = "0.1.0"\nedition = "2021"\n'
        )
        python3_real = shutil.which("python3") or "/usr/bin/python3"
        (Path(fake_bin) / "python3").symlink_to(python3_real)
        restricted_env = {**os.environ, "PATH": fake_bin}
        result = _run_hook(
            {"session_id": session_id, "cwd": build_dir, "stop_hook_active": False},
            env=restricted_env,
        )
        assert result.returncode == 0, f"got {result.returncode}"
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert (
            not change_marker.exists()
        ), "change marker must be cleared when the tool-presence gate finds nothing resolvable"
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)
        shutil.rmtree(fake_bin, ignore_errors=True)
        if change_marker.exists():
            change_marker.unlink()


def test_vb_g09_garbage_retry_marker_with_armed_change_marker_still_blocks():
    """TC-VB-G09: garbage retry-marker text + failing dir; change marker
    armed -> block still emitted; change marker still exists."""
    assert shutil.which(
        "npm"
    ), "npm required to drive build output through the jq reason path"
    session_id = str(uuid.uuid4())
    verify_marker = Path(f"/tmp/.codex-build-verify-{session_id}")
    change_marker = _arm_change_marker(session_id)
    build_dir = _make_failing_build_dir()
    try:
        verify_marker.write_text("garbage")
        result = _run_hook(
            {"session_id": session_id, "cwd": build_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, f"got {result.returncode}"
        parsed = json.loads(result.stdout)
        assert parsed.get("decision") == "block", f"got {parsed!r}"
        assert change_marker.exists(), "change marker must still exist after the block"
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)
        if verify_marker.exists():
            verify_marker.unlink()
        if change_marker.exists():
            change_marker.unlink()


def test_vb_g10_retry_cap_with_armed_change_marker_does_not_clear_it():
    """TC-VB-G10: failing dir; change marker armed; retry marker count already
    1 -> retry-cap silent pass; change marker STILL EXISTS."""
    assert shutil.which(
        "npm"
    ), "npm required to drive build output through the jq reason path"
    session_id = str(uuid.uuid4())
    verify_marker = Path(f"/tmp/.codex-build-verify-{session_id}")
    change_marker = _arm_change_marker(session_id)
    build_dir = _make_failing_build_dir()
    try:
        verify_marker.write_text("1")
        result = _run_hook(
            {"session_id": session_id, "cwd": build_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, f"got {result.returncode}"
        assert (
            result.stdout.strip() == ""
        ), f"retry cap already at 1 -> expected silent pass, got {result.stdout!r}"
        assert (
            change_marker.exists()
        ), "the retry-cap silent-pass path must not clear the change marker"
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)
        if verify_marker.exists():
            verify_marker.unlink()
        if change_marker.exists():
            change_marker.unlink()


def test_vb_g11_stop_hook_active_with_armed_change_marker_does_not_clear_it():
    """TC-VB-G11: failing dir; change marker armed; stop_hook_active=true ->
    silent pass; change marker STILL EXISTS."""
    session_id = str(uuid.uuid4())
    change_marker = _arm_change_marker(session_id)
    build_dir = _make_failing_build_dir()
    try:
        result = _run_hook(
            {"session_id": session_id, "cwd": build_dir, "stop_hook_active": True}
        )
        assert result.returncode == 0, f"got {result.returncode}"
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert (
            change_marker.exists()
        ), "the stop_hook_active short-circuit must not clear the change marker"
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)
        if change_marker.exists():
            change_marker.unlink()


def test_vb_no_run_state_exemption_stop_blocks_on_failing_build():
    """No-exemption contract (removes docs/ADR/run-state subsystems, AC3):
    the Stop-site run-state exemption is gone entirely, not merely narrowed.

    Reproduces the exact scenario the old code exempted (test_vb_g12: fresh,
    cwd-matching, non-converged run-state.json for THIS session, no `live`
    key, which used to read as an open red window) against a failing build
    dir with the change marker armed. With the state branch removed there is
    no window to read: the Stop site must run verification and block, the
    same as any marker-gated call with no run-state file at all - agent_type
    is None here (no hook_event_name in the payload), so there is no
    SubagentStop branch to fall back on either.
    """
    assert shutil.which(
        "npm"
    ), "npm required to drive build output through the jq reason path"
    session_id = str(uuid.uuid4())
    change_marker = _arm_change_marker(session_id)
    build_dir = _make_failing_build_dir()
    try:
        # Inline leftover-file fixture: a stale run-state.json shaped like the
        # removed subsystem's snapshot, proving its presence has zero effect.
        runs_dir = Path(build_dir) / ".alp-river" / "runs" / session_id
        runs_dir.mkdir(parents=True, exist_ok=True)
        state_file = runs_dir / "run-state.json"
        state_file.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "run_id": session_id,
                    "cwd": build_dir,
                    "route": ["code"],
                    "mid_run_stage": "code-implementer",
                }
            ),
            encoding="utf-8",
        )
        t = time.time()
        os.utime(state_file, (t, t))
        result = _run_hook(
            {"session_id": session_id, "cwd": build_dir, "stop_hook_active": False}
        )
        assert result.returncode == 0, f"got {result.returncode}"
        parsed = json.loads(result.stdout)
        assert parsed.get("decision") == "block", (
            "the run-state exemption no longer exists; a live run-state file "
            "that used to open the red window must not suppress verification "
            f"on a failing build; got {result.stdout!r}"
        )
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)
        if change_marker.exists():
            change_marker.unlink()
