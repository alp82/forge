"""Tests for hooks/session-start.sh - the minimal SessionStart injection.

Contract: emit a hookSpecificOutput/additionalContext JSON object (plain text
without jq) carrying exactly the minimal forge context - the entry rule
("code-modifying requests enter via /forge"), the flow-skill pointer, and,
only when the installed skills are wired in a stale shape, the "re-run
/setup-forge" nag. A symlink into the stable root is current and stays silent;
a symlink that dangles or points into the versioned plugin cache nags (it will
break on the next update); a COPY nags when its .forge-version stamp differs
from the plugin's; an absent one means setup was never run and stays silent.

Driven with HOME pointed at a temp dir so the real ~/.claude/skills never
leaks into assertions.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SESSION_START_SH = (
    REPO_ROOT / "adapters" / "claude-code" / "hooks" / "session-start.sh"
)


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
        assert "host-vendor: anthropic" in ctx, (
            f"host-vendor line missing - the worker forwarder reads it to "
            f"exclude same-vendor second opinions: {ctx!r}"
        )
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


def test_dangling_symlink_triggers_the_nag():
    home = tempfile.mkdtemp()
    try:
        skills = Path(home) / ".claude" / "skills"
        skills.mkdir(parents=True)
        (skills / "forge").symlink_to(
            Path(home) / "gone" / "forge", target_is_directory=True
        )
        ctx = _context(_run_hook(home))
        assert "re-run /setup-forge" in ctx, (
            f"a dangling skill link must nag: {ctx!r}"
        )
        assert "dangling" in ctx, f"the nag must name the dangling shape: {ctx!r}"
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_cache_pointing_symlink_triggers_the_nag():
    home = tempfile.mkdtemp()
    try:
        skills = Path(home) / ".claude" / "skills"
        skills.mkdir(parents=True)
        # A resolving link whose target sits under the versioned plugin cache -
        # healthy today, dangles on the next update, so it nags now.
        cached = (
            Path(home) / ".claude" / "plugins" / "cache" / "mkt" / "forge"
            / "1.0.0" / "skills" / "forge"
        )
        cached.mkdir(parents=True)
        (skills / "forge").symlink_to(cached, target_is_directory=True)
        ctx = _context(_run_hook(home))
        assert "re-run /setup-forge" in ctx, (
            f"a cache-pointing skill link must nag: {ctx!r}"
        )
        assert "cache" in ctx, f"the nag must name the cache shape: {ctx!r}"
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_stale_adapter_skill_copy_triggers_the_nag():
    """The sync-nag loop scans both root skills/*/ and the adapter path
    adapters/claude-code/skills/*/ (session-start.sh line 35) - setup-forge
    only exists under the adapter path, so this is the only case that
    exercises that second glob term. Without it, a typo'd or later-broken
    adapter glob would pass the rest of the suite while a stale installed
    setup-forge copy silently stopped nagging."""
    home = tempfile.mkdtemp()
    try:
        copy_dir = Path(home) / ".claude" / "skills" / "setup-forge"
        copy_dir.mkdir(parents=True)
        (copy_dir / ".forge-version").write_text("0.0.1")
        ctx = _context(_run_hook(home))
        assert "re-run /setup-forge" in ctx, (
            f"a stale setup-forge copy, discovered only via the adapter-path "
            f"glob, must nag: {ctx!r}"
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
