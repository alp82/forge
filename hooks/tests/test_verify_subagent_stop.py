"""Failing (red) tests for the SubagentStop leg of the verify gates
(verify-tests.py, verify-build.py).

These drive the SAME two gate scripts, but with payloads that carry
`"hook_event_name": "SubagentStop"` plus an `"agent_type"`. At SubagentStop the
red window is read off the STOPPING AGENT alone: a code-implementer or fixer
stop closes the window (verify now), and every other stage - test-author,
reviewers, planners, unknown, or an empty agent_type - leaves it open (skip, so
deliberately-red TDD tests never block). Scope-stripped membership: a
plugin-scoped `alp-river:fixer` reduces to `fixer`.

The retry marker is EVENT-NAMESPACED: a SubagentStop gate keys its retry cap off
`<retry_prefix>-sub-<session_id>` (e.g. /tmp/.claude-test-verify-sub-<sid>),
while the Stop gate keeps `<retry_prefix>-<session_id>`. The change marker stays
SHARED across both events - it is the Edit/Write rendezvous and must survive from
a subagent's Edit to the main-session Stop.

RED until verify_shared.run_verify_gate() + red_window(agent_type=...) exist, the
scripts route through them, and hooks.json registers both gates at SubagentStop.

Three recorded facts about this gate (probe-only, not asserted here):
  1. stop_hook_active is UNDOCUMENTED at SubagentStop but present in the real
     payload; reading it true skips that stop (defensive, harmless if absent).
  2. A post-block second subagent stop is never re-verified at SubagentStop.
     Both (1) and (2) are safe ONLY because the event-namespaced Stop gate
     backstops at end of turn.
  3. The `-sub` retry marker keys on the MAIN session id
     (anthropics/claude-code#7881), so it is ONE marker shared by every
     implementer and fixer stop in the session - on persistent red the mid-run
     gate alternates block/skip across successive writer stops, backstopped
     agent-side by the milestone loop's EARLY-pass test-verifier and at turn end
     by the event-namespaced Stop gate (not redesigned here).
"""

import json
import shutil
import tempfile
import uuid
from pathlib import Path

from verify_gate_helpers import arm_change_marker, run_hook

VERIFY_TESTS_PY = Path(__file__).resolve().parents[1] / "verify-tests.py"
VERIFY_BUILD_PY = Path(__file__).resolve().parents[1] / "verify-build.py"

TESTS_CHANGE_PREFIX = "claude-code-changed-tests"
BUILD_CHANGE_PREFIX = "claude-code-changed-build"

# Sentinel so a test can build a payload with NO agent_type key at all.
_ABSENT = object()


def _tests_sub_retry(session_id):
    """The event-namespaced retry marker for the tests gate at SubagentStop."""
    return Path(f"/tmp/.claude-test-verify-sub-{session_id}")


def _tests_stop_retry(session_id):
    """The Stop-branch retry marker for the tests gate (non-namespaced)."""
    return Path(f"/tmp/.claude-test-verify-{session_id}")


def _build_sub_retry(session_id):
    return Path(f"/tmp/.claude-build-verify-sub-{session_id}")


def _subagent_payload(session_id, cwd, *, agent_type=_ABSENT, stop_hook_active=False):
    payload = {
        "session_id": session_id,
        "cwd": cwd,
        "hook_event_name": "SubagentStop",
        "stop_hook_active": stop_hook_active,
    }
    if agent_type is not _ABSENT:
        payload["agent_type"] = agent_type
    return payload


def _make_failing_tests_dir():
    d = tempfile.mkdtemp()
    pkg = {
        "name": "test-failing-tests",
        "version": "0.0.1",
        "scripts": {"test": r'printf "FAIL: \"test \\ path\"\n" >&2; exit 1'},
    }
    (Path(d) / "package.json").write_text(json.dumps(pkg))
    return d


def _make_passing_tests_dir():
    d = tempfile.mkdtemp()
    pkg = {
        "name": "test-passing-tests",
        "version": "0.0.1",
        "scripts": {"test": "exit 0"},
    }
    (Path(d) / "package.json").write_text(json.dumps(pkg))
    return d


def _make_failing_build_dir():
    d = tempfile.mkdtemp()
    pkg = {
        "name": "test-failing-build",
        "version": "0.0.1",
        "scripts": {"build": r'printf "oops: \" \\ /a/b\n" >&2; exit 1'},
    }
    (Path(d) / "package.json").write_text(json.dumps(pkg))
    return d


# ---------------------------------------------------------------------------
# Implementation-writer stops close the window: verify and block on red
# ---------------------------------------------------------------------------


def test_subagent_implementer_stop_blocks_and_writes_sub_retry_marker():
    """A code-implementer SubagentStop + armed change marker + failing dir ->
    block JSON with the pinned reason prefix; the change marker persists (a
    subagent's Edit rendezvous must survive to the main Stop); the retry marker
    is written under the `-sub` namespace, never the Stop namespace."""
    assert shutil.which("npm"), "npm required to drive the failing tests"
    session_id = str(uuid.uuid4())
    change_marker = arm_change_marker(TESTS_CHANGE_PREFIX, session_id)
    sub_retry = _tests_sub_retry(session_id)
    stop_retry = _tests_stop_retry(session_id)
    test_dir = _make_failing_tests_dir()
    try:
        result = run_hook(
            VERIFY_TESTS_PY,
            _subagent_payload(session_id, test_dir, agent_type="code-implementer"),
        )
        assert (
            result.returncode == 0
        ), f"hook must exit 0; got {result.returncode}; stderr={result.stderr!r}"
        parsed = json.loads(result.stdout)
        assert (
            parsed.get("decision") == "block"
        ), f"an implementer stop on a failing dir must block; got {result.stdout!r}"
        assert isinstance(parsed.get("reason"), str) and parsed["reason"].startswith(
            "Tests are failing"
        ), f"reason must start with 'Tests are failing'; got {parsed.get('reason')!r}"
        assert (
            change_marker.exists()
        ), "the shared change marker must persist after a SubagentStop block"
        assert sub_retry.exists(), (
            "the retry marker must be written under the -sub namespace "
            f"({sub_retry}) after a SubagentStop block"
        )
        assert not stop_retry.exists(), (
            "a SubagentStop block must NOT write the Stop-namespace retry marker "
            f"({stop_retry}) - the events are isolated"
        )
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        for m in (change_marker, sub_retry, stop_retry):
            if m.exists():
                m.unlink()


def test_subagent_fixer_and_plugin_scoped_writer_stops_block():
    """fixer, plugin-scoped alp-river:code-implementer, and alp-river:fixer stops
    all close the window (scope-stripped base-name membership) -> block."""
    assert shutil.which("npm"), "npm required to drive the failing tests"
    for agent_type in ("fixer", "alp-river:code-implementer", "alp-river:fixer"):
        session_id = str(uuid.uuid4())
        change_marker = arm_change_marker(TESTS_CHANGE_PREFIX, session_id)
        sub_retry = _tests_sub_retry(session_id)
        test_dir = _make_failing_tests_dir()
        try:
            result = run_hook(
                VERIFY_TESTS_PY,
                _subagent_payload(session_id, test_dir, agent_type=agent_type),
            )
            assert result.returncode == 0, f"[{agent_type}] got {result.returncode}"
            parsed = json.loads(result.stdout)
            assert parsed.get("decision") == "block", (
                f"[{agent_type}] a writer stop must block on a failing dir; "
                f"got {result.stdout!r}"
            )
            assert (
                change_marker.exists()
            ), f"[{agent_type}] the change marker must persist after a block"
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)
            for m in (change_marker, sub_retry):
                if m.exists():
                    m.unlink()


def test_subagent_implementer_stop_mid_run_blocks():
    """An implementer SubagentStop blocks mid-run on a failing dir - the window
    is read off the stopping agent_type alone, so a writer stop always
    verifies."""
    assert shutil.which("npm"), "npm required to drive the failing tests"
    session_id = str(uuid.uuid4())
    change_marker = arm_change_marker(TESTS_CHANGE_PREFIX, session_id)
    sub_retry = _tests_sub_retry(session_id)
    test_dir = _make_failing_tests_dir()
    try:
        result = run_hook(
            VERIFY_TESTS_PY,
            _subagent_payload(session_id, test_dir, agent_type="code-implementer"),
        )
        assert result.returncode == 0, f"got {result.returncode}"
        parsed = json.loads(result.stdout)
        assert parsed.get("decision") == "block", (
            "a writer stop must verify and block on a failing dir; "
            f"got {result.stdout!r}"
        )
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        for m in (change_marker, sub_retry):
            if m.exists():
                m.unlink()


# ---------------------------------------------------------------------------
# Non-writer / test-author stops keep the window open: silent pass
# ---------------------------------------------------------------------------


def test_subagent_test_author_stop_skips_and_marker_survives():
    """A test-author SubagentStop + failing dir + armed change marker -> silent
    pass (deliberate TDD skip); the change marker SURVIVES for the main Stop."""
    assert shutil.which("npm"), "npm required to drive the failing tests"
    session_id = str(uuid.uuid4())
    change_marker = arm_change_marker(TESTS_CHANGE_PREFIX, session_id)
    sub_retry = _tests_sub_retry(session_id)
    test_dir = _make_failing_tests_dir()
    try:
        result = run_hook(
            VERIFY_TESTS_PY,
            _subagent_payload(session_id, test_dir, agent_type="test-author"),
        )
        assert result.returncode == 0, f"got {result.returncode}"
        assert result.stdout.strip() == "", (
            "a test-author stop keeps the red window open -> silent pass; "
            f"got {result.stdout!r}"
        )
        assert (
            change_marker.exists()
        ), "the deliberate TDD skip must not consume the change marker"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        for m in (change_marker, sub_retry):
            if m.exists():
                m.unlink()


def test_subagent_non_writer_and_absent_or_empty_agent_type_skip():
    """A correctness-reviewer stop, an absent agent_type, an empty-string
    agent_type, and a not-a-fixer stop all keep the window open -> silent pass
    with the change marker surviving. Membership is exact base-name after scope
    stripping, independent of the matcher's regex-search leniency."""
    assert shutil.which("npm"), "npm required to drive the failing tests"
    cases = [
        ("correctness-reviewer", "correctness-reviewer"),
        ("absent", _ABSENT),
        ("empty-string", ""),
        ("not-a-fixer", "not-a-fixer"),
    ]
    for label, agent_type in cases:
        session_id = str(uuid.uuid4())
        change_marker = arm_change_marker(TESTS_CHANGE_PREFIX, session_id)
        sub_retry = _tests_sub_retry(session_id)
        test_dir = _make_failing_tests_dir()
        try:
            result = run_hook(
                VERIFY_TESTS_PY,
                _subagent_payload(session_id, test_dir, agent_type=agent_type),
            )
            assert result.returncode == 0, f"[{label}] got {result.returncode}"
            assert result.stdout.strip() == "", (
                f"[{label}] a non-writer stop keeps the window open -> silent pass; "
                f"got {result.stdout!r}"
            )
            assert (
                change_marker.exists()
            ), f"[{label}] a skip must not consume the change marker"
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)
            for m in (change_marker, sub_retry):
                if m.exists():
                    m.unlink()


# ---------------------------------------------------------------------------
# Shared marker-gate guards still apply at SubagentStop
# ---------------------------------------------------------------------------


def test_subagent_change_marker_absent_is_silent_pass():
    """An implementer stop with NO change marker armed -> silent pass (the
    Edit/Write rendezvous never fired this turn)."""
    assert shutil.which("npm"), "npm required to drive the failing tests"
    session_id = str(uuid.uuid4())
    sub_retry = _tests_sub_retry(session_id)
    test_dir = _make_failing_tests_dir()
    try:
        result = run_hook(
            VERIFY_TESTS_PY,
            _subagent_payload(session_id, test_dir, agent_type="code-implementer"),
        )
        assert result.returncode == 0, f"got {result.returncode}"
        assert result.stdout.strip() == "", (
            "no change marker -> silent pass even for an implementer stop; "
            f"got {result.stdout!r}"
        )
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        if sub_retry.exists():
            sub_retry.unlink()


def test_subagent_stop_hook_active_is_silent_pass():
    """stop_hook_active true short-circuits an implementer stop to a silent pass
    (reading the undocumented field true skips that stop)."""
    session_id = str(uuid.uuid4())
    change_marker = arm_change_marker(TESTS_CHANGE_PREFIX, session_id)
    sub_retry = _tests_sub_retry(session_id)
    test_dir = _make_failing_tests_dir()
    try:
        result = run_hook(
            VERIFY_TESTS_PY,
            _subagent_payload(
                session_id,
                test_dir,
                agent_type="code-implementer",
                stop_hook_active=True,
            ),
        )
        assert result.returncode == 0, f"got {result.returncode}"
        assert result.stdout.strip() == "", (
            "stop_hook_active=true must short-circuit to a silent pass; "
            f"got {result.stdout!r}"
        )
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        for m in (change_marker, sub_retry):
            if m.exists():
                m.unlink()


def test_subagent_retry_cap_second_failing_stop_skips():
    """With the `-sub` retry marker already at 1, a second failing implementer
    stop is a silent pass (the mid-run cap is honored, keyed on the -sub
    namespace)."""
    assert shutil.which("npm"), "npm required to drive the failing tests"
    session_id = str(uuid.uuid4())
    change_marker = arm_change_marker(TESTS_CHANGE_PREFIX, session_id)
    sub_retry = _tests_sub_retry(session_id)
    test_dir = _make_failing_tests_dir()
    try:
        sub_retry.write_text("1")
        result = run_hook(
            VERIFY_TESTS_PY,
            _subagent_payload(session_id, test_dir, agent_type="code-implementer"),
        )
        assert result.returncode == 0, f"got {result.returncode}"
        assert result.stdout.strip() == "", (
            "the -sub retry cap at 1 must silence a second failing stop; "
            f"got {result.stdout!r}"
        )
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        for m in (change_marker, sub_retry):
            if m.exists():
                m.unlink()


def test_subagent_passing_dir_clears_both_markers():
    """An implementer stop on a passing dir -> silent pass; both the shared
    change marker and the `-sub` retry marker are cleared."""
    assert shutil.which("npm"), "npm required to run the test script"
    session_id = str(uuid.uuid4())
    change_marker = arm_change_marker(TESTS_CHANGE_PREFIX, session_id)
    sub_retry = _tests_sub_retry(session_id)
    test_dir = _make_passing_tests_dir()
    try:
        result = run_hook(
            VERIFY_TESTS_PY,
            _subagent_payload(session_id, test_dir, agent_type="code-implementer"),
        )
        assert result.returncode == 0, f"got {result.returncode}"
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert (
            not change_marker.exists()
        ), "a passing verification run must clear the shared change marker"
        assert (
            not sub_retry.exists()
        ), "a passing verification run must clear the -sub retry marker"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        for m in (change_marker, sub_retry):
            if m.exists():
                m.unlink()


# ---------------------------------------------------------------------------
# Cross-event compositions (the blocker pin + the marker rendezvous flow)
# ---------------------------------------------------------------------------


def test_cross_event_retry_isolation_burned_sub_retry_does_not_silence_stop():
    """THE blocker pin: burn the retry at a SubagentStop block, re-arm the change
    marker, then run the SAME session as a Stop payload on the still-failing dir
    -> it must BLOCK again, never silent_pass. A retry burned at SubagentStop
    (the -sub namespace) must not silence the end-of-turn Stop gate (the Stop
    namespace)."""
    assert shutil.which("npm"), "npm required to drive the failing tests"
    session_id = str(uuid.uuid4())
    change_marker = arm_change_marker(TESTS_CHANGE_PREFIX, session_id)
    sub_retry = _tests_sub_retry(session_id)
    stop_retry = _tests_stop_retry(session_id)
    test_dir = _make_failing_tests_dir()
    try:
        first = run_hook(
            VERIFY_TESTS_PY,
            _subagent_payload(session_id, test_dir, agent_type="code-implementer"),
        )
        assert first.returncode == 0, f"first (SubagentStop) got {first.returncode}"
        assert (
            json.loads(first.stdout).get("decision") == "block"
        ), f"first SubagentStop must block; got {first.stdout!r}"

        # Re-arm the shared change marker for the end-of-turn Stop.
        arm_change_marker(TESTS_CHANGE_PREFIX, session_id)

        second = run_hook(
            VERIFY_TESTS_PY,
            {"session_id": session_id, "cwd": test_dir, "stop_hook_active": False},
        )
        assert second.returncode == 0, f"second (Stop) got {second.returncode}"
        assert second.stdout.strip() != "", (
            "the Stop gate must NOT be silenced by a retry burned at SubagentStop; "
            f"expected a block, got {second.stdout!r}"
        )
        assert (
            json.loads(second.stdout).get("decision") == "block"
        ), f"the Stop gate must block again on the still-failing dir; got {second.stdout!r}"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        for m in (change_marker, sub_retry, stop_retry):
            if m.exists():
                m.unlink()


def test_cross_event_marker_flow_green_subagent_clears_then_stop_reverifies():
    """Cross-event marker flow: a green SubagentStop clears the shared change
    marker; a later arm_change_marker re-arms it; a later Stop payload finds it
    and verifies (blocks on the now-failing dir)."""
    assert shutil.which("npm"), "npm required to drive the test scripts"
    session_id = str(uuid.uuid4())
    change_marker = arm_change_marker(TESTS_CHANGE_PREFIX, session_id)
    sub_retry = _tests_sub_retry(session_id)
    stop_retry = _tests_stop_retry(session_id)
    passing_dir = _make_passing_tests_dir()
    failing_dir = _make_failing_tests_dir()
    try:
        green = run_hook(
            VERIFY_TESTS_PY,
            _subagent_payload(session_id, passing_dir, agent_type="code-implementer"),
        )
        assert green.returncode == 0, f"green SubagentStop got {green.returncode}"
        assert green.stdout.strip() == "", f"green stop got {green.stdout!r}"
        assert (
            not change_marker.exists()
        ), "a green SubagentStop must clear the shared change marker"

        re_armed = arm_change_marker(TESTS_CHANGE_PREFIX, session_id)
        assert re_armed.exists(), "re-arm must recreate the shared change marker"

        stop = run_hook(
            VERIFY_TESTS_PY,
            {"session_id": session_id, "cwd": failing_dir, "stop_hook_active": False},
        )
        assert stop.returncode == 0, f"Stop got {stop.returncode}"
        assert (
            json.loads(stop.stdout).get("decision") == "block"
        ), f"the Stop gate must find the re-armed marker and block; got {stop.stdout!r}"
    finally:
        shutil.rmtree(passing_dir, ignore_errors=True)
        shutil.rmtree(failing_dir, ignore_errors=True)
        for m in (change_marker, sub_retry, stop_retry):
            if m.exists():
                m.unlink()


# ---------------------------------------------------------------------------
# Smoke subset against verify-build.py (implementer-block + test-author-skip)
# ---------------------------------------------------------------------------


def test_subagent_verify_build_implementer_stop_blocks():
    """verify-build smoke: an implementer SubagentStop + armed change marker +
    failing build -> block; the `-sub` retry marker is written under the build
    namespace."""
    assert shutil.which("npm"), "npm required to drive the failing build"
    session_id = str(uuid.uuid4())
    change_marker = arm_change_marker(BUILD_CHANGE_PREFIX, session_id)
    sub_retry = _build_sub_retry(session_id)
    build_dir = _make_failing_build_dir()
    try:
        result = run_hook(
            VERIFY_BUILD_PY,
            _subagent_payload(session_id, build_dir, agent_type="code-implementer"),
        )
        assert result.returncode == 0, f"got {result.returncode}"
        parsed = json.loads(result.stdout)
        assert (
            parsed.get("decision") == "block"
        ), f"an implementer stop on a failing build must block; got {result.stdout!r}"
        assert sub_retry.exists(), (
            f"the build retry marker must be written under the -sub namespace "
            f"({sub_retry})"
        )
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)
        for m in (change_marker, sub_retry):
            if m.exists():
                m.unlink()


def test_subagent_verify_build_test_author_stop_skips():
    """verify-build smoke: a test-author SubagentStop + failing build + armed
    change marker -> silent pass; the change marker survives."""
    assert shutil.which("npm"), "npm required to drive the failing build"
    session_id = str(uuid.uuid4())
    change_marker = arm_change_marker(BUILD_CHANGE_PREFIX, session_id)
    sub_retry = _build_sub_retry(session_id)
    build_dir = _make_failing_build_dir()
    try:
        result = run_hook(
            VERIFY_BUILD_PY,
            _subagent_payload(session_id, build_dir, agent_type="test-author"),
        )
        assert result.returncode == 0, f"got {result.returncode}"
        assert result.stdout.strip() == "", (
            "a test-author stop keeps the window open -> silent pass; "
            f"got {result.stdout!r}"
        )
        assert (
            change_marker.exists()
        ), "the deliberate TDD skip must not consume the change marker"
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)
        for m in (change_marker, sub_retry):
            if m.exists():
                m.unlink()
