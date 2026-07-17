"""Tests for hooks/review-owed.py - the review-owed Stop gate.

Contract: mark-code-change.py arms /tmp/.claude-code-changed-review-<sid> on
every real project edit and clears it when a lens findings file is written in
a .forge run dir. At Stop, an armed marker means the change was never
reviewed: block once with a pointer at the review wave. Max 1 block per
session (at the cap both markers clear and the gate stands down); the
stop_hook_active short-circuit never re-blocks an already-blocked loop and
keeps the review debt armed for the next turn. Always exit 0; every non-block
branch prints nothing.
"""

import json
import subprocess
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
    try:
        review.write_text("1")
        result = _run_hook({"session_id": session_id, "stop_hook_active": False})
        assert result.returncode == 0, f"got {result.returncode}: {result.stderr!r}"
        parsed = json.loads(result.stdout)
        assert parsed.get("decision") == "block", f"got {result.stdout!r}"
        assert "crossfire" in parsed.get("reason", ""), (
            f"the block reason must point at the review wave; got {parsed!r}"
        )
        assert review.exists(), "a block must leave the review debt armed"
        assert retry.exists(), "a block must burn the single retry"
    finally:
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
    try:
        review.write_text("1")
        retry.write_text("1")
        result = _run_hook({"session_id": session_id, "stop_hook_active": False})
        assert result.returncode == 0, f"got {result.returncode}: {result.stderr!r}"
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert not retry.exists(), "the cap must clear the retry marker"
        assert not review.exists(), (
            "the cap must clear the review debt so the gate does not "
            "re-block every other Stop for the rest of the session"
        )
    finally:
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
