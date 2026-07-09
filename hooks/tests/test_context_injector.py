"""Tests for hooks/user-context-injector.sh, written first (TDD).

First dedicated test surface for the injector. The psychology layer is
deleted as a runtime mechanism: the injector emits DOCTRINE, USER_CONTEXT,
and PROJECT_CONTEXT blocks only. Covers the Anchor-restate directive
removal, a roster-wide spot-check that no agent receives a PSYCHOLOGY
block, source- and directory-shape pins for the deleted layer, the two
folded-anchor pins (skeptic in plan-challenger, teacher in discuss), and a
regression pin for the already-implemented per-agent doctrine slicing
(DOCTRINE_MAP). The ADR one-pass rewrite is covered by Group E below; only
the version-bump gate lives elsewhere (test_release_version.py).

Runs under pytest. Drives the real hook via subprocess, matching the
project's "probe hooks via pytest, never guard-tripping inline shell" rule.
"""

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INJECTOR = REPO_ROOT / "hooks" / "user-context-injector.sh"


def _run_injector(subagent_type, cwd):
    """Drive user-context-injector.sh the way Claude Code does: an Agent
    PreToolUse payload on stdin. Returns the additionalContext string (empty
    on silent exit). `cwd` is a plain string path so a later milestone can
    reuse this helper for ADR fixture trees under tmp_path."""
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
# strict-output stages, a doctrine-only stage, plus capture-agent and
# reuse-scanner. The last two render near-empty payloads under tmp_path, so
# those params are cheap extras rather than real shape coverage; the teeth
# against a psychology-block regression are Group C pins (a)/(b).
NO_PSYCHOLOGY_SPOT_CHECK = [
    "plan-challenger",
    "discuss",
    "code-planner",
    "fixer",
    "security-reviewer",
    "capture-agent",
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
# Group E - ADR one-pass rewrite (milestone 2): no per-ADR subprocess fan-out
# ---------------------------------------------------------------------------
#
# summarize_adrs() has been rewritten to a single-pass implementation,
# replacing the old per-ADR awk+cut loop. test_no_per_adr_subprocess_fanout
# pins the one-pass source shape and test_empty_adr_file_yields_no_bullet
# pins the deliberate empty-file behavior delta. test_adr_summary_multi_file_behavior
# and the directory failure-mode tests pin existing behavior that survived
# the rewrite unchanged.


def _write_adr(adr_dir, filename, content):
    """Write one ADR fixture file under adr_dir, creating parents as needed."""
    adr_dir.mkdir(parents=True, exist_ok=True)
    (adr_dir / filename).write_text(content, encoding="utf-8")


def test_no_per_adr_subprocess_fanout():
    """The summarize_adrs() function body carries exactly one awk invocation
    and zero `cut -f` invocations - a single pass over each ADR file, not a
    per-file awk-then-cut pipeline. Sliced to the function body so a comment
    mentioning "awk" elsewhere in the file cannot skew the count; invocation
    is matched as a call (awk/cut followed by its argument), not a naked
    substring occurrence."""
    source = INJECTOR.read_text(encoding="utf-8")
    match = re.search(
        r"^summarize_adrs\(\) \{\n(.*?)^\}\n", source, re.DOTALL | re.MULTILINE
    )
    assert match, "summarize_adrs() function body not found in injector source"
    body = match.group(1)

    awk_invocations = re.findall(r"\bawk\s+['\"]", body)
    cut_invocations = re.findall(r"\bcut\s+-f", body)

    assert (
        len(awk_invocations) == 1
    ), f"expected exactly one awk invocation in summarize_adrs(), found {len(awk_invocations)}"
    assert (
        len(cut_invocations) == 0
    ), f"expected zero cut -f invocations in summarize_adrs(), found {len(cut_invocations)}"


def test_adr_summary_multi_file_behavior(tmp_path):
    """A mixed fixture set of ADRs exercises: frontmatter + Summary-section
    extraction, fallback to the first paragraph when frontmatter/Summary are
    absent, exclusion of deprecated status, exclusion of superseded status,
    exclusion of TODO summaries, filename-based skip of 0000-template.md, and
    the hyphen-less stem's num guard (ADR-9999 from 9999.md). Surviving
    bullets appear in source-file order with the exact `- ADR-<num>: <title>
    [<status>] - <summary> (docs/adr/<file>)` format."""
    docs_dir = tmp_path / "docs"
    adr_dir = docs_dir / "adr"

    _write_adr(
        adr_dir,
        "0001-use-thing.md",
        "---\n"
        "status: accepted\n"
        "---\n"
        "# Use Thing\n"
        "\n"
        "## Summary\n"
        "\n"
        "This is the summary text for use thing.\n",
    )
    _write_adr(
        adr_dir,
        "0002-no-frontmatter.md",
        "# No Frontmatter Title\n"
        "\n"
        "This is the first paragraph used as fallback summary.\n",
    )
    _write_adr(
        adr_dir,
        "0003-deprecated-thing.md",
        "---\n"
        "status: deprecated\n"
        "---\n"
        "# Deprecated Thing\n"
        "\n"
        "## Summary\n"
        "\n"
        "This ADR is deprecated and excluded.\n",
    )
    _write_adr(
        adr_dir,
        "0006-superseded-thing.md",
        "---\n"
        "status: superseded\n"
        "---\n"
        "# Superseded Thing\n"
        "\n"
        "## Summary\n"
        "\n"
        "This ADR is superseded and excluded.\n",
    )
    _write_adr(
        adr_dir,
        "0004-todo-thing.md",
        "---\n"
        "status: accepted\n"
        "---\n"
        "# Todo Thing\n"
        "\n"
        "## Summary\n"
        "\n"
        "_TODO:_ still need to fill this in.\n",
    )
    _write_adr(
        adr_dir,
        "0000-template.md",
        "---\n"
        "status: accepted\n"
        "---\n"
        "# Template\n"
        "\n"
        "## Summary\n"
        "\n"
        "Template boilerplate text.\n",
    )
    _write_adr(
        adr_dir,
        "9999.md",
        "---\n"
        "status: accepted\n"
        "---\n"
        "# Nohyphen Title\n"
        "\n"
        "## Summary\n"
        "\n"
        "Nohyphen summary text.\n",
    )

    ctx = _run_injector("code-planner", str(tmp_path))

    # Accepted ADR with frontmatter + Summary section (case 16).
    assert (
        "- ADR-0001: Use Thing [accepted] - This is the summary text for use thing. "
        "(docs/adr/0001-use-thing.md)" in ctx
    )

    # Missing frontmatter falls back to first paragraph, status unknown (case 17).
    assert (
        "- ADR-0002: No Frontmatter Title [unknown status] - This is the first "
        "paragraph used as fallback summary. (docs/adr/0002-no-frontmatter.md)" in ctx
    )

    # Deprecated status is excluded entirely (case 18).
    assert "ADR-0003" not in ctx

    # Superseded status is excluded entirely (case 18b).
    assert "ADR-0006" not in ctx

    # TODO summary is excluded entirely (case 19).
    assert "ADR-0004" not in ctx

    # 0000-template.md is skipped by filename regardless of content (case 20).
    assert "ADR-0000" not in ctx
    assert "Template boilerplate text" not in ctx

    # Hyphen-less stem still yields the right ADR number (case 21).
    assert (
        "- ADR-9999: Nohyphen Title [accepted] - Nohyphen summary text. "
        "(docs/adr/9999.md)" in ctx
    )

    # Surviving bullets appear in source-file order.
    assert ctx.index("ADR-0001") < ctx.index("ADR-0002") < ctx.index("ADR-9999")


def test_empty_adr_file_yields_no_bullet(tmp_path):
    """Edge case / deliberate behavior delta: a zero-length .md file under
    docs/adr/ yields no bullet at all. This differs from the prior
    implementation, which emitted a stub `[unknown status]` bullet for an
    empty file; the new one-pass behavior omits it entirely."""
    docs_dir = tmp_path / "docs"
    adr_dir = docs_dir / "adr"
    _write_adr(adr_dir, "0005-empty.md", "")

    ctx = _run_injector("code-planner", str(tmp_path))

    assert "ADR-0005" not in ctx


def test_missing_adr_directory_yields_no_section_and_no_error(tmp_path):
    """When docs/adr/ does not exist, the ADR summary section is simply
    absent - no error, no crash (existing `[ -d "$adr_dir" ] || return 0`
    guard, unchanged by this task)."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True)

    ctx = _run_injector("code-planner", str(tmp_path))

    assert "### ADRs" not in ctx


def test_empty_adr_directory_yields_no_section_and_no_error(tmp_path):
    """docs/adr/ exists but contains zero matching .md files: no ADR summary
    section, no error."""
    docs_dir = tmp_path / "docs"
    adr_dir = docs_dir / "adr"
    adr_dir.mkdir(parents=True)

    ctx = _run_injector("code-planner", str(tmp_path))

    assert "### ADRs" not in ctx
