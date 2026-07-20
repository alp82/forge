"""Tests for hooks/mark-code-change.py - the codex PostToolUse marker armer.

It reads a JSON payload from stdin:

    {"session_id": "...", "cwd": "...", "tool_name": "<edit tool>",
     "tool_input": {"file_path": "..."} | {"path": "..."} | {"patch": "..."}}

CONTRACT (codex port - RISK-4 tolerant reads):
  - ALWAYS exits 0 with EMPTY stdout (a marker-arming side effect hook, never
    a decision/block hook - it must never surface anything to the agent).
  - Matched tool names: apply_patch / edit / write / str_replace / create_file
    plus the Claude-shaped Edit / Write. Any other tool_name is a silent no-op.
  - Path derivation: tool_input.file_path, then tool_input.path, then the
    apply_patch body (tool_input.patch / tool_input.input) scanned for
    `*** Update File:` / `*** Add File:` paths (relative paths join to cwd).
  - Arms three session-keyed marker files when any derived path is a real
    project file: inside cwd, and the resolved (symlink-following) path has
    neither ".forge" nor ".alp-river" as an exact path component.
    Markers: /tmp/.codex-changed-tests-<session_id>
             /tmp/.codex-changed-build-<session_id>
             /tmp/.codex-changed-review-<session_id>
    All markers arm together.
  - FAIL-TOWARD-ARM: a matched edit tool with NO derivable path arms anyway -
    failing toward skip would silently disarm the whole gated tier. Derived
    paths that all fail the project-file judgment (outside cwd, scratch dir,
    escaping symlink) do NOT arm - the judgment ran and said no.
  - is INERT on a .forge run-dir write (including a findings-<lens>.md lens
    file): arms nothing and clears nothing. Settling the review debt moved to
    review-owed.py, which checks findings mtime at Stop under the main
    session_id.
  - session_id missing/empty falls back to a pid-keyed marker name:
    /tmp/.codex-changed-<kind>-fallback-<pid>
  - Unparseable stdin or a non-edit tool_name -> no markers, exit 0, empty
    stdout (fail-open on the outer frame, never crashes).

Idiom: subprocess-driven, JSON-on-stdin, mirroring the sibling gate suites.
"""

import glob
import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

MARK_CODE_CHANGE_PY = Path(__file__).resolve().parents[1] / "mark-code-change.py"


def _run_hook(payload, *, raw_stdin=None, env=None):
    """Pass either a payload dict (JSON-encoded onto stdin) or raw_stdin (a
    literal string, for the unparseable-stdin case)."""
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
        Path(f"/tmp/.codex-changed-tests-{session_id}"),
        Path(f"/tmp/.codex-changed-build-{session_id}"),
        Path(f"/tmp/.codex-changed-review-{session_id}"),
    )


def _cleanup(*paths):
    for p in paths:
        if p is not None and p.exists():
            p.unlink()


def _assert_silent_ok(result):
    assert result.returncode == 0, (
        f"expected returncode 0, got {result.returncode}; "
        f"stderr={result.stderr!r}"
    )
    assert (
        result.stdout.strip() == ""
    ), f"marker-arming hook must never write stdout, got {result.stdout!r}"


# ---------------------------------------------------------------------------
# TC-MCC-01: Edit on a file under cwd -> all three markers created, silent
# ---------------------------------------------------------------------------


def test_edit_under_cwd_arms_all_markers_silently():
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
        _assert_silent_ok(result)
        assert tests_marker.exists(), f"expected tests marker at {tests_marker}"
        assert build_marker.exists(), f"expected build marker at {build_marker}"
        assert review_marker.exists(), f"expected review marker at {review_marker}"
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        _cleanup(tests_marker, build_marker, review_marker)


# ---------------------------------------------------------------------------
# TC-MCC-02: lower-case codex tool names arm identically
# ---------------------------------------------------------------------------


def test_lowercase_codex_tool_names_arm_identically():
    for tool in ("edit", "write", "str_replace", "create_file"):
        session_id = str(uuid.uuid4())
        tests_marker, build_marker, review_marker = _markers(session_id)
        cwd = tempfile.mkdtemp()
        try:
            target = Path(cwd) / "new_file.py"
            result = _run_hook(
                {
                    "session_id": session_id,
                    "cwd": cwd,
                    "tool_name": tool,
                    "tool_input": {"file_path": str(target)},
                }
            )
            _assert_silent_ok(result)
            assert tests_marker.exists(), (
                f"tool {tool!r}: expected tests marker at {tests_marker}"
            )
            assert build_marker.exists(), (
                f"tool {tool!r}: expected build marker at {build_marker}"
            )
        finally:
            shutil.rmtree(cwd, ignore_errors=True)
            _cleanup(tests_marker, build_marker, review_marker)


# ---------------------------------------------------------------------------
# TC-MCC-03: tool_input.path (alternate field) is read like file_path
# ---------------------------------------------------------------------------


def test_path_field_is_read_like_file_path():
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
                "tool_name": "edit",
                "tool_input": {"path": str(target)},
            }
        )
        _assert_silent_ok(result)
        assert tests_marker.exists(), f"expected tests marker at {tests_marker}"
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        _cleanup(tests_marker, build_marker, review_marker)


# ---------------------------------------------------------------------------
# apply_patch: patch-body path parsing (RISK-4)
# ---------------------------------------------------------------------------


def test_apply_patch_update_file_relative_path_arms():
    session_id = str(uuid.uuid4())
    tests_marker, build_marker, review_marker = _markers(session_id)
    cwd = tempfile.mkdtemp()
    try:
        patch = (
            "*** Begin Patch\n"
            "*** Update File: src/app.py\n"
            "@@\n-print(1)\n+print(2)\n"
            "*** End Patch\n"
        )
        result = _run_hook(
            {
                "session_id": session_id,
                "cwd": cwd,
                "tool_name": "apply_patch",
                "tool_input": {"patch": patch},
            }
        )
        _assert_silent_ok(result)
        assert tests_marker.exists(), (
            "an apply_patch body updating a project-relative file must arm; "
            f"expected {tests_marker}"
        )
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        _cleanup(tests_marker, build_marker, review_marker)


def test_apply_patch_add_file_in_input_field_arms():
    session_id = str(uuid.uuid4())
    tests_marker, build_marker, review_marker = _markers(session_id)
    cwd = tempfile.mkdtemp()
    try:
        patch = (
            "*** Begin Patch\n"
            "*** Add File: docs/note.md\n"
            "+hello\n"
            "*** End Patch\n"
        )
        result = _run_hook(
            {
                "session_id": session_id,
                "cwd": cwd,
                "tool_name": "apply_patch",
                "tool_input": {"input": patch},
            }
        )
        _assert_silent_ok(result)
        assert tests_marker.exists(), (
            "an apply_patch body (tool_input.input) adding a project file must "
            f"arm; expected {tests_marker}"
        )
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        _cleanup(tests_marker, build_marker, review_marker)


def test_apply_patch_touching_only_forge_scratch_does_not_arm():
    session_id = str(uuid.uuid4())
    tests_marker, build_marker, review_marker = _markers(session_id)
    cwd = tempfile.mkdtemp()
    try:
        patch = (
            "*** Begin Patch\n"
            "*** Update File: .forge/run/plan.md\n"
            "@@\n-a\n+b\n"
            "*** End Patch\n"
        )
        result = _run_hook(
            {
                "session_id": session_id,
                "cwd": cwd,
                "tool_name": "apply_patch",
                "tool_input": {"patch": patch},
            }
        )
        _assert_silent_ok(result)
        assert not tests_marker.exists(), (
            "an apply_patch touching only .forge scratch paths must not arm"
        )
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        _cleanup(tests_marker, build_marker, review_marker)


# ---------------------------------------------------------------------------
# FAIL-TOWARD-ARM: matched edit tool, no derivable path -> arm anyway
# ---------------------------------------------------------------------------


def test_matched_tool_with_no_derivable_path_arms_anyway():
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
        _assert_silent_ok(result)
        assert tests_marker.exists(), (
            "a matched edit tool with no derivable file path must arm anyway "
            "(fail-toward-arm) - failing toward skip would silently disarm the "
            "gated tier"
        )
        assert build_marker.exists()
        assert review_marker.exists()
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        _cleanup(tests_marker, build_marker, review_marker)


# ---------------------------------------------------------------------------
# TC-MCC-04: derived path outside cwd -> judged and rejected, no markers
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
        _assert_silent_ok(result)
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
        _assert_silent_ok(result)
        assert tests_marker.exists(), (
            "the exclusion must match the exact '.alp-river' path component, "
            "not a substring of a differently-named directory - expected the "
            f"tests marker at {tests_marker} to exist"
        )
        assert build_marker.exists()
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        _cleanup(tests_marker, build_marker, review_marker)


# ---------------------------------------------------------------------------
# TC-MCC-07: non-edit tool_name -> no markers
# ---------------------------------------------------------------------------


def test_non_edit_tool_name_creates_no_markers():
    for tool in ("Bash", "shell", "Read"):
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
                    "tool_name": tool,
                    "tool_input": {"file_path": str(target)},
                }
            )
            _assert_silent_ok(result)
            assert not tests_marker.exists(), f"tool {tool!r} must not arm"
            assert not build_marker.exists(), f"tool {tool!r} must not arm"
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
        set(glob.glob("/tmp/.codex-changed-tests-fallback-*"))
        | set(glob.glob("/tmp/.codex-changed-build-fallback-*"))
        | set(glob.glob("/tmp/.codex-changed-review-fallback-*"))
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
        _assert_silent_ok(result)
        after = (
            set(glob.glob("/tmp/.codex-changed-tests-fallback-*"))
            | set(glob.glob("/tmp/.codex-changed-build-fallback-*"))
            | set(glob.glob("/tmp/.codex-changed-review-fallback-*"))
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
        _assert_silent_ok(result)
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
        _assert_silent_ok(result)
        assert not tests_marker.exists(), "a .forge write must not arm the tests marker"
        assert not build_marker.exists(), "a .forge write must not arm the build marker"
        assert (
            not review_marker.exists()
        ), "a .forge write must not arm the review marker"
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        _cleanup(tests_marker, build_marker, review_marker)


# ---------------------------------------------------------------------------
# TC-MCC-13: a findings-<lens>.md write in a .forge run dir is INERT here -
# arms nothing and clears nothing. Settling the review debt moved to
# review-owed.py (Stop-time findings-mtime check under the main session_id),
# so a pre-armed review marker must SURVIVE this write.
# ---------------------------------------------------------------------------


def test_findings_write_in_forge_run_dir_is_inert():
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
        _assert_silent_ok(result)
        assert review_marker.exists(), (
            "a .forge findings write must NOT clear the review marker - "
            "clearing moved to review-owed.py at Stop"
        )
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
        _assert_silent_ok(result)
        assert review_marker.exists(), (
            "a findings-named file outside a .forge run dir is a project file: "
            "it must not settle the review debt"
        )
        assert tests_marker.exists(), "a project-file edit must still arm the tests marker"
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
        _cleanup(tests_marker, build_marker, review_marker)
