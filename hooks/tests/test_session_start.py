"""Tests for hooks/session-start.sh - the minimal SessionStart injection.

Contract: emit a hookSpecificOutput/additionalContext JSON object (plain text
without jq) carrying exactly the minimal forge context - the entry rule
("code-modifying requests enter via /forge"), the flow-skill pointer, and,
only when an installed skill COPY is stamped with a version that differs from
the plugin's, the "re-run /setup-forge" nag. A symlinked skill is always
current; an absent one means setup was never run - both stay silent.

Driven with HOME pointed at a temp dir so the real ~/.claude/skills never
leaks into assertions.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SESSION_START_SH = REPO_ROOT / "hooks" / "session-start.sh"


def _plugin_version():
    return json.loads(
        (REPO_ROOT / ".claude-plugin" / "plugin.json").read_text()
    )["version"]


def _run_hook(home):
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["CLAUDE_PLUGIN_ROOT"] = str(REPO_ROOT)
    return subprocess.run(
        ["bash", str(SESSION_START_SH)],
        capture_output=True,
        text=True,
        env=env,
    )


def _context(result):
    """The injected context, whichever emission path (jq JSON or plain) ran."""
    out = result.stdout.strip()
    try:
        return json.loads(out)["hookSpecificOutput"]["additionalContext"]
    except (json.JSONDecodeError, ValueError, KeyError, TypeError):
        return out


def test_emits_entry_rule_and_flow_pointer():
    home = tempfile.mkdtemp()
    try:
        result = _run_hook(home)
        assert result.returncode == 0, f"got {result.returncode}: {result.stderr!r}"
        ctx = _context(result)
        assert "/forge" in ctx, f"entry rule missing from context: {ctx!r}"
        assert "skills/forge/SKILL.md" in ctx, f"flow pointer missing: {ctx!r}"
        assert "/crossfire" in ctx, f"review-verb pointer missing: {ctx!r}"
        assert "setup-forge" not in ctx, (
            f"no nag may appear when no skill copy is installed: {ctx!r}"
        )
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_stale_skill_copy_triggers_the_setup_forge_nag():
    home = tempfile.mkdtemp()
    try:
        copy_dir = Path(home) / ".claude" / "skills" / "forge"
        copy_dir.mkdir(parents=True)
        (copy_dir / "SKILL.md").write_text("---\nname: forge\n---\n")
        (copy_dir / ".forge-version").write_text("0.0.1")
        ctx = _context(_run_hook(home))
        assert "re-run /setup-forge" in ctx, (
            f"a copy stamped 0.0.1 against plugin {_plugin_version()} must nag: {ctx!r}"
        )
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_current_stamp_and_symlink_stay_silent():
    home = tempfile.mkdtemp()
    try:
        skills = Path(home) / ".claude" / "skills"
        copy_dir = skills / "forge"
        copy_dir.mkdir(parents=True)
        (copy_dir / ".forge-version").write_text(_plugin_version())
        (skills / "crossfire").symlink_to(
            REPO_ROOT / "skills" / "crossfire", target_is_directory=True
        )
        ctx = _context(_run_hook(home))
        assert "setup-forge" not in ctx, (
            f"a current copy and a symlink must not nag: {ctx!r}"
        )
    finally:
        shutil.rmtree(home, ignore_errors=True)
