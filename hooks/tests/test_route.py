"""Router tests, written first (TDD).

Encodes the locked route-assembly rules: OR over `subscribes`, AND over required `input`,
optional (`?`) inputs that order-but-never-drop, the `routes` filter against the live path,
topo-sort on precedence, size = stage count, grow/shrink by signal, and sticky-guard
persistence. Runs under pytest and standalone (`python3 hooks/tests/test_route.py`).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # hooks/
import route
import check_catalog


def S(routes, req=(), opt=(), out=(), sub=(), pub=(), guard=None):
    """Build a normalized catalog stage entry (matches gen-catalog output shape)."""
    s = {
        "routes": list(routes),
        "data": {
            "input": {"required": list(req), "optional": list(opt)},
            "output": list(out),
        },
        "signals": {"subscribes": list(sub), "publishes": list(pub)},
    }
    if guard:
        s["guard"] = guard
    return s


CATALOG = {
    "stages": {
        "scan": S(
            ["build", "talk"],
            req=["intent"],
            out=["reuse-map"],
            sub=["build"],
            pub=["missing-infra", "scope-shift"],
        ),
        "impl": S(
            ["build"],
            req=["plan", "tests"],
            out=["diff"],
            sub=["plan-ready"],
            pub=["code-written", "scope-shift"],
        ),
        "sec": S(
            ["build", "spike"],
            req=["diff"],
            out=["findings"],
            sub=["auth-surface"],
            pub=["findings:security", "scope-shift"],
            guard="sticky",
        ),
        "proto": S(
            ["build"],
            req=["intent"],
            out=["tracer"],
            sub=["missing-infra"],
            pub=["scope-shift"],
        ),
        # optional `reuse-map`: plan runs without it, but orders after scan when scan is present
        "plan": S(
            ["build"],
            req=["intent"],
            opt=["reuse-map"],
            out=["blueprint"],
            sub=["plan-needed"],
            pub=["plan-ready", "scope-shift"],
        ),
        # three single-purpose stages on the same signal to exercise the routes filter
        "buildonly": S(["build"], sub=["ping"], pub=["scope-shift"]),
        "spikeonly": S(["spike"], sub=["ping"], pub=["scope-shift"]),
        "both": S(["build", "spike"], sub=["ping"], pub=["scope-shift"]),
    }
}


def r(live, available=(), already_run=()):
    return route.compute_route(CATALOG, set(live), set(available), set(already_run))


def test_or_subscribe_triggers_on_any_signal():
    assert "sec" in r(["auth-surface"], available=["diff"])["route"]
    assert "sec" not in r(["build"], available=["diff"])["route"]


def test_and_required_drops_unsatisfiable_input():
    # impl needs plan AND tests; with no producer for tests it cannot run
    assert "impl" not in r(["plan-ready"], available=["plan"])["route"]
    assert "impl" in r(["plan-ready"], available=["plan", "tests"])["route"]


def test_topo_order_producer_before_consumer():
    # impl produces diff; sec needs diff -> impl precedes sec
    order = r(["plan-ready", "auth-surface"], available=["plan", "tests"])["route"]
    assert order.index("impl") < order.index("sec")


def test_optional_input_never_drops_and_orders_after_producer():
    # optional producer absent -> the stage still runs (optional never drops)
    assert "plan" in r(["plan-needed"], available=["intent"])["route"]
    # optional producer present (scan -> reuse-map) -> plan orders after scan
    order = r(["build", "plan-needed"], available=["intent"])["route"]
    assert "plan" in order and "scan" in order
    assert order.index("scan") < order.index("plan")


def test_routes_filter_drops_off_path_stage():
    on_build = r(["build", "ping"], available=["intent"])
    assert "buildonly" in on_build["route"] and "both" in on_build["route"]
    assert "spikeonly" not in on_build["route"]
    assert on_build["dropped"].get("spikeonly") == "off-path"
    on_spike = r(["spike", "ping"], available=["intent"])
    assert "spikeonly" in on_spike["route"] and "both" in on_spike["route"]
    assert "buildonly" not in on_spike["route"]
    assert on_spike["dropped"].get("buildonly") == "off-path"


def test_no_path_signal_skips_routes_filter():
    # pre-triage seed: no build/spike/talk live -> nothing is filtered by route
    res = r(["ping"])
    assert {"buildonly", "spikeonly", "both"} <= set(res["route"])


def test_multi_path_stage_survives_on_each_path():
    assert "both" in r(["build", "ping"], available=["intent"])["route"]
    assert "both" in r(["spike", "ping"], available=["intent"])["route"]


def test_size_is_stage_count():
    assert route.size_label(1) == "XS"
    assert route.size_label(2) == "S"
    assert route.size_label(5) == "M"
    assert r(["build"], available=["intent"])["size"] == "XS"


def test_route_grows_and_shrinks_with_signals():
    base = r(["build"], available=["intent"])
    assert base["route"] == ["scan"]
    grown = r(["build", "missing-infra"], available=["intent"])
    assert set(grown["route"]) == {"scan", "proto"}  # proto joins via missing-infra
    shrunk = r(["build"], available=["intent"])
    assert shrunk["route"] == ["scan"]  # signal gone -> proto drops


def test_sticky_guard_persists_across_recompose():
    prev = r(["build", "auth-surface"], available=["intent", "diff"])
    assert "sec" in prev["route"]
    now = r(["build"], available=["intent", "diff"])  # auth-surface gone
    assert "sec" not in now["route"]  # would drop...
    merged = route.merge_sticky(CATALOG, prev["route"], now)
    assert "sec" in merged["route"]  # ...but sticky keeps it


def test_deterministic_same_input_same_route():
    a = r(["plan-ready", "auth-surface"], available=["plan", "tests"])
    b = r(["plan-ready", "auth-surface"], available=["plan", "tests"])
    assert a == b


def _real_catalog():
    return route.load_catalog(
        Path(__file__).resolve().parents[2] / "generated" / "catalog.json"
    )


def test_real_catalog_build_spine():
    cat = _real_catalog()
    assert set(cat["stages"]) >= {
        "implementer",
        "reuse-scanner",
        "security-reviewer",
        "discuss",
        "spike-build",
    }
    res = route.compute_route(cat, {"build"}, available={"confirmed-intent"})
    # reuse-scanner now subscribes needs-tests, so it does NOT trigger on {build} alone
    assert "reuse-scanner" not in res["route"]
    assert "discuss" not in res["route"]  # talk-only stage stays off the build path
    # health-checker now subscribes needs-tests too, so it does NOT trigger on {build} alone
    assert "health-checker" not in res["route"]


def test_real_catalog_routes_filter_on_spike():
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"spike", "needs-tests", "code-written"},
        available={"confirmed-intent", "diff"},
    )
    assert "spike-build" in res["route"]
    assert "correctness-reviewer" in res["route"]  # routes include spike
    assert "quality-reviewer" not in res["route"]  # build-only lens, filtered off spike
    assert res["dropped"].get("quality-reviewer") == "off-path"


def test_real_catalog_talk_path():
    cat = _real_catalog()
    res = route.compute_route(
        cat, {"talk", "ambiguous"}, available={"request", "triage-read"}
    )
    assert "discuss" in res["route"]
    assert "interviewer" in res["route"]  # ambiguous + talk
    # discuss optionally consumes interviewer's confirmed-intent -> orders after it
    assert res["route"].index("interviewer") < res["route"].index("discuss")


def test_real_catalog_coherence():
    # the coherence gate, run against the real catalog: no orphan subscribes, every required
    # input has a producer or seed, scope-shift + routes on every stage
    assert check_catalog.check(_real_catalog()) == []


def test_family_prefix_subscribe_matches_qualified():
    cat = {
        "stages": {
            "fix": S(
                ["build"],
                req=["findings"],
                out=["diff"],
                sub=["findings"],
                pub=["code-written", "scope-shift"],
            ),
        }
    }
    assert (
        "fix"
        in route.compute_route(cat, {"findings:correctness"}, available={"findings"})[
            "route"
        ]
    )
    assert (
        "fix" in route.compute_route(cat, {"findings"}, available={"findings"})["route"]
    )


def test_real_catalog_new_lenses_contract():
    stages = _real_catalog()["stages"]
    for name, family in (
        ("naming-clarity", "findings:naming-clarity"),
        ("assumptions", "findings:assumptions"),
    ):
        s = stages[name]
        assert s["routes"] == ["build"]
        assert s["data"]["input"]["required"] == ["diff"]
        assert s["data"]["output"] == ["findings"]
        # lenses now subscribe needs-tests (was code-written)
        assert s["signals"]["subscribes"] == ["needs-tests"]
        assert family in s["signals"]["publishes"]
        assert "clean" in s["signals"]["publishes"]
        assert "scope-shift" in s["signals"]["publishes"]


def test_real_catalog_new_lenses_compose_on_code_written():
    # Renamed/retargeted: lenses are triggered by needs-tests, not code-written
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"build", "needs-tests", "code-written"},
        available={"confirmed-intent", "diff"},
    )
    assert "naming-clarity" in res["route"]
    assert "assumptions" in res["route"]
    assert res["triggered_by"]["naming-clarity"] == "needs-tests"
    assert res["triggered_by"]["assumptions"] == "needs-tests"


def test_real_catalog_new_lenses_need_diff():
    cat = _real_catalog()
    res = route.compute_route(
        cat, {"build", "needs-tests", "code-written"}, available={"confirmed-intent"}
    )  # no diff
    assert "naming-clarity" not in res["route"]
    assert "assumptions" not in res["route"]
    # positive control: triage subscribes request-received and is seeded externally;
    # use correctness-reviewer (build+spike lens, triggered by code-written) as positive control
    # but code-written requires diff, so use reuse-scanner which subscribes needs-tests
    # and has no required inputs - it should appear in route
    assert "reuse-scanner" in res["route"]


def test_real_catalog_new_lenses_off_spike():
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"spike", "needs-tests", "code-written"},
        available={"confirmed-intent", "diff"},
    )
    assert res["dropped"].get("naming-clarity") == "off-path"
    assert res["dropped"].get("assumptions") == "off-path"
    assert "spike-build" in res["route"]  # positive control: spike route still composes


# ---------------------------------------------------------------------------
# NEW TESTS (RED - assert post-change wiring not yet implemented)
# ---------------------------------------------------------------------------

# EXCLUSION SET: all stages that must NOT appear in trivial route
_EXCLUSION_SET = {
    "acceptance-reviewer",
    "accessibility-reviewer",
    "architecture-reviewer",
    "assumptions",
    "consistency-reviewer",
    "design-consistency-reviewer",
    "naming-clarity",
    "performance-reviewer",
    "plan-adherence-reviewer",
    "quality-reviewer",
    "reuse-reviewer",
    "structure-reviewer",
    "test-gap",
    "test-verifier",
    "ux-reviewer",
    "visual-verifier",
    "capture-agent",
    "reuse-scanner",
    "health-checker",
    "requirements-clarifier",
    "prototype-identifier",
    "plan-challenger",
    "test-plan",
}

# The 16 deep lenses (exclusion set minus the non-lens stages)
_DEEP_LENSES = {
    "acceptance-reviewer",
    "accessibility-reviewer",
    "architecture-reviewer",
    "assumptions",
    "consistency-reviewer",
    "design-consistency-reviewer",
    "naming-clarity",
    "performance-reviewer",
    "plan-adherence-reviewer",
    "quality-reviewer",
    "reuse-reviewer",
    "structure-reviewer",
    "test-gap",
    "test-verifier",
    "ux-reviewer",
    "visual-verifier",
}


def test_real_catalog_trivial_route_minimal():
    """Trivial path: skip-tests fires via trivial signal, planner fires via trivial,
    none of the deep review stages or TDD chain appear."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"build", "trivial"},
        available={"request", "triage-read", "confirmed-intent"},
    )
    assert "skip-tests" in res["route"], "skip-tests must be in trivial route"
    assert "planner" in res["route"], "planner must be in trivial route"
    route_set = set(res["route"])
    for stage in _EXCLUSION_SET:
        assert stage not in route_set, f"{stage} must NOT be in trivial route"


def test_real_catalog_trivial_route_post_code():
    """After code is written on the trivial path, correctness-reviewer joins but deep
    lenses do not (they are gated behind needs-tests, not code-written)."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"build", "trivial", "code-written"},
        available={
            "request",
            "triage-read",
            "confirmed-intent",
            "green-light",
            "approved-plan",
            "diff",
        },
    )
    assert (
        "correctness-reviewer" in res["route"]
    ), "correctness-reviewer must appear post-code"
    route_set = set(res["route"])
    for stage in _DEEP_LENSES:
        assert (
            stage not in route_set
        ), f"deep lens {stage} must NOT be in trivial post-code route"


def test_real_catalog_trivial_multi_file_no_prototype_identifier():
    """LEAK GUARD: multi-file signal on trivial path must NOT trigger prototype-identifier.
    After the fix, prototype-identifier subscribes needs-tests only, not multi-file."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"build", "trivial", "multi-file"},
        available={"request", "triage-read", "confirmed-intent"},
    )
    assert (
        "prototype-identifier" not in res["route"]
    ), "prototype-identifier must not appear on trivial multi-file route"
    assert (
        res["triggered_by"].get("prototype-identifier") is None
    ), "prototype-identifier must not be triggered on trivial multi-file path"
    route_set = set(res["route"])
    for stage in _EXCLUSION_SET:
        assert (
            stage not in route_set
        ), f"{stage} must NOT be in trivial multi-file route"


def test_real_catalog_needs_tests_implementer_dropped_pre_test_chain():
    """Before tests are written, implementer cannot satisfy its green-light requirement
    so it must be dropped as unsatisfiable-input."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"build", "needs-tests", "plan-ready"},
        available={"request", "triage-read", "confirmed-intent", "approved-plan"},
    )
    assert (
        "implementer" not in res["route"]
    ), "implementer must be absent before test chain"
    assert (
        res["dropped"].get("implementer") == "unsatisfiable-input"
    ), "implementer must be dropped as unsatisfiable-input"
    assert "test-plan" in res["route"], "test-plan must be in route when plan-ready"


def test_real_catalog_needs_tests_implementer_after_test_review():
    """TDD LOCK: once tests are red and approved, test-review must precede implementer."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"build", "needs-tests", "plan-ready", "test-cases-ready", "tests-red"},
        available={
            "request",
            "triage-read",
            "confirmed-intent",
            "approved-plan",
            "test-cases",
            "tests",
        },
    )
    assert (
        "implementer" in res["route"]
    ), "implementer must be in route after test chain"
    assert "test-review" in res["route"], "test-review must be in route"
    order = res["route"]
    assert order.index("test-review") < order.index(
        "implementer"
    ), "test-review must precede implementer"
    assert "test-author" in res["route"], "test-author must be in route"
    assert order.index("test-author") < order.index(
        "test-review"
    ), "test-author must precede test-review"


def test_real_catalog_needs_tests_reuse_scanner_survives():
    """GAP 1: reuse-scanner must trigger on needs-tests signal."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"build", "needs-tests"},
        available={"request", "triage-read", "confirmed-intent"},
    )
    assert (
        "reuse-scanner" in res["route"]
    ), "reuse-scanner must appear when needs-tests is live"
    assert (
        res["dropped"].get("reuse-scanner") != "unsatisfiable-input"
    ), "reuse-scanner must not be dropped as unsatisfiable-input"


def test_real_catalog_needs_tests_reuse_scanner_dropped_without_confirmed_intent():
    """GAP 1 contrast: without confirmed-intent, reuse-scanner's required input is absent."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"build", "needs-tests"},
        available={"request", "triage-read"},  # NO confirmed-intent
    )
    assert (
        "reuse-scanner" not in res["route"]
    ), "reuse-scanner must be absent without confirmed-intent"
    assert (
        res["dropped"].get("reuse-scanner") == "unsatisfiable-input"
    ), "reuse-scanner must be dropped as unsatisfiable-input without confirmed-intent"


def test_optional_producer_in_route_creates_ordering_edge_without_artifact():
    """GAP 2 regression (SYNTHETIC): optional input creates ordering edge even without artifact.
    Two stages: alpha (triggered, produces alpha-out), beta (opt=alpha-out, triggered).
    Both in route; alpha ordered before beta even though alpha-out is absent from available.
    """
    cat = {
        "stages": {
            "alpha": S(
                ["build"],
                out=["alpha-out"],
                sub=["go"],
                pub=["scope-shift"],
            ),
            "beta": S(
                ["build"],
                req=[],
                opt=["alpha-out"],
                out=["beta-out"],
                sub=["go"],
                pub=["scope-shift"],
            ),
        }
    }
    res = route.compute_route(cat, {"build", "go"}, available=set())
    assert "alpha" in res["route"], "alpha must be in route"
    assert "beta" in res["route"], "beta must be in route"
    assert res["route"].index("alpha") < res["route"].index(
        "beta"
    ), "alpha must precede beta via optional ordering edge even without alpha-out in available"


def test_real_catalog_needs_tests_stale_green_light_does_not_bypass_ordering():
    """FLIP: green-light in available (stale/prior run) must not bypass test-review -> implementer
    ordering. The XOR contract + orchestrator invalidation are not unit-testable at the router;
    this asserts only the in-route-producer ordering edge."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"build", "needs-tests", "plan-ready", "test-cases-ready", "tests-red"},
        available={
            "request",
            "triage-read",
            "confirmed-intent",
            "approved-plan",
            "test-cases",
            "tests",
            "green-light",  # green-light STALE in available
        },
    )
    assert "implementer" in res["route"], "implementer must be in route"
    assert "test-review" in res["route"], "test-review must be in route"
    order = res["route"]
    assert order.index("test-review") < order.index(
        "implementer"
    ), "test-review must precede implementer even with stale green-light in available"


def test_real_catalog_coherence_post_migration():
    """Catalog coherence check passes after migration."""
    assert check_catalog.check(_real_catalog()) == []


def test_real_catalog_has_40_stages_with_skip_tests():
    """After adding skip-tests, catalog must have 40 stages."""
    cat = _real_catalog()
    stages = cat["stages"]
    assert len(stages) == 40, f"expected 40 stages, got {len(stages)}"
    assert "skip-tests" in stages, "skip-tests stage must exist in catalog"


def test_real_catalog_no_stage_outputs_validated_tests():
    """After migration, no stage should output validated-tests (replaced by green-light)."""
    cat = _real_catalog()
    for name, stage in cat["stages"].items():
        assert (
            "validated-tests" not in stage["data"]["output"]
        ), f"{name} must not output validated-tests"


def test_real_catalog_skip_tests_stage_contract():
    """skip-tests: routes==[build], input.required==[], input.optional==[], subscribes==[trivial],
    green-light in output, scope-shift in publishes."""
    stages = _real_catalog()["stages"]
    assert "skip-tests" in stages, "skip-tests must exist"
    s = stages["skip-tests"]
    assert s["routes"] == [
        "build"
    ], f"skip-tests routes must be ['build'], got {s['routes']}"
    assert (
        s["data"]["input"]["required"] == []
    ), f"skip-tests required input must be [], got {s['data']['input']['required']}"
    assert (
        s["data"]["input"]["optional"] == []
    ), f"skip-tests optional input must be [], got {s['data']['input']['optional']}"
    assert s["signals"]["subscribes"] == [
        "trivial"
    ], f"skip-tests subscribes must be ['trivial'], got {s['signals']['subscribes']}"
    assert (
        "green-light" in s["data"]["output"]
    ), f"green-light must be in skip-tests output"
    assert (
        "scope-shift" in s["signals"]["publishes"]
    ), "scope-shift must be in skip-tests publishes"


def test_real_catalog_test_review_outputs_green_light():
    """After migration, test-review outputs green-light (not validated-tests)."""
    stages = _real_catalog()["stages"]
    s = stages["test-review"]
    assert (
        "green-light" in s["data"]["output"]
    ), "green-light must be in test-review output"
    assert (
        "validated-tests" not in s["data"]["output"]
    ), "validated-tests must NOT be in test-review output"


def test_real_catalog_implementer_requires_green_light():
    """After migration, implementer requires green-light (not validated-tests)."""
    stages = _real_catalog()["stages"]
    s = stages["implementer"]
    assert (
        "green-light" in s["data"]["input"]["required"]
    ), "green-light must be in implementer required input"
    assert (
        "validated-tests" not in s["data"]["input"]["required"]
    ), "validated-tests must NOT be in implementer required input"


def test_real_catalog_triage_publishes_trivial_and_needs_tests():
    """After migration, triage publishes both trivial and needs-tests signals, and
    triage (not only interviewer) outputs confirmed-intent so a clear build's pre-flight
    is never starved."""
    stages = _real_catalog()["stages"]
    pubs = stages["triage"]["signals"]["publishes"]
    assert "trivial" in pubs, "triage must publish trivial"
    assert "needs-tests" in pubs, "triage must publish needs-tests"
    assert "confirmed-intent" in stages["triage"]["data"]["output"]


def test_real_catalog_planner_subscribes_trivial_and_clarified():
    """After migration, planner subscribes both trivial and clarified."""
    stages = _real_catalog()["stages"]
    s = stages["planner"]
    subs = s["signals"]["subscribes"]
    assert "trivial" in subs, f"planner must subscribe trivial, got subscribes={subs}"
    assert (
        "clarified" in subs
    ), f"planner must subscribe clarified, got subscribes={subs}"
    assert (
        "confirmed-intent" in s["data"]["input"]["required"]
    ), "planner must require confirmed-intent"
    assert (
        "clarified-intent" in s["data"]["input"]["optional"]
        or "clarified-intent" in s["data"]["input"]["required"]
    ), "planner must accept clarified-intent (required or optional)"


if __name__ == "__main__":
    import traceback

    tests = [
        v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
