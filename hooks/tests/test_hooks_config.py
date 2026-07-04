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
