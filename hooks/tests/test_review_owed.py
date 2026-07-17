"""Tests for hooks/review-owed.py - the review-owed Stop gate.

Contract: mark-code-change.py arms /tmp/.claude-code-changed-review-<sid> on
every real project edit (its mtime tracks the last edit). At Stop, the debt is
settled iff a findings-<lens>.md under a .forge run dir postdates that marker -
the mechanism- and session_id-agnostic evidence a wave ran after the change.
An armed marker with no fresh findings means the change was never reviewed:
block once with a pointer at the review wave. Max 1 block per session (at the
cap both markers clear and the gate stands down); the stop_hook_active
short-circuit never re-blocks an already-blocked loop and keeps the review debt
armed for the next turn. Always exit 0; every non-block branch prints nothing.
"""

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

REVIEW_OWED_PY = Path(__file__).resolve().parents[1] / "review-owed.py"


def _review_marker(session_id):
    return Path(f"/tmp/.claude-code-changed-review-{session_id}")


def _retry_marker(session_id):
    return Path(f"/tmp/.claude-review-owed-{session_id}")


def _run_hook(payload, *, raw_stdin=None):
    stdin_text = raw_stdin if raw_stdin is not None else json.dumps(payload)
    return subprocess.run(
        ["python3", str(REVIEW_OWED_PY)],
        input=stdin_text,
        capture_output=True,
        text=True,
    )


def _cleanup(*paths):
    for p in paths:
        p.unlink(missing_ok=True)


def test_armed_marker_blocks_with_review_pointer():
    session_id = str(uuid.uuid4())
    review, retry = _review_marker(session_id), _retry_marker(session_id)
    cwd = tempfile.mkdtemp()  # isolated: no .forge, so no findings can settle
    try:
        review.write_text("1")
        result = _run_hook(
            {"session_id": session_id, "cwd": cwd, "stop_hook_active": False}
        )
        assert result.returncode == 0, f"got {result.returncode}: {result.stderr!r}"
        parsed = json.loads(result.stdout)
        assert parsed.get("decision") == "block", f"got {result.stdout!r}"
        assert "crossfire" in parsed.get("reason", ""), (
            f"the block reason must point at the review wave; got {parsed!r}"
        )
        assert review.exists(), "a block must leave the review debt armed"
        assert retry.exists(), "a block must burn the single retry"
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        _cleanup(review, retry)


def test_fresh_findings_settle_the_debt():
    """A findings file newer than the marker (a wave ran after the change)
    clears the debt at Stop - no matter how or by whom it was written."""
    session_id = str(uuid.uuid4())
    review, retry = _review_marker(session_id), _retry_marker(session_id)
    cwd = tempfile.mkdtemp()
    try:
        review.write_text("1")
        run_dir = Path(cwd) / ".forge" / "run"
        run_dir.mkdir(parents=True)
        findings = run_dir / "findings-correctness.md"
        findings.write_text("pass")
        marker_mtime = review.stat().st_mtime
        os.utime(findings, (marker_mtime + 10, marker_mtime + 10))
        result = _run_hook(
            {"session_id": session_id, "cwd": cwd, "stop_hook_active": False}
        )
        assert result.returncode == 0, f"got {result.returncode}: {result.stderr!r}"
        assert result.stdout.strip() == "", (
            f"fresh findings must settle the debt silently; got {result.stdout!r}"
        )
        assert not review.exists(), "settling must clear the review marker"
        assert not retry.exists(), "settling must clear the retry marker"
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        _cleanup(review, retry)


def test_stale_findings_do_not_settle_the_debt():
    """Findings older than the marker (code changed again after the wave) must
    NOT settle - the block must fire. This is the review-then-edit-again case."""
    session_id = str(uuid.uuid4())
    review, retry = _review_marker(session_id), _retry_marker(session_id)
    cwd = tempfile.mkdtemp()
    try:
        run_dir = Path(cwd) / ".forge" / "run"
        run_dir.mkdir(parents=True)
        findings = run_dir / "findings-correctness.md"
        findings.write_text("pass")
        review.write_text("1")
        findings_mtime = findings.stat().st_mtime
        os.utime(review, (findings_mtime + 10, findings_mtime + 10))
        result = _run_hook(
            {"session_id": session_id, "cwd": cwd, "stop_hook_active": False}
        )
        assert result.returncode == 0, f"got {result.returncode}: {result.stderr!r}"
        parsed = json.loads(result.stdout)
        assert parsed.get("decision") == "block", (
            f"findings older than the last change must not settle the debt; got {parsed!r}"
        )
        assert review.exists(), "a block must leave the review debt armed"
        assert retry.exists(), "a block must burn the single retry"
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        _cleanup(review, retry)


def test_unreadable_findings_file_does_not_crash_or_settle():
    """A findings entry whose stat() raises (here a dangling symlink) is skipped,
    not fatal: the hook stays fail-toward-block rather than crashing."""
    session_id = str(uuid.uuid4())
    review, retry = _review_marker(session_id), _retry_marker(session_id)
    cwd = tempfile.mkdtemp()
    try:
        review.write_text("1")
        run_dir = Path(cwd) / ".forge" / "run"
        run_dir.mkdir(parents=True)
        (run_dir / "findings-correctness.md").symlink_to(Path(cwd) / "gone.md")
        result = _run_hook(
            {"session_id": session_id, "cwd": cwd, "stop_hook_active": False}
        )
        assert result.returncode == 0, f"got {result.returncode}: {result.stderr!r}"
        parsed = json.loads(result.stdout)
        assert parsed.get("decision") == "block", (
            f"an unreadable findings file must not settle the debt; got {parsed!r}"
        )
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        _cleanup(review, retry)


def test_no_marker_is_silent_pass():
    session_id = str(uuid.uuid4())
    result = _run_hook({"session_id": session_id, "stop_hook_active": False})
    assert result.returncode == 0, f"got {result.returncode}: {result.stderr!r}"
    assert result.stdout.strip() == "", f"got {result.stdout!r}"
    assert not _retry_marker(session_id).exists()


def test_second_stop_after_block_stands_down_and_clears_both_markers():
    session_id = str(uuid.uuid4())
    review, retry = _review_marker(session_id), _retry_marker(session_id)
    cwd = tempfile.mkdtemp()  # isolated: the stand-down must not depend on findings
    try:
        review.write_text("1")
        retry.write_text("1")
        result = _run_hook(
            {"session_id": session_id, "cwd": cwd, "stop_hook_active": False}
        )
        assert result.returncode == 0, f"got {result.returncode}: {result.stderr!r}"
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert not retry.exists(), "the cap must clear the retry marker"
        assert not review.exists(), (
            "the cap must clear the review debt so the gate does not "
            "re-block every other Stop for the rest of the session"
        )
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        _cleanup(review, retry)


def test_stop_hook_active_short_circuits_and_keeps_review_marker():
    session_id = str(uuid.uuid4())
    review, retry = _review_marker(session_id), _retry_marker(session_id)
    try:
        review.write_text("1")
        result = _run_hook({"session_id": session_id, "stop_hook_active": True})
        assert result.returncode == 0, f"got {result.returncode}: {result.stderr!r}"
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert review.exists(), (
            "the stop_hook_active short-circuit must keep the review debt "
            "armed for the next turn"
        )
        assert not retry.exists(), "the short-circuit must clear the retry marker"
    finally:
        _cleanup(review, retry)


def test_unparseable_stdin_is_silent_pass():
    for raw in ("{not valid json", ""):
        result = _run_hook(None, raw_stdin=raw)
        assert result.returncode == 0, (
            f"raw={raw!r}: got {result.returncode}; stderr={result.stderr!r}"
        )
        assert result.stdout.strip() == "", f"raw={raw!r}: got {result.stdout!r}"
