"""Tests for the artifact-handles change.

RED tests (r01-r05): fail until WORKFLOW.md gains the leitwort, the read-imperative
envelope, and the threshold name; .gitignore gains .alp-river/; audit.DOCTRINE_PHRASES
gains the canary and reaches length 8; doctrine integrity stays 100; and both version
files reach 1.2.19.

GREEN-now regression guards (g10-g11): pass against the current repo and must stay
green after the implementation lands.

Plan-handle extension guards (b01-b05): the in-body handle-read line lands in the 5
new <APPROVED_PLAN> consumers (outside the fence so the catalog stays byte-identical),
stays out of the 3 inline carve-outs, and the audit fragment exempts the by-design
repetition while doctrine integrity holds at 100.

Conventions mirror test_briefs.py: REAL_REPO_ROOT via Path(__file__).resolve().parents[2];
insert hooks/ on sys.path; import audit and check_catalog; RED/GREEN-labeled test names.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # hooks/
import audit
import check_catalog

REAL_REPO_ROOT = Path(__file__).resolve().parents[2]

# The leitwort for the artifact-handles doctrine.
ARTIFACT_HANDLES_LEITWORT = "artifacts on disk, handles in context"

# The stable, distinctive slice of the v2 read-imperative envelope.
READ_IMPERATIVE_SLICE = "its bytes ARE the artifact"

# The threshold environment-variable name.
THRESHOLD_NAME = "RIVER_ARTIFACT_OFFLOAD_CHARS"

# The reviewers that must carry <APPROVED_PLAN> in their input_template.
REVIEWER_NAMES = (
    "acceptance-reviewer",
    "architecture-reviewer",
    "assumptions",
    "consistency-reviewer",
    "correctness-reviewer",
    "naming-clarity",
    "quality-reviewer",
    "reuse-reviewer",
    "simplicity-reviewer",
    "structure-reviewer",
)


# ---------------------------------------------------------------------------
# RED r01 - WORKFLOW.md contains the leitwort
# ---------------------------------------------------------------------------


def test_artifact_handles_r01_workflow_contains_leitwort():
    """RED-1: WORKFLOW.md contains the literal substring
    "artifacts on disk, handles in context".

    Fails until the implementer adds the leitwort to WORKFLOW.md.
    """
    workflow = REAL_REPO_ROOT / "WORKFLOW.md"
    assert workflow.is_file(), f"WORKFLOW.md not found at {workflow}"
    content = workflow.read_text(encoding="utf-8")
    assert ARTIFACT_HANDLES_LEITWORT in content, (
        f"WORKFLOW.md must contain the leitwort {ARTIFACT_HANDLES_LEITWORT!r}; "
        f"phrase is absent today"
    )


# ---------------------------------------------------------------------------
# RED r02 - WORKFLOW.md contains the read-imperative envelope slice
# ---------------------------------------------------------------------------


def test_artifact_handles_r02_workflow_contains_read_imperative_envelope():
    """RED-2: WORKFLOW.md contains the substring "its bytes ARE the artifact".

    This is the stable, distinctive slice of the v2 envelope:
    "Read the verbatim <APPROVED_PLAN> at <path> - its bytes ARE the artifact."

    Fails until the implementer adds the envelope to WORKFLOW.md.
    """
    workflow = REAL_REPO_ROOT / "WORKFLOW.md"
    assert workflow.is_file(), f"WORKFLOW.md not found at {workflow}"
    content = workflow.read_text(encoding="utf-8")
    assert READ_IMPERATIVE_SLICE in content, (
        f"WORKFLOW.md must contain {READ_IMPERATIVE_SLICE!r}; "
        f"phrase is absent today"
    )


# ---------------------------------------------------------------------------
# RED r03 - WORKFLOW.md contains the threshold variable name
# ---------------------------------------------------------------------------


def test_artifact_handles_r03_workflow_contains_threshold_name():
    """RED-3: WORKFLOW.md contains the substring "RIVER_ARTIFACT_OFFLOAD_CHARS".

    Fails until the implementer adds the threshold variable name to WORKFLOW.md.
    """
    workflow = REAL_REPO_ROOT / "WORKFLOW.md"
    assert workflow.is_file(), f"WORKFLOW.md not found at {workflow}"
    content = workflow.read_text(encoding="utf-8")
    assert THRESHOLD_NAME in content, (
        f"WORKFLOW.md must contain {THRESHOLD_NAME!r}; "
        f"variable name is absent today"
    )


# ---------------------------------------------------------------------------
# RED r04 - .gitignore contains .alp-river/ and not the old .river/
# ---------------------------------------------------------------------------


def test_artifact_handles_r04_gitignore_contains_river_dir():
    """RED-4: repo-root .gitignore contains ".alp-river/" as a line or substring
    AND no longer contains the old ".river/" entry (the clean-break check -
    a lingering ".river/" would mean the rename is incomplete).

    Fails until the implementer renames the entry to .alp-river/ in .gitignore.
    """
    gitignore = REAL_REPO_ROOT / ".gitignore"
    assert gitignore.is_file(), f".gitignore not found at {gitignore}"
    content = gitignore.read_text(encoding="utf-8")
    assert (
        ".alp-river/" in content
    ), f".gitignore must contain '.alp-river/'; entry is absent today"
    assert (
        ".river/" not in content
    ), f".gitignore must not contain the old '.river/'; the rename is incomplete"


# ---------------------------------------------------------------------------
# RED r05 - audit.DOCTRINE_PHRASES contains the artifact canary tuple
# ---------------------------------------------------------------------------


def test_artifact_handles_r05_doctrine_phrases_contains_artifact_canary():
    """RED-5: audit.DOCTRINE_PHRASES contains the artifact-handles canary tuple
    ("artifacts on disk, handles in context", "WORKFLOW.md").

    Fails until the implementer adds the entry to DOCTRINE_PHRASES in audit.py.
    """
    target = (ARTIFACT_HANDLES_LEITWORT, "WORKFLOW.md")
    assert target in audit.DOCTRINE_PHRASES, (
        f"DOCTRINE_PHRASES must contain {target!r}; "
        f"current entries: {audit.DOCTRINE_PHRASES!r}"
    )


# ---------------------------------------------------------------------------
# GREEN g10 - all 10 reviewers have <APPROVED_PLAN> in their input_template
# ---------------------------------------------------------------------------


def test_artifact_handles_g10_reviewer_input_templates_unchanged():
    """GREEN-10 (regression guard): each of the 10 reviewers has an input_template
    in generated/catalog.json that contains the literal "<APPROVED_PLAN>".

    Passes now. Would fail if a catalog regeneration dropped the APPROVED_PLAN
    slot from any reviewer template.
    """
    catalog_path = REAL_REPO_ROOT / "generated" / "catalog.json"
    assert catalog_path.is_file(), f"generated/catalog.json not found at {catalog_path}"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    stages = catalog.get("stages", {})

    for name in REVIEWER_NAMES:
        assert (
            name in stages
        ), f"Reviewer stage '{name}' missing from generated/catalog.json stages"
        tmpl = stages[name].get("input_template", "")
        assert "<APPROVED_PLAN>" in tmpl, (
            f"stages['{name}'].input_template must contain '<APPROVED_PLAN>'; "
            f"template starts with: {tmpl[:120]!r}"
        )


# ---------------------------------------------------------------------------
# GREEN g11 - catalog stage count is 49 and no orphans
# ---------------------------------------------------------------------------


def test_artifact_handles_g11_catalog_stage_count_and_no_orphans():
    """GREEN-11 (regression guard): generated/catalog.json has exactly 49 stages
    and check_catalog.check(...) reports no orphaned signals.

    Passes now. Would fail if the implementer accidentally adds new stages or
    breaks signal wiring.

    Stage count pinned at: 49 (was 50 until the interviewer + requirements-clarifier
    merge into clarifier).
    """
    PINNED_STAGE_COUNT = 49
    catalog_path = REAL_REPO_ROOT / "generated" / "catalog.json"
    assert catalog_path.is_file(), f"generated/catalog.json not found at {catalog_path}"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))

    orphans = check_catalog.check(catalog)
    assert orphans == [], (
        f"generated/catalog.json has orphaned signals: {orphans!r}. "
        f"Signal wiring must remain coherent."
    )

    stage_count = len(catalog.get("stages", {}))
    assert stage_count == PINNED_STAGE_COUNT, (
        f"generated/catalog.json stage count changed: expected {PINNED_STAGE_COUNT}, "
        f"got {stage_count}. If a new stage was intentionally added, update the "
        f"pinned count in this test."
    )


# ---------------------------------------------------------------------------
# Plan-handle extension (b01-b05)
# ---------------------------------------------------------------------------

# The 5 new <APPROVED_PLAN> consumers that gain the in-body handle-read line.
HANDLE_CONSUMER = (
    "code-implementer",
    "plan-challenger",
    "fixer",
    "test-plan",
    "test-review",
)

# The verbatim in-body handle-read line, byte-identical to doctrine/reviewer-contract.md:27.
HANDLE_READ_LINE = (
    "When an `<APPROVED_PLAN>` slot holds a handle line rather than the block, "
    "Read the file at that path and treat its bytes as the verbatim plan "
    "(`WORKFLOW.md` ## Input Template Contract)."
)

# The distinctive fragment that identifies the handle-read line and the audit exemption.
HANDLE_FRAGMENT = "holds a handle line rather than the block"

# The 3 inline carve-outs that must NOT carry the handle-read line.
INLINE_CARVE_OUTS = (
    "plan-adherence-reviewer",
    "plan-arbiter",
    "safety-gate",
)


def test_artifact_handles_b01_handle_consumers_carry_read_line():
    """b01: each of the 5 handle consumers carries the verbatim handle-read line
    in its agents/<name>.md body.

    Fails until the implementer adds the line after each consumer's ## Input block.
    """
    for name in HANDLE_CONSUMER:
        agent = REAL_REPO_ROOT / "agents" / f"{name}.md"
        assert agent.is_file(), f"agent file not found at {agent}"
        content = agent.read_text(encoding="utf-8")
        assert HANDLE_READ_LINE in content, (
            f"agents/{name}.md must contain the verbatim handle-read line; "
            f"line is absent today"
        )


def test_artifact_handles_b02_inline_carve_outs_omit_fragment():
    """b02: the 3 inline carve-outs do NOT carry the handle fragment - they always
    receive the verbatim inline block, never a handle.

    Fails if the implementer wrongly adds the line to a carve-out.
    """
    for name in INLINE_CARVE_OUTS:
        agent = REAL_REPO_ROOT / "agents" / f"{name}.md"
        assert agent.is_file(), f"agent file not found at {agent}"
        content = agent.read_text(encoding="utf-8")
        assert HANDLE_FRAGMENT not in content, (
            f"agents/{name}.md must NOT contain {HANDLE_FRAGMENT!r}; "
            f"this consumer stays inline"
        )


def test_artifact_handles_b03_audit_fragment_present():
    """b03: the handle fragment is registered in audit._MANDATED_CONTRACT_FRAGMENTS,
    exempting the by-design 6-file repetition from the dup-check.

    Fails until the implementer adds the fragment to the tuple.
    """
    assert HANDLE_FRAGMENT in audit._MANDATED_CONTRACT_FRAGMENTS, (
        f"_MANDATED_CONTRACT_FRAGMENTS must contain {HANDLE_FRAGMENT!r}; "
        f"current entries: {audit._MANDATED_CONTRACT_FRAGMENTS!r}"
    )


def test_artifact_handles_b04_catalog_slot_intact_and_line_outside_fence():
    """b04: each handle consumer's input_template still declares <APPROVED_PLAN>
    AND does NOT contain the handle fragment - the latter pins the in-body line
    landed OUTSIDE the ## Input fence, so generated/catalog.json stays byte-identical.

    Fails if the line landed inside a fence (the fragment would leak into the template).
    """
    catalog_path = REAL_REPO_ROOT / "generated" / "catalog.json"
    assert catalog_path.is_file(), f"generated/catalog.json not found at {catalog_path}"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    stages = catalog.get("stages", {})

    for name in HANDLE_CONSUMER:
        assert (
            name in stages
        ), f"stage '{name}' missing from generated/catalog.json stages"
        tmpl = stages[name].get("input_template", "")
        assert "<APPROVED_PLAN>" in tmpl, (
            f"stages['{name}'].input_template must contain '<APPROVED_PLAN>'; "
            f"template starts with: {tmpl[:120]!r}"
        )
        assert HANDLE_FRAGMENT not in tmpl, (
            f"stages['{name}'].input_template must NOT contain {HANDLE_FRAGMENT!r}; "
            f"the handle-read line leaked into the fence - catalog is no longer byte-identical"
        )


def test_artifact_handles_b05_doctrine_integrity_holds_at_100():
    """b05: doctrine integrity stays 100 after the change, and no doctrine-hygiene
    offender mentions the handle line (the audit fragment exempts the repetition).

    Fails if a canary was reworded (integrity drops) or the fragment exemption is
    missing (the repeated line surfaces as a hygiene offender).
    """
    scorecard = audit.build_scorecard(REAL_REPO_ROOT)
    integrity = scorecard["categories"]["doctrine integrity"]["score"]
    assert (
        integrity == 100
    ), f"doctrine integrity must be 100, got {integrity}; a canary was likely reworded"
    hygiene_fixes = scorecard["categories"]["doctrine hygiene"]["fixes"]
    offenders = [fix for fix in hygiene_fixes if HANDLE_FRAGMENT in fix]
    assert offenders == [], (
        f"no doctrine-hygiene offender may mention {HANDLE_FRAGMENT!r}; "
        f"the audit fragment must exempt the by-design repetition. offenders: {offenders!r}"
    )


def test_artifact_handles_b06_canonical_source_carries_read_line():
    """b06: the canonical source - doctrine/reviewer-contract.md - carries the
    verbatim handle-read line that the 5 consumers derive from.

    Fails if the line is removed from the one-home source, even when the 5
    consumer copies still exist. Guards the b01 assumption that the copies
    are faithful derivatives of a living canonical definition.
    """
    canonical = REAL_REPO_ROOT / "doctrine" / "reviewer-contract.md"
    assert canonical.is_file(), f"canonical source not found at {canonical}"
    content = canonical.read_text(encoding="utf-8")
    assert HANDLE_READ_LINE in content, (
        f"doctrine/reviewer-contract.md (canonical source) must contain the "
        f"verbatim handle-read line; line is absent"
    )
