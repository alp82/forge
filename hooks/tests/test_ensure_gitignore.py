"""Tests for hooks/ensure-gitignore.sh - a SessionStart hook (startup/resume).

CONTRACT:
  - Reads {"cwd": "..."} on STDIN (other fields, if any, are ignored).
  - ALWAYS exits 0 (never crashes, never non-zero - all writes guarded with `|| true`).
  - Not a git work tree -> exit 0, silent (empty stdout), no .gitignore created.
  - Git work tree:
    - Ensures a `.alp-river/` line exists in .gitignore, creating the file if
      absent, appending to it if present (with a trailing-newline safety check
      before appending), guarded by the idempotency regex
      `^[[:space:]]*/?\\.alp-river/?[[:space:]]*$` (optional leading slash,
      optional trailing slash) so a matching line is never duplicated.
    - Detects any file tracked by git under .alp-river/ and, when found, emits a
      turn-1 instruction naming the exact command `git rm -r --cached .alp-river`
      - the hook NEVER executes that command itself.
  - stdout is EITHER empty OR one valid JSON object carrying
    hookSpecificOutput.additionalContext (STDOUT-pure).
  - `.cwd` missing/empty falls back to $PWD.
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "ensure-gitignore.sh"
HOOKS_JSON = Path(__file__).resolve().parents[1] / "hooks.json"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def init_git_repo(tmp):
    """Initialize a git repo at tmp with a usable local identity."""
    subprocess.run(["git", "init", "-q", str(tmp)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )


def commit_tracked_alp_river_file(tmp):
    """Create and commit a file under .alp-river/ so git ls-files finds it.

    Uses `git add -f` so the file is force-added even when a pre-existing
    .gitignore already ignores .alp-river/ - reproducing the "tracked despite
    being ignored" state some scenarios require (a plain `git add .` would
    silently skip an ignored path and never enter it into the index)."""
    d = tmp / ".alp-river" / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    f = d / "plan-x.md"
    f.write_text("plan", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp), "add", "-f", "."], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(tmp), "commit", "-q", "-m", "seed tracked .alp-river file"],
        check=True,
        capture_output=True,
    )


def tracked_alp_river_paths(tmp):
    """Return the (possibly empty) output of `git ls-files -- .alp-river` in tmp."""
    result = subprocess.run(
        ["git", "-C", str(tmp), "ls-files", "--", ".alp-river"],
        capture_output=True,
        text=True,
    )
    return result.stdout


def run_hook(cwd_field=None, run_cwd=None, raw_stdin=None, env=None):
    """Invoke ensure-gitignore.sh via bash with a {"cwd": ...} payload on STDIN.

    - cwd_field: value placed in the JSON payload's "cwd" key. If None, the key
      is omitted entirely (tests the $PWD fallback).
    - run_cwd: the subprocess's actual working directory (defaults to cwd_field
      when both are relevant; the hook is expected to fall back to $PWD).
    - raw_stdin: if given, used verbatim as stdin instead of building JSON
      (used for the empty/malformed-stdin case).
    - Returns the subprocess.CompletedProcess result.
    """
    if raw_stdin is not None:
        payload = raw_stdin
    else:
        payload = json.dumps({"cwd": cwd_field} if cwd_field is not None else {})
    return subprocess.run(
        ["bash", str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        cwd=run_cwd,
        env=env,
    )


def assert_exit0(r, label):
    assert r.returncode == 0, (
        f"{label}: hook must ALWAYS exit 0; got returncode={r.returncode}; "
        f"stderr={r.stderr!r}"
    )


def assert_stdout_pure_json(r, label):
    """When stdout is non-empty, it must be exactly one legal
    hookSpecificOutput.additionalContext JSON object - no stray text mixed in."""
    stripped = r.stdout.strip()
    assert stripped, f"{label}: expected non-empty stdout, got {r.stdout!r}"
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"{label}: stdout must be pure JSON (no stray echo/debug text); "
            f"got stdout={r.stdout!r}; error={exc}"
        )
    assert "hookSpecificOutput" in parsed and "additionalContext" in parsed.get(
        "hookSpecificOutput", {}
    ), f"{label}: expected hookSpecificOutput.additionalContext shape; got {parsed!r}"


# ---------------------------------------------------------------------------
# A. Hook runtime behavior
# ---------------------------------------------------------------------------


def test_eg_1_not_git_repo_silent_exit0():
    """EG-1: cwd is a plain (non-git) directory -> exit 0, empty stdout, no .gitignore created."""
    tmp = Path(tempfile.mkdtemp())
    try:
        r = run_hook(cwd_field=str(tmp))
        assert_exit0(r, "EG-1")
        assert (
            r.stdout.strip() == ""
        ), f"EG-1: expected empty stdout for a non-git directory; got {r.stdout!r}"
        assert not (
            tmp / ".gitignore"
        ).exists(), "EG-1: no .gitignore should be created outside a git work tree"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_eg_2_fresh_repo_no_gitignore_creates_it():
    """EG-2: git repo with no .gitignore -> exit 0, file created with a .alp-river/ line,
    stdout notes the addition."""
    tmp = Path(tempfile.mkdtemp())
    try:
        init_git_repo(tmp)
        r = run_hook(cwd_field=str(tmp))
        assert_exit0(r, "EG-2")
        gi = tmp / ".gitignore"
        assert gi.exists(), "EG-2: .gitignore must be created when absent"
        assert ".alp-river/" in gi.read_text(
            encoding="utf-8"
        ), "EG-2: created .gitignore must contain a .alp-river/ line"
        assert r.stdout.strip(), "EG-2: stdout must note the addition"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_eg_3_existing_gitignore_entry_absent_appends_preserves_content():
    """EG-3: .gitignore has unrelated content and no .alp-river entry -> the
    pre-existing content is preserved, exactly one .alp-river/ line is added,
    stdout notes the addition."""
    tmp = Path(tempfile.mkdtemp())
    try:
        init_git_repo(tmp)
        gi = tmp / ".gitignore"
        gi.write_text("node_modules/\n", encoding="utf-8")
        r = run_hook(cwd_field=str(tmp))
        assert_exit0(r, "EG-3")
        content = gi.read_text(encoding="utf-8")
        assert (
            "node_modules/" in content
        ), "EG-3: pre-existing content must be preserved"
        lines = [ln for ln in content.splitlines() if ln.strip() == ".alp-river/"]
        assert (
            len(lines) == 1
        ), f"EG-3: expected exactly one '.alp-river/' line, got {lines!r} in {content!r}"
        assert r.stdout.strip(), "EG-3: stdout must note the addition"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_eg_4_idempotent_entry_present_with_trailing_slash():
    """EG-4: .gitignore already contains '.alp-river/' verbatim -> file is
    byte-for-byte unchanged, no duplicate line, no 'added' note for this concern."""
    tmp = Path(tempfile.mkdtemp())
    try:
        init_git_repo(tmp)
        gi = tmp / ".gitignore"
        original = ".alp-river/\n"
        gi.write_text(original, encoding="utf-8")
        r = run_hook(cwd_field=str(tmp))
        assert_exit0(r, "EG-4")
        assert gi.read_text(encoding="utf-8") == original, (
            "EG-4: .gitignore must be byte-for-byte unchanged when the entry "
            "already matches with a trailing slash"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_eg_5_idempotent_entry_present_without_trailing_slash():
    """EG-5: .gitignore contains '.alp-river' (no slash) -> no duplicate line
    appended; the optional-slash regex recognizes this as already present."""
    tmp = Path(tempfile.mkdtemp())
    try:
        init_git_repo(tmp)
        gi = tmp / ".gitignore"
        gi.write_text(".alp-river\n", encoding="utf-8")
        r = run_hook(cwd_field=str(tmp))
        assert_exit0(r, "EG-5")
        content = gi.read_text(encoding="utf-8")
        matching_lines = [
            ln
            for ln in content.splitlines()
            if ln.strip() in (".alp-river", ".alp-river/")
        ]
        assert len(matching_lines) == 1, (
            f"EG-5: no duplicate should be appended for a slash-less pre-existing "
            f"entry; got lines {matching_lines!r} in {content!r}"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_eg_6_trailing_newline_safety():
    """EG-6: .gitignore's last line has no trailing newline -> after the hook
    runs, '.alp-river/' is on its own standalone line; the concatenation
    'distalp-river' must not appear anywhere in the file."""
    tmp = Path(tempfile.mkdtemp())
    try:
        init_git_repo(tmp)
        gi = tmp / ".gitignore"
        gi.write_text("dist", encoding="utf-8")  # no trailing newline
        r = run_hook(cwd_field=str(tmp))
        assert_exit0(r, "EG-6")
        content = gi.read_text(encoding="utf-8")
        assert (
            "distalp-river" not in content
        ), f"EG-6: trailing-newline safety violated; got {content!r}"
        assert (
            ".alp-river/" in content.splitlines()
        ), f"EG-6: '.alp-river/' must appear as its own standalone line; got {content!r}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_eg_7_tracked_by_git_emits_instruction_never_runs_it():
    """EG-7: a file under .alp-river/ is committed, .gitignore already correct ->
    stdout contains 'tracked by git' and the exact command
    'git rm -r --cached .alp-river'; the hook must NOT have run that command
    itself (git ls-files still shows the tracked path after the hook runs)."""
    tmp = Path(tempfile.mkdtemp())
    try:
        init_git_repo(tmp)
        (tmp / ".gitignore").write_text(".alp-river/\n", encoding="utf-8")
        commit_tracked_alp_river_file(tmp)
        r = run_hook(cwd_field=str(tmp))
        assert_exit0(r, "EG-7")
        assert (
            "tracked by git" in r.stdout
        ), f"EG-7: expected 'tracked by git' phrase in stdout; got {r.stdout!r}"
        assert (
            "git rm -r --cached .alp-river" in r.stdout
        ), f"EG-7: expected the exact untrack command in stdout; got {r.stdout!r}"
        assert tracked_alp_river_paths(tmp).strip(), (
            "EG-7: the hook must NEVER execute the untrack command itself; "
            "tracked .alp-river paths must still be present after it runs"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_eg_8_tracked_and_gitignore_absent_combined_state():
    """EG-8: a tracked .alp-river file exists AND .gitignore lacks the entry ->
    stdout contains BOTH the addition note and the untrack instruction, AND
    .gitignore now contains '.alp-river/'."""
    tmp = Path(tempfile.mkdtemp())
    try:
        init_git_repo(tmp)
        commit_tracked_alp_river_file(tmp)
        r = run_hook(cwd_field=str(tmp))
        assert_exit0(r, "EG-8")
        gi = tmp / ".gitignore"
        assert gi.exists() and ".alp-river/" in gi.read_text(
            encoding="utf-8"
        ), "EG-8: .gitignore must now contain the .alp-river/ entry"
        assert (
            "git rm -r --cached .alp-river" in r.stdout
        ), f"EG-8: expected the untrack instruction in stdout; got {r.stdout!r}"
        assert r.stdout.strip(), "EG-8: stdout must also note the gitignore addition"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_eg_9_tracked_and_ignored_instruction_only():
    """EG-9: a tracked .alp-river file exists AND .gitignore already contains
    the entry -> stdout contains ONLY the untrack instruction (no addition
    note), and .gitignore still has exactly one .alp-river line (no duplicate)."""
    tmp = Path(tempfile.mkdtemp())
    try:
        init_git_repo(tmp)
        gi = tmp / ".gitignore"
        gi.write_text(".alp-river/\n", encoding="utf-8")
        commit_tracked_alp_river_file(tmp)
        r = run_hook(cwd_field=str(tmp))
        assert_exit0(r, "EG-9")
        assert (
            "git rm -r --cached .alp-river" in r.stdout
        ), f"EG-9: expected the untrack instruction in stdout; got {r.stdout!r}"
        content = gi.read_text(encoding="utf-8")
        matching_lines = [
            ln for ln in content.splitlines() if ln.strip() == ".alp-river/"
        ]
        assert (
            len(matching_lines) == 1
        ), f"EG-9: no duplicate .alp-river/ line should be introduced; got {content!r}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_eg_10_steady_state_fully_silent():
    """EG-10: .gitignore already has the entry AND nothing under .alp-river is
    tracked -> exit 0 AND stdout is exactly empty."""
    tmp = Path(tempfile.mkdtemp())
    try:
        init_git_repo(tmp)
        gi = tmp / ".gitignore"
        gi.write_text(".alp-river/\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(tmp), "add", "."], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(tmp), "commit", "-q", "-m", "add gitignore"],
            check=True,
            capture_output=True,
        )
        r = run_hook(cwd_field=str(tmp))
        assert_exit0(r, "EG-10")
        assert (
            r.stdout.strip() == ""
        ), f"EG-10: expected fully silent steady-state stdout; got {r.stdout!r}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_eg_11_empty_stdin_no_crash():
    """EG-11: no JSON payload at all on stdin, in a plain (non-git) directory ->
    exit 0, no crash, no traceback-like output on stderr."""
    tmp = Path(tempfile.mkdtemp())
    try:
        r = run_hook(raw_stdin="", run_cwd=str(tmp))
        assert_exit0(r, "EG-11")
        assert (
            "Traceback" not in r.stderr
        ), f"EG-11: unexpected traceback on stderr: {r.stderr!r}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_eg_12_missing_cwd_falls_back_to_pwd():
    """EG-12: stdin JSON omits .cwd -> hook falls back to $PWD to locate the
    repo, and behaves per the fresh-repo-creates-gitignore case (EG-2) for
    that directory."""
    tmp = Path(tempfile.mkdtemp())
    try:
        init_git_repo(tmp)
        r = run_hook(cwd_field=None, run_cwd=str(tmp))
        assert_exit0(r, "EG-12")
        gi = tmp / ".gitignore"
        assert gi.exists() and ".alp-river/" in gi.read_text(
            encoding="utf-8"
        ), "EG-12: $PWD fallback must locate the repo and create .gitignore there"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_eg_13_unwritable_gitignore_still_exits_zero():
    """EG-13: .gitignore exists but the containing directory is not writable ->
    exit 0 regardless; a guarded (|| true) write failure must not crash or
    return non-zero."""
    tmp = Path(tempfile.mkdtemp())
    try:
        init_git_repo(tmp)
        gi = tmp / ".gitignore"
        gi.write_text("node_modules/\n", encoding="utf-8")
        tmp.chmod(0o500)  # read+execute only: no new files, no renames, in this dir
        try:
            r = run_hook(cwd_field=str(tmp))
            assert_exit0(r, "EG-13")
        finally:
            tmp.chmod(0o700)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_eg_15_stdout_purity_across_output_scenarios():
    """EG-15: in every scenario that produces output, stdout is exactly the
    legal hookSpecificOutput.additionalContext JSON - no stray echo/debug text
    mixed into stdout."""
    scenarios = []

    tmp_fresh = Path(tempfile.mkdtemp())
    scenarios.append(("fresh-repo-EG2", tmp_fresh, lambda t: init_git_repo(t)))

    def existing_absent(t):
        init_git_repo(t)
        (t / ".gitignore").write_text("node_modules/\n", encoding="utf-8")

    tmp_existing_absent = Path(tempfile.mkdtemp())
    scenarios.append(("existing-absent-EG3", tmp_existing_absent, existing_absent))

    def tracked_ignored(t):
        init_git_repo(t)
        (t / ".gitignore").write_text(".alp-river/\n", encoding="utf-8")
        commit_tracked_alp_river_file(t)

    tmp_tracked_ignored = Path(tempfile.mkdtemp())
    scenarios.append(("tracked-ignored-EG7", tmp_tracked_ignored, tracked_ignored))

    def tracked_absent(t):
        init_git_repo(t)
        commit_tracked_alp_river_file(t)

    tmp_tracked_absent = Path(tempfile.mkdtemp())
    scenarios.append(("tracked-absent-EG8", tmp_tracked_absent, tracked_absent))

    try:
        for label, tmp, setup in scenarios:
            setup(tmp)
            r = run_hook(cwd_field=str(tmp))
            assert_exit0(r, f"EG-15[{label}]")
            assert_stdout_pure_json(r, f"EG-15[{label}]")
    finally:
        for _, tmp, _ in scenarios:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# B. Regex-edge cases
# ---------------------------------------------------------------------------


def test_eg_16_commented_entry_not_recognized_appends_active_line():
    """EG-16: .gitignore contains '# .alp-river/' (commented out, no active
    entry) -> the anchor-only regex does not treat a comment as "already
    present" (a commented line does not ignore the folder), so the hook
    appends an active '.alp-river/' line; the resulting file has both the
    comment and the new active line."""
    tmp = Path(tempfile.mkdtemp())
    try:
        init_git_repo(tmp)
        gi = tmp / ".gitignore"
        gi.write_text("# .alp-river/\n", encoding="utf-8")
        r = run_hook(cwd_field=str(tmp))
        assert_exit0(r, "EG-16")
        content = gi.read_text(encoding="utf-8")
        assert (
            "# .alp-river/" in content
        ), f"EG-16: the pre-existing comment must be preserved; got {content!r}"
        active_lines = [
            ln for ln in content.splitlines() if ln.strip() == ".alp-river/"
        ]
        assert len(active_lines) == 1, (
            f"EG-16: an active '.alp-river/' line must be appended alongside the "
            f"comment (a commented line is not a match); got {content!r}"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_eg_17_leading_slash_variant_recognized_no_duplicate():
    """EG-17: .gitignore contains '/.alp-river/' (leading slash, root-anchored)
    -> the idempotency regex's optional leading slash recognizes this as
    already present, so no second '.alp-river/' line is appended."""
    tmp = Path(tempfile.mkdtemp())
    try:
        init_git_repo(tmp)
        gi = tmp / ".gitignore"
        original_line = "/.alp-river/"
        gi.write_text(original_line + "\n", encoding="utf-8")
        r = run_hook(cwd_field=str(tmp))
        assert_exit0(r, "EG-17")
        content = gi.read_text(encoding="utf-8")
        assert (
            original_line in content
        ), f"EG-17: the pre-existing leading-slash line must be preserved; got {content!r}"
        unslashed_lines = [
            ln for ln in content.splitlines() if ln.strip() == ".alp-river/"
        ]
        assert len(unslashed_lines) == 0, (
            f"EG-17: no additional unslashed '.alp-river/' line should be appended "
            f"when the leading-slash variant already covers the path; got {content!r}"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# C. Registration (hooks/hooks.json)
# ---------------------------------------------------------------------------


def _session_start_matcher(config, matcher_name):
    for block in config.get("hooks", {}).get("SessionStart", []):
        if block.get("matcher") == matcher_name:
            return block.get("hooks", [])
    return []


def _has_ensure_gitignore_entry(hook_list):
    for entry in hook_list:
        if entry.get("type") == "command" and "ensure-gitignore.sh" in entry.get(
            "command", ""
        ):
            return entry
    return None


def test_eg_18_registered_in_session_start_startup():
    """EG-18: SessionStart.startup contains a command-type entry invoking
    ${CLAUDE_PLUGIN_ROOT}/hooks/ensure-gitignore.sh with timeout 5, positioned
    after the existing inject-workflow.sh entry."""
    config = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    startup_hooks = _session_start_matcher(config, "startup")
    entry = _has_ensure_gitignore_entry(startup_hooks)
    assert (
        entry is not None
    ), "EG-18: expected SessionStart.startup to register ensure-gitignore.sh"
    assert (
        entry.get("command") == "${CLAUDE_PLUGIN_ROOT}/hooks/ensure-gitignore.sh"
    ), f"EG-18: unexpected command string: {entry.get('command')!r}"
    assert (
        entry.get("timeout") == 5
    ), f"EG-18: expected timeout 5, got {entry.get('timeout')!r}"

    commands = [h.get("command", "") for h in startup_hooks]
    inject_idx = next(
        (i for i, c in enumerate(commands) if "inject-workflow.sh" in c), None
    )
    ensure_idx = next(
        (i for i, c in enumerate(commands) if "ensure-gitignore.sh" in c), None
    )
    assert (
        inject_idx is not None and ensure_idx is not None
    ), "EG-18: both inject-workflow.sh and ensure-gitignore.sh must be present"
    assert (
        ensure_idx > inject_idx
    ), "EG-18: ensure-gitignore.sh must be positioned after inject-workflow.sh"


def test_eg_19_registered_in_session_start_resume():
    """EG-19: SessionStart.resume contains the same ensure-gitignore.sh entry,
    also positioned after inject-workflow.sh."""
    config = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    resume_hooks = _session_start_matcher(config, "resume")
    entry = _has_ensure_gitignore_entry(resume_hooks)
    assert (
        entry is not None
    ), "EG-19: expected SessionStart.resume to register ensure-gitignore.sh"
    assert (
        entry.get("command") == "${CLAUDE_PLUGIN_ROOT}/hooks/ensure-gitignore.sh"
    ), f"EG-19: unexpected command string: {entry.get('command')!r}"
    assert (
        entry.get("timeout") == 5
    ), f"EG-19: expected timeout 5, got {entry.get('timeout')!r}"

    commands = [h.get("command", "") for h in resume_hooks]
    inject_idx = next(
        (i for i, c in enumerate(commands) if "inject-workflow.sh" in c), None
    )
    ensure_idx = next(
        (i for i, c in enumerate(commands) if "ensure-gitignore.sh" in c), None
    )
    assert (
        inject_idx is not None and ensure_idx is not None
    ), "EG-19: both inject-workflow.sh and ensure-gitignore.sh must be present"
    assert (
        ensure_idx > inject_idx
    ), "EG-19: ensure-gitignore.sh must be positioned after inject-workflow.sh"


def test_eg_20_not_registered_on_clear_or_compact():
    """EG-20: neither the clear nor the compact SessionStart matcher blocks
    reference ensure-gitignore.sh - explicit negative check for the plan's
    stated scope boundary."""
    config = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    for matcher_name in ("clear", "compact"):
        hooks_list = _session_start_matcher(config, matcher_name)
        entry = _has_ensure_gitignore_entry(hooks_list)
        assert entry is None, (
            f"EG-20: ensure-gitignore.sh must NOT be registered on '{matcher_name}'; "
            f"found entry {entry!r}"
        )
