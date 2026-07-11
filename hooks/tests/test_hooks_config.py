"""Structural checks on hooks/hooks.json for the change-marker gate rollout
(Group E, TC-HOOKS-01..03).

These are static content assertions against hooks.json, not subprocess runs.
RED until:
  - hooks.json has a PostToolUse Edit|Write entry invoking mark-code-change.py,
    positioned after the gen-catalog.py entry, with a numeric timeout and no
    "async": true key (the marker-arming write must stay synchronous so the
    marker exists before the Stop hooks can ever observe it).
  - the auto-format.sh entry carries "async": true and keeps "timeout": 30.
"""

import json
from pathlib import Path

HOOKS_JSON = Path(__file__).resolve().parents[1] / "hooks.json"


def _load():
    return json.loads(HOOKS_JSON.read_text())


def _post_tool_use_edit_write_hooks():
    config = _load()
    for group in config["hooks"]["PostToolUse"]:
        if group.get("matcher") == "Edit|Write":
            return group["hooks"]
    raise AssertionError("no PostToolUse Edit|Write matcher group found in hooks.json")


# ---------------------------------------------------------------------------
# TC-HOOKS-01: hooks.json parses as valid JSON
# ---------------------------------------------------------------------------


def test_hooks_json_parses_as_valid_json():
    config = _load()
    assert isinstance(config, dict), "hooks.json must parse to a JSON object"
    assert "hooks" in config, "hooks.json must have a top-level 'hooks' key"


# ---------------------------------------------------------------------------
# TC-HOOKS-02: mark-code-change.py entry after gen-catalog.py, synchronous
# ---------------------------------------------------------------------------


def test_mark_code_change_entry_present_after_gen_catalog_and_synchronous():
    hooks = _post_tool_use_edit_write_hooks()
    commands = [h.get("command", "") for h in hooks]

    gen_catalog_idx = next(
        (i for i, c in enumerate(commands) if "gen-catalog.py" in c), None
    )
    assert (
        gen_catalog_idx is not None
    ), "expected an existing gen-catalog.py entry under PostToolUse Edit|Write"

    mark_change_idx = next(
        (i for i, c in enumerate(commands) if "mark-code-change.py" in c), None
    )
    assert mark_change_idx is not None, (
        "expected a PostToolUse Edit|Write entry invoking mark-code-change.py; "
        f"got commands={commands!r}"
    )
    assert mark_change_idx > gen_catalog_idx, (
        "mark-code-change.py entry must be positioned after the gen-catalog.py "
        f"entry; gen_catalog_idx={gen_catalog_idx}, mark_change_idx={mark_change_idx}"
    )

    entry = hooks[mark_change_idx]
    assert isinstance(
        entry.get("timeout"), (int, float)
    ), f"mark-code-change.py entry must carry a numeric timeout, got {entry.get('timeout')!r}"
    assert "async" not in entry, (
        "mark-code-change.py entry must NOT carry an 'async' key - it must stay "
        f"synchronous so the marker exists before Stop hooks run; entry={entry!r}"
    )


# ---------------------------------------------------------------------------
# TC-HOOKS-03: auto-format entry stays async with timeout 30
# ---------------------------------------------------------------------------


def test_auto_format_entry_is_async_with_timeout_30():
    hooks = _post_tool_use_edit_write_hooks()
    entry = next((h for h in hooks if "auto-format.sh" in h.get("command", "")), None)
    assert (
        entry is not None
    ), "expected an auto-format.sh entry under PostToolUse Edit|Write"
    assert (
        entry.get("async") is True
    ), f'auto-format.sh entry must carry "async": true; got {entry!r}'
    assert (
        entry.get("timeout") == 30
    ), f'auto-format.sh entry must retain "timeout": 30; got {entry!r}'


# ---------------------------------------------------------------------------
# TC-HOOKS-04: SubagentStop group registers both verify scripts
# ---------------------------------------------------------------------------


def test_subagent_stop_group_registers_both_verify_scripts():
    """The SubagentStop group exists with the pinned agent-type matcher and
    registers both gate scripts with the pinned numeric timeouts (130 for
    verify-tests, 190 for verify-build - mirroring the Stop group)."""
    config = _load()
    groups = config["hooks"].get("SubagentStop")
    assert groups, "hooks.json must have a SubagentStop group"
    group = next(
        (g for g in groups if g.get("matcher") == "(.*:)?(code-implementer|fixer)"),
        None,
    )
    assert group is not None, (
        "expected a SubagentStop group with the literal matcher "
        f"'(.*:)?(code-implementer|fixer)'; got {groups!r}"
    )
    hooks = group["hooks"]
    tests_entry = next(
        (h for h in hooks if "verify-tests.py" in h.get("command", "")), None
    )
    build_entry = next(
        (h for h in hooks if "verify-build.py" in h.get("command", "")), None
    )
    assert (
        tests_entry is not None
    ), f"SubagentStop group must register verify-tests.py; got {hooks!r}"
    assert (
        build_entry is not None
    ), f"SubagentStop group must register verify-build.py; got {hooks!r}"
    assert (
        tests_entry.get("timeout") == 130
    ), f"verify-tests.py SubagentStop entry must carry timeout 130; got {tests_entry!r}"
    assert (
        build_entry.get("timeout") == 190
    ), f"verify-build.py SubagentStop entry must carry timeout 190; got {build_entry!r}"


# ---------------------------------------------------------------------------
# TC-HOOKS-05: SessionStart group runs inject-workflow.sh on every matcher
# ---------------------------------------------------------------------------


def test_session_start_group_runs_inject_workflow_on_every_matcher():
    """SessionStart wires inject-workflow.sh on every matcher, plus the
    gitignore guard on startup/resume. recover-run-state.sh stays removed
    (gone with docs/ADR/run-state). startup and resume run inject-workflow.sh
    then ensure-gitignore.sh; clear and compact run only inject-workflow.sh."""
    config = _load()
    groups = config["hooks"].get("SessionStart")
    assert groups, "hooks.json must have a SessionStart group"

    matchers = {g.get("matcher") for g in groups}
    assert matchers == {
        "startup",
        "resume",
        "clear",
        "compact",
    }, f"expected exactly the startup/resume/clear/compact matchers; got {matchers!r}"

    expected = {
        "startup": [
            "${CLAUDE_PLUGIN_ROOT}/hooks/inject-workflow.sh",
            "${CLAUDE_PLUGIN_ROOT}/hooks/ensure-gitignore.sh",
        ],
        "resume": [
            "${CLAUDE_PLUGIN_ROOT}/hooks/inject-workflow.sh",
            "${CLAUDE_PLUGIN_ROOT}/hooks/ensure-gitignore.sh",
        ],
        "clear": ["${CLAUDE_PLUGIN_ROOT}/hooks/inject-workflow.sh"],
        "compact": ["${CLAUDE_PLUGIN_ROOT}/hooks/inject-workflow.sh"],
    }
    for group in groups:
        matcher = group.get("matcher")
        commands = [h.get("command", "") for h in group.get("hooks", [])]
        assert commands == expected[matcher], (
            f"SessionStart matcher {matcher!r} must run exactly "
            f"{expected[matcher]!r}; got commands={commands!r}"
        )
        assert not any("recover-run-state.sh" in c for c in commands), (
            f"SessionStart matcher {matcher!r} must not register "
            f"recover-run-state.sh; got commands={commands!r}"
        )


def test_subagent_stop_group_present_alongside_stop_group():
    """The Stop group still exists with its two verify entries next to the new
    SubagentStop group - a regression guard against a careless top-level key
    replace."""
    config = _load()
    assert "SubagentStop" in config["hooks"], "SubagentStop group must exist"
    stop_groups = config["hooks"].get("Stop")
    assert stop_groups, "the Stop group must still exist alongside SubagentStop"
    stop_commands = [
        h.get("command", "") for g in stop_groups for h in g.get("hooks", [])
    ]
    assert any(
        "verify-tests.py" in c for c in stop_commands
    ), f"Stop group must still register verify-tests.py; got {stop_commands!r}"
    assert any(
        "verify-build.py" in c for c in stop_commands
    ), f"Stop group must still register verify-build.py; got {stop_commands!r}"
