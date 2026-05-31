"""Router tests, written first (TDD).

Encodes the locked route-assembly rules: OR over `subscribes`, AND over required `input`,
optional (`?`) inputs that order-but-never-drop, the `routes` filter against the live path,
topo-sort on precedence, size = stage count, grow/shrink by signal, and sticky-guard
persistence. Runs under pytest and standalone (`python3 hooks/tests/test_route.py`).
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # hooks/
import route
import check_catalog


def S(routes, req=(), opt=(), out=(), sub=(), pub=(), guard=None, lock=None):
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
    if lock:
        s["lock"] = lock
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
# LOCK / HELD UNIT TESTS (TC-U01 - TC-U21, RED - held key not yet in compute_route)
# ---------------------------------------------------------------------------

# Synthetic catalog for lock tests; `impl` has configurable lock via S() kwarg.


def _lock_catalog(lock=None, extra_stages=None):
    """Return a minimal catalog with a lockable `impl` stage and optional extras."""
    stages = {
        "impl": S(
            ["build"],
            req=["plan"],
            out=["diff"],
            sub=["plan-ready"],
            pub=["code-written", "scope-shift"],
            lock=lock,
        ),
    }
    if extra_stages:
        stages.update(extra_stages)
    return {"stages": stages}


def _rl(catalog, live, available=()):
    """Driver for lock-catalog tests."""
    return route.compute_route(catalog, set(live), set(available), set())


# --- TC-U01 ---
def test_lock_active_held_absent_from_route():
    """Stage with active lock is absent from route and appears in held."""
    cat = _lock_catalog(lock=[{"while": "needs-tests", "until": "tests-ready"}])
    res = _rl(cat, ["plan-ready", "needs-tests"], available=["plan"])
    assert "impl" not in res["route"], "locked impl must not be in route"
    assert "impl" in res["held"], "locked impl must be in held"


# --- TC-U02 ---
def test_route_held_disjoint():
    """route and held sets must be disjoint when a lock is active."""
    cat = _lock_catalog(lock=[{"while": "needs-tests", "until": "tests-ready"}])
    res = _rl(cat, ["plan-ready", "needs-tests"], available=["plan"])
    assert (
        set(res["route"]) & set(res["held"]) == set()
    ), "route and held must be disjoint"


# --- TC-U03 ---
def test_lock_releases_when_until_published():
    """Lock releases when the `until` signal is live - stage moves to route."""
    cat = _lock_catalog(lock=[{"while": "needs-tests", "until": "tests-ready"}])
    res = _rl(cat, ["plan-ready", "needs-tests", "tests-ready"], available=["plan"])
    assert "impl" in res["route"], "impl must be in route once until-signal is live"
    assert "impl" not in res.get("held", {}), "impl must not be held once lock released"


# --- TC-U04 ---
def test_lock_inactive_when_while_absent():
    """Lock is inactive when the `while` signal is not live - stage runs normally."""
    cat = _lock_catalog(lock=[{"while": "needs-tests", "until": "tests-ready"}])
    res = _rl(cat, ["plan-ready"], available=["plan"])
    assert "impl" in res["route"], "impl must be in route when while-signal absent"
    assert res.get("held", {}) == {}, "held must be empty when no lock active"


# --- TC-U05 ---
def test_multiple_locks_and_both_active():
    """Two active locks: stage is held; both unmet untils listed in held['impl']."""
    cat = _lock_catalog(
        lock=[
            {"while": "needs-tests", "until": "tests-ready"},
            {"while": "review-needed", "until": "review-done"},
        ]
    )
    res = _rl(cat, ["plan-ready", "needs-tests", "review-needed"], available=["plan"])
    assert "impl" in res["held"], "impl must be held when both locks active"
    unmet = res["held"]["impl"]
    assert "tests-ready" in unmet, "tests-ready must be listed as unmet until"
    assert "review-done" in unmet, "review-done must be listed as unmet until"


# --- TC-U06 ---
def test_multiple_locks_one_resolved():
    """One lock resolved, one still active: stage remains held; held lists only the remaining until."""
    cat = _lock_catalog(
        lock=[
            {"while": "needs-tests", "until": "tests-ready"},
            {"while": "review-needed", "until": "review-done"},
        ]
    )
    res = _rl(
        cat,
        ["plan-ready", "needs-tests", "review-needed", "tests-ready"],
        available=["plan"],
    )
    assert "impl" in res["held"], "impl must still be held with one lock active"
    unmet = res["held"]["impl"]
    assert "review-done" in unmet, "review-done must still be listed as unmet until"
    assert (
        "tests-ready" not in unmet
    ), "tests-ready must not appear in unmet (already live)"


# --- TC-U07 ---
def test_multiple_locks_both_resolved_runs():
    """Both locks resolved: stage is in route, not held."""
    cat = _lock_catalog(
        lock=[
            {"while": "needs-tests", "until": "tests-ready"},
            {"while": "review-needed", "until": "review-done"},
        ]
    )
    res = _rl(
        cat,
        ["plan-ready", "needs-tests", "review-needed", "tests-ready", "review-done"],
        available=["plan"],
    )
    assert "impl" in res["route"], "impl must be in route when both locks resolved"
    assert "impl" not in res.get("held", {}), "impl must not be in held"


# --- TC-U08 ---
def test_family_prefix_until_released():
    """Family-prefix match on until: `tests-ready:foo` in live releases a `tests-ready` until."""
    cat = _lock_catalog(lock=[{"while": "needs-tests", "until": "tests-ready"}])
    res = _rl(cat, ["plan-ready", "needs-tests", "tests-ready:foo"], available=["plan"])
    assert (
        "impl" in res["route"]
    ), "impl must be in route: tests-ready:foo satisfies until=tests-ready"


# --- TC-U09 ---
def test_family_prefix_while_matched():
    """Family-prefix match on while: `needs-tests:logic` in live activates a `needs-tests` while."""
    cat = _lock_catalog(lock=[{"while": "needs-tests", "until": "tests-ready"}])
    # needs-tests:logic present, tests-ready absent -> lock active -> impl held
    res = _rl(cat, ["plan-ready", "needs-tests:logic"], available=["plan"])
    assert (
        "impl" in res["held"]
    ), "impl must be held: needs-tests:logic satisfies while=needs-tests"


# --- TC-U10 ---
def test_held_payload_is_unmet_until():
    """held['impl'] is a list and contains the unmet until signal name."""
    cat = _lock_catalog(lock=[{"while": "needs-tests", "until": "tests-ready"}])
    res = _rl(cat, ["plan-ready", "needs-tests"], available=["plan"])
    assert isinstance(res["held"]["impl"], list), "held['impl'] must be a list"
    assert (
        "tests-ready" in res["held"]["impl"]
    ), "held['impl'] must contain the unmet until"


# --- TC-U11 ---
def test_held_payload_never_deadlock_string():
    """held values are lists of signal names, not the string 'deadlock'."""
    cat = _lock_catalog(
        lock=[
            {"while": "needs-tests", "until": "tests-ready"},
            {"while": "review-needed", "until": "review-done"},
        ]
    )
    res = _rl(cat, ["plan-ready", "needs-tests", "review-needed"], available=["plan"])
    for val in res["held"].values():
        assert val != "deadlock", "held value must never be the string 'deadlock'"


# --- TC-U12 ---
def test_held_stage_excluded_from_toposort():
    """A held stage does not contribute its outputs; downstream consumers become unsatisfiable.

    impl (locked) produces 'diff'; reviewer requires 'diff'; both triggered.
    impl held -> reviewer dropped unsatisfiable. impl in held, reviewer not in route.
    """
    cat = {
        "stages": {
            "impl": S(
                ["build"],
                req=["plan"],
                out=["diff"],
                sub=["plan-ready"],
                pub=["code-written", "scope-shift"],
                lock=[{"while": "needs-tests", "until": "tests-ready"}],
            ),
            "reviewer": S(
                ["build"],
                req=["diff"],
                out=["findings"],
                sub=["plan-ready"],
                pub=["scope-shift"],
            ),
        }
    }
    res = route.compute_route(
        cat, {"plan-ready", "needs-tests"}, available={"plan"}, already_run=frozenset()
    )
    assert "impl" in res["held"], "impl must be in held"
    assert (
        "reviewer" not in res["route"]
    ), "reviewer must not be in route (diff unavailable)"


# --- TC-U13 ---
def test_held_key_present_even_when_empty():
    """Result always has a 'held' key; it equals {} when no stage is held."""
    cat = _lock_catalog()  # no lock
    res = _rl(cat, ["plan-ready"], available=["plan"])
    assert "held" in res, "'held' key must always be present in result"
    assert res["held"] == {}, "held must be {} when no stage is locked"


# --- TC-U14 ---
def test_lock_inactive_cheap_path():
    """Lock present but while-signal absent (cheap path): stage runs, held empty."""
    cat = _lock_catalog(lock=[{"while": "needs-tests", "until": "tests-ready"}])
    res = _rl(cat, ["plan-ready"], available=["plan"])
    assert "impl" in res["route"], "impl must run on cheap path (while-signal absent)"
    assert res.get("held", {}) == {}, "held must be empty on cheap path"


# --- TC-U15 ---
def test_normalize_lock_strips_hash():
    """gen-catalog normalize_stage strips # sigils from lock while/until values."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "gen_catalog",
        Path(__file__).resolve().parents[1] / "gen-catalog.py",
    )
    gen_catalog = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen_catalog)
    normalize_stage = gen_catalog.normalize_stage

    stage_fm = {
        "routes": ["build"],
        "data": {"input": [], "output": []},
        "signals": {"subscribes": [], "publishes": ["scope-shift"]},
        "lock": [{"while": "#needs-tests", "until": "#tests-ready"}],
    }
    result = normalize_stage("impl", stage_fm)
    assert result["lock"] == [
        {"while": "needs-tests", "until": "tests-ready"}
    ], f"lock sigils must be stripped, got {result.get('lock')}"


# --- TC-U16 ---
def test_normalize_lock_passthrough_bare():
    """gen-catalog normalize_stage leaves bare (no-#) lock values unchanged."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "gen_catalog",
        Path(__file__).resolve().parents[1] / "gen-catalog.py",
    )
    gen_catalog = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen_catalog)
    normalize_stage = gen_catalog.normalize_stage

    stage_fm = {
        "routes": ["build"],
        "data": {"input": [], "output": []},
        "signals": {"subscribes": [], "publishes": ["scope-shift"]},
        "lock": [{"while": "needs-tests", "until": "tests-ready"}],
    }
    result = normalize_stage("impl", stage_fm)
    assert result["lock"] == [
        {"while": "needs-tests", "until": "tests-ready"}
    ], f"bare lock values must pass through unchanged, got {result.get('lock')}"


# --- TC-U17 ---
def test_normalize_lock_raises_on_malformed():
    """gen-catalog _normalize_lock raises ValueError when a lock entry is missing 'until'."""
    import importlib.util
    import pytest

    spec = importlib.util.spec_from_file_location(
        "gen_catalog",
        Path(__file__).resolve().parents[1] / "gen-catalog.py",
    )
    gen_catalog = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen_catalog)

    with pytest.raises(ValueError, match="until"):
        gen_catalog._normalize_lock([{"while": "needs-tests"}], "impl")


# --- TC-U18 ---
def test_check_catalog_flags_lock_while_no_publisher():
    """check() reports a problem when lock.while names an unpublished, non-seed signal."""
    # Use request-received (a SEED_SIGNAL) for subscribes so orphan-subscribe check
    # does not fire; only the lock.while invariant should trigger.
    ghost_catalog = {
        "stages": {
            "impl": S(
                ["build"],
                req=[],
                out=["diff"],
                sub=["request-received"],
                pub=["tests-ready", "scope-shift"],
                lock=[{"while": "ghost-signal", "until": "tests-ready"}],
            ),
        }
    }
    problems = check_catalog.check(ghost_catalog)
    assert any(
        "ghost-signal" in p for p in problems
    ), f"check() must flag ghost-signal in lock.while, problems={problems}"


# --- TC-U18 ---
def test_check_catalog_flags_lock_until_no_publisher():
    """check() reports a problem when lock.until names an unpublished, non-seed signal."""
    phantom_catalog = {
        "stages": {
            "impl": S(
                ["build"],
                req=[],
                out=["diff"],
                sub=["request-received"],
                pub=["needs-tests", "scope-shift"],
                lock=[{"while": "needs-tests", "until": "phantom-done"}],
            ),
        }
    }
    problems = check_catalog.check(phantom_catalog)
    assert any(
        "phantom-done" in p for p in problems
    ), f"check() must flag phantom-done in lock.until, problems={problems}"


# --- TC-U19 ---
def test_check_catalog_passes_when_lock_signals_resolve():
    """check() returns [] when lock.while is published by another stage and lock.until is published."""
    clean_catalog = {
        "stages": {
            "impl": S(
                ["build"],
                req=[],
                out=["diff"],
                sub=["request-received"],
                pub=["scope-shift"],
                lock=[{"while": "needs-tests", "until": "tests-ready"}],
            ),
            "test-author": S(
                ["build"],
                out=["tests-ready"],
                sub=["request-received"],
                pub=["needs-tests", "tests-ready", "scope-shift"],
            ),
        }
    }
    problems = check_catalog.check(clean_catalog)
    assert problems == [], f"check() must pass for valid lock signals, got {problems}"


# --- TC-U20 ---
def test_S_factory_lock_absent_by_default():
    """S() without lock kwarg must not add a 'lock' key."""
    s = S(["build"], sub=["go"], pub=["scope-shift"])
    assert "lock" not in s, "S() must not add 'lock' key when lock kwarg is absent"


# --- TC-U21 ---
def test_S_factory_lock_present():
    """S() with lock kwarg stores the value under 'lock'."""
    lock_val = [{"while": "needs-tests", "until": "tests-ready"}]
    s = S(["build"], sub=["go"], pub=["scope-shift"], lock=lock_val)
    assert "lock" in s, "S() must add 'lock' key when lock kwarg is provided"
    assert (
        s["lock"] == lock_val
    ), f"s['lock'] must equal the provided value, got {s.get('lock')}"


# ---------------------------------------------------------------------------
# RETAINED NON-TRIVIAL SYNTHETIC TESTS (unchanged from before)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# INTEGRATION TESTS - REAL CATALOG (TC-I01 - TC-I11, RED until catalog regen)
# ---------------------------------------------------------------------------

# EXCLUSION SET: all stages that must NOT appear in cheap-path route (no needs-tests)
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

# The 16 deep lenses (exclusion set minus the non-lens stages). All stay absent on a cheap
# path: none of their triggering signals are live there. The UI lenses are now ui-touched-
# gated and visual-verifier is run-visual-gated, so they need an even stronger signal than
# the needs-tests lenses to appear.
_DEEP_LENSES = {
    "acceptance-reviewer",
    "accessibility-reviewer",  # ui-touched-gated
    "architecture-reviewer",
    "assumptions",
    "consistency-reviewer",
    "design-consistency-reviewer",  # ui-touched-gated
    "naming-clarity",
    "performance-reviewer",
    "plan-adherence-reviewer",
    "quality-reviewer",
    "reuse-reviewer",
    "structure-reviewer",
    "test-gap",
    "test-verifier",
    "ux-reviewer",  # ui-touched-gated
    "visual-verifier",  # run-visual-gated (opt-in only)
}


# --- TC-I01 ---
def test_real_catalog_has_39_stages_no_skip_tests():
    """After migration, catalog has 39 stages and skip-tests is absent."""
    cat = _real_catalog()
    stages = cat["stages"]
    assert len(stages) == 39, f"expected 39 stages, got {len(stages)}"
    assert "skip-tests" not in stages, "skip-tests must NOT exist in migrated catalog"


# --- TC-I02 ---
def test_real_catalog_implementer_contract():
    """implementer: required input == ['approved-plan'] only; lock present with TDD guard."""
    stages = _real_catalog()["stages"]
    s = stages["implementer"]
    assert s["data"]["input"]["required"] == [
        "approved-plan"
    ], f"implementer required must be ['approved-plan'], got {s['data']['input']['required']}"
    assert (
        "green-light" not in s["data"]["input"]["required"]
    ), "green-light must NOT be in implementer required input"
    assert "lock" in s, "implementer must have a 'lock' field"
    assert s["lock"] == [
        {"while": "needs-tests", "until": "tests-ready"}
    ], f"implementer lock must be [{{while:needs-tests,until:tests-ready}}], got {s.get('lock')}"


# --- TC-I03 ---
def test_real_catalog_test_review_contract():
    """test-review: data.output == []; 'tests-ready' in publishes."""
    stages = _real_catalog()["stages"]
    s = stages["test-review"]
    assert (
        s["data"]["output"] == []
    ), f"test-review output must be [], got {s['data']['output']}"
    assert (
        "tests-ready" in s["signals"]["publishes"]
    ), "tests-ready must be in test-review publishes"
    assert (
        "green-light" not in s["data"]["output"]
    ), "green-light must NOT be in test-review output"


# --- TC-I04 ---
def test_real_catalog_triage_publishes_intent_confirmed_not_trivial():
    """triage: publishes intent-confirmed and needs-tests; does not publish trivial."""
    stages = _real_catalog()["stages"]
    pubs = stages["triage"]["signals"]["publishes"]
    assert "intent-confirmed" in pubs, "triage must publish intent-confirmed"
    assert "needs-tests" in pubs, "triage must publish needs-tests"
    assert "trivial" not in pubs, "triage must NOT publish trivial after migration"


# --- TC-I05 ---
def test_real_catalog_planner_subscribes_intent_confirmed_not_trivial():
    """planner: subscribes has 'clarified' + 'intent-confirmed'; does not subscribe trivial."""
    stages = _real_catalog()["stages"]
    s = stages["planner"]
    subs = s["signals"]["subscribes"]
    assert "clarified" in subs, f"planner must subscribe clarified, got {subs}"
    assert (
        "intent-confirmed" in subs
    ), f"planner must subscribe intent-confirmed, got {subs}"
    assert "trivial" not in subs, f"planner must NOT subscribe trivial, got {subs}"


# --- TC-I06 ---
def test_real_catalog_correctness_publishes_needs_tests():
    """correctness-reviewer publishes needs-tests (it gates the TDD chain)."""
    stages = _real_catalog()["stages"]
    s = stages["correctness-reviewer"]
    assert (
        "needs-tests" in s["signals"]["publishes"]
    ), "correctness-reviewer must publish needs-tests"


# --- TC-I07 ---
def test_real_catalog_implementer_held_before_tests_ready():
    """TDD LOCK: before tests-ready, implementer is in held (lock active), not route."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"build", "needs-tests", "plan-ready"},
        available={"confirmed-intent", "approved-plan"},
    )
    assert (
        "implementer" not in res["route"]
    ), "implementer must be absent from route before tests-ready"
    assert (
        "implementer" in res["held"]
    ), "implementer must be in held (lock active) before tests-ready"


# --- TC-I08 ---
def test_real_catalog_implementer_in_route_after_tests_ready():
    """TDD LOCK released: with tests-ready live, implementer is in route, not held."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {
            "build",
            "needs-tests",
            "plan-ready",
            "test-cases-ready",
            "tests-red",
            "tests-ready",
        },
        available={"confirmed-intent", "approved-plan", "test-cases", "tests"},
    )
    assert (
        "implementer" in res["route"]
    ), "implementer must be in route once tests-ready is live"
    assert "implementer" not in res.get(
        "held", {}
    ), "implementer must not be held once lock released"


# --- TC-I09 ---
def test_real_catalog_trivial_build_implementer_runs():
    """Cheap path (no needs-tests): implementer lock inactive, runs normally, held empty."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"build", "plan-ready"},
        available={"confirmed-intent", "approved-plan"},
    )
    assert (
        "implementer" in res["route"]
    ), "implementer must be in route on cheap path (no needs-tests)"
    assert (
        res.get("held", {}).get("implementer") is None
    ), "implementer must not be in held on cheap path"


# --- TC-I10 ---
def test_real_catalog_coherence_after_migration():
    """check_catalog.check() returns [] on the migrated catalog."""
    assert check_catalog.check(_real_catalog()) == []


# --- TC-I11 ---
def test_real_catalog_route_held_disjoint():
    """route and held sets are disjoint when implementer's lock is active."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"build", "needs-tests", "plan-ready"},
        available={"confirmed-intent", "approved-plan"},
    )
    assert (
        set(res["route"]) & set(res["held"]) == set()
    ), "route and held must be disjoint"


# ---------------------------------------------------------------------------
# REWRITTEN MIGRATION TESTS (cheap-path variants replacing trivial/skip-tests)
# ---------------------------------------------------------------------------


def test_real_catalog_cheap_path_route_minimal():
    """Cheap path (no needs-tests signal): planner fires via intent-confirmed,
    implementer runs immediately, none of the deep review stages or TDD chain appear."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"build", "intent-confirmed"},
        available={"request", "triage-read", "confirmed-intent"},
    )
    assert "planner" in res["route"], "planner must be in cheap-path route"
    assert (
        "skip-tests" not in res["route"]
    ), "skip-tests must not exist in migrated catalog"
    route_set = set(res["route"])
    for stage in _EXCLUSION_SET:
        assert stage not in route_set, f"{stage} must NOT be in cheap-path route"


def test_real_catalog_cheap_path_post_code():
    """Cheap path after code written: correctness-reviewer joins but deep lenses do not
    (they are gated behind needs-tests)."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"build", "intent-confirmed", "code-written"},
        available={
            "request",
            "triage-read",
            "confirmed-intent",
            "approved-plan",
            "diff",
        },
    )
    assert (
        "correctness-reviewer" in res["route"]
    ), "correctness-reviewer must appear post-code on cheap path"
    route_set = set(res["route"])
    for stage in _DEEP_LENSES:
        assert (
            stage not in route_set
        ), f"deep lens {stage} must NOT be in cheap-path post-code route"


def test_real_catalog_cheap_path_multi_file_no_prototype_identifier():
    """LEAK GUARD: multi-file on cheap path must NOT trigger prototype-identifier.
    prototype-identifier subscribes needs-tests only."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"build", "intent-confirmed", "multi-file"},
        available={"request", "triage-read", "confirmed-intent"},
    )
    assert (
        "prototype-identifier" not in res["route"]
    ), "prototype-identifier must not appear on cheap-path multi-file route"
    assert (
        res["triggered_by"].get("prototype-identifier") is None
    ), "prototype-identifier must not be triggered on cheap-path multi-file"
    route_set = set(res["route"])
    for stage in _EXCLUSION_SET:
        assert (
            stage not in route_set
        ), f"{stage} must NOT be in cheap-path multi-file route"


def test_real_catalog_needs_tests_implementer_held_pre_test_chain():
    """Before tests are written, implementer's lock is active - it is in held, not dropped."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"build", "needs-tests", "plan-ready"},
        available={"request", "triage-read", "confirmed-intent", "approved-plan"},
    )
    assert (
        "implementer" not in res["route"]
    ), "implementer must be absent from route before test chain"
    assert (
        "implementer" in res["held"]
    ), "implementer must be in held (not dropped) before test chain"
    assert (
        res["dropped"].get("implementer") != "unsatisfiable-input"
    ), "implementer must NOT be dropped as unsatisfiable-input (it is held)"
    assert "test-plan" in res["route"], "test-plan must be in route when plan-ready"


def test_real_catalog_needs_tests_implementer_after_tests_ready():
    """TDD LOCK (release side): implementer becomes runnable only once `tests-ready` is
    live, which only test-review can publish - so test-review necessarily ran first. The
    ordering is enforced temporally across recomposes (test-review is already_run by the
    time the lock releases), not within one order array."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {
            "build",
            "needs-tests",
            "plan-ready",
            "test-cases-ready",
            "tests-red",
            "tests-ready",
        },
        available={
            "request",
            "triage-read",
            "confirmed-intent",
            "approved-plan",
            "test-cases",
            "tests",
        },
        already_run={
            "triage",
            "reuse-scanner",
            "health-checker",
            "prototype-identifier",
            "requirements-clarifier",
            "planner",
            "plan-challenger",
            "test-plan",
            "test-author",
            "test-review",
        },
    )
    assert (
        "implementer" in res["route"]
    ), "implementer is runnable once tests-ready is live"
    assert (
        "implementer" not in res["held"]
    ), "implementer is no longer held after release"
    assert (
        "test-review" not in res["route"]
    ), "test-review already ran (sole publisher of tests-ready), so it is not re-routed"


def test_real_catalog_needs_tests_stale_tests_ready_artifact_does_not_release_lock():
    """Lock checks LIVE SIGNALS, not available artifacts.

    `tests-ready` in available (stale artifact from a prior run) must NOT release
    the lock. The lock only releases when `tests-ready` appears in live signals.
    """
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"build", "needs-tests", "plan-ready"},  # tests-ready NOT in live
        available={
            "request",
            "triage-read",
            "confirmed-intent",
            "approved-plan",
            "tests-ready",  # stale artifact in available, NOT a live signal
        },
    )
    assert (
        "implementer" not in res["route"]
    ), "implementer must NOT be in route: stale tests-ready artifact does not release lock"
    assert (
        "implementer" in res["held"]
    ), "implementer must be in held: lock checks live, not available"


# --- CLI boundary: malformed request fails loud, legitimate empty stays empty ---
_ROUTE_PY = Path(__file__).resolve().parents[1] / "route.py"


def _run_cli(stdin_text):
    """Drive route.py's _main() the way the orchestrator does: JSON on stdin."""
    return subprocess.run(
        [sys.executable, str(_ROUTE_PY)],
        input=stdin_text,
        capture_output=True,
        text=True,
    )


def test_main_rejects_unknown_key():
    """A typo'd top-level key (`liv` for `live`) fails loudly, not silently as empty."""
    proc = _run_cli('{"liv":["build"]}')
    assert proc.returncode != 0, "unknown request key must fail nonzero"
    assert (
        "liv" in proc.stderr
    ), f"stderr must name the offending key, got {proc.stderr!r}"
    assert (
        "empty" not in proc.stdout
    ), "guard must fire before compute_route - no empty-route output"


def test_main_allows_bare_empty_object():
    """A bare {} (empty-stdin pre-seed) has no keys to reject and returns the empty route."""
    proc = _run_cli("{}")
    assert proc.returncode == 0, f"bare {{}} must succeed, stderr={proc.stderr!r}"
    res = json.loads(proc.stdout)
    assert res["route"] == [], f"bare {{}} must yield empty route, got {res['route']}"
    assert res["size"] == "empty", f"bare {{}} size must be 'empty', got {res['size']}"


def test_main_allows_explicit_empty_trigger_convergence():
    """An explicit {"live":[]} (known key, no triggers) still converges to the empty route."""
    proc = _run_cli('{"live":[]}')
    assert proc.returncode == 0, f'{{"live":[]}} must succeed, stderr={proc.stderr!r}'
    res = json.loads(proc.stdout)
    assert (
        res["route"] == []
    ), f"empty-trigger call must yield empty route, got {res['route']}"
    assert (
        res["size"] == "empty"
    ), f"empty-trigger size must be 'empty', got {res['size']}"


def test_main_rejects_non_dict_toplevel():
    """A top-level JSON list (not an object) fails loudly before compute_route, not with
    an AttributeError - the guard names the type and exits 2."""
    proc = _run_cli("[1,2,3]")
    assert (
        proc.returncode == 2
    ), f"non-dict top-level must exit 2, got {proc.returncode}"
    assert (
        "must be a JSON object" in proc.stderr
    ), f"stderr must explain the request shape, got {proc.stderr!r}"
    assert "list" in proc.stderr, f"stderr must name the type, got {proc.stderr!r}"
    assert (
        "route" not in proc.stdout
    ), "guard must fire before compute_route - no route output"


# ---------------------------------------------------------------------------
# FIX 1: investigator -> planner ordering via the planner's optional `?diagnosis`
# ---------------------------------------------------------------------------


def test_real_catalog_planner_orders_after_investigator_on_bug():
    """On a bug build, the investigator (sub `bug`, produces `diagnosis`) and the planner
    (opt `?diagnosis`) are both in route, and the planner is ordered after the investigator.
    """
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"build", "bug", "intent-confirmed"},
        available={"request", "triage-read", "confirmed-intent"},
    )
    assert (
        "investigator" in res["route"]
    ), "investigator must be in route on a bug build"
    assert "planner" in res["route"], "planner must be in route on a bug build"
    assert res["route"].index("investigator") < res["route"].index(
        "planner"
    ), "planner must be ordered after the investigator (via optional ?diagnosis edge)"


def test_real_catalog_planner_runs_without_diagnosis():
    """No bug signal: the planner runs without the investigator - `?diagnosis` is optional,
    so its absence never drops or blocks the planner."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"build", "intent-confirmed"},
        available={"request", "triage-read", "confirmed-intent"},
    )
    assert "planner" in res["route"], "planner must run without a diagnosis"
    assert (
        "investigator" not in res["route"]
    ), "investigator must be absent when no bug signal is live"


# ---------------------------------------------------------------------------
# FIX 2: UI lenses fire on `ui-touched`, not `needs-tests`; visual-verifier is opt-in only
# ---------------------------------------------------------------------------


def test_real_catalog_ui_lenses_off_non_ui_logic_build():
    """A logic build with code written but no `ui-touched`: the UI lenses stay off; the
    non-UI correctness lens still fires (positive control)."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"build", "needs-tests", "code-written"},
        available={"confirmed-intent", "diff"},
    )
    route_set = set(res["route"])
    for lens in (
        "accessibility-reviewer",
        "design-consistency-reviewer",
        "ux-reviewer",
        "visual-verifier",
    ):
        assert lens not in route_set, f"{lens} must NOT fire without ui-touched"
    assert (
        "correctness-reviewer" in route_set
    ), "correctness-reviewer must still fire (positive control)"


def test_real_catalog_ui_lenses_on_ui_touched():
    """With `ui-touched` live, the three UI review lenses fire; visual-verifier still does
    not (it is gated on `run-visual` alone now)."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"build", "needs-tests", "code-written", "ui-touched"},
        available={"confirmed-intent", "diff"},
    )
    route_set = set(res["route"])
    for lens in (
        "accessibility-reviewer",
        "design-consistency-reviewer",
        "ux-reviewer",
    ):
        assert lens in route_set, f"{lens} must fire when ui-touched is live"
    assert (
        "visual-verifier" not in route_set
    ), "visual-verifier must NOT fire on ui-touched - it is run-visual-gated"


def test_real_catalog_visual_verifier_opt_in_only():
    """visual-verifier fires only on `run-visual`; `ui-touched` alone does not pull it in."""
    cat = _real_catalog()
    opted_in = route.compute_route(
        cat,
        {"build", "run-visual", "code-written"},
        available={"confirmed-intent", "diff"},
    )
    assert (
        "visual-verifier" in opted_in["route"]
    ), "visual-verifier must fire when run-visual is live"
    no_opt = route.compute_route(
        cat,
        {"build", "needs-tests", "ui-touched", "code-written"},
        available={"confirmed-intent", "diff"},
    )
    assert (
        "visual-verifier" not in no_opt["route"]
    ), "visual-verifier must NOT fire without run-visual"


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
