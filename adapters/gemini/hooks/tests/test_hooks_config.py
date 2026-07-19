"""Structural checks on adapters/gemini/hooks/hooks.json for the forge hook surface.

These are static content assertions against hooks.json, not subprocess runs.
The gemini hook surface is exactly six hooks mapped onto gemini's turn/tool
lifecycle events: session-start.sh (BeforeAgent - fires before every turn incl.
the first, the documented context-injection surface), block-git-writes.sh
(BeforeTool over the shell-tool matcher), mark-code-change.py (AfterTool over
the edit-tool matcher), and the three stop-gates (verify-tests.py,
verify-build.py, review-owed.py) on AfterAgent (decision:"block" triggers an
automatic retry turn). Six is the ceiling, not a floor (contract section 9).

Schema note (RISK-6): the gemini survey gives the entry fields (matcher,
type:"command", command, timeout) but not the file's top-level shape; this
suite pins the flat-entries-under-event-keys assumption the adapter ships.

Timeout note (RISK-9): the survey does not fix the timeout unit. The values are
written as milliseconds (5000 / 130000 / 190000) so they are safe under BOTH
readings - correct as ms, and a harmless over-long bound if read as seconds
(the inner subprocess timeout in verify_shared.py is the real execution guard).
"""

import json
import os
import re
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
HOOKS_JSON = HOOKS_DIR / "hooks.json"


def _load():
    return json.loads(HOOKS_JSON.read_text())


def _entries(config, event):
    return config["hooks"][event]


def _all_commands(config):
    return [
        entry.get("command", "")
        for entries in config["hooks"].values()
        for entry in entries
    ]


def test_hooks_json_parses_as_valid_json():
    config = _load()
    assert isinstance(config, dict), "hooks.json must parse to a JSON object"
    assert "hooks" in config, "hooks.json must have a top-level 'hooks' key"


def test_only_the_four_events_are_wired():
    config = _load()
    assert set(config["hooks"]) == {
        "BeforeAgent",
        "BeforeTool",
        "AfterTool",
        "AfterAgent",
    }, (
        "the forge hook surface wires exactly BeforeAgent/BeforeTool/"
        f"AfterTool/AfterAgent; got {sorted(config['hooks'])!r}"
    )


def test_entries_are_flat_with_the_surveyed_fields():
    """Every entry is a flat object carrying at least command + timeout - the
    survey's field list (type/command/timeout), no Claude-style nested hooks
    arrays (RISK-6)."""
    config = _load()
    for event, entries in config["hooks"].items():
        assert isinstance(entries, list) and entries, f"{event}: expected a list"
        for entry in entries:
            assert isinstance(entry, dict), f"{event}: entries must be flat objects"
            assert "hooks" not in entry, (
                f"{event}: gemini entries are flat, never Claude-style nested "
                f"groups; got {entry!r}"
            )
            assert entry.get("type") == "command", (
                f"{event}: every entry declares type:'command'; got {entry!r}"
            )
            assert isinstance(entry.get("command"), str) and entry["command"], (
                f"{event}: every entry needs a command; got {entry!r}"
            )
            assert isinstance(entry.get("timeout"), (int, float)), (
                f"{event}: every entry needs a numeric timeout; got {entry!r}"
            )


def test_before_agent_runs_session_start_sh_unmatched():
    """BeforeAgent carries no tool matcher - it is a turn-lifecycle event that
    fires before every turn, so injection lands on the first turn too."""
    config = _load()
    entries = _entries(config, "BeforeAgent")
    assert len(entries) == 1, f"expected one BeforeAgent entry; got {entries!r}"
    entry = entries[0]
    assert entry["command"].endswith("session-start.sh"), f"got {entry!r}"
    assert entry.get("matcher") in (None, ".*"), (
        "BeforeAgent must fire on every turn (no tool matcher, or '.*'); "
        f"got {entry.get('matcher')!r}"
    )


def test_before_tool_matcher_covers_the_shell_tool_candidates():
    """RISK-2: only run_shell_command is documented, so the matcher regex must
    cover every plausible spelling - and must not swallow edit/read tools."""
    config = _load()
    entries = _entries(config, "BeforeTool")
    assert len(entries) == 1, f"expected one BeforeTool entry; got {entries!r}"
    entry = entries[0]
    assert entry["command"].endswith("block-git-writes.sh"), f"got {entry!r}"
    matcher = re.compile(entry["matcher"])
    for name in ("run_shell_command", "shell", "local_shell", "bash", "Bash", "exec_command"):
        assert matcher.search(name), (
            f"BeforeTool matcher must cover shell-tool candidate {name!r}; "
            f"matcher={entry['matcher']!r}"
        )
    for name in ("write_file", "replace", "edit", "write", "apply_patch", "read_file"):
        assert not matcher.fullmatch(name), (
            f"BeforeTool matcher must not swallow non-shell tool {name!r}; "
            f"matcher={entry['matcher']!r}"
        )


def test_after_tool_matcher_covers_the_edit_tool_candidates():
    """RISK-4: gemini's edit-tool names are documented only for write_file /
    replace, so the matcher regex must cover those plus every plausible
    cross-harness spelling including apply_patch."""
    config = _load()
    entries = _entries(config, "AfterTool")
    assert len(entries) == 1, f"expected one AfterTool entry; got {entries!r}"
    entry = entries[0]
    assert "mark-code-change.py" in entry["command"], f"got {entry!r}"
    matcher = re.compile(entry["matcher"])
    for name in (
        "write_file",
        "replace",
        "apply_patch",
        "edit",
        "write",
        "str_replace",
        "create_file",
        "Edit",
        "Write",
    ):
        assert matcher.search(name), (
            f"AfterTool matcher must cover edit-tool candidate {name!r}; "
            f"matcher={entry['matcher']!r}"
        )
    assert "async" not in entry, (
        "mark-code-change.py must stay synchronous so the marker exists before "
        f"the AfterAgent hooks can ever observe it; entry={entry!r}"
    )


def test_after_agent_registers_the_three_gates_in_order():
    config = _load()
    entries = _entries(config, "AfterAgent")
    names = [e["command"].rsplit("/", 1)[-1] for e in entries]
    assert names == [
        "verify-tests.py",
        "verify-build.py",
        "review-owed.py",
    ], f"AfterAgent must run the three gates in order; got {names!r}"
    timeouts = {n: e.get("timeout") for n, e in zip(names, entries)}
    assert timeouts["verify-tests.py"] == 130000, f"got {timeouts!r}"
    assert timeouts["verify-build.py"] == 190000, f"got {timeouts!r}"
    assert isinstance(timeouts["review-owed.py"], (int, float)), f"got {timeouts!r}"


def test_every_wired_script_exists_and_is_executable():
    """RISK-7: commands are repo-relative paths; every referenced script must
    exist under adapters/gemini/hooks/ and carry the executable bit."""
    config = _load()
    for command in _all_commands(config):
        script = command.replace("python3 ", "").replace(
            "adapters/gemini/hooks/", ""
        )
        path = HOOKS_DIR / script
        assert path.is_file(), (
            f"hooks.json references {script!r} but "
            f"adapters/gemini/hooks/{script} does not exist"
        )
        assert os.access(path, os.X_OK), (
            f"adapters/gemini/hooks/{script} must be executable"
        )


def test_no_dead_hook_is_referenced():
    """Regression guard: none of the culled hooks may creep into this port -
    six behaviors is the ceiling (contract section 9)."""
    dead = (
        "route.py",
        "gen-catalog.py",
        "check_catalog.py",
        "audit.py",
        "auto-format.sh",
        "notify.sh",
        "user-context-injector.sh",
        "user-prompt-submit.sh",
        "inject-workflow.sh",
        "ensure-gitignore.sh",
        "workflow-anchor.sh",
    )
    text = HOOKS_JSON.read_text()
    for name in dead:
        assert name not in text, f"dead hook {name!r} referenced in hooks.json"
