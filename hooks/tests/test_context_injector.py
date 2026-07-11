"""Tests for hooks/user-context-injector.sh, written first (TDD).

First dedicated test surface for the injector. The psychology layer is
deleted as a runtime mechanism: the injector emits DOCTRINE and USER_CONTEXT
blocks only. Covers the Anchor-restate directive removal, a roster-wide
spot-check that no agent receives a PSYCHOLOGY block, source- and
directory-shape pins for the deleted layer, the two folded-anchor pins
(skeptic in plan-challenger, teacher in discuss), and a regression pin for
the already-implemented per-agent doctrine slicing (DOCTRINE_MAP). The
version-bump gate lives elsewhere (test_release_version.py).

Runs under pytest. Drives the real hook via subprocess, matching the
project's "probe hooks via pytest, never guard-tripping inline shell" rule.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INJECTOR = REPO_ROOT / "hooks" / "user-context-injector.sh"


def _run_injector(subagent_type, cwd):
    """Drive user-context-injector.sh the way Claude Code does: an Agent
    PreToolUse payload on stdin. Returns the additionalContext string (empty
    on silent exit). `cwd` is a plain string path."""
    payload = json.dumps(
        {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": subagent_type},
            "cwd": cwd,
        }
    )
    proc = subprocess.run(
        ["bash", str(INJECTOR)],
        input=payload,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "CLAUDE_PLUGIN_ROOT": str(REPO_ROOT),
        },
    )
    assert proc.returncode == 0, f"injector must exit 0, stderr={proc.stderr!r}"
    if not proc.stdout.strip():
        return ""
    out = json.loads(proc.stdout)
    return out.get("hookSpecificOutput", {}).get("additionalContext", "") or out.get(
        "additionalContext", ""
    )


# ---------------------------------------------------------------------------
# Group A - Anchor-restate directive is gone
# ---------------------------------------------------------------------------


def test_anchor_restate_directive_gone(tmp_path):
    """The generic 'restate your Anchor' directive is deleted from the
    injector source and never appears in any rendered payload."""
    source = INJECTOR.read_text(encoding="utf-8")
    assert (
        "restate your Anchor" not in source
    ), "the Anchor-restate directive must be deleted from the injector script"

    cwd = str(tmp_path)
    plan_challenger_ctx = _run_injector("plan-challenger", cwd)
    assert "restate your Anchor" not in plan_challenger_ctx

    discuss_ctx = _run_injector("discuss", cwd)
    assert "restate your Anchor" not in discuss_ctx


# ---------------------------------------------------------------------------
# Group B - No agent receives a PSYCHOLOGY block (roster-wide spot-check)
# ---------------------------------------------------------------------------

# The two formerly-persona'd conversational stages, three formerly-mapped
# strict-output stages, a doctrine-only stage, plus reuse-scanner, which
# renders a near-empty payload under tmp_path, so that param is a cheap extra
# rather than real shape coverage; the teeth against a psychology-block
# regression are Group C pins (a)/(b).
NO_PSYCHOLOGY_SPOT_CHECK = [
    "plan-challenger",
    "discuss",
    "code-planner",
    "fixer",
    "security-reviewer",
    "reuse-scanner",
    "test-gap",
]


@pytest.mark.parametrize("agent", NO_PSYCHOLOGY_SPOT_CHECK)
def test_no_agent_gets_psychology_block(agent, tmp_path):
    """No agent payload contains a PSYCHOLOGY block; the layer is deleted."""
    ctx = _run_injector(agent, str(tmp_path))
    assert "## PSYCHOLOGY" not in ctx, f"{agent} must not receive a PSYCHOLOGY block"


# ---------------------------------------------------------------------------
# Group C - psychology layer deleted; folded anchors present in-file
# ---------------------------------------------------------------------------


def test_psychology_layer_gone_from_source():
    """The injector source contains neither 'psycholog' nor 'persona'
    case-insensitively - covers resolve_persona, psychologyOverrides, and
    every PSYCHOLOGY header mention."""
    source = INJECTOR.read_text(encoding="utf-8").lower()
    assert "psycholog" not in source
    assert "persona" not in source


def test_psychology_directory_deleted():
    """psychology/ (agent-map.json, skeptic.md, teacher.md) is deleted along
    with the directory itself."""
    assert not (REPO_ROOT / "psychology").exists()


def test_plan_challenger_carries_skeptic_anchor():
    """agents/plan-challenger.md carries the skeptic leitwort anchor
    verbatim, folded in-file after the psychology layer's removal."""
    source = (REPO_ROOT / "agents" / "plan-challenger.md").read_text(encoding="utf-8")
    assert "Probe assumptions. Distrust green tests." in source


def test_discuss_carries_teacher_anchor():
    """agents/discuss.md carries the teacher leitwort anchor verbatim,
    folded in-file after the psychology layer's removal."""
    source = (REPO_ROOT / "agents" / "discuss.md").read_text(encoding="utf-8")
    assert "Write the why next to the what. Leave no magic." in source


# ---------------------------------------------------------------------------
# Group D - Doctrine injection sliced per agent type (pins already-implemented
# behavior; expected green immediately)
# ---------------------------------------------------------------------------


def test_doctrine_sliced_per_agent(tmp_path):
    """test-gap's payload carries a DOCTRINE slice from doctrine/communication.md
    and excludes doctrine/code-doctrine.md. reuse-scanner (absent from
    DOCTRINE_MAP) gets no DOCTRINE block at all."""
    test_gap_ctx = _run_injector("test-gap", str(tmp_path))
    assert "## DOCTRINE" in test_gap_ctx
    assert "Name the unknowns by their gap" in test_gap_ctx
    assert "Simplicity over cleverness" not in test_gap_ctx

    reuse_scanner_ctx = _run_injector("reuse-scanner", str(tmp_path))
    assert "## DOCTRINE" not in reuse_scanner_ctx


# ---------------------------------------------------------------------------
# Group E - agent types absent from the case statement fall through to the
# terminal silent exit (empty output, exit 0)
# ---------------------------------------------------------------------------

DEAD_ARM_AGENT_TYPES = [
    "health-checker",
    "prototype-identifier",
    "researcher",
    "code-prototyper",
    "data-prototyper",
    "performance-prototyper",
    "explainer-prototyper",
]


@pytest.mark.parametrize("agent", DEAD_ARM_AGENT_TYPES)
def test_agent_types_without_a_case_arm_get_silent_exit(agent, tmp_path):
    """health-checker, prototype-identifier, researcher, and the
    *-prototyper family (other than design-prototyper/ux-prototyper, which
    keep their own case arm) have no case arm and fall through to the
    terminal `*` arm: no output, exit 0."""
    ctx = _run_injector(agent, str(tmp_path))
    assert ctx == "", f"{agent} must produce no additionalContext, got {ctx!r}"
