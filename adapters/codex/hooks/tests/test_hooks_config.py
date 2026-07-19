"""Structural checks on adapters/codex/hooks/hooks.json for the forge hook surface.

These are static content assertions against the shipped nested-schema template,
not subprocess runs. The codex hook surface is exactly six hooks: session-start.sh
(SessionStart, no matcher - fires on init or resume), block-git-writes.sh
(PreToolUse over the shell-tool matcher), mark-code-change.py (PostToolUse over
the edit-tool matcher, synchronous), and the three Stop gates (verify-tests.py,
verify-build.py, review-owed.py). Six is the ceiling, not a floor (contract
section 9).

Schema note: verified live against Codex CLI 0.143.0, `$CODEX_HOME/hooks.json`
requires the Claude-shaped NESTED schema - each event maps to a list of
MatcherGroups `{ matcher?, hooks: [ { type, command, timeout, statusMessage? } ] }`;
the top level wraps the event map under a `hooks` key. hooks.json here is the
TEMPLATE (commands name scripts by basename); install-forge-hooks.py resolves those
to absolute paths when it merges them into codex's own hooks file. The installer's
own resolution/merge/ownership behavior is covered in test_install_forge_hooks.py.
"""

import json
import os
import re
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
HOOKS_JSON = HOOKS_DIR / "hooks.json"


def _load():
    return json.loads(HOOKS_JSON.read_text())


def _groups(config, event):
    """The MatcherGroup list wired for an event."""
    return config["hooks"][event]


def _inner(config, event):
    """Every inner hook object across all of an event's MatcherGroups."""
    return [h for group in config["hooks"][event] for h in group["hooks"]]


def _all_commands(config):
    return [
        h.get("command", "")
        for groups in config["hooks"].values()
        for group in groups
        for h in group["hooks"]
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


def test_entries_are_nested_matcher_groups_with_the_real_fields():
    """The live-verified codex schema is nested: each event is a list of
    MatcherGroups, each with an inner `hooks` array of `{type:"command",
    command, timeout}` objects. A flat entry (command directly on the group)
    is the pre-#61 shape codex rejects at parse time."""
    config = _load()
    for event, groups in config["hooks"].items():
        assert isinstance(groups, list) and groups, f"{event}: expected a list"
        for group in groups:
            assert isinstance(group, dict), f"{event}: groups must be objects"
            assert "command" not in group, (
                f"{event}: the command belongs on the inner hook, not the "
                f"MatcherGroup - codex requires the nested shape; got {group!r}"
            )
            inner = group.get("hooks")
            assert isinstance(inner, list) and inner, (
                f"{event}: each MatcherGroup needs a non-empty inner 'hooks' "
                f"array; got {group!r}"
            )
            for h in inner:
                assert h.get("type") == "command", (
                    f"{event}: inner hook type must be 'command'; got {h!r}"
                )
                assert isinstance(h.get("command"), str) and h["command"], (
                    f"{event}: every inner hook needs a command; got {h!r}"
                )
                assert isinstance(h.get("timeout"), (int, float)), (
                    f"{event}: every inner hook needs a numeric timeout; got {h!r}"
                )


def test_session_start_runs_session_start_sh_unmatched():
    """SessionStart carries no matcher - codex documents the event as 'init or
    resume' with no matcher vocabulary, so the hook fires on every start."""
    config = _load()
    groups = _groups(config, "SessionStart")
    assert len(groups) == 1, f"expected one SessionStart group; got {groups!r}"
    group = groups[0]
    assert group.get("matcher") in (None, ".*"), (
        "SessionStart must fire on every start (no matcher, or '.*'); "
        f"got {group.get('matcher')!r}"
    )
    inner = group["hooks"]
    assert len(inner) == 1 and inner[0]["command"].endswith("session-start.sh"), (
        f"got {inner!r}"
    )
    assert inner[0]["timeout"] == 5, f"got {inner!r}"


def test_pre_tool_use_matcher_covers_the_shell_tool_candidates():
    """The shell tool reports as `Bash` (verified live); the matcher regex must
    cover it and the other plausible spellings - and must not swallow edit/read
    tools."""
    config = _load()
    groups = _groups(config, "PreToolUse")
    assert len(groups) == 1, f"expected one PreToolUse group; got {groups!r}"
    group = groups[0]
    inner = group["hooks"]
    assert len(inner) == 1 and inner[0]["command"].endswith("block-git-writes.sh"), (
        f"got {inner!r}"
    )
    matcher = re.compile(group["matcher"])
    for name in ("shell", "local_shell", "bash", "Bash", "exec_command", "unified_exec"):
        assert matcher.search(name), (
            f"PreToolUse matcher must cover shell-tool candidate {name!r}; "
            f"matcher={group['matcher']!r}"
        )
    for name in ("edit", "write", "apply_patch", "read"):
        assert not matcher.fullmatch(name), (
            f"PreToolUse matcher must not swallow non-shell tool {name!r}; "
            f"matcher={group['matcher']!r}"
        )


def test_post_tool_use_matcher_covers_the_edit_tool_candidates():
    """The edit-tool names are matched broadly (codex uses Claude-shaped tool
    names - Edit/Write - plus apply_patch); the matcher regex must cover every
    plausible spelling."""
    config = _load()
    groups = _groups(config, "PostToolUse")
    assert len(groups) == 1, f"expected one PostToolUse group; got {groups!r}"
    group = groups[0]
    inner = group["hooks"]
    assert len(inner) == 1 and "mark-code-change.py" in inner[0]["command"], (
        f"got {inner!r}"
    )
    matcher = re.compile(group["matcher"])
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
            f"matcher={group['matcher']!r}"
        )
    assert "async" not in inner[0], (
        "mark-code-change.py must stay synchronous so the marker exists before "
        f"the Stop hooks can ever observe it; hook={inner[0]!r}"
    )


def test_stop_registers_the_three_gates_in_order():
    config = _load()
    inner = _inner(config, "Stop")
    names = [h["command"].rsplit("/", 1)[-1].replace("python3 ", "") for h in inner]
    assert names == [
        "verify-tests.py",
        "verify-build.py",
        "review-owed.py",
    ], f"Stop must run the three gates in order; got {names!r}"
    timeouts = {n: h.get("timeout") for n, h in zip(names, inner)}
    assert timeouts["verify-tests.py"] == 130, f"got {timeouts!r}"
    assert timeouts["verify-build.py"] == 190, f"got {timeouts!r}"
    assert isinstance(timeouts["review-owed.py"], (int, float)), f"got {timeouts!r}"


def test_every_wired_script_exists_and_is_executable():
    """Template commands name scripts by basename (install-forge-hooks.py resolves
    them to absolute paths); every referenced script must exist under
    adapters/codex/hooks/ and carry the executable bit."""
    config = _load()
    for command in _all_commands(config):
        script = command.replace("python3 ", "").strip()
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
