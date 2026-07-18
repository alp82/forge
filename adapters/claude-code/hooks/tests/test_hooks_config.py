"""Structural checks on adapters/claude-code/hooks/hooks.json for the forge hook surface.

These are static content assertions against hooks.json, not subprocess runs.
The 2.0 hook surface is exactly six hooks: session-start.sh (SessionStart, all
four matchers), block-git-writes.sh (PreToolUse Bash), mark-code-change.py
(PostToolUse Edit|Write, synchronous), and the three Stop gates
(verify-tests.py, verify-build.py, review-owed.py). Everything else - the
deterministic router, catalog sync, context injection, auto-format, and the
notification hooks - is gone or evicted to personal settings.
"""

import json
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
HOOKS_JSON = HOOKS_DIR / "hooks.json"


def _load():
    return json.loads(HOOKS_JSON.read_text())


def _all_commands(config):
    return [
        h.get("command", "")
        for groups in config["hooks"].values()
        for g in groups
        for h in g.get("hooks", [])
    ]


def test_hooks_json_parses_as_valid_json():
    config = _load()
    assert isinstance(config, dict), "hooks.json must parse to a JSON object"
    assert "hooks" in config, "hooks.json must have a top-level 'hooks' key"


def test_only_the_four_surviving_events_are_wired():
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


def test_session_start_runs_session_start_sh_on_every_matcher():
    config = _load()
    groups = config["hooks"]["SessionStart"]
    matchers = {g.get("matcher") for g in groups}
    assert matchers == {
        "startup",
        "resume",
        "clear",
        "compact",
    }, f"expected exactly the startup/resume/clear/compact matchers; got {matchers!r}"
    for group in groups:
        commands = [h.get("command", "") for h in group.get("hooks", [])]
        assert commands == [
            "${CLAUDE_PLUGIN_ROOT}/adapters/claude-code/hooks/session-start.sh"
        ], (
            f"SessionStart matcher {group.get('matcher')!r} must run exactly "
            f"session-start.sh; got {commands!r}"
        )


def test_pre_tool_use_wires_block_git_writes_on_bash():
    config = _load()
    groups = config["hooks"]["PreToolUse"]
    assert len(groups) == 1 and groups[0].get("matcher") == "Bash", (
        f"PreToolUse must carry exactly one Bash matcher group; got {groups!r}"
    )
    commands = [h.get("command", "") for h in groups[0]["hooks"]]
    assert commands == [
        "${CLAUDE_PLUGIN_ROOT}/adapters/claude-code/hooks/block-git-writes.sh"
    ], (
        f"PreToolUse Bash must run exactly block-git-writes.sh; got {commands!r}"
    )


def test_mark_code_change_is_the_only_post_tool_use_hook_and_synchronous():
    config = _load()
    groups = config["hooks"]["PostToolUse"]
    assert len(groups) == 1 and groups[0].get("matcher") == "Edit|Write", (
        f"PostToolUse must carry exactly one Edit|Write matcher group; got {groups!r}"
    )
    hooks = groups[0]["hooks"]
    assert len(hooks) == 1 and "mark-code-change.py" in hooks[0].get("command", ""), (
        f"PostToolUse Edit|Write must run exactly mark-code-change.py; got {hooks!r}"
    )
    entry = hooks[0]
    assert isinstance(entry.get("timeout"), (int, float)), (
        f"mark-code-change.py entry must carry a numeric timeout; got {entry!r}"
    )
    assert "async" not in entry, (
        "mark-code-change.py must stay synchronous so the marker exists before "
        f"the Stop hooks can ever observe it; entry={entry!r}"
    )


def test_stop_group_registers_the_three_gates_in_order():
    config = _load()
    groups = config["hooks"]["Stop"]
    assert len(groups) == 1, f"expected exactly one Stop group; got {groups!r}"
    hooks = groups[0]["hooks"]
    names = [h.get("command", "").rsplit("/", 1)[-1] for h in hooks]
    assert names == [
        "verify-tests.py",
        "verify-build.py",
        "review-owed.py",
    ], f"Stop must run the three gates in order; got {names!r}"
    timeouts = {n: h.get("timeout") for n, h in zip(names, hooks)}
    assert timeouts["verify-tests.py"] == 130, f"got {timeouts!r}"
    assert timeouts["verify-build.py"] == 190, f"got {timeouts!r}"
    assert isinstance(timeouts["review-owed.py"], (int, float)), f"got {timeouts!r}"


def test_every_wired_script_exists_on_disk():
    config = _load()
    for command in _all_commands(config):
        script = command.replace("python3 ", "").replace(
            "${CLAUDE_PLUGIN_ROOT}/adapters/claude-code/hooks/", ""
        )
        assert (HOOKS_DIR / script).is_file(), (
            f"hooks.json references {script!r} but "
            f"adapters/claude-code/hooks/{script} does not exist"
        )


def test_no_dead_hook_is_referenced():
    """Regression guard: none of the removed hooks may creep back into the
    wiring - the router, catalog sync, injectors, auto-format (evicted to
    personal settings), and the notification hooks (same eviction)."""
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
