"""Tests for hooks/mark-code-change.py.

It is a PostToolUse (Edit|Write) hook that reads a JSON payload from stdin:

    {"session_id": "...", "cwd": "...", "tool_name": "Edit"|"Write"|...,
     "tool_input": {"file_path": "..."}}

CONTRACT:
  - ALWAYS exits 0 with EMPTY stdout (a marker-arming side effect hook, never
    a decision/block hook - it must never surface anything to the agent).
  - Arms three session-keyed marker files when, and only when, ALL of:
      * tool_name is "Edit" or "Write"
      * tool_input.file_path is present and resolves to a path INSIDE cwd
      * the resolved (symlink-following) path has neither ".forge" nor
        ".alp-river" as an exact path component (run scratch dirs are excluded
        so the gates don't self-trigger on the run's own bookkeeping writes)
    Markers: /tmp/.claude-code-changed-tests-<session_id>
             /tmp/.claude-code-changed-build-<session_id>
             /tmp/.claude-code-changed-review-<session_id>
    All markers arm together (Edit and Write arm identically).
  - CLEARS the review marker when the write is a lens findings file
    (findings-<lens>.md) inside a .forge run dir - the deterministic
    "a review ran" signal consumed by review-owed.py.
  - session_id missing/empty falls back to a pid-keyed marker name so the
    gate still arms for a single-process invocation:
      /tmp/.claude-code-changed-<kind>-fallback-<pid>
  - Any of: unparseable stdin, missing tool_input.file_path, a non-Edit/Write
    tool_name, a file_path outside cwd, or the scratch-dir exclusion -> no
    markers are created, exit 0, empty stdout (fail-open, never crashes).

Idiom: subprocess-driven, JSON-on-stdin, mirroring hooks/tests/test_verify_tests.py.
No inline shell echoes of git verbs in any payload here.
"""

import glob
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

# Path to the script under test (does not exist yet - tests are red by design)
MARK_CODE_CHANGE_PY = Path(__file__).resolve().parents[1] / "mark-code-change.py"


def _run_hook(payload, *, raw_stdin=None, env=None):
    """Mirror of the _run_cli pattern used in test_route.py / test_verify_tests.py.

    Pass either a payload dict (JSON-encoded onto stdin) or raw_stdin (a literal
    string, for the unparseable-stdin case). env overrides the subprocess
    environment when provided.
    """
    stdin_text = raw_stdin if raw_stdin is not None else json.dumps(payload)
    return subprocess.run(
        ["python3", str(MARK_CODE_CHANGE_PY)],
        input=stdin_text,
        capture_output=True,
        text=True,
        env=env,
    )


def _markers(session_id):
    return (
        Path(f"/tmp/.claude-code-changed-tests-{session_id}"),
        Path(f"/tmp/.claude-code-changed-build-{session_id}"),
        Path(f"/tmp/.claude-code-changed-review-{session_id}"),
    )


def _cleanup(*paths):
    for p in paths:
        if p is not None and p.exists():
            p.unlink()


# ---------------------------------------------------------------------------
# TC-MCC-01: Edit on a file under cwd -> both markers created, silent
# ---------------------------------------------------------------------------


def test_edit_under_cwd_arms_both_markers_silently():
    session_id = str(uuid.uuid4())
    tests_marker, build_marker, review_marker = _markers(session_id)
    cwd = tempfile.mkdtemp()
    try:
        target = Path(cwd) / "app.py"
        target.write_text("print(1)\n")
        result = _run_hook(
            {
                "session_id": session_id,
                "cwd": cwd,
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
            }
        )
        assert result.returncode == 0, (
            f"expected returncode 0, got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert (
            result.stdout.strip() == ""
        ), f"marker-arming hook must never write stdout, got {result.stdout!r}"
        assert tests_marker.exists(), f"expected tests marker at {tests_marker}"
        assert build_marker.exists(), f"expected build marker at {build_marker}"
        assert review_marker.exists(), f"expected review marker at {review_marker}"
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        _cleanup(tests_marker, build_marker, review_marker)


# ---------------------------------------------------------------------------
# TC-MCC-02: Write payload arms identically to Edit
# ---------------------------------------------------------------------------


def test_write_under_cwd_arms_both_markers_identically_to_edit():
    session_id = str(uuid.uuid4())
    tests_marker, build_marker, review_marker = _markers(session_id)
    cwd = tempfile.mkdtemp()
    try:
        target = Path(cwd) / "new_file.py"
        result = _run_hook(
            {
                "session_id": session_id,
                "cwd": cwd,
                "tool_name": "Write",
                "tool_input": {"file_path": str(target)},
            }
        )
        assert result.returncode == 0, (
            f"expected returncode 0, got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert (
            result.stdout.strip() == ""
        ), f"marker-arming hook must never write stdout, got {result.stdout!r}"
        assert tests_marker.exists(), f"expected tests marker at {tests_marker}"
        assert build_marker.exists(), f"expected build marker at {build_marker}"
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        _cleanup(tests_marker, build_marker, review_marker)


# ---------------------------------------------------------------------------
# TC-MCC-03: file under <cwd>/.alp-river/artifacts/... -> excluded, no markers
# ---------------------------------------------------------------------------


def test_alp_river_scratch_path_is_excluded():
    session_id = str(uuid.uuid4())
    tests_marker, build_marker, review_marker = _markers(session_id)
    cwd = tempfile.mkdtemp()
    try:
        artifacts_dir = Path(cwd) / ".alp-river" / "artifacts"
        artifacts_dir.mkdir(parents=True)
        target = artifacts_dir / "plan-example.md"
        target.write_text("plan body")
        result = _run_hook(
            {
                "session_id": session_id,
                "cwd": cwd,
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
            }
        )
        assert result.returncode == 0, (
            f"expected returncode 0, got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert (
            not tests_marker.exists()
        ), "a write inside .alp-river must not arm the tests marker"
        assert (
            not build_marker.exists()
        ), "a write inside .alp-river must not arm the build marker"
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        _cleanup(tests_marker, build_marker, review_marker)


# ---------------------------------------------------------------------------
# TC-MCC-04: file outside cwd -> no markers
# ---------------------------------------------------------------------------


def test_file_outside_cwd_creates_no_markers():
    session_id = str(uuid.uuid4())
    tests_marker, build_marker, review_marker = _markers(session_id)
    cwd = tempfile.mkdtemp()
    outside = tempfile.mkdtemp()
    try:
        target = Path(outside) / "scratch.md"
        target.write_text("notes\n")
        result = _run_hook(
            {
                "session_id": session_id,
                "cwd": cwd,
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
            }
        )
        assert result.returncode == 0, (
            f"expected returncode 0, got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert (
            not tests_marker.exists()
        ), "a write outside cwd must not arm the tests marker"
        assert (
            not build_marker.exists()
        ), "a write outside cwd must not arm the build marker"
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        shutil.rmtree(outside, ignore_errors=True)
        _cleanup(tests_marker, build_marker, review_marker)


# ---------------------------------------------------------------------------
# TC-MCC-05: dir named "not.alp-river-backup" is NOT excluded (component match
# only, not a substring match)
# ---------------------------------------------------------------------------


def test_similarly_named_dir_is_not_excluded_by_substring():
    session_id = str(uuid.uuid4())
    tests_marker, build_marker, review_marker = _markers(session_id)
    cwd = tempfile.mkdtemp()
    try:
        lookalike_dir = Path(cwd) / "not.alp-river-backup"
        lookalike_dir.mkdir()
        target = lookalike_dir / "file.py"
        target.write_text("print(1)\n")
        result = _run_hook(
            {
                "session_id": session_id,
                "cwd": cwd,
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
            }
        )
        assert result.returncode == 0, (
            f"expected returncode 0, got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert tests_marker.exists(), (
            "the exclusion must match the exact '.alp-river' path component, "
            "not a substring of a differently-named directory - expected the "
            f"tests marker at {tests_marker} to exist"
        )
        assert build_marker.exists(), (
            "the exclusion must match the exact '.alp-river' path component, "
            "not a substring of a differently-named directory - expected the "
            f"build marker at {build_marker} to exist"
        )
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        _cleanup(tests_marker, build_marker, review_marker)


# ---------------------------------------------------------------------------
# TC-MCC-06: missing tool_input.file_path -> no markers
# ---------------------------------------------------------------------------


def test_missing_file_path_creates_no_markers():
    session_id = str(uuid.uuid4())
    tests_marker, build_marker, review_marker = _markers(session_id)
    cwd = tempfile.mkdtemp()
    try:
        result = _run_hook(
            {
                "session_id": session_id,
                "cwd": cwd,
                "tool_name": "Edit",
                "tool_input": {},
            }
        )
        assert result.returncode == 0, (
            f"expected returncode 0, got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert not tests_marker.exists()
        assert not build_marker.exists()
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        _cleanup(tests_marker, build_marker, review_marker)


# ---------------------------------------------------------------------------
# TC-MCC-07: tool_name "Bash" (not Edit/Write) -> no markers
# ---------------------------------------------------------------------------


def test_non_edit_write_tool_name_creates_no_markers():
    session_id = str(uuid.uuid4())
    tests_marker, build_marker, review_marker = _markers(session_id)
    cwd = tempfile.mkdtemp()
    try:
        target = Path(cwd) / "app.py"
        target.write_text("print(1)\n")
        result = _run_hook(
            {
                "session_id": session_id,
                "cwd": cwd,
                "tool_name": "Bash",
                "tool_input": {"file_path": str(target)},
            }
        )
        assert result.returncode == 0, (
            f"expected returncode 0, got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert not tests_marker.exists()
        assert not build_marker.exists()
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        _cleanup(tests_marker, build_marker, review_marker)


# ---------------------------------------------------------------------------
# TC-MCC-08: unparseable stdin -> no markers, exit 0, empty stdout
# ---------------------------------------------------------------------------


def test_unparseable_stdin_is_silent_noop():
    for raw in ("{not valid json", ""):
        result = _run_hook(None, raw_stdin=raw)
        assert result.returncode == 0, (
            f"raw={raw!r}: expected returncode 0, got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert (
            result.stdout.strip() == ""
        ), f"raw={raw!r}: expected empty stdout, got {result.stdout!r}"


# ---------------------------------------------------------------------------
# TC-MCC-09: session_id omitted/empty -> fallback pid-keyed markers
# ---------------------------------------------------------------------------


def test_missing_session_id_falls_back_to_pid_keyed_markers():
    before = (
        set(glob.glob("/tmp/.claude-code-changed-tests-fallback-*"))
        | set(glob.glob("/tmp/.claude-code-changed-build-fallback-*"))
        | set(glob.glob("/tmp/.claude-code-changed-review-fallback-*"))
    )
    cwd = tempfile.mkdtemp()
    new_markers = []
    try:
        target = Path(cwd) / "app.py"
        target.write_text("print(1)\n")
        result = _run_hook(
            {
                "cwd": cwd,
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
            }
        )
        assert result.returncode == 0, (
            f"expected returncode 0, got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        after = (
            set(glob.glob("/tmp/.claude-code-changed-tests-fallback-*"))
            | set(glob.glob("/tmp/.claude-code-changed-build-fallback-*"))
            | set(glob.glob("/tmp/.claude-code-changed-review-fallback-*"))
        )
        new_markers = sorted(after - before)
        assert len(new_markers) == 3, (
            "expected exactly one new fallback marker per kind (tests, build, "
            f"review) to appear; new_markers={new_markers!r}"
        )
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        for m in new_markers:
            p = Path(m)
            if p.exists():
                p.unlink()


# ---------------------------------------------------------------------------
# TC-MCC-10: symlink inside cwd resolving outside cwd -> no markers
# ---------------------------------------------------------------------------


def test_symlink_escaping_cwd_creates_no_markers():
    session_id = str(uuid.uuid4())
    tests_marker, build_marker, review_marker = _markers(session_id)
    cwd = tempfile.mkdtemp()
    outside = tempfile.mkdtemp()
    try:
        real_target = Path(outside) / "escaped.py"
        real_target.write_text("print(1)\n")
        link = Path(cwd) / "link"
        link.symlink_to(outside, target_is_directory=True)
        target = link / "escaped.py"
        result = _run_hook(
            {
                "session_id": session_id,
                "cwd": cwd,
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
            }
        )
        assert result.returncode == 0, (
            f"expected returncode 0, got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert (
            not tests_marker.exists()
        ), "a symlinked path that resolves outside cwd must not arm the tests marker"
        assert (
            not build_marker.exists()
        ), "a symlinked path that resolves outside cwd must not arm the build marker"
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        shutil.rmtree(outside, ignore_errors=True)
        _cleanup(tests_marker, build_marker, review_marker)


# ---------------------------------------------------------------------------
# TC-MCC-11: stdout is ALWAYS empty - cross-cutting, re-asserted per case above
# (each test already asserts result.stdout.strip() == ""; no separate run needed)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# TC-MCC-12: file under <cwd>/.forge/<slug>/... -> excluded, no markers
# ---------------------------------------------------------------------------


def test_forge_scratch_path_is_excluded():
    session_id = str(uuid.uuid4())
    tests_marker, build_marker, review_marker = _markers(session_id)
    cwd = tempfile.mkdtemp()
    try:
        run_dir = Path(cwd) / ".forge" / "example-run"
        run_dir.mkdir(parents=True)
        target = run_dir / "plan.md"
        target.write_text("plan body")
        result = _run_hook(
            {
                "session_id": session_id,
                "cwd": cwd,
                "tool_name": "Write",
                "tool_input": {"file_path": str(target)},
            }
        )
        assert result.returncode == 0, (
            f"expected returncode 0, got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert not tests_marker.exists(), "a .forge write must not arm the tests marker"
        assert not build_marker.exists(), "a .forge write must not arm the build marker"
        assert (
            not review_marker.exists()
        ), "a .forge write must not arm the review marker"
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        _cleanup(tests_marker, build_marker, review_marker)


# ---------------------------------------------------------------------------
# TC-MCC-13: a findings-<lens>.md write in a .forge run dir CLEARS the review
# marker (the deterministic "a review ran" signal) and arms nothing
# ---------------------------------------------------------------------------


def test_findings_write_in_forge_run_dir_clears_review_marker():
    session_id = str(uuid.uuid4())
    tests_marker, build_marker, review_marker = _markers(session_id)
    cwd = tempfile.mkdtemp()
    try:
        review_marker.write_text("1")
        run_dir = Path(cwd) / ".forge" / "example-run"
        run_dir.mkdir(parents=True)
        target = run_dir / "findings-correctness.md"
        result = _run_hook(
            {
                "session_id": session_id,
                "cwd": cwd,
                "tool_name": "Write",
                "tool_input": {"file_path": str(target)},
            }
        )
        assert result.returncode == 0, (
            f"expected returncode 0, got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert (
            not review_marker.exists()
        ), "a findings-<lens>.md write in a .forge run dir must clear the review marker"
        assert not tests_marker.exists(), "a findings write must not arm the tests marker"
        assert not build_marker.exists(), "a findings write must not arm the build marker"
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        _cleanup(tests_marker, build_marker, review_marker)


# ---------------------------------------------------------------------------
# TC-MCC-14: a findings-named file OUTSIDE .forge does NOT clear the review
# marker (and, as a real project file, arms all three)
# ---------------------------------------------------------------------------


def test_findings_name_outside_forge_does_not_clear_review_marker():
    session_id = str(uuid.uuid4())
    tests_marker, build_marker, review_marker = _markers(session_id)
    cwd = tempfile.mkdtemp()
    try:
        review_marker.write_text("1")
        target = Path(cwd) / "findings-correctness.md"
        target.write_text("not a run artifact")
        result = _run_hook(
            {
                "session_id": session_id,
                "cwd": cwd,
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
            }
        )
        assert result.returncode == 0, (
            f"expected returncode 0, got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert result.stdout.strip() == "", f"got {result.stdout!r}"
        assert review_marker.exists(), (
            "a findings-named file outside a .forge run dir is a project file: "
            "it must not settle the review debt"
        )
        assert tests_marker.exists(), "a project-file edit must still arm the tests marker"
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        _cleanup(tests_marker, build_marker, review_marker)
