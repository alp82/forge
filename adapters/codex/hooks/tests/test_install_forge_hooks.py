"""Tests for install-forge-hooks.py - the writer that merges forge's enforcement
hooks into codex's own $CODEX_HOME/hooks.json.

The installer is load-bearing: codex does not load plugin-carried hooks
(plugin_hooks is a removed feature), so this script IS the enforcement layer's
install path. What must hold:

  - it resolves the template's basename commands to ABSOLUTE paths (codex
    substitutes no plugin-root variable);
  - it OWNS ONLY forge's entries - a user's or Orca's hooks in the same file
    survive untouched;
  - it is IDEMPOTENT - re-running replaces forge's own groups, never stacking
    duplicates;
  - it refuses to clobber a hooks.json it cannot parse.

Imported by path since the hooks dir is not a package.
"""

import importlib.util
import json
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
INSTALLER = HOOKS_DIR / "install-forge-hooks.py"


def _load_installer():
    spec = importlib.util.spec_from_file_location("install_forge_hooks", INSTALLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ifh = _load_installer()


def _run(codex_home, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    rc = ifh.main()
    assert rc == 0, f"installer exited {rc}"
    return json.loads((codex_home / "hooks.json").read_text())


def test_resolves_commands_to_absolute_paths(tmp_path, monkeypatch):
    config = _run(tmp_path, monkeypatch)
    for groups in config["hooks"].values():
        for group in groups:
            for h in group["hooks"]:
                cmd = h["command"].replace("python3 ", "")
                assert cmd.startswith("/"), f"command not absolute: {h['command']!r}"
                assert str(HOOKS_DIR) in cmd, (
                    f"command must point into the hooks dir; got {h['command']!r}"
                )


def test_all_four_events_written(tmp_path, monkeypatch):
    config = _run(tmp_path, monkeypatch)
    assert set(config["hooks"]) == {
        "SessionStart",
        "PreToolUse",
        "PostToolUse",
        "Stop",
    }


def test_preserves_foreign_hooks_and_description(tmp_path, monkeypatch):
    (tmp_path / "hooks.json").write_text(
        json.dumps(
            {
                "description": "user's own hooks",
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": "/usr/local/bin/my.sh", "timeout": 3}]}
                    ],
                    "PreToolUse": [
                        {"matcher": "^Bash$", "hooks": [{"type": "command", "command": "/opt/orca/guard.sh", "timeout": 5}]}
                    ],
                },
            }
        )
    )
    config = _run(tmp_path, monkeypatch)
    assert config.get("description") == "user's own hooks"
    text = json.dumps(config)
    assert "/usr/local/bin/my.sh" in text, "foreign SessionStart hook was lost"
    assert "/opt/orca/guard.sh" in text, "foreign PreToolUse hook was lost"
    # Foreign group kept AND forge's group appended.
    assert len(config["hooks"]["SessionStart"]) == 2
    assert len(config["hooks"]["PreToolUse"]) == 2


def test_idempotent_no_duplicate_forge_groups(tmp_path, monkeypatch):
    first = _run(tmp_path, monkeypatch)
    second = _run(tmp_path, monkeypatch)
    assert first == second, "a second install changed the file - not idempotent"
    # exactly one forge group per event (no foreign hooks seeded here)
    for event, groups in second["hooks"].items():
        forge = [g for g in groups if ifh._is_forge_group(g)]
        assert len(forge) == 1, f"{event}: expected one forge group, got {len(forge)}"


def test_refuses_to_clobber_unparseable_hooks_json(tmp_path, monkeypatch):
    (tmp_path / "hooks.json").write_text("{ not json ]")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    assert ifh.main() != 0, "installer must fail rather than overwrite invalid JSON"
    assert (tmp_path / "hooks.json").read_text() == "{ not json ]", (
        "installer must leave an unparseable file untouched"
    )


def test_ownership_is_by_script_basename(tmp_path, monkeypatch):
    """A prior forge install under a DIFFERENT plugin path is still recognized as
    forge's own (ownership keys on the script basename, not the absolute path), so
    re-install re-owns it instead of stacking a second copy."""
    (tmp_path / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": "/old/plugin/path/session-start.sh", "timeout": 5}]}
                    ]
                }
            }
        )
    )
    config = _run(tmp_path, monkeypatch)
    ss = config["hooks"]["SessionStart"]
    assert len(ss) == 1, "a stale forge group at an old path should be replaced, not kept"
    assert str(HOOKS_DIR) in ss[0]["hooks"][0]["command"]
