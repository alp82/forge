"""Structural checks on adapters/codex/hooks/hooks.json for the forge hook surface.

These are static content assertions against hooks.json, not subprocess runs.
The codex hook surface is exactly six hooks: session-start.sh (SessionStart,
no matcher - fires on init or resume), block-git-writes.sh (PreToolUse over
the shell-tool matcher), mark-code-change.py (PostToolUse over the edit-tool
matcher, synchronous), and the three Stop gates (verify-tests.py,
verify-build.py, review-owed.py). Six is the ceiling, not a floor (contract
section 9).

Schema note (RISK-6): the codex survey gives the entry fields (matcher,
command, timeout, statusMessage) but not the file's top-level shape; this
suite pins the flat-entries-under-event-keys assumption the adapter ships.
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
        "SessionStart",
        "PreToolUse",
        "PostToolUse",
        "Stop",
    }, (
        "the forge hook surface wires exactly SessionStart/PreToolUse/"
        f"PostToolUse/Stop; got {sorted(config['hooks'])!r}"
    )


def test_entries_are_flat_with_the_surveyed_fields():
    """Every entry is a flat object carrying at least command + timeout - the
    survey's field list, no Claude-style nested hooks arrays (RISK-6)."""
    config = _load()
    for event, entries in config["hooks"].items():
        assert isinstance(entries, list) and entries, f"{event}: expected a list"
        for entry in entries:
            assert isinstance(entry, dict), f"{event}: entries must be flat objects"
            assert "hooks" not in entry, (
                f"{event}: codex entries are flat, never Claude-style nested "
                f"groups; got {entry!r}"
            )
            assert isinstance(entry.get("command"), str) and entry["command"], (
                f"{event}: every entry needs a command; got {entry!r}"
            )
            assert isinstance(entry.get("timeout"), (int, float)), (
                f"{event}: every entry needs a numeric timeout; got {entry!r}"
            )


def test_session_start_runs_session_start_sh_unmatched():
    """SessionStart carries no matcher - codex documents the event as 'init or
    resume' with no matcher vocabulary, so the hook fires on every start."""
    config = _load()
    entries = _entries(config, "SessionStart")
    assert len(entries) == 1, f"expected one SessionStart entry; got {entries!r}"
    entry = entries[0]
    assert entry["command"].endswith("session-start.sh"), f"got {entry!r}"
    assert entry.get("matcher") in (None, ".*"), (
        "SessionStart must fire on every start (no matcher, or '.*'); "
        f"got {entry.get('matcher')!r}"
    )
    assert entry["timeout"] == 5, f"got {entry!r}"


def test_pre_tool_use_matcher_covers_the_shell_tool_candidates():
    """RISK-2: the shell tool name is undocumented, so the matcher regex must
    cover every plausible spelling - and must not swallow edit/read tools."""
    config = _load()
    entries = _entries(config, "PreToolUse")
    assert len(entries) == 1, f"expected one PreToolUse entry; got {entries!r}"
    entry = entries[0]
    assert entry["command"].endswith("block-git-writes.sh"), f"got {entry!r}"
    matcher = re.compile(entry["matcher"])
    for name in ("shell", "local_shell", "bash", "Bash", "exec_command"):
        assert matcher.search(name), (
            f"PreToolUse matcher must cover shell-tool candidate {name!r}; "
            f"matcher={entry['matcher']!r}"
        )
    for name in ("edit", "write", "apply_patch", "read"):
        assert not matcher.fullmatch(name), (
            f"PreToolUse matcher must not swallow non-shell tool {name!r}; "
            f"matcher={entry['matcher']!r}"
        )


def test_post_tool_use_matcher_covers_the_edit_tool_candidates():
    """RISK-4: the edit-tool names are undocumented, so the matcher regex must
    cover every plausible spelling including apply_patch."""
    config = _load()
    entries = _entries(config, "PostToolUse")
    assert len(entries) == 1, f"expected one PostToolUse entry; got {entries!r}"
    entry = entries[0]
    assert "mark-code-change.py" in entry["command"], f"got {entry!r}"
    matcher = re.compile(entry["matcher"])
    for name in (
        "apply_patch",
        "edit",
        "write",
        "str_replace",
        "create_file",
        "Edit",
        "Write",
    ):
        assert matcher.search(name), (
            f"PostToolUse matcher must cover edit-tool candidate {name!r}; "
            f"matcher={entry['matcher']!r}"
        )
    assert "async" not in entry, (
        "mark-code-change.py must stay synchronous so the marker exists before "
        f"the Stop hooks can ever observe it; entry={entry!r}"
    )


def test_stop_registers_the_three_gates_in_order():
    config = _load()
    entries = _entries(config, "Stop")
    names = [e["command"].rsplit("/", 1)[-1] for e in entries]
    assert names == [
        "verify-tests.py",
        "verify-build.py",
        "review-owed.py",
    ], f"Stop must run the three gates in order; got {names!r}"
    timeouts = {n: e.get("timeout") for n, e in zip(names, entries)}
    assert timeouts["verify-tests.py"] == 130, f"got {timeouts!r}"
    assert timeouts["verify-build.py"] == 190, f"got {timeouts!r}"
    assert isinstance(timeouts["review-owed.py"], (int, float)), f"got {timeouts!r}"


def test_every_wired_script_exists_and_is_executable():
    """RISK-7: commands are plugin-root-relative paths; every referenced script
    must exist under adapters/codex/hooks/ and carry the executable bit."""
    config = _load()
    for command in _all_commands(config):
        script = command.replace("python3 ", "").replace(
            "adapters/codex/hooks/", ""
        )
        path = HOOKS_DIR / script
        assert path.is_file(), (
            f"hooks.json references {script!r} but "
            f"adapters/codex/hooks/{script} does not exist"
        )
        assert os.access(path, os.X_OK), (
            f"adapters/codex/hooks/{script} must be executable"
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
