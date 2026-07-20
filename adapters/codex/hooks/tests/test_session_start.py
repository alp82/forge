"""Tests for hooks/session-start.sh - the codex SessionStart injection.

Contract: emit a hookSpecificOutput/additionalContext JSON object (plain text
without jq - RISK-1 fallback) carrying exactly the minimal forge context - the
entry rule ("code-modifying requests enter via the forge skill"), the
flow-skill pointer, and, only when the installed tier agents are stale, the
"re-run $setup-forge" nag. setup-forge writes ~/.codex/agents/forge-<tier>.toml
files stamped `# forge-version: X.Y.Z`; a stamp differing from the plugin
version, a missing stamp, or an incomplete tier set nags. No forge agent file
at all means setup was never run and stays silent.

Driven with HOME pointed at a temp dir so the real ~/.codex never leaks into
assertions. The script self-locates via BASH_SOURCE (no plugin-root env var is
documented for codex - RISK-7).
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SESSION_START_SH = REPO_ROOT / "adapters" / "codex" / "hooks" / "session-start.sh"

TIERS = ("mini", "standard", "large", "ultra")


def _plugin_version():
    return json.loads(
        (REPO_ROOT / ".codex-plugin" / "plugin.json").read_text()
    )["version"]


def _run_hook(home):
    env = dict(os.environ)
    env["HOME"] = str(home)
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


def _write_agents(home, stamp, tiers=TIERS):
    agents = Path(home) / ".codex" / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    for tier in tiers:
        body = f'name = "forge-{tier}"\n'
        if stamp is not None:
            body += f"# forge-version: {stamp}\n"
        (agents / f"forge-{tier}.toml").write_text(body)


def test_emits_entry_rule_and_flow_pointer():
    home = tempfile.mkdtemp()
    try:
        result = _run_hook(home)
        assert result.returncode == 0, f"got {result.returncode}: {result.stderr!r}"
        ctx = _context(result)
        assert "forge" in ctx, f"entry rule missing from context: {ctx!r}"
        assert "skills/forge/SKILL.md" in ctx, f"flow pointer missing: {ctx!r}"
        assert "crossfire" in ctx, f"review-verb pointer missing: {ctx!r}"
        assert "host-vendor: openai" in ctx, (
            f"host-vendor line missing - the worker forwarder reads it to "
            f"exclude same-vendor second opinions: {ctx!r}"
        )
        assert "setup-forge" not in ctx, (
            f"no nag may appear when no tier agent is installed: {ctx!r}"
        )
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_stale_agent_stamp_triggers_the_setup_forge_nag():
    home = tempfile.mkdtemp()
    try:
        _write_agents(home, "0.0.1")
        ctx = _context(_run_hook(home))
        assert "re-run $setup-forge" in ctx, (
            f"agents stamped 0.0.1 against plugin {_plugin_version()} must nag: {ctx!r}"
        )
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_missing_stamp_on_existing_agents_triggers_the_nag():
    home = tempfile.mkdtemp()
    try:
        _write_agents(home, None)
        ctx = _context(_run_hook(home))
        assert "re-run $setup-forge" in ctx, (
            f"agent files with no forge-version stamp must nag: {ctx!r}"
        )
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_incomplete_tier_set_triggers_the_nag():
    home = tempfile.mkdtemp()
    try:
        _write_agents(home, _plugin_version(), tiers=("mini", "standard"))
        ctx = _context(_run_hook(home))
        assert "re-run $setup-forge" in ctx, (
            f"an incomplete tier-agent set must nag: {ctx!r}"
        )
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_current_stamps_stay_silent():
    home = tempfile.mkdtemp()
    try:
        _write_agents(home, _plugin_version())
        ctx = _context(_run_hook(home))
        assert "setup-forge" not in ctx, (
            f"current agent stamps must not nag: {ctx!r}"
        )
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_non_forge_agent_files_stay_silent():
    """A user's own agent files (not forge-<tier>.toml) never trigger the nag."""
    home = tempfile.mkdtemp()
    try:
        agents = Path(home) / ".codex" / "agents"
        agents.mkdir(parents=True)
        (agents / "my-reviewer.toml").write_text('name = "my-reviewer"\n')
        ctx = _context(_run_hook(home))
        assert "setup-forge" not in ctx, (
            f"a user's own agent file must not trigger the forge nag: {ctx!r}"
        )
    finally:
        shutil.rmtree(home, ignore_errors=True)
