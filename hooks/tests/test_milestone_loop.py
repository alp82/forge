"""Milestone-loop tests (RED before implementation).

Tests the catalog and router invariants introduced by the milestone-loop build:
  - `milestone-scope` field on 4 stages (correctness-reviewer, security-reviewer,
    structure-reviewer = 'local'; test-verifier = 'both')
  - `#milestone-diverged` edge: code-implementer publishes, plan-challenger subscribes
  - check_catalog gains LIGHT value-validation for milestone-scope + orphan-subscribe
    guard on the new edge

RED/GREEN summary
-----------------
TC-M1  RED   - milestone-scope field is absent from all 4 stages in the current catalog
TC-M2  RED   - milestone-scope field is absent, so the "exactly those 4" assertion fails
TC-M3  RED   - plan-challenger does not yet subscribe #milestone-diverged, so it is absent
               from the route on the trigger signal set
TC-M4  RED   - plan-challenger's subscribes list does not yet contain milestone-diverged
TC-M5  RED   - code-implementer's publishes list does not yet contain milestone-diverged
TC-M6  GREEN - TDD lock holds code-implementer when #needs-tests is live and #tests-ready
               is absent; existing lock behavior, guards the boundary re-hold that the
               milestone spec reuses
TC-M7  RED   - check_catalog does not yet validate milestone-scope values or detect the
               orphaned milestone-diverged subscription
TC-M8  GREEN - stage count is 48 and absence of milestone-scope is the valid state right
               now; the gen-catalog guard-emit (absence stays absence) is already correct
"""

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # hooks/
import check_catalog
import route


def _real_catalog():
    return route.load_catalog(
        Path(__file__).resolve().parents[2] / "generated" / "catalog.json"
    )


# ---------------------------------------------------------------------------
# TC-M1 (catalog-contract, RED)
# ---------------------------------------------------------------------------


# --- TC-M1 ---
def test_milestone_scope_field_values_on_four_stages():
    """The 4 tagged stages carry milestone-scope with the exact prescribed values.

    correctness-reviewer, security-reviewer, structure-reviewer -> 'local'
    test-verifier -> 'both'

    Fails now: the field is absent from all four stages.
    """
    stages = _real_catalog()["stages"]

    local_stages = ("correctness-reviewer", "security-reviewer", "structure-reviewer")
    for name in local_stages:
        s = stages[name]
        assert (
            "milestone-scope" in s
        ), f"{name}: missing `milestone-scope` field (expected 'local')"
        assert (
            s["milestone-scope"] == "local"
        ), f"{name}: milestone-scope must be 'local', got {s['milestone-scope']!r}"

    tv = stages["test-verifier"]
    assert (
        "milestone-scope" in tv
    ), "test-verifier: missing `milestone-scope` field (expected 'both')"
    assert (
        tv["milestone-scope"] == "both"
    ), f"test-verifier: milestone-scope must be 'both', got {tv['milestone-scope']!r}"


# ---------------------------------------------------------------------------
# TC-M2 (catalog-contract, RED)
# ---------------------------------------------------------------------------


# --- TC-M2 ---
def test_milestone_scope_present_on_exactly_four_stages():
    """Exactly the 4 designated stages carry milestone-scope; no other stage does.

    Fails now: the field is absent from all stages, so the "has field" assertion
    on the tagged four fails immediately.
    """
    stages = _real_catalog()["stages"]
    _TAGGED = {
        "correctness-reviewer",
        "security-reviewer",
        "structure-reviewer",
        "test-verifier",
    }

    # Tagged stages must have the field
    for name in _TAGGED:
        assert (
            "milestone-scope" in stages[name]
        ), f"{name}: must carry `milestone-scope` but the field is absent"

    # No other stage may carry the field
    for name, s in stages.items():
        if name not in _TAGGED:
            assert (
                "milestone-scope" not in s
            ), f"{name}: must NOT carry `milestone-scope` (not a tagged stage)"


# ---------------------------------------------------------------------------
# TC-M3 (router-trace, RED)
# ---------------------------------------------------------------------------


# --- TC-M3 ---
def test_plan_challenger_in_route_on_milestone_diverged():
    """With {code, significant-build, milestone-diverged, ...} live and @approved-plan
    available, plan-challenger is in the route because it subscribes #milestone-diverged.

    Fails now: plan-challenger does not yet subscribe milestone-diverged, so it is not
    triggered by that signal and is absent from the route unless significant-build alone
    already pulls it in - but the test uses a signal set WITHOUT significant-build to
    isolate the milestone-diverged subscription.
    """
    cat = _real_catalog()
    # Use ONLY milestone-diverged as the trigger (no significant-build) so the route
    # inclusion proves the subscription to milestone-diverged specifically.
    res = route.compute_route(
        cat,
        {"code", "milestone-diverged"},
        available={"approved-plan"},
    )
    assert "plan-challenger" in res["route"], (
        "plan-challenger must be in route when milestone-diverged is live "
        "(it subscribes #milestone-diverged); "
        f"route={res['route']}, triggered_by={res.get('triggered_by', {})}"
    )
    assert res.get("triggered_by", {}).get("plan-challenger") == "milestone-diverged", (
        "plan-challenger must be triggered by milestone-diverged, "
        f"got triggered_by={res.get('triggered_by', {}).get('plan-challenger')!r}"
    )


# ---------------------------------------------------------------------------
# TC-M4 (router-trace / construction-invariant, RED)
# ---------------------------------------------------------------------------


# --- TC-M4 ---
def test_plan_challenger_subscribes_both_significant_build_and_milestone_diverged():
    """plan-challenger's catalog entry subscribes both significant-build AND
    milestone-diverged; the two subscriptions are recorded together.

    Fails now: milestone-diverged is absent from plan-challenger's subscribes list.
    """
    stages = _real_catalog()["stages"]
    pc = stages["plan-challenger"]
    subs = pc["signals"]["subscribes"]

    assert (
        "significant-build" in subs
    ), f"plan-challenger must subscribe significant-build, got {subs}"
    assert (
        "milestone-diverged" in subs
    ), f"plan-challenger must subscribe milestone-diverged (new edge), got {subs}"


# ---------------------------------------------------------------------------
# TC-M5 (catalog-contract, RED)
# ---------------------------------------------------------------------------


# --- TC-M5 ---
def test_code_implementer_publishes_milestone_diverged():
    """code-implementer's signals.publishes includes milestone-diverged.

    Fails now: the signal is absent from code-implementer's publishes list.
    """
    stages = _real_catalog()["stages"]
    pubs = stages["code-implementer"]["signals"]["publishes"]
    assert (
        "milestone-diverged" in pubs
    ), f"code-implementer must publish milestone-diverged, got {pubs}"


# ---------------------------------------------------------------------------
# TC-M6 (router-trace, REUSE-GUARD - GREEN)
# ---------------------------------------------------------------------------


# --- TC-M6 ---
def test_code_implementer_held_when_needs_tests_live_and_tests_ready_absent():
    """REUSE-GUARD: the TDD lock holds code-implementer when #needs-tests is live
    and #tests-ready is absent from the live set.

    The milestone boundary re-hold reuses this same existing lock; this test guards
    that the lock primitive stays intact. Green now, must stay green.

    Mirrors the pattern of TC-I07 in test_route.py.
    """
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "needs-tests", "plan-ready"},
        available={"confirmed-intent", "approved-plan"},
    )
    assert (
        "code-implementer" not in res["route"]
    ), "code-implementer must be absent from route (TDD lock active, tests-ready absent)"
    assert (
        "code-implementer" in res["held"]
    ), "code-implementer must be in held (TDD lock active)"
    assert (
        "tests-ready" in res["held"]["code-implementer"]
    ), "held payload must list tests-ready as an unmet until signal"


# ---------------------------------------------------------------------------
# TC-M7 (check_catalog, RED)
# ---------------------------------------------------------------------------


# --- TC-M7 ---
def test_check_catalog_flags_invalid_milestone_scope_value():
    """check_catalog.check() returns a problem naming a stage whose milestone-scope
    is set to an out-of-domain value (e.g. 'remote').

    Also asserts:
    - An untagged stage (no milestone-scope key) produces NO milestone-scope problem.
    - Deleting the #milestone-diverged publisher (code-implementer) while plan-challenger
      still subscribes it yields a check_catalog orphan-subscribe problem.

    Fails now: check_catalog does not yet validate milestone-scope values, and the
    milestone-diverged edge does not exist in the catalog.
    """
    # --- Part A: invalid value 'remote' on correctness-reviewer ---
    cat = copy.deepcopy(_real_catalog())
    # Inject milestone-scope with an invalid value on one stage
    cat["stages"]["correctness-reviewer"]["milestone-scope"] = "remote"
    problems = check_catalog.check(cat)
    assert any(
        "correctness-reviewer" in p and "milestone-scope" in p for p in problems
    ), (
        f"check_catalog must flag correctness-reviewer for invalid milestone-scope='remote'; "
        f"problems={problems}"
    )

    # --- Part B: absence is valid - untagged stage produces no milestone-scope problem ---
    cat2 = copy.deepcopy(_real_catalog())
    # visual-verifier has no milestone-scope (and must not)
    assert (
        "milestone-scope" not in cat2["stages"]["visual-verifier"]
    ), "pre-condition: visual-verifier must not have milestone-scope in real catalog"
    problems2 = check_catalog.check(cat2)
    ms_problems_for_vv = [
        p for p in problems2 if "visual-verifier" in p and "milestone-scope" in p
    ]
    assert ms_problems_for_vv == [], (
        f"absence of milestone-scope on visual-verifier must produce no problem; "
        f"got {ms_problems_for_vv}"
    )

    # --- Part C: orphan subscriber when publisher is removed ---
    # Deep-copy the real catalog (which already has the milestone-diverged edge wired)
    # and remove ALL occurrences of milestone-diverged from code-implementer's publishes,
    # while plan-challenger still subscribes it - creating a genuine orphan.
    cat3 = copy.deepcopy(_real_catalog())
    ci_pubs = cat3["stages"]["code-implementer"]["signals"]["publishes"]
    cat3["stages"]["code-implementer"]["signals"]["publishes"] = [
        s for s in ci_pubs if s != "milestone-diverged"
    ]
    problems3 = check_catalog.check(cat3)
    assert any(
        "plan-challenger" in p and "milestone-diverged" in p for p in problems3
    ), (
        f"check_catalog must flag plan-challenger for orphan subscribe on milestone-diverged "
        f"(publisher removed); problems={problems3}"
    )


# ---------------------------------------------------------------------------
# TC-M8 (catalog-contract, REUSE-GUARD - GREEN)
# ---------------------------------------------------------------------------


# --- TC-M8 ---
def test_stage_count_stays_47_and_absence_is_valid():
    """REUSE-GUARD: stage count stays at 48 (no stages added by this change) and a
    stage without milestone-scope has no such key in the catalog (gen-catalog guard
    emit - absence stays absence).

    Green now, must stay green.
    """
    cat = _real_catalog()
    stages = cat["stages"]

    assert (
        len(stages) == 48
    ), f"stage count must remain 48 after milestone-loop change, got {len(stages)}"

    # Spot-check: stages that must NOT gain milestone-scope
    _NO_SCOPE_STAGES = (
        "visual-verifier",
        "quality-reviewer",
        "code-implementer",
        "code-planner",
        "triage",
        "fixer",
    )
    for name in _NO_SCOPE_STAGES:
        assert "milestone-scope" not in stages[name], (
            f"{name}: must NOT carry `milestone-scope` (gen-catalog guard - absence stays absence); "
            f"got {stages[name].get('milestone-scope')!r}"
        )
