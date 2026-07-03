"""Router tests, written first (TDD).

Encodes the locked route-assembly rules: OR over `subscribes`, AND over required `input`,
optional (`?`) inputs that order-but-never-drop, the `routes` filter against the live path,
topo-sort on precedence, size = stage count, grow/shrink by signal, and sticky-guard
persistence. Runs under pytest and standalone (`python3 hooks/tests/test_route.py`).
"""

import json
import os
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
            ["code", "talk"],
            req=["intent"],
            out=["reuse-map"],
            sub=["code"],
            pub=["missing-infra", "scope-shift"],
        ),
        "impl": S(
            ["code"],
            req=["plan", "tests"],
            out=["diff"],
            sub=["plan-ready"],
            pub=["code-written", "scope-shift"],
        ),
        "sec": S(
            ["code", "sketch"],
            req=["diff"],
            out=["findings"],
            sub=["auth-surface"],
            pub=["findings:security", "scope-shift"],
            guard="sticky",
        ),
        "proto": S(
            ["code"],
            req=["intent"],
            out=["tracer"],
            sub=["missing-infra"],
            pub=["scope-shift"],
        ),
        # optional `reuse-map`: plan runs without it, but orders after scan when scan is present
        "plan": S(
            ["code"],
            req=["intent"],
            opt=["reuse-map"],
            out=["blueprint"],
            sub=["plan-needed"],
            pub=["plan-ready", "scope-shift"],
        ),
        # three single-purpose stages on the same signal to exercise the routes filter
        "codeonly": S(["code"], sub=["ping"], pub=["scope-shift"]),
        "sketchonly": S(["sketch"], sub=["ping"], pub=["scope-shift"]),
        "both": S(["code", "sketch"], sub=["ping"], pub=["scope-shift"]),
    }
}


def r(live, available=(), already_run=()):
    return route.compute_route(CATALOG, set(live), set(available), set(already_run))


def test_or_subscribe_triggers_on_any_signal():
    assert "sec" in r(["auth-surface"], available=["diff"])["route"]
    assert "sec" not in r(["code"], available=["diff"])["route"]


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
    order = r(["code", "plan-needed"], available=["intent"])["route"]
    assert "plan" in order and "scan" in order
    assert order.index("scan") < order.index("plan")


def test_routes_filter_drops_off_path_stage():
    on_code = r(["code", "ping"], available=["intent"])
    assert "codeonly" in on_code["route"] and "both" in on_code["route"]
    assert "sketchonly" not in on_code["route"]
    assert on_code["dropped"].get("sketchonly") == "off-path"
    on_sketch = r(["sketch", "ping"], available=["intent"])
    assert "sketchonly" in on_sketch["route"] and "both" in on_sketch["route"]
    assert "codeonly" not in on_sketch["route"]
    assert on_sketch["dropped"].get("codeonly") == "off-path"


def test_no_path_signal_skips_routes_filter():
    # pre-triage seed: no code/sketch/talk/system live -> nothing is filtered by route
    res = r(["ping"])
    assert {"codeonly", "sketchonly", "both"} <= set(res["route"])


def test_multi_path_stage_survives_on_each_path():
    assert "both" in r(["code", "ping"], available=["intent"])["route"]
    assert "both" in r(["sketch", "ping"], available=["intent"])["route"]


def test_size_is_stage_count():
    assert route.size_label(1) == "XS"
    assert route.size_label(2) == "S"
    assert route.size_label(5) == "M"
    assert r(["code"], available=["intent"])["size"] == "XS"


def test_route_grows_and_shrinks_with_signals():
    base = r(["code"], available=["intent"])
    assert base["route"] == ["scan"]
    grown = r(["code", "missing-infra"], available=["intent"])
    assert set(grown["route"]) == {"scan", "proto"}  # proto joins via missing-infra
    shrunk = r(["code"], available=["intent"])
    assert shrunk["route"] == ["scan"]  # signal gone -> proto drops


def test_sticky_guard_persists_across_recompose():
    prev = r(["code", "auth-surface"], available=["intent", "diff"])
    assert "sec" in prev["route"]
    now = r(["code"], available=["intent", "diff"])  # auth-surface gone
    assert "sec" not in now["route"]  # would drop...
    merged = route.merge_sticky(CATALOG, prev["route"], now)
    assert "sec" in merged["route"]  # ...but sticky keeps it


def test_deterministic_same_input_same_route():
    a = r(["plan-ready", "auth-surface"], available=["plan", "tests"])
    b = r(["plan-ready", "auth-surface"], available=["plan", "tests"])
    assert a == b


# ---------------------------------------------------------------------------
# WAVE SCHEDULING - parallel cohorts from the topo levels (additive `waves` key)
# ---------------------------------------------------------------------------


def test_waves_present_and_flatten_to_route():
    res = r(["plan-ready", "auth-surface"], available=["plan", "tests"])
    assert "waves" in res
    assert [n for w in res["waves"] for n in w] == res["route"]


def test_waves_independent_stages_share_a_wave():
    # scan, codeonly, both all trigger with no inter-dependency -> one parallel cohort
    res = r(["code", "ping"], available=["intent"])
    wave = next(w for w in res["waves"] if "codeonly" in w)
    assert "both" in wave


def test_waves_producer_and_consumer_split_across_waves():
    # impl produces diff; sec consumes it -> impl's wave precedes sec's wave
    res = r(["plan-ready", "auth-surface"], available=["plan", "tests"])
    wi = next(i for i, w in enumerate(res["waves"]) if "impl" in w)
    ws = next(i for i, w in enumerate(res["waves"]) if "sec" in w)
    assert wi < ws


def test_waves_single_stage_is_one_wave():
    assert r(["code"], available=["intent"])["waves"] == [["scan"]]


def test_waves_empty_route_has_empty_waves():
    res = r([])
    assert res["route"] == [] and res["waves"] == []


def _real_catalog():
    return route.load_catalog(
        Path(__file__).resolve().parents[2] / "generated" / "catalog.json"
    )


def test_real_catalog_code_path():
    cat = _real_catalog()
    assert set(cat["stages"]) >= {
        "code-implementer",
        "reuse-scanner",
        "security-reviewer",
        "discuss",
        "sketch-build",
    }
    res = route.compute_route(cat, {"code"}, available={"confirmed-intent"})
    # reuse-scanner now subscribes significant-build, so it does NOT trigger on {code} alone
    assert "reuse-scanner" not in res["route"]
    assert "discuss" not in res["route"]  # talk-only stage stays off the code path
    # health-checker now subscribes significant-build too, so it does NOT trigger on {code} alone
    assert "health-checker" not in res["route"]


def test_real_catalog_routes_filter_on_sketch():
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"sketch", "significant-build", "code-written"},
        available={"confirmed-intent", "diff"},
    )
    assert "sketch-build" in res["route"]
    assert "correctness-reviewer" in res["route"]  # routes include sketch
    assert "quality-reviewer" not in res["route"]  # code-only lens, filtered off sketch
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
                ["code"],
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
        assert s["routes"] == ["code"]
        assert s["data"]["input"]["required"] == ["diff"]
        assert s["data"]["output"] == ["findings"]
        # lenses now subscribe significant-build (was needs-tests, before that code-written)
        assert s["signals"]["subscribes"] == ["significant-build"]
        assert family in s["signals"]["publishes"]
        assert "clean" in s["signals"]["publishes"]
        assert "scope-shift" in s["signals"]["publishes"]


def test_real_catalog_new_lenses_compose_on_code_written():
    # Retargeted: lenses subscribe significant-build (not needs-tests or code-written)
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "significant-build", "code-written"},
        available={"confirmed-intent", "diff"},
    )
    assert "naming-clarity" in res["route"]
    assert "assumptions" in res["route"]
    assert res["triggered_by"]["naming-clarity"] == "significant-build"
    assert res["triggered_by"]["assumptions"] == "significant-build"


def test_real_catalog_new_lenses_need_diff():
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "significant-build", "code-written", "needs-tests"},
        available={"confirmed-intent"},
    )  # no diff - naming-clarity/assumptions require diff so they drop
    assert "naming-clarity" not in res["route"]
    assert "assumptions" not in res["route"]
    # positive control: health-checker subscribes significant-build (post-migration) and
    # has no required inputs, so it appears on {code, significant-build, ...}
    assert "health-checker" in res["route"]


def test_real_catalog_new_lenses_off_sketch():
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"sketch", "significant-build", "code-written"},
        available={"confirmed-intent", "diff"},
    )
    assert res["dropped"].get("naming-clarity") == "off-path"
    assert res["dropped"].get("assumptions") == "off-path"
    assert (
        "sketch-build" in res["route"]
    )  # positive control: sketch route still composes


# ---------------------------------------------------------------------------
# LOCK / HELD UNIT TESTS (TC-U01 - TC-U21)
# ---------------------------------------------------------------------------

# Synthetic catalog for lock tests; `impl` has configurable lock via S() kwarg.


def _lock_catalog(lock=None, extra_stages=None):
    """Return a minimal catalog with a lockable `impl` stage and optional extras."""
    stages = {
        "impl": S(
            ["code"],
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
                ["code"],
                req=["plan"],
                out=["diff"],
                sub=["plan-ready"],
                pub=["code-written", "scope-shift"],
                lock=[{"while": "needs-tests", "until": "tests-ready"}],
            ),
            "reviewer": S(
                ["code"],
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
        "routes": ["code"],
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
        "routes": ["code"],
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
                ["code"],
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


# --- TC-U18b ---
def test_check_catalog_flags_lock_until_no_publisher():
    """check() reports a problem when lock.until names an unpublished, non-seed signal."""
    phantom_catalog = {
        "stages": {
            "impl": S(
                ["code"],
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
                ["code"],
                req=[],
                out=["diff"],
                sub=["request-received"],
                pub=["scope-shift"],
                lock=[{"while": "needs-tests", "until": "tests-ready"}],
            ),
            "test-author": S(
                ["code"],
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
    s = S(["code"], sub=["go"], pub=["scope-shift"])
    assert "lock" not in s, "S() must not add 'lock' key when lock kwarg is absent"


# --- TC-U21 ---
def test_S_factory_lock_present():
    """S() with lock kwarg stores the value under 'lock'."""
    lock_val = [{"while": "needs-tests", "until": "tests-ready"}]
    s = S(["code"], sub=["go"], pub=["scope-shift"], lock=lock_val)
    assert "lock" in s, "S() must add 'lock' key when lock kwarg is provided"
    assert (
        s["lock"] == lock_val
    ), f"s['lock'] must equal the provided value, got {s.get('lock')}"


# ---------------------------------------------------------------------------
# RETAINED NON-TRIVIAL SYNTHETIC TESTS (unchanged from before)
# ---------------------------------------------------------------------------


def test_real_catalog_needs_tests_reuse_scanner_absent():
    """D-07: reuse-scanner moved to significant-build - NOT triggered by needs-tests alone."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "needs-tests"},
        available={"request", "triage-read", "confirmed-intent"},
    )
    assert (
        "reuse-scanner" not in res["route"]
    ), "reuse-scanner must NOT appear on needs-tests alone (now subscribes significant-build)"


def test_real_catalog_significant_build_reuse_scanner_positive():
    """D-07 positive control: reuse-scanner triggers on significant-build."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "significant-build"},
        available={"confirmed-intent"},
    )
    assert (
        "reuse-scanner" in res["route"]
    ), "reuse-scanner must appear when significant-build is live"


def test_real_catalog_needs_tests_reuse_scanner_dropped_without_confirmed_intent():
    """D-07 companion: without confirmed-intent, reuse-scanner's required input absent.

    The reason field changes: previously unsatisfiable-input (when on needs-tests);
    now reuse-scanner is not triggered at all on needs-tests, so it is off-trigger
    (not in route and not in dropped as unsatisfiable-input on this signal set).
    """
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "needs-tests"},
        available={"request", "triage-read"},  # NO confirmed-intent
    )
    assert (
        "reuse-scanner" not in res["route"]
    ), "reuse-scanner must be absent without significant-build"
    # With significant-build absent, reuse-scanner is not triggered at all - not dropped as
    # unsatisfiable-input either, it simply is not a candidate.
    assert (
        res["dropped"].get("reuse-scanner") != "unsatisfiable-input"
        or "reuse-scanner" not in res["dropped"]
    ), "reuse-scanner is not triggered on needs-tests so must not appear as unsatisfiable-input"


def test_optional_producer_in_route_creates_ordering_edge_without_artifact():
    """GAP 2 regression (SYNTHETIC): optional input creates ordering edge even without artifact.
    Two stages: alpha (triggered, produces alpha-out), beta (opt=alpha-out, triggered).
    Both in route; alpha ordered before beta even though alpha-out is absent from available.
    """
    cat = {
        "stages": {
            "alpha": S(
                ["code"],
                out=["alpha-out"],
                sub=["go"],
                pub=["scope-shift"],
            ),
            "beta": S(
                ["code"],
                req=[],
                opt=["alpha-out"],
                out=["beta-out"],
                sub=["go"],
                pub=["scope-shift"],
            ),
        }
    }
    res = route.compute_route(cat, {"code", "go"}, available=set())
    assert "alpha" in res["route"], "alpha must be in route"
    assert "beta" in res["route"], "beta must be in route"
    assert res["route"].index("alpha") < res["route"].index(
        "beta"
    ), "alpha must precede beta via optional ordering edge even without alpha-out in available"


# ---------------------------------------------------------------------------
# INTEGRATION TESTS - REAL CATALOG (TC-I01 - TC-I11, RED until catalog regen)
# ---------------------------------------------------------------------------

# EXCLUSION SET: all stages that must NOT appear in cheap-path route (no needs-tests, no significant-build)
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
    "capture-agent",
    "reuse-scanner",
    "health-checker",
    "requirements-clarifier",
    "prototype-identifier",
    "plan-challenger",
    "test-plan",
    # TC-P09/TC-P10: prototypers subscribe significant-build indirectly (via prototype-identifier),
    # so they must not appear on the cheap path (no significant-build signal).
    "code-prototyper",
    "data-prototyper",
    "performance-prototyper",
    "design-prototyper",
    "ux-prototyper",
}

# The 15 deep lenses (exclusion set minus the non-lens stages). All stay absent on a cheap
# path: none of their triggering signals are live there. The UI lenses are now ui-touched-
# gated, so they need an even stronger signal than the needs-tests lenses to appear.
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
}


# --- TC-I01 / TC-P01 ---
def test_real_catalog_has_50_stages_no_skip_tests():
    """Catalog has 50 stages and skip-tests is absent."""
    cat = _real_catalog()
    stages = cat["stages"]
    assert len(stages) == 50, f"expected 50 stages, got {len(stages)}"
    assert "skip-tests" not in stages, "skip-tests must NOT exist in migrated catalog"


# ---------------------------------------------------------------------------
# PROTOTYPER SPLIT TESTS (TC-P02 - TC-P19, RED until agents authored + catalog regen)
# ---------------------------------------------------------------------------


# --- TC-P16 ---
def test_real_catalog_prototyper_renamed_to_code_prototyper():
    """After the split, 'prototyper' is gone and 'code-prototyper' is present."""
    stages = _real_catalog()["stages"]
    assert "prototyper" not in stages, "'prototyper' must NOT exist after rename"
    assert "code-prototyper" in stages, "'code-prototyper' must exist after rename"


# --- TC-P17 ---
def test_real_catalog_design_explorer_renamed_to_design_prototyper():
    """After the split, 'design-explorer' is gone and 'design-prototyper' is present."""
    stages = _real_catalog()["stages"]
    assert (
        "design-explorer" not in stages
    ), "'design-explorer' must NOT exist after rename"
    assert "design-prototyper" in stages, "'design-prototyper' must exist after rename"


# --- TC-P11 ---
def test_real_catalog_prototypers_do_not_subscribe_significant_build():
    """None of the 5 prototypers subscribe 'significant-build' directly.

    They are downstream of prototype-identifier (which subscribes significant-build);
    direct subscription would make them appear on every significant-build route without
    the identifier gate.
    """
    stages = _real_catalog()["stages"]
    prototypers = (
        "code-prototyper",
        "data-prototyper",
        "performance-prototyper",
        "design-prototyper",
        "ux-prototyper",
    )
    for name in prototypers:
        s = stages[name]
        subs = s["signals"]["subscribes"]
        assert (
            "significant-build" not in subs
        ), f"{name} must NOT subscribe significant-build, got {subs}"


# --- TC-P12 ---
def test_real_catalog_prototype_identifier_subscribes_significant_build_not_needs_tests():
    """prototype-identifier subscribes 'significant-build' and does NOT subscribe
    'needs-tests' - the rename must not have changed this stage's signals."""
    stages = _real_catalog()["stages"]
    assert (
        "prototype-identifier" in stages
    ), "prototype-identifier must remain in catalog"
    s = stages["prototype-identifier"]
    subs = s["signals"]["subscribes"]
    assert (
        "significant-build" in subs
    ), f"prototype-identifier must subscribe significant-build, got {subs}"
    assert (
        "needs-tests" not in subs
    ), f"prototype-identifier must NOT subscribe needs-tests, got {subs}"


# --- TC-P13 ---
def test_real_catalog_prototypers_not_in_deep_lenses():
    """None of the 5 new/renamed prototypers appear in the deep-lenses set.

    Deep lenses subscribe significant-build and require 'diff' as input and produce
    'findings:*'. Prototypers operate before implementation and must not be confused
    with post-code review lenses.
    """
    stages = _real_catalog()["stages"]
    prototypers = {
        "code-prototyper",
        "data-prototyper",
        "performance-prototyper",
        "design-prototyper",
        "ux-prototyper",
    }
    for name in prototypers:
        assert (
            name not in _DEEP_LENSES
        ), f"{name} must NOT be in _DEEP_LENSES (not a post-code review lens)"
        if name in stages:
            s = stages[name]
            # Prototypers must not subscribe significant-build (TC-P11 already covers this,
            # but an explicit check here keeps failure locality tight for this lens assertion)
            assert (
                "significant-build" not in s["signals"]["subscribes"]
            ), f"{name} subscribes significant-build - would be a deep lens candidate"


# --- TC-P14 ---
def test_real_catalog_check_catalog_clean_after_prototyper_split():
    """check_catalog.check() returns [] after the prototyper split is regenerated.

    Sub-invariants enforced by check_catalog:
    - domain:integration, domain:data, domain:performance each have a publisher + subscriber
    - user-flow-needed has a publisher + subscriber
    - ux-flow-locked is published but unsubscribed (like design-locked)
    - every new/renamed prototyper has routes subset of {code,sketch,talk,system},
      publishes scope-shift, and has a non-empty input_template
    """
    assert (
        check_catalog.check(_real_catalog()) == []
    ), "check_catalog.check() must return [] after prototyper split regen"


# --- TC-P02 ---
def test_real_catalog_code_prototyper_triggered_by_domain_integration():
    """live {code, domain:integration} with prototype-identification available ->
    code-prototyper is in route."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "domain:integration"},
        available={"prototype-identification"},
    )
    assert (
        "code-prototyper" in res["route"]
    ), "code-prototyper must be in route on {code, domain:integration}"


# --- TC-P03 ---
def test_real_catalog_data_prototyper_triggered_by_domain_data():
    """live {code, domain:data} with prototype-identification available ->
    data-prototyper is in route."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "domain:data"},
        available={"prototype-identification"},
    )
    assert (
        "data-prototyper" in res["route"]
    ), "data-prototyper must be in route on {code, domain:data}"


# --- TC-P04 ---
def test_real_catalog_performance_prototyper_triggered_by_domain_performance():
    """live {code, domain:performance} with prototype-identification available ->
    performance-prototyper is in route."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "domain:performance"},
        available={"prototype-identification"},
    )
    assert (
        "performance-prototyper" in res["route"]
    ), "performance-prototyper must be in route on {code, domain:performance}"


# --- TC-P06 ---
def test_real_catalog_ux_prototyper_triggered_by_user_flow_needed():
    """live {code, user-flow-needed} with clarified-intent available ->
    ux-prototyper is in route."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "user-flow-needed"},
        available={"clarified-intent"},
    )
    assert (
        "ux-prototyper" in res["route"]
    ), "ux-prototyper must be in route on {code, user-flow-needed}"


# --- TC-P07 ---
def test_real_catalog_design_and_ux_prototypers_same_wave():
    """live {code, design-needed, user-flow-needed} with clarified-intent available ->
    both design-prototyper and ux-prototyper are in route AND in the same wave."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "design-needed", "user-flow-needed"},
        available={"clarified-intent"},
    )
    assert (
        "design-prototyper" in res["route"]
    ), "design-prototyper must be in route on {code, design-needed, user-flow-needed}"
    assert (
        "ux-prototyper" in res["route"]
    ), "ux-prototyper must be in route on {code, design-needed, user-flow-needed}"
    design_wave = next(
        i for i, w in enumerate(res["waves"]) if "design-prototyper" in w
    )
    ux_wave = next(i for i, w in enumerate(res["waves"]) if "ux-prototyper" in w)
    assert design_wave == ux_wave, (
        f"design-prototyper (wave {design_wave}) and ux-prototyper (wave {ux_wave}) "
        "must be in the same wave (no dependency between them)"
    )


# --- TC-P08 ---
def test_real_catalog_three_domain_prototypers_coexist():
    """live {code, domain:integration, domain:data, domain:performance} with
    prototype-identification available -> all three domain prototypers are present
    and toposort completes without error."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "domain:integration", "domain:data", "domain:performance"},
        available={"prototype-identification"},
    )
    for name in ("code-prototyper", "data-prototyper", "performance-prototyper"):
        assert (
            name in res["route"]
        ), f"{name} must be in route when its domain signal is live"


# --- TC-P18 ---
def test_real_catalog_ux_prototyper_absent_on_design_needed_only():
    """live {code, design-needed} (no user-flow-needed) with clarified-intent available ->
    ux-prototyper is NOT in route (subscription specificity)."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "design-needed"},
        available={"clarified-intent"},
    )
    assert (
        "ux-prototyper" not in res["route"]
    ), "ux-prototyper must NOT be in route when only design-needed is live (not user-flow-needed)"


# --- TC-P19 ---
def test_real_catalog_design_prototyper_absent_on_user_flow_needed_only():
    """live {code, user-flow-needed} (no design-needed) with clarified-intent available ->
    design-prototyper is NOT in route (subscription specificity)."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "user-flow-needed"},
        available={"clarified-intent"},
    )
    assert (
        "design-prototyper" not in res["route"]
    ), "design-prototyper must NOT be in route when only user-flow-needed is live (not design-needed)"


# --- TC-P20 ---
def test_real_catalog_requirements_clarifier_publishes_user_flow_needed():
    """requirements-clarifier publishes user-flow-needed (publish-side coverage)."""
    stages = _real_catalog()["stages"]
    assert (
        "user-flow-needed" in stages["requirements-clarifier"]["signals"]["publishes"]
    ), "requirements-clarifier must publish user-flow-needed"


# --- TC-P21 ---
def test_real_catalog_code_planner_optional_ux_spec():
    """code-planner accepts ux-spec as an optional input (merge-path catalog contract)."""
    stages = _real_catalog()["stages"]
    assert (
        "ux-spec" in stages["code-planner"]["data"]["input"]["optional"]
    ), "code-planner must list ux-spec in optional inputs"


# --- TC-P22 ---
def test_real_catalog_ux_prototyper_orders_before_code_planner():
    """ux-prototyper precedes code-planner when user-flow-needed + ux-flow-locked
    are live (ux-prototyper produces ux-spec, code-planner optionally consumes it)."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "user-flow-needed", "ux-flow-locked", "intent-confirmed", "clarified"},
        available={"confirmed-intent", "clarified-intent", "ux-spec"},
    )
    assert "ux-prototyper" in res["route"], "ux-prototyper must be in route"
    assert "code-planner" in res["route"], "code-planner must be in route"
    assert res["route"].index("ux-prototyper") < res["route"].index(
        "code-planner"
    ), "ux-prototyper must be ordered before code-planner (via optional ux-spec edge)"


# --- TC-I02 / D-01 ---
def test_real_catalog_implementer_contract():
    """implementer: required input == ['approved-plan'] only; lock has 2 entries (TDD + plan-gate)."""
    stages = _real_catalog()["stages"]
    s = stages["code-implementer"]
    assert s["data"]["input"]["required"] == [
        "approved-plan"
    ], f"implementer required must be ['approved-plan'], got {s['data']['input']['required']}"
    assert (
        "green-light" not in s["data"]["input"]["required"]
    ), "green-light must NOT be in implementer required input"
    assert "lock" in s, "implementer must have a 'lock' field"
    lock = s["lock"]
    assert len(lock) == 2, f"implementer lock must have exactly 2 entries, got {lock}"
    whiles = {e["while"] for e in lock}
    untils = {e["until"] for e in lock}
    assert "needs-tests" in whiles, "lock must contain while:needs-tests"
    assert "plan-ready" in whiles, "lock must contain while:plan-ready"
    assert "tests-ready" in untils, "lock must contain until:tests-ready"
    assert "plan-approved" in untils, "lock must contain until:plan-approved"


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
    """triage: publishes intent-confirmed, needs-tests, and significant-build; does not publish trivial."""
    stages = _real_catalog()["stages"]
    pubs = stages["triage"]["signals"]["publishes"]
    assert "intent-confirmed" in pubs, "triage must publish intent-confirmed"
    assert "needs-tests" in pubs, "triage must publish needs-tests"
    assert "significant-build" in pubs, "triage must publish significant-build"
    assert "trivial" not in pubs, "triage must NOT publish trivial after migration"


# --- TC-I05 ---
def test_real_catalog_planner_subscribes_intent_confirmed_not_trivial():
    """planner: subscribes has 'clarified' + 'intent-confirmed'; does not subscribe trivial."""
    stages = _real_catalog()["stages"]
    s = stages["code-planner"]
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


# --- TC-I06a ---
def test_real_catalog_correctness_publishes_significant_build():
    """correctness-reviewer publishes significant-build (late cheap-path escalation pulls the
    deep lenses). Both needs-tests and significant-build must be in its publishes list.

    RED until correctness-reviewer's agent file is updated to publish significant-build.
    """
    stages = _real_catalog()["stages"]
    s = stages["correctness-reviewer"]
    assert (
        "significant-build" in s["signals"]["publishes"]
    ), "correctness-reviewer must publish significant-build (late escalation for deep lenses)"
    assert (
        "needs-tests" in s["signals"]["publishes"]
    ), "correctness-reviewer must still publish needs-tests alongside significant-build"


# --- TC-I06b ---
def test_real_catalog_plan_challenger_publishes_plan_approved():
    """plan-challenger publishes plan-approved (the plan-gate lock's until signal).

    plan-approved must have at least one publisher in the catalog; plan-challenger is
    the designated publisher. The router suite cannot prove the orchestrator calls it
    at the right moment - that is integration-level. This test anchors the catalog
    contract: plan-challenger's publishes list contains plan-approved.
    """
    stages = _real_catalog()["stages"]
    s = stages["plan-challenger"]
    assert (
        "plan-approved" in s["signals"]["publishes"]
    ), "plan-challenger must publish plan-approved (plan-gate lock until signal)"


# --- TC-I07 ---
def test_real_catalog_implementer_held_before_tests_ready():
    """TDD LOCK: before tests-ready, implementer is in held (lock active), not route."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "needs-tests", "plan-ready"},
        available={"confirmed-intent", "approved-plan"},
    )
    assert (
        "code-implementer" not in res["route"]
    ), "implementer must be absent from route before tests-ready"
    assert (
        "code-implementer" in res["held"]
    ), "implementer must be in held (lock active) before tests-ready"


# --- TC-I08 ---
def test_real_catalog_implementer_in_route_after_tests_ready():
    """TDD LOCK and plan-gate both released: with tests-ready and plan-approved live,
    implementer is in route, not held."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {
            "code",
            "needs-tests",
            "plan-ready",
            "plan-approved",
            "test-cases-ready",
            "tests-red",
            "tests-ready",
        },
        available={"confirmed-intent", "approved-plan", "test-cases", "tests"},
    )
    assert (
        "code-implementer" in res["route"]
    ), "implementer must be in route once tests-ready and plan-approved are live"
    assert "code-implementer" not in res.get(
        "held", {}
    ), "implementer must not be held once both locks released"


# --- TC-I09 / D-02 ---
def test_real_catalog_trivial_code_implementer_runs():
    """Cheap path with plan-ready but no plan-approved: plan-gate holds the implementer."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "plan-ready"},
        available={"confirmed-intent", "approved-plan"},
    )
    assert (
        "code-implementer" not in res["route"]
    ), "implementer must be held on cheap path when plan-approved is absent"
    assert "code-implementer" in res.get(
        "held", {}
    ), "implementer must be in held waiting for plan-approved"
    assert (
        "plan-approved" in res["held"]["code-implementer"]
    ), "held payload must list plan-approved as unmet until"


def test_real_catalog_trivial_code_implementer_runs_with_plan_approved():
    """Cheap path with plan-approved: plan-gate releases, implementer runs."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "plan-ready", "plan-approved"},
        available={"confirmed-intent", "approved-plan"},
    )
    assert (
        "code-implementer" in res["route"]
    ), "implementer must be in route once plan-approved is live on cheap path"
    assert (
        res.get("held", {}).get("code-implementer") is None
    ), "implementer must not be in held once plan-approved is live"


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
        {"code", "needs-tests", "plan-ready"},
        available={"confirmed-intent", "approved-plan"},
    )
    assert (
        set(res["route"]) & set(res["held"]) == set()
    ), "route and held must be disjoint"


# --- TC-I12 ---
def test_real_catalog_15_movers_subscribe_significant_build():
    """The 15 stages that moved from needs-tests to significant-build each subscribe
    significant-build and do NOT subscribe needs-tests.

    3 TDD chain stages (test-plan, test-gap, test-verifier) stay on needs-tests - they
    are explicitly excluded from the mover set.
    """
    _MOVERS = {
        "acceptance-reviewer",
        "architecture-reviewer",
        "assumptions",
        "capture-agent",
        "consistency-reviewer",
        "health-checker",
        "naming-clarity",
        "performance-reviewer",
        "plan-adherence-reviewer",
        "plan-challenger",
        "prototype-identifier",
        "quality-reviewer",
        "reuse-reviewer",
        "reuse-scanner",
        "structure-reviewer",
    }
    _TDD_CHAIN = {"test-plan", "test-gap", "test-verifier"}
    stages = _real_catalog()["stages"]
    for name in _MOVERS:
        s = stages[name]
        subs = s["signals"]["subscribes"]
        assert (
            "significant-build" in subs
        ), f"{name} must subscribe significant-build (15-mover), got {subs}"
        assert (
            "needs-tests" not in subs
        ), f"{name} must NOT subscribe needs-tests after migration, got {subs}"
    for name in _TDD_CHAIN:
        s = stages[name]
        subs = s["signals"]["subscribes"]
        assert (
            "needs-tests" in subs
        ), f"{name} is TDD chain and must still subscribe needs-tests, got {subs}"
        assert (
            "significant-build" not in subs
        ), f"{name} is TDD chain and must NOT subscribe significant-build, got {subs}"


# --- TC-I13 ---
def test_real_catalog_significant_build_scout_stages():
    """significant-build pulls in Scout pre-impl stages (reuse-scanner, health-checker,
    prototype-identifier) on {code, significant-build}."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "significant-build"},
        available={"confirmed-intent"},
    )
    for stage in ("reuse-scanner", "health-checker", "prototype-identifier"):
        assert (
            stage in res["route"]
        ), f"{stage} must be in route when significant-build is live"


# --- TC-I14 ---
def test_real_catalog_significant_build_deep_lenses_on_code_written():
    """significant-build pulls in deep review lenses when code-written is also live.

    Stages that subscribe significant-build and require diff compose once diff is available.
    """
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "significant-build", "code-written"},
        available={"confirmed-intent", "diff"},
    )
    for stage in (
        "naming-clarity",
        "assumptions",
        "architecture-reviewer",
        "quality-reviewer",
    ):
        assert (
            stage in res["route"]
        ), f"{stage} must be in route on significant-build + code-written with diff"
    assert (
        "simplicity-reviewer" in res["route"]
    ), "simplicity-reviewer must be in route when significant-build is live (always-on via #code-written)"


# --- TC-I15: re-numbered to avoid clash with the original TC-I11 block above ---
def test_real_catalog_needs_tests_pulls_only_tdd_chain():
    """needs-tests (without significant-build) pulls ONLY the TDD chain stages.

    test-plan, test-gap, test-verifier are in route; the 15 movers are NOT triggered
    by needs-tests alone.
    """
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "needs-tests", "plan-ready"},
        available={"confirmed-intent", "approved-plan"},
    )
    route_set = set(res["route"])
    for stage in ("test-plan",):
        assert (
            stage in route_set
        ), f"{stage} must be in route when needs-tests is live (TDD chain)"
    _MOVERS = {
        "acceptance-reviewer",
        "architecture-reviewer",
        "assumptions",
        "capture-agent",
        "consistency-reviewer",
        "health-checker",
        "naming-clarity",
        "performance-reviewer",
        "plan-adherence-reviewer",
        "plan-challenger",
        "prototype-identifier",
        "quality-reviewer",
        "reuse-reviewer",
        "reuse-scanner",
        "structure-reviewer",
    }
    for stage in _MOVERS:
        assert (
            stage not in route_set
        ), f"{stage} must NOT be in route on needs-tests alone (subscribes significant-build)"


# ---------------------------------------------------------------------------
# REWRITTEN MIGRATION TESTS (cheap-path variants replacing trivial/skip-tests)
# ---------------------------------------------------------------------------


def test_real_catalog_cheap_path_route_minimal():
    """Cheap path (no needs-tests signal): planner fires via intent-confirmed,
    none of the deep review stages or TDD chain appear. Implementer is held by
    the plan-gate lock until plan-approved is published."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "intent-confirmed"},
        available={"request", "triage-read", "confirmed-intent"},
    )
    assert "code-planner" in res["route"], "planner must be in cheap-path route"
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
        {"code", "intent-confirmed", "code-written"},
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
    assert (
        "simplicity-reviewer" in res["route"]
    ), "simplicity-reviewer must appear post-code on cheap path"
    route_set = set(res["route"])
    for stage in _DEEP_LENSES:
        assert (
            stage not in route_set
        ), f"deep lens {stage} must NOT be in cheap-path post-code route"


def test_real_catalog_cheap_path_multi_file_no_prototype_identifier():
    """LEAK GUARD: multi-file on cheap path must NOT trigger prototype-identifier.
    prototype-identifier subscribes significant-build, which is absent on the cheap path.
    """
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "intent-confirmed", "multi-file"},
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
    """Before tests are written, implementer is held by both TDD lock AND plan-gate lock."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "needs-tests", "plan-ready"},
        available={"request", "triage-read", "confirmed-intent", "approved-plan"},
    )
    assert (
        "code-implementer" not in res["route"]
    ), "implementer must be absent from route before test chain"
    assert (
        "code-implementer" in res["held"]
    ), "implementer must be in held (not dropped) before test chain"
    assert (
        res["dropped"].get("code-implementer") != "unsatisfiable-input"
    ), "implementer must NOT be dropped as unsatisfiable-input (it is held)"
    unmet = res["held"]["code-implementer"]
    assert "tests-ready" in unmet, "held must list tests-ready as unmet (TDD lock)"
    assert (
        "plan-approved" in unmet
    ), "held must list plan-approved as unmet (plan-gate lock)"
    assert "test-plan" in res["route"], "test-plan must be in route when plan-ready"


def test_real_catalog_needs_tests_implementer_after_tests_ready():
    """D-04: tests-ready live but plan-approved absent - plan-gate still holds implementer."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {
            "code",
            "needs-tests",
            "plan-ready",
            "test-cases-ready",
            "tests-red",
            "tests-ready",
            # plan-approved intentionally absent
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
            "code-planner",
            "plan-challenger",
            "test-plan",
            "test-author",
            "test-review",
        },
    )
    assert (
        "code-implementer" not in res["route"]
    ), "implementer must still be held: plan-approved absent even though tests-ready is live"
    assert (
        "code-implementer" in res["held"]
    ), "implementer must be in held waiting for plan-approved"
    assert (
        "plan-approved" in res["held"]["code-implementer"]
    ), "held payload must list plan-approved as unmet until"


def test_real_catalog_needs_tests_implementer_runs_with_both_released():
    """D-04 sibling: both tests-ready AND plan-approved live - implementer runs."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {
            "code",
            "needs-tests",
            "plan-ready",
            "test-cases-ready",
            "tests-red",
            "tests-ready",
            "plan-approved",
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
            "code-planner",
            "plan-challenger",
            "test-plan",
            "test-author",
            "test-review",
        },
    )
    assert (
        "code-implementer" in res["route"]
    ), "implementer is runnable once both tests-ready and plan-approved are live"
    assert "code-implementer" not in res.get(
        "held", {}
    ), "implementer is no longer held after both locks release"
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
        {"code", "needs-tests", "plan-ready"},  # tests-ready NOT in live
        available={
            "request",
            "triage-read",
            "confirmed-intent",
            "approved-plan",
            "tests-ready",  # stale artifact in available, NOT a live signal
        },
    )
    assert (
        "code-implementer" not in res["route"]
    ), "implementer must NOT be in route: stale tests-ready artifact does not release lock"
    assert (
        "code-implementer" in res["held"]
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
    proc = _run_cli('{"liv":["code"]}')
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
    """Explicit empty lists for all known keys (not nulls) still converge to the
    empty route (TC-ROUTE-05 regression control: unaffected by null coercion)."""
    proc = _run_cli('{"live": [], "available": [], "already_run": []}')
    assert (
        proc.returncode == 0
    ), f"empty-list request must succeed, stderr={proc.stderr!r}"
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
# CLI boundary: null-tolerance for live/available/already_run (plan step 8)
# ---------------------------------------------------------------------------


def test_main_tolerates_all_null_request_keys():
    """TC-ROUTE-01: an explicit JSON null for each of live/available/already_run
    coerces to empty (same as an absent key), not a TypeError. Pre-fix, `req.get(
    "live", [])` returns None (not the [] default) when the key is present with a
    JSON null value, so `set(None)` inside compute_route raises - this is the bug
    this fix closes (TC-ROUTE-02's pre-fix baseline)."""
    proc = _run_cli('{"live": null, "available": null, "already_run": null}')
    assert proc.returncode == 0, (
        f"all-null request must succeed, not raise TypeError; "
        f"stderr={proc.stderr!r}"
    )
    res = json.loads(proc.stdout)
    assert (
        res["route"] == []
    ), f"all-null request must yield empty route, got {res['route']}"
    assert (
        res["size"] == "empty"
    ), f"all-null request size must be 'empty', got {res['size']}"


def test_main_tolerates_mixed_null_and_populated_keys():
    """TC-ROUTE-03: a null `live`/`already_run` coerces to empty while a populated
    `available` list is respected as-is - only the null keys coerce."""
    proc = _run_cli('{"live": null, "available": ["some-stage"], "already_run": []}')
    assert (
        proc.returncode == 0
    ), f"mixed null/non-null request must succeed, stderr={proc.stderr!r}"
    res = json.loads(proc.stdout)
    assert (
        res["route"] == []
    ), f"no live signals must yield empty route, got {res['route']}"
    assert (
        res["size"] == "empty"
    ), f"mixed null/non-null request size must be 'empty', got {res['size']}"


def test_main_absent_keys_match_explicit_null_output():
    """TC-ROUTE-04: omitting live/available/already_run entirely yields the same
    empty-route output as sending explicit JSON nulls - missing key and explicit
    null must behave identically."""
    proc_absent = _run_cli("{}")
    proc_null = _run_cli('{"live": null, "available": null, "already_run": null}')
    assert proc_absent.returncode == 0 and proc_null.returncode == 0, (
        f"both absent-key and explicit-null requests must succeed; "
        f"absent stderr={proc_absent.stderr!r} null stderr={proc_null.stderr!r}"
    )
    assert json.loads(proc_absent.stdout) == json.loads(proc_null.stdout), (
        "an absent key and an explicit JSON null for the same key must produce "
        "identical route output"
    )


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
        {"code", "bug", "intent-confirmed"},
        available={"request", "triage-read", "confirmed-intent"},
    )
    assert (
        "code-investigator" in res["route"]
    ), "investigator must be in route on a bug build"
    assert "code-planner" in res["route"], "planner must be in route on a bug build"
    assert res["route"].index("code-investigator") < res["route"].index(
        "code-planner"
    ), "planner must be ordered after the investigator (via optional ?diagnosis edge)"


def test_real_catalog_planner_runs_without_diagnosis():
    """No bug signal: the planner runs without the investigator - `?diagnosis` is optional,
    so its absence never drops or blocks the planner."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "intent-confirmed"},
        available={"request", "triage-read", "confirmed-intent"},
    )
    assert "code-planner" in res["route"], "planner must run without a diagnosis"
    assert (
        "code-investigator" not in res["route"]
    ), "investigator must be absent when no bug signal is live"


# ---------------------------------------------------------------------------
# FIX 2: UI lenses fire on `ui-touched`, not `needs-tests`
# ---------------------------------------------------------------------------


def test_real_catalog_ui_lenses_off_non_ui_logic_code():
    """A logic build with code written but no `ui-touched`: the UI lenses stay off; the
    non-UI correctness lens still fires (positive control)."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "needs-tests", "code-written"},
        available={"confirmed-intent", "diff"},
    )
    route_set = set(res["route"])
    for lens in (
        "accessibility-reviewer",
        "design-consistency-reviewer",
        "ux-reviewer",
    ):
        assert lens not in route_set, f"{lens} must NOT fire without ui-touched"
    assert (
        "correctness-reviewer" in route_set
    ), "correctness-reviewer must still fire (positive control)"


def test_real_catalog_ui_lenses_on_ui_touched():
    """With `ui-touched` live, the three UI review lenses fire."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "needs-tests", "code-written", "ui-touched"},
        available={"confirmed-intent", "diff"},
    )
    route_set = set(res["route"])
    for lens in (
        "accessibility-reviewer",
        "design-consistency-reviewer",
        "ux-reviewer",
    ):
        assert lens in route_set, f"{lens} must fire when ui-touched is live"


# ---------------------------------------------------------------------------
# VISUAL-VERIFIER REMOVAL (TC-CAT-1, TC-SIG-2, TC-ROUTE-3, TC-UI-3)
# ---------------------------------------------------------------------------


# --- TC-CAT-1 ---
def test_visual_verifier_absent_from_catalog():
    """visual-verifier must not appear in the catalog stages after removal."""
    stages = _real_catalog()["stages"]
    assert (
        "visual-verifier" not in stages
    ), "visual-verifier must be absent from catalog after removal"


# --- TC-SIG-2 ---
def test_run_visual_absent_from_seed_signals():
    """run-visual must not appear in check_catalog.SEED_SIGNALS after removal."""
    assert (
        "run-visual" not in check_catalog.SEED_SIGNALS
    ), "run-visual must be removed from SEED_SIGNALS alongside visual-verifier"


# --- TC-ROUTE-3 ---
def test_visual_verifier_absent_from_route_even_with_run_visual_and_ui_touched():
    """Even with run-visual AND ui-touched live, visual-verifier must not appear in the route."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "run-visual", "code-written", "ui-touched"},
        available={"confirmed-intent", "diff"},
    )
    assert (
        "visual-verifier" not in res["route"]
    ), "visual-verifier must be absent from route after removal (run-visual + ui-touched live)"


# --- TC-UI-3 (publisher continuity - GREEN, must stay green) ---
def test_ux_reviewer_still_publishes_findings_ux():
    """ux-reviewer still publishes findings:ux after visual-verifier is removed.

    Green now and must stay green - ux-reviewer is the keeper of this signal.
    """
    stages = _real_catalog()["stages"]
    assert any(
        "findings:ux" in s["signals"]["publishes"] for s in stages.values()
    ), "at least one stage must still publish findings:ux (ux-reviewer continuity)"


# ---------------------------------------------------------------------------
# SYSTEM PATH - path, safety gate, and bug disambiguation by path
#
# NOTE: plan-approved on the system path is orchestrator-sourced (published by
# plan-challenger, which the orchestrator runs before system-executor). The router
# suite cannot prove self-release - it can only verify that plan-approved in live
# signals releases the lock. The orchestrator is responsible for ensuring plan-challenger
# publishes plan-approved before system-executor is dispatched.
# ---------------------------------------------------------------------------


def test_real_catalog_system_path_composes():
    """On the system path, the system-planner composes and the code-planner is off-path."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"system", "intent-confirmed"},
        available={"request", "triage-read", "confirmed-intent"},
    )
    assert (
        "system-planner" in res["route"]
    ), "system-planner must compose on the system path"
    assert "code-planner" not in res["route"], "code-planner is off the system path"
    assert res["dropped"].get("code-planner") == "off-path"


def test_real_catalog_ambiguous_system_pulls_interviewer():
    """An ambiguous system request must reach the interviewer, not stall on an empty route."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"system", "ambiguous"},
        available={"request", "triage-read"},
        already_run={"triage"},
    )
    assert "interviewer" in res["route"], (
        "interviewer must compose for an ambiguous system request - "
        "without it the route is empty and the run stalls"
    )


def test_real_catalog_system_executor_held_on_destructive_op():
    """A destructive-op arms the safety gate and holds the system-executor by its lock."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"system", "plan-ready", "destructive-op"},
        available={"confirmed-intent", "system-plan"},
    )
    assert "system-executor" not in res["route"], "executor must be held, not routed"
    assert (
        "system-executor" in res["held"]
    ), "executor must be in held under the safety lock"
    assert "safety-gate" in res["route"], "safety-gate must be armed by destructive-op"


def test_real_catalog_system_executor_runs_after_safety_approved():
    """D-06: safety-approved present but plan-approved absent - plan-gate still holds executor."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"system", "plan-ready", "destructive-op", "safety-approved"},
        available={"confirmed-intent", "system-plan"},
    )
    assert (
        "system-executor" not in res["route"]
    ), "executor must still be held: plan-approved absent even though safety-approved is live"
    assert "system-executor" in res.get(
        "held", {}
    ), "executor must be in held waiting for plan-approved"
    assert (
        "plan-approved" in res["held"]["system-executor"]
    ), "held payload must list plan-approved as unmet until"


def test_real_catalog_system_executor_runs_after_safety_and_plan_approved():
    """D-06 sibling: both safety-approved AND plan-approved live - executor runs."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"system", "plan-ready", "destructive-op", "safety-approved", "plan-approved"},
        available={"confirmed-intent", "system-plan"},
    )
    assert (
        "system-executor" in res["route"]
    ), "executor runs once both safety-approved and plan-approved are live"
    assert "system-executor" not in res.get(
        "held", {}
    ), "executor no longer held after both locks release"


def test_real_catalog_bug_routes_to_matching_investigator():
    """`#bug` is shared; `routes` sends it to the path's own investigator, not the other's."""
    cat = _real_catalog()
    sys_res = route.compute_route(
        cat,
        {"system", "bug", "intent-confirmed"},
        available={"request", "triage-read", "confirmed-intent"},
    )
    assert "system-investigator" in sys_res["route"]
    assert "code-investigator" not in sys_res["route"]
    code_res = route.compute_route(
        cat,
        {"code", "bug", "intent-confirmed"},
        available={"request", "triage-read", "confirmed-intent"},
    )
    assert "code-investigator" in code_res["route"]
    assert "system-investigator" not in code_res["route"]


def test_real_catalog_system_executor_runs_clean_when_no_destructive_op():
    """D-05: plan-ready without plan-approved now holds system-executor via plan-gate lock."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"system", "plan-ready"},
        available={"confirmed-intent", "system-plan"},
    )
    assert (
        "system-executor" not in res["route"]
    ), "executor must be held when plan-approved is absent (plan-gate lock)"
    assert "system-executor" in res.get(
        "held", {}
    ), "executor must be in held waiting for plan-approved"
    assert (
        "plan-approved" in res["held"]["system-executor"]
    ), "held payload must list plan-approved as unmet until"


def test_real_catalog_system_executor_runs_with_plan_approved_no_destructive_op():
    """D-05 sibling: plan-approved present, no destructive-op - executor runs."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"system", "plan-ready", "plan-approved"},
        available={"confirmed-intent", "system-plan"},
    )
    assert (
        "system-executor" in res["route"]
    ), "executor runs when plan-approved is live and no destructive-op is present"
    assert (
        res.get("held", {}).get("system-executor") is None
    ), "no lock held when plan-approved present and no destructive-op"


# ---------------------------------------------------------------------------
# RC3: extract_input_template, catalog.input_template, check_catalog invariant
# ---------------------------------------------------------------------------
# Load gen-catalog at module level so the module imports (collection is never
# broken), but reference extract_input_template INSIDE each test body so that
# AttributeError on missing function fails only the relevant test.

import importlib.util as _ilu

_GEN_CATALOG_PATH = Path(__file__).resolve().parents[1] / "gen-catalog.py"
_gen_catalog_spec = _ilu.spec_from_file_location("gen_catalog", _GEN_CATALOG_PATH)
_gen_catalog = _ilu.module_from_spec(_gen_catalog_spec)
_gen_catalog_spec.loader.exec_module(_gen_catalog)


# --- RC3-A01 ---
def test_extract_input_template_happy_path():
    """extract_input_template returns the inner fence text for a well-formed ## Input section."""
    fn = lambda text: _gen_catalog._extract_fenced_block(text, "## Input")
    text = "## Input\n\n```\n<FOO>bar</FOO>\n```\n"
    assert (
        fn(text) == "<FOO>bar</FOO>\n"
    ), f"expected inner fence text, got {fn(text)!r}"


# --- RC3-A02 ---
def test_extract_input_template_no_heading():
    """extract_input_template returns '' when no ## Input section exists."""
    fn = lambda text: _gen_catalog._extract_fenced_block(text, "## Input")
    text = "## Output\n\n```\nfoo\n```\n"
    assert fn(text) == "", f"expected empty string, got {fn(text)!r}"


# --- RC3-A03 ---
def test_extract_input_template_heading_no_fence():
    """extract_input_template returns '' when ## Input has no fence before the next ## heading."""
    fn = lambda text: _gen_catalog._extract_fenced_block(text, "## Input")
    text = "## Input\n\nSome prose without a fence.\n\n## Output\n\n```\nfoo\n```\n"
    assert (
        fn(text) == ""
    ), f"expected empty string (no fence under ## Input), got {fn(text)!r}"


# --- RC3-A04 ---
def test_extract_input_template_stops_at_next_heading():
    """The fence under a later ## Output section is NOT captured when ## Input has no fence."""
    fn = lambda text: _gen_catalog._extract_fenced_block(text, "## Input")
    # ## Input has no fence; ## Output has one - must not bleed through
    text = "## Input\n\nNo fence here.\n\n## Output\n\n```\ncaptured-wrongly\n```\n"
    result = fn(text)
    assert "captured-wrongly" not in result, (
        "fence under ## Output must not bleed into ## Input extraction, "
        f"got {result!r}"
    )
    assert result == "", f"expected '', got {result!r}"


# --- RC3-A05 ---
def test_extract_input_template_empty_fence():
    """extract_input_template returns '' for an empty fence (open immediately closed)."""
    fn = lambda text: _gen_catalog._extract_fenced_block(text, "## Input")
    text = "## Input\n\n```\n```\n"
    assert fn(text) == "", f"expected empty string for empty fence, got {fn(text)!r}"


# --- RC3-A06 ---
def test_extract_input_template_two_headings_first_wins():
    """Two ## Input headings - only the first match's block is returned."""
    fn = lambda text: _gen_catalog._extract_fenced_block(text, "## Input")
    text = (
        "## Input\n\n```\nfirst-block\n```\n\n" "## Input\n\n```\nsecond-block\n```\n"
    )
    result = fn(text)
    assert result == "first-block\n", f"expected first block only, got {result!r}"
    assert "second-block" not in result, "second ## Input block must not appear"


# ---------------------------------------------------------------------------
# RC3-B: catalog assertions against the real catalog
# ---------------------------------------------------------------------------


# --- RC3-B01 ---
def test_real_catalog_every_stage_has_input_template():
    """Every stage entry in the regenerated catalog has an 'input_template' key of type str."""
    cat = _real_catalog()
    for name, stage in cat["stages"].items():
        assert "input_template" in stage, f"{name}: missing 'input_template' field"
        assert isinstance(
            stage["input_template"], str
        ), f"{name}: input_template must be str, got {type(stage['input_template'])}"


# --- RC3-B02 ---
def test_real_catalog_triage_input_template_empty():
    """triage has no ## Input section - its input_template must be ''."""
    cat = _real_catalog()
    triage = cat["stages"]["triage"]
    assert (
        triage["input_template"] == ""
    ), f"triage input_template must be '', got {triage['input_template']!r}"


# --- RC3-B03 ---
def test_real_catalog_test_chain_templates_nonempty():
    """test-gap, test-plan, and test-review each have a non-empty input_template
    after their ## Input sections are authored."""
    cat = _real_catalog()
    for name, expected_tag in (
        ("test-gap", "<DIFF>"),
        ("test-plan", "<APPROVED_PLAN>"),
        ("test-review", "<TESTS>"),
    ):
        tmpl = cat["stages"][name]["input_template"]
        assert tmpl, f"{name}: input_template must be non-empty after RC3"
        assert (
            expected_tag in tmpl
        ), f"{name}: input_template must contain {expected_tag}, got {tmpl!r}"


# --- RC3-B04 ---
def test_real_catalog_adr_drafter_template_nonempty_with_tag():
    """adr-drafter's ## Inputs heading renamed to ## Input; template is non-empty
    and contains <DECISION_TITLE>."""
    cat = _real_catalog()
    tmpl = cat["stages"]["adr-drafter"]["input_template"]
    assert (
        tmpl
    ), "adr-drafter: input_template must be non-empty after RC3 heading rename"
    assert (
        "<DECISION_TITLE>" in tmpl
    ), f"adr-drafter: input_template must contain <DECISION_TITLE>, got {tmpl!r}"


# ---------------------------------------------------------------------------
# RC3-C: check_catalog template-presence invariant
# ---------------------------------------------------------------------------


# --- RC3-C01 ---
def test_check_catalog_flags_consuming_stage_without_template():
    """A stage with non-empty required input and empty input_template must be flagged.

    Uses req=["request"] so `request` is a SEED_ARTIFACT - the existing producer check
    stays silent and only the (not-yet-existing) template-presence invariant should fire.
    """
    bad_stage = S(
        ["code"],
        req=["request"],
        out=["test-cases"],
        sub=["request-received"],
        pub=["scope-shift"],
    )
    bad_stage["input_template"] = ""  # consuming stage - no template
    synthetic = {"stages": {"bad-consumer": bad_stage}}
    problems = check_catalog.check(synthetic)
    tmpl_problems = [
        p
        for p in problems
        if "bad-consumer" in p and ("input_template" in p or "template" in p.lower())
    ]
    assert tmpl_problems, (
        f"check() must flag bad-consumer with a template-specific problem, "
        f"problems={problems}"
    )


# --- RC3-C02 ---
def test_check_catalog_exempt_triage_passes_without_template():
    """A stage named 'triage' (in TEMPLATE_EXEMPT) with required input and empty template
    must NOT be flagged by the template-presence invariant."""
    triage_stage = S(
        ["code", "talk", "sketch", "system"],
        req=["request"],
        out=["triage-read"],
        sub=["request-received"],
        pub=["scope-shift"],
    )
    triage_stage["input_template"] = ""
    synthetic = {"stages": {"triage": triage_stage}}
    problems = check_catalog.check(synthetic)
    # The only problem allowed is the orphan-subscribe check (request-received is a seed,
    # so none) or produces-check; NOT a template-presence problem.
    template_problems = [
        p for p in problems if "input_template" in p or "template" in p.lower()
    ]
    assert (
        not template_problems
    ), f"triage must be exempt from template-presence invariant, got {template_problems}"


# --- RC3-C03 ---
def test_real_catalog_coherence_after_rc3():
    """check_catalog.check(_real_catalog()) == [] after templates are authored and catalog
    regenerated, AND stable consuming stages carry non-empty input_template
    (regression - red until RC3 is complete)."""
    cat = _real_catalog()
    assert check_catalog.check(cat) == []
    # Coupled to the RC3 deliverable: consuming stages must have non-empty input_template.
    # KeyError-red today (field absent); green only after field is populated and catalog
    # regenerated.
    for stage_name in ("code-planner", "test-review", "correctness-reviewer"):
        assert cat["stages"][stage_name][
            "input_template"
        ].strip(), f"{stage_name}: input_template must be non-empty after RC3"


# ---------------------------------------------------------------------------
# RC3-D: idempotency and no-drift
# ---------------------------------------------------------------------------


# --- RC3-D01 ---
def test_build_catalog_idempotent():
    """build_catalog() called twice yields byte-identical JSON (sort_keys=True)."""
    first = json.dumps(_gen_catalog.build_catalog(), sort_keys=True)
    second = json.dumps(_gen_catalog.build_catalog(), sort_keys=True)
    assert first == second, "build_catalog() must be idempotent"


# --- RC3-D02 ---
def test_catalog_no_drift_from_committed():
    """The in-memory build_catalog() output matches the committed generated/catalog.json
    byte-for-byte (no uncommitted drift)."""
    committed_path = Path(__file__).resolve().parents[2] / "generated" / "catalog.json"
    committed = json.loads(committed_path.read_text(encoding="utf-8"))
    live = _gen_catalog.build_catalog()
    assert json.dumps(live, sort_keys=True) == json.dumps(
        committed, sort_keys=True
    ), "build_catalog() output differs from committed catalog.json - regenerate"


# ---------------------------------------------------------------------------
# RC3-E: router tolerance - no input_template key required by compute_route
# ---------------------------------------------------------------------------


# --- RC3-E01 ---
def test_router_tolerates_missing_input_template():
    """A synthetic stage with NO input_template key still routes correctly.
    compute_route never reads input_template."""
    stage_no_tmpl = S(
        ["code"],
        req=["plan"],
        out=["diff"],
        sub=["plan-ready"],
        pub=["code-written", "scope-shift"],
    )
    # Confirm S() does not add input_template by default
    assert (
        "input_template" not in stage_no_tmpl
    ), "S() must not add input_template - this confirms the router never requires it"
    cat = {"stages": {"impl": stage_no_tmpl}}
    res = route.compute_route(
        cat, {"plan-ready"}, available={"plan"}, already_run=set()
    )
    assert (
        "impl" in res["route"]
    ), "stage without input_template must still route normally"


# ---------------------------------------------------------------------------
# COVERAGE-GAP TESTS (GAP 1 - GAP 4): plan-approval gate edge cases
# ---------------------------------------------------------------------------


# --- GAP 1 ---
def test_real_catalog_system_executor_held_both_locks_simultaneously():
    """Both safety-gate lock AND plan-gate lock are active at the same time.

    live: {system, plan-ready, destructive-op} - neither safety-approved nor plan-approved
    present. system-executor must be in held and the held payload must list BOTH
    unmet until signals (safety-approved AND plan-approved).

    Existing tests cover each lock individually; none asserts both unmet untils
    together on the real catalog.
    """
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"system", "plan-ready", "destructive-op"},
        available={"confirmed-intent", "system-plan"},
    )
    assert "system-executor" not in res["route"], "executor must not be in route"
    assert "system-executor" in res["held"], "executor must be in held"
    unmet = res["held"]["system-executor"]
    assert (
        "safety-approved" in unmet
    ), f"held payload must list safety-approved as unmet until, got {unmet}"
    assert (
        "plan-approved" in unmet
    ), f"held payload must list plan-approved as unmet until, got {unmet}"


# --- GAP 2 ---
def test_real_catalog_stale_plan_approved_artifact_does_not_release_plan_gate():
    """Lock checks LIVE SIGNALS, not available artifacts - for the plan-gate.

    plan-approved present as a stale AVAILABLE artifact (NOT in live) must NOT
    release the plan-gate lock on code-implementer. Mirrors the existing
    test_real_catalog_needs_tests_stale_tests_ready_artifact_does_not_release_lock
    for the TDD lock, but exercises the plan-gate lock instead.
    """
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "plan-ready"},  # plan-approved NOT in live
        available={
            "confirmed-intent",
            "approved-plan",
            "plan-approved",  # stale artifact in available, NOT a live signal
        },
    )
    assert (
        "code-implementer" not in res["route"]
    ), "implementer must NOT be in route: stale plan-approved artifact does not release lock"
    assert (
        "code-implementer" in res["held"]
    ), "implementer must be in held: lock checks live signals, not available artifacts"
    assert (
        "plan-approved" in res["held"]["code-implementer"]
    ), "held payload must list plan-approved as unmet until"


# --- GAP 3 ---
def test_real_catalog_significant_build_without_needs_tests_excludes_tdd_lenses():
    """significant-build WITHOUT needs-tests: deep review lenses ARE in route, but
    test-gap and test-verifier are NOT.

    This proves the Fix-4 property: a large no-tests change gets full review WITHOUT
    test-gap/test-verifier nagging for TDD coverage.
    """
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "significant-build", "code-written"},  # NO needs-tests
        available={"confirmed-intent", "diff"},
    )
    route_set = set(res["route"])
    # Deep lenses triggered by significant-build must be present (positive control)
    for deep_lens in ("quality-reviewer", "architecture-reviewer", "naming-clarity"):
        assert (
            deep_lens in route_set
        ), f"{deep_lens} must be in route on significant-build + code-written"
    # TDD-chain lenses must NOT appear without needs-tests
    assert (
        "test-gap" not in route_set
    ), "test-gap must NOT be in route without needs-tests"
    assert (
        "test-verifier" not in route_set
    ), "test-verifier must NOT be in route without needs-tests"


# --- GAP 4 ---
def test_real_catalog_family_prefix_plan_approved_releases_plan_gate_code_implementer():
    """Family-prefix plan-approved variant releases the plan-gate on the REAL catalog.

    live: {code, plan-ready, plan-approved:auto} - a qualified variant of plan-approved
    satisfies the until=plan-approved lock entry on code-implementer.
    Existing family-prefix coverage is on the synthetic _lock_catalog only; this
    anchors the same property against the real code-implementer lock.
    """
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "plan-ready", "plan-approved:auto"},
        available={"confirmed-intent", "approved-plan"},
    )
    assert (
        "code-implementer" in res["route"]
    ), "implementer must be in route: plan-approved:auto satisfies until=plan-approved"
    assert (
        res.get("held", {}).get("code-implementer") is None
    ), "implementer must not be held once plan-approved:auto releases the plan-gate"


# ---------------------------------------------------------------------------
# TC-SR: SIMPLICITY-REVIEWER (always-on post-code reviewer)
# RED until: agent authored, catalog regenerated, injector wired
# ---------------------------------------------------------------------------


# --- TC-SR-01 ---
def test_simplicity_reviewer_catalog_contract():
    """simplicity-reviewer catalog entry: routes==['code'], input.required==['diff'],
    output==['findings'], subscribes==['code-written'] (not significant-build),
    publishes contains findings:simplicity, clean, scope-shift.

    RED until agent authored + catalog regenerated.
    """
    cat = _real_catalog()
    s = cat["stages"]["simplicity-reviewer"]  # KeyError until catalog regen
    assert s["routes"] == [
        "code"
    ], f"simplicity-reviewer routes must be ['code'], got {s['routes']}"
    assert s["data"]["input"]["required"] == [
        "diff"
    ], f"simplicity-reviewer required input must be ['diff'], got {s['data']['input']['required']}"
    assert s["data"]["output"] == [
        "findings"
    ], f"simplicity-reviewer output must be ['findings'], got {s['data']['output']}"
    subs = s["signals"]["subscribes"]
    assert (
        "code-written" in subs
    ), f"simplicity-reviewer must subscribe code-written, got {subs}"
    assert (
        "significant-build" not in subs
    ), f"simplicity-reviewer must NOT subscribe significant-build (always-on), got {subs}"
    pubs = s["signals"]["publishes"]
    assert (
        "findings:simplicity" in pubs
    ), f"simplicity-reviewer must publish findings:simplicity, got {pubs}"
    assert "clean" in pubs, f"simplicity-reviewer must publish clean, got {pubs}"
    assert (
        "scope-shift" in pubs
    ), f"simplicity-reviewer must publish scope-shift, got {pubs}"


# --- TC-SR-02 ---
def test_simplicity_reviewer_always_on():
    """simplicity-reviewer is in route when live contains {code, intent-confirmed, code-written}
    and diff is available. triggered_by == 'code-written'. correctness-reviewer also in route
    (positive control - both always-on post-code reviewers).

    RED until catalog regenerated.
    """
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "intent-confirmed", "code-written"},
        available={
            "request",
            "triage-read",
            "confirmed-intent",
            "approved-plan",
            "diff",
        },
    )
    assert "simplicity-reviewer" in res["route"], (
        "simplicity-reviewer must be in route on {code, intent-confirmed, code-written} "
        f"with diff available; route={res['route']}"
    )
    assert res["triggered_by"].get("simplicity-reviewer") == "code-written", (
        "simplicity-reviewer must be triggered by code-written, "
        f"got triggered_by={res['triggered_by'].get('simplicity-reviewer')!r}"
    )
    assert (
        "correctness-reviewer" in res["route"]
    ), "correctness-reviewer must also be in route (positive control - both always-on)"


# --- TC-SR-03 ---
def test_simplicity_reviewer_absent_pre_code():
    """simplicity-reviewer is NOT in route when code-written is absent from live signals.

    Pre-code signal set: {code, intent-confirmed}. The stage must not trigger.
    After regen this is a post-regen invariant: the stage exists but must still be absent
    pre-code because it subscribes code-written.

    RED until catalog regenerated (currently KeyError - stage absent; post-regen stays RED
    only if the assertion fails, which it must not once wired correctly).
    """
    cat = _real_catalog()
    # Verify the stage exists first (otherwise the test is vacuously true today)
    assert (
        "simplicity-reviewer" in cat["stages"]
    ), "simplicity-reviewer must exist in catalog (RED: agent not yet authored)"
    res = route.compute_route(
        cat,
        {"code", "intent-confirmed"},
        available={"request", "triage-read", "confirmed-intent"},
    )
    assert (
        "simplicity-reviewer" not in res["route"]
    ), "simplicity-reviewer must NOT be in route when code-written is absent"


# --- TC-SR-04 ---
def test_simplicity_reviewer_unsatisfiable_without_diff():
    """simplicity-reviewer is dropped as unsatisfiable-input when diff is not available,
    even though code-written is live.

    RED until catalog regenerated.
    """
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "intent-confirmed", "code-written"},
        available={"request", "triage-read", "confirmed-intent"},
        # diff intentionally absent
    )
    assert res["dropped"].get("simplicity-reviewer") == "unsatisfiable-input", (
        "simplicity-reviewer must be dropped as unsatisfiable-input when diff is absent; "
        f"dropped={res['dropped'].get('simplicity-reviewer')!r}"
    )


# --- TC-SR-05 ---
def test_simplicity_reviewer_off_sketch():
    """simplicity-reviewer routes==['code'] so it is dropped as off-path on a sketch build.
    correctness-reviewer (which routes include sketch) is in route as a positive control.

    RED until catalog regenerated.
    """
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"sketch", "code-written"},
        available={"confirmed-intent", "diff"},
    )
    assert res["dropped"].get("simplicity-reviewer") == "off-path", (
        "simplicity-reviewer must be dropped as off-path on sketch; "
        f"dropped={res['dropped'].get('simplicity-reviewer')!r}"
    )
    assert (
        "correctness-reviewer" in res["route"]
    ), "correctness-reviewer must be in route on sketch (positive control)"


# --- TC-SR-06 ---
def test_simplicity_reviewer_not_in_exclusion_or_deep_lenses():
    """simplicity-reviewer must NOT appear in _EXCLUSION_SET or _DEEP_LENSES.

    It is an always-on post-code reviewer (like correctness-reviewer), so it must be
    absent from both gating sets. GREEN now - guards against future re-gating.
    """
    assert (
        "simplicity-reviewer" not in _EXCLUSION_SET
    ), "simplicity-reviewer must NOT be in _EXCLUSION_SET (it is always-on, not deep-lens-gated)"
    assert (
        "simplicity-reviewer" not in _DEEP_LENSES
    ), "simplicity-reviewer must NOT be in _DEEP_LENSES (it subscribes code-written, not significant-build)"


def _parse_doctrine_map_reviewers(text: str) -> set:
    """Return DOCTRINE_MAP keys whose value contains 'reviewer-contract', comment lines excluded."""
    import re

    result: set[str] = set()
    in_doctrine_map = False
    for line in text.splitlines():
        stripped = line.strip()
        if "declare -A DOCTRINE_MAP" in stripped:
            in_doctrine_map = True
            continue
        if in_doctrine_map:
            if stripped == ")":
                in_doctrine_map = False
                continue
            if stripped.startswith("#"):
                continue
            # match: [agent-name]="...reviewer-contract..."
            m = re.match(r'\[([^\]]+)\]="([^"]*)"', stripped)
            if m and "reviewer-contract" in m.group(2):
                result.add(m.group(1))
    return result


def _parse_case_arm_agents(text: str) -> set:
    """Return the |-split case-arm tokens from the case "$subagent_type" block, comment lines excluded."""
    result: set[str] = set()
    in_case = False
    for line in text.splitlines():
        stripped = line.strip()
        if 'case "$subagent_type"' in stripped:
            in_case = True
            continue
        if in_case:
            if stripped == "esac":
                in_case = False
                continue
            if stripped.startswith("#"):
                continue
            if stripped.endswith(")"):
                arm_body = stripped[:-1]  # strip trailing )
                for token in arm_body.split("|"):
                    token = token.strip()
                    if token and not token.startswith("*"):
                        result.add(token)
    return result


# The fixed expected set of known reviewer-contract agents.
# A mis-parsed DOCTRINE_MAP line will shrink the parsed set below this floor and fail loudly.
_EXPECTED_REVIEWER_CONTRACT_AGENTS = {
    "correctness-reviewer",
    "quality-reviewer",
    "simplicity-reviewer",
    "architecture-reviewer",
    "structure-reviewer",
    "consistency-reviewer",
    "reuse-reviewer",
    "security-reviewer",
    "performance-reviewer",
    "acceptance-reviewer",
    "naming-clarity",
    "assumptions",
}


# --- TC-SR-07 ---
def test_every_reviewer_contract_agent_is_wired():
    """Every agent in DOCTRINE_MAP whose value contains 'reviewer-contract' must appear
    as a case arm in user-context-injector.sh.

    Checks that simplicity-reviewer is also wired in the case statement. Excludes
    commented lines. plan-adherence-reviewer and test-gap are communication-only
    (no reviewer-contract) and must not false-fail.
    """
    injector_path = (
        Path(__file__).resolve().parents[2] / "hooks" / "user-context-injector.sh"
    )
    text = injector_path.read_text(encoding="utf-8")

    reviewer_contract_agents = _parse_doctrine_map_reviewers(text)
    case_arm_agents = _parse_case_arm_agents(text)

    # Hard floor: parsed set must be a superset of the known agents.
    # A single mis-parsed DOCTRINE_MAP line shrinks the set and fails loudly here.
    missing_expected = _EXPECTED_REVIEWER_CONTRACT_AGENTS - reviewer_contract_agents
    assert not missing_expected, (
        f"DOCTRINE_MAP parse returned fewer reviewer-contract agents than expected. "
        f"Missing from parsed set: {sorted(missing_expected)}. "
        "Check that the injector file was read correctly and DOCTRINE_MAP contains all known agents."
    )

    assert (
        case_arm_agents
    ), "case arms must be non-empty; check that the injector file was read correctly"

    # Assert that every reviewer-contract-keyed agent is a subset of case arm agents
    missing = reviewer_contract_agents - case_arm_agents
    assert not missing, (
        f"Agents in DOCTRINE_MAP with reviewer-contract but missing from case arms: {sorted(missing)}. "
        "Wire them into the case statement in user-context-injector.sh."
    )


_INJECTOR_PY = Path(__file__).resolve().parents[1] / "user-context-injector.sh"


def _run_injector(subagent_type, cwd):
    """Drive user-context-injector.sh the way Claude Code does: an Agent PreToolUse
    payload on stdin. Returns the additionalContext string (empty on silent exit)."""
    payload = json.dumps(
        {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": subagent_type},
            "cwd": cwd,
        }
    )
    proc = subprocess.run(
        ["bash", str(_INJECTOR_PY)],
        input=payload,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "CLAUDE_PLUGIN_ROOT": str(_INJECTOR_PY.resolve().parents[1]),
        },
    )
    assert proc.returncode == 0, f"injector must exit 0, stderr={proc.stderr!r}"
    if not proc.stdout.strip():
        return ""
    out = json.loads(proc.stdout)
    return out.get("hookSpecificOutput", {}).get("additionalContext", "") or out.get(
        "additionalContext", ""
    )


def test_injected_psychology_block_carries_anchor_and_vocalize_directive():
    """The psychology block for a persona-wired agent ships both the persona's verbatim
    Anchor line and the generic directive telling the agent to vocalize it. security-reviewer
    maps to the defender persona."""
    ctx = _run_injector("security-reviewer", str(Path.cwd()))
    assert (
        "Harden the seams. Find the abuse case first." in ctx
    ), "defender's verbatim Anchor line must ship in the psychology block"
    assert (
        "restate your Anchor above in your own voice" in ctx
    ), "the vocalize directive must ship once in the psychology block"


# ---------------------------------------------------------------------------
# RC4: _extract_fenced_block (## Output (strict)), catalog.output_template, check_catalog canary
# ---------------------------------------------------------------------------
# These exercise _gen_catalog._extract_fenced_block bound to the "## Output (strict)"
# heading - the shared fenced-block extractor that lands SIGNALS_PUBLISHED in output_template.


# --- RC4-A01 ---
def test_extract_output_template_happy_path():
    """extract_output_template returns inner fence text for a well-formed ## Output (strict) section."""
    fn = lambda text: _gen_catalog._extract_fenced_block(text, "## Output (strict)")
    text = "## Output (strict)\n\n```\nSIGNALS_PUBLISHED: #clean\n```\n"
    result = fn(text)
    assert (
        result == "SIGNALS_PUBLISHED: #clean\n"
    ), f"expected inner fence text, got {result!r}"


# --- RC4-A02 ---
def test_extract_output_template_no_heading():
    """extract_output_template returns '' when no ## Output (strict) section exists."""
    fn = lambda text: _gen_catalog._extract_fenced_block(text, "## Output (strict)")
    text = "## Input\n\n```\n<FOO>bar</FOO>\n```\n"
    assert fn(text) == "", f"expected empty string, got {fn(text)!r}"


# --- RC4-A03 ---
def test_extract_output_template_heading_no_fence():
    """extract_output_template returns '' when ## Output (strict) has no fence before the next ## heading."""
    fn = lambda text: _gen_catalog._extract_fenced_block(text, "## Output (strict)")
    text = "## Output (strict)\n\nSome prose, no fence.\n\n## Next Section\n\n```\nfoo\n```\n"
    assert (
        fn(text) == ""
    ), f"expected empty string (no fence under ## Output (strict)), got {fn(text)!r}"


# --- RC4-A04 ---
def test_extract_output_template_stops_at_next_heading():
    """A fence under a later section does NOT bleed into the return value."""
    fn = lambda text: _gen_catalog._extract_fenced_block(text, "## Output (strict)")
    text = "## Output (strict)\n\nNo fence here.\n\n## Later\n\n```\ncaptured-wrongly\n```\n"
    result = fn(text)
    assert "captured-wrongly" not in result, (
        "fence under a later ## heading must not bleed into ## Output (strict) extraction, "
        f"got {result!r}"
    )
    assert result == "", f"expected '', got {result!r}"


# --- RC4-A05 ---
def test_extract_output_template_empty_fence():
    """extract_output_template returns '' for an empty fence (open immediately closed)."""
    fn = lambda text: _gen_catalog._extract_fenced_block(text, "## Output (strict)")
    text = "## Output (strict)\n\n```\n```\n"
    assert fn(text) == "", f"expected empty string for empty fence, got {fn(text)!r}"


# --- RC4-A06 ---
def test_extract_output_template_two_headings_first_wins():
    """Two ## Output (strict) headings: only the first match's fence is returned."""
    fn = lambda text: _gen_catalog._extract_fenced_block(text, "## Output (strict)")
    text = (
        "## Output (strict)\n\n```\nfirst-block\n```\n\n"
        "## Output (strict)\n\n```\nsecond-block\n```\n"
    )
    result = fn(text)
    assert result == "first-block\n", f"expected first block only, got {result!r}"
    assert (
        "second-block" not in result
    ), "second ## Output (strict) block must not appear"


# --- RC4-A07 ---
def test_extract_output_template_exact_opener_guard():
    """The opener matches the EXACT string '## Output (strict)', not startswith.

    A file whose only Output-ish heading is '## Output discipline' (prose, no fence,
    as in simplicity-reviewer) must yield ''. Same for bare '## Output' (discuss-style).
    """
    fn = lambda text: _gen_catalog._extract_fenced_block(text, "## Output (strict)")

    # simplicity-reviewer pattern: ## Output discipline - prose heading, no fence
    discipline_text = (
        "## Output discipline\n\nName the replacement, show the shorter form.\n\n"
        "## Floor\n\nDo not flag the floor.\n"
    )
    result_discipline = fn(discipline_text)
    assert result_discipline == "", (
        "'## Output discipline' must not match the exact '## Output (strict)' opener; "
        f"got {result_discipline!r}"
    )

    # discuss-style: bare ## Output
    bare_text = "## Output\n\n```\nsome content\n```\n"
    result_bare = fn(bare_text)
    assert result_bare == "", (
        "'## Output' bare must not match '## Output (strict)'; " f"got {result_bare!r}"
    )


# ---------------------------------------------------------------------------
# RC4-B: catalog output_template field - real catalog assertions
# ---------------------------------------------------------------------------


# --- RC4-B01 ---
def test_real_catalog_every_stage_has_output_template():
    """Every stage entry in the regenerated catalog has an 'output_template' key of type str."""
    cat = _real_catalog()
    for name, stage in cat["stages"].items():
        assert "output_template" in stage, f"{name}: missing 'output_template' field"
        assert isinstance(
            stage["output_template"], str
        ), f"{name}: output_template must be str, got {type(stage['output_template'])}"


# --- RC4-B02 ---
def test_real_catalog_reviewer_stages_have_nonempty_output_template():
    """The five core reviewer stages have non-empty output_template after RC4."""
    cat = _real_catalog()
    reviewer_stages = (
        "correctness-reviewer",
        "security-reviewer",
        "acceptance-reviewer",
        "reuse-reviewer",
        "plan-adherence-reviewer",
    )
    for name in reviewer_stages:
        tmpl = cat["stages"][name]["output_template"]
        assert tmpl.strip(), f"{name}: output_template must be non-empty after RC4"


# --- RC4-B03 ---
def test_real_catalog_reviewer_output_template_contains_signals_published():
    """Every reviewer's output_template contains the substring 'SIGNALS_PUBLISHED:'."""
    cat = _real_catalog()
    reviewer_stages = (
        "correctness-reviewer",
        "security-reviewer",
        "acceptance-reviewer",
        "reuse-reviewer",
        "plan-adherence-reviewer",
    )
    for name in reviewer_stages:
        tmpl = cat["stages"][name]["output_template"]
        assert (
            "SIGNALS_PUBLISHED:" in tmpl
        ), f"{name}: output_template must contain 'SIGNALS_PUBLISHED:', got {tmpl!r}"


# --- RC4-B04 ---
def test_real_catalog_triage_output_template_empty():
    """triage has no ## Output (strict) section - its output_template must be ''."""
    cat = _real_catalog()
    triage = cat["stages"]["triage"]
    assert (
        triage.get("output_template", "") == ""
    ), f"triage output_template must be '', got {triage.get('output_template', '')!r}"


# ---------------------------------------------------------------------------
# RC4-C: check_catalog reviewer-signal canary (SIGNALS_PUBLISHED line)
# ---------------------------------------------------------------------------

# Helper: a reviewer-shaped stage for check_catalog canary tests.
_REVIEWER_ROUTES = ["code", "sketch"]
_REVIEWER_SUBS = ["code-written"]
_REVIEWER_PUB_CLEAN = ["clean", "findings:correctness", "scope-shift"]
_REVIEWER_PUB_FINDINGS = ["findings:correctness", "scope-shift"]


def _reviewer_stage(pub=None, output_template=""):
    """Build a synthetic reviewer stage (publishes 'findings:*' family, scope-shift)."""
    if pub is None:
        pub = list(_REVIEWER_PUB_CLEAN)
    s = S(
        _REVIEWER_ROUTES,
        req=["diff"],
        out=["findings"],
        sub=_REVIEWER_SUBS,
        pub=pub,
    )
    s["input_template"] = "<TOUCHED_FILES>stub</TOUCHED_FILES>\n"
    s["output_template"] = output_template
    return s


# --- RC4-C01 ---
def test_check_catalog_flags_reviewer_without_signals_published_in_output_template():
    """A synthetic reviewer with pub=['clean','scope-shift'] and output_template=''
    is flagged with a problem naming the stage and output_template/SIGNALS_PUBLISHED."""
    stage = _reviewer_stage(pub=["clean", "scope-shift"], output_template="")
    synthetic = {"stages": {"test-reviewer": stage}}
    problems = check_catalog.check(synthetic)
    matched = [
        p
        for p in problems
        if "test-reviewer" in p and ("output_template" in p or "SIGNALS_PUBLISHED" in p)
    ]
    assert matched, (
        f"check() must flag a reviewer with empty output_template; "
        f"problems={problems}"
    )


# --- RC4-C02 ---
def test_check_catalog_reviewer_with_clean_in_signals_published_not_flagged():
    """A reviewer whose output_template contains a SIGNALS_PUBLISHED: line with #clean
    is NOT flagged for the reviewer-signal canary."""
    tmpl = "VERDICT: [pass | fail]\nSIGNALS_PUBLISHED: #clean\n"
    stage = _reviewer_stage(pub=["clean", "scope-shift"], output_template=tmpl)
    synthetic = {"stages": {"test-reviewer": stage}}
    problems = check_catalog.check(synthetic)
    canary_problems = [
        p
        for p in problems
        if "test-reviewer" in p and ("output_template" in p or "SIGNALS_PUBLISHED" in p)
    ]
    assert not canary_problems, (
        f"check() must NOT flag a reviewer with #clean in SIGNALS_PUBLISHED; "
        f"problems={canary_problems}"
    )


# --- RC4-C03 ---
def test_check_catalog_reviewer_missing_clean_in_signals_published_flagged():
    """A reviewer declaring clean (pub contains 'clean') but whose SIGNALS_PUBLISHED line
    lacks #clean is flagged."""
    tmpl = "VERDICT: [pass | fail]\nSIGNALS_PUBLISHED: #findings:x\n"
    stage = _reviewer_stage(pub=["clean", "scope-shift"], output_template=tmpl)
    synthetic = {"stages": {"test-reviewer": stage}}
    problems = check_catalog.check(synthetic)
    matched = [
        p
        for p in problems
        if "test-reviewer" in p
        and ("output_template" in p or "SIGNALS_PUBLISHED" in p or "clean" in p)
    ]
    assert matched, (
        f"check() must flag a reviewer whose SIGNALS_PUBLISHED line lacks #clean "
        f"but pub declares clean; problems={problems}"
    )


# --- RC4-C04 ---
def test_check_catalog_non_reviewer_not_flagged_for_signals_published():
    """A non-reviewer stage (pub contains code-written, scope-shift, no findings:*)
    with empty output_template is NOT flagged by the reviewer-signal canary."""
    stage = S(
        ["code"],
        req=["plan"],
        out=["diff"],
        sub=["plan-ready"],
        pub=["code-written", "scope-shift"],
    )
    stage["input_template"] = "<PLAN>stub</PLAN>\n"
    stage["output_template"] = ""
    synthetic = {"stages": {"code-implementer": stage}}
    problems = check_catalog.check(synthetic)
    canary_problems = [
        p
        for p in problems
        if "code-implementer" in p
        and ("output_template" in p or "SIGNALS_PUBLISHED" in p)
    ]
    assert not canary_problems, (
        f"non-reviewer stage must NOT be flagged by reviewer-signal canary; "
        f"problems={canary_problems}"
    )


# --- RC4-C05 ---
def test_check_catalog_reviewer_signals_published_outside_fence_flagged():
    """A reviewer whose SIGNALS_PUBLISHED line is in the file body but NOT inside the
    captured output_template (fence) is still flagged as missing the line in the template.
    """
    # output_template is empty (the ## Output (strict) fence was absent or empty),
    # so the canary sees no SIGNALS_PUBLISHED: in the captured template.
    stage = _reviewer_stage(pub=["clean", "scope-shift"], output_template="")
    synthetic = {"stages": {"test-reviewer": stage}}
    problems = check_catalog.check(synthetic)
    matched = [
        p
        for p in problems
        if "test-reviewer" in p and ("output_template" in p or "SIGNALS_PUBLISHED" in p)
    ]
    assert matched, (
        "SIGNALS_PUBLISHED outside the fence (empty output_template) must be flagged; "
        f"problems={problems}"
    )


# --- RC4-C06 ---
def test_check_catalog_reviewer_family_findings_signal():
    """Family-aware canary: a reviewer publishing findings:acceptance whose SIGNALS_PUBLISHED
    line lacks #findings is flagged; one with #findings is not flagged."""
    # Missing #findings in SIGNALS_PUBLISHED -> flagged
    tmpl_bad = "VERDICT: [pass | fail]\nSIGNALS_PUBLISHED: #scope-shift\n"
    stage_bad = _reviewer_stage(
        pub=["findings:acceptance", "scope-shift"], output_template=tmpl_bad
    )
    synthetic_bad = {"stages": {"acceptance-reviewer": stage_bad}}
    problems_bad = check_catalog.check(synthetic_bad)
    matched = [
        p
        for p in problems_bad
        if "acceptance-reviewer" in p
        and ("output_template" in p or "SIGNALS_PUBLISHED" in p or "findings" in p)
    ]
    assert matched, (
        "check() must flag acceptance-reviewer whose SIGNALS_PUBLISHED lacks #findings; "
        f"problems={problems_bad}"
    )

    # Has #findings in SIGNALS_PUBLISHED -> not flagged for canary
    tmpl_good = "VERDICT: [pass | fail]\nSIGNALS_PUBLISHED: #findings\n"
    stage_good = _reviewer_stage(
        pub=["findings:acceptance", "scope-shift"], output_template=tmpl_good
    )
    synthetic_good = {"stages": {"acceptance-reviewer": stage_good}}
    problems_good = check_catalog.check(synthetic_good)
    canary_problems = [
        p
        for p in problems_good
        if "acceptance-reviewer" in p
        and ("output_template" in p or "SIGNALS_PUBLISHED" in p)
    ]
    assert not canary_problems, (
        "check() must NOT flag acceptance-reviewer with #findings in SIGNALS_PUBLISHED; "
        f"problems={canary_problems}"
    )


# --- RC4-C07 ---
def test_check_catalog_non_reviewer_publishing_findings_lens_not_flagged():
    """Discriminator narrowing: a stage that publishes a findings:* signal but whose data
    output is NOT bare `findings` (a non-reviewer like plan-challenger/researcher/adr-drafter)
    is NOT flagged by the SIGNALS_PUBLISHED canary, even with an empty output_template.
    """
    stage = S(
        ["code"],
        req=["plan"],
        out=["plan-challenge"],
        sub=["plan-ready"],
        pub=["findings:challenge", "scope-shift"],
    )
    stage["input_template"] = "<PLAN>stub</PLAN>\n"
    stage["output_template"] = ""
    synthetic = {"stages": {"plan-challenger": stage}}
    problems = check_catalog.check(synthetic)
    canary_problems = [
        p
        for p in problems
        if "plan-challenger" in p
        and ("output_template" in p or "SIGNALS_PUBLISHED" in p)
    ]
    assert not canary_problems, (
        "a stage publishing findings:* but emitting a non-findings artifact is not a "
        f"reviewer and must not trip the SIGNALS_PUBLISHED canary; problems={canary_problems}"
    )


# --- RC4-C08 ---
def test_check_catalog_reviewer_findings_lens_mismatch_flagged():
    """Tightened lens-match: a reviewer publishing findings:right whose SIGNALS_PUBLISHED line
    names #findings:wrong IS flagged; one whose line names #findings:right is NOT."""
    tmpl_bad = (
        "VERDICT: [pass | fail]\nSIGNALS_PUBLISHED: [#clean OR #findings:wrong]\n"
    )
    stage_bad = _reviewer_stage(
        pub=["findings:right", "clean", "scope-shift"], output_template=tmpl_bad
    )
    synthetic_bad = {"stages": {"test-reviewer": stage_bad}}
    problems_bad = check_catalog.check(synthetic_bad)
    matched = [p for p in problems_bad if "test-reviewer" in p and "findings" in p]
    assert matched, (
        "a reviewer whose SIGNALS_PUBLISHED lens does not match a published findings lens "
        f"must be flagged; problems={problems_bad}"
    )

    tmpl_good = (
        "VERDICT: [pass | fail]\nSIGNALS_PUBLISHED: [#clean OR #findings:right]\n"
    )
    stage_good = _reviewer_stage(
        pub=["findings:right", "clean", "scope-shift"], output_template=tmpl_good
    )
    synthetic_good = {"stages": {"test-reviewer": stage_good}}
    problems_good = check_catalog.check(synthetic_good)
    canary_problems = [
        p
        for p in problems_good
        if "test-reviewer" in p
        and ("output_template" in p or "SIGNALS_PUBLISHED" in p or "findings" in p)
    ]
    assert not canary_problems, (
        "a reviewer whose SIGNALS_PUBLISHED lens matches its published findings lens must "
        f"NOT be flagged; problems={canary_problems}"
    )


# ---------------------------------------------------------------------------
# RC5: whole-token and every-token SIGNALS_PUBLISHED validation
# (plan-audit-fix-batch.md step 9) - unit tests against
# check_catalog._check_reviewer_signals(name, s, pubs) directly, on synthetic
# stage dicts, rather than through check_catalog.check().
# ---------------------------------------------------------------------------


def _sig_stage(signal_line):
    """A minimal synthetic stage dict carrying only what _check_reviewer_signals
    reads: an output_template whose SIGNALS_PUBLISHED: line is the given text."""
    return {
        "output_template": f"VERDICT: [pass | fail]\nSIGNALS_PUBLISHED: {signal_line}\n"
    }


# --- RC5-01 ---
def test_check_reviewer_signals_whole_token_rejects_substring_clean():
    """TC-CATALOG-01: pubs={'clean'}, line contains '#cleanup' (not '#clean' as a
    whole token) - must be flagged as lacking #clean. Closes the substring
    false-negative where '#clean' in '#cleanup' reads as satisfied today."""
    problems = check_catalog._check_reviewer_signals(
        "test-reviewer", _sig_stage("#cleanup done"), {"clean"}
    )
    matched = [p for p in problems if "lacks `#clean`" in p]
    assert matched, (
        f"'#cleanup' must NOT whole-token-satisfy a published 'clean' signal; "
        f"problems={problems}"
    )


# --- RC5-02 ---
def test_check_reviewer_signals_whole_token_no_phantom_clean():
    """TC-CATALOG-02: pubs has no 'clean', line contains '#cleanup' - must NOT be
    flagged for a phantom '#clean' token. Closes the substring false-positive
    where '#clean' in '#cleanup' reads as a stray #clean token today."""
    problems = check_catalog._check_reviewer_signals(
        "test-reviewer", _sig_stage("#cleanup done"), {"findings:security"}
    )
    clean_problems = [p for p in problems if "clean" in p]
    assert not clean_problems, (
        f"'#cleanup' must not be misread as a phantom '#clean' token; "
        f"problems={clean_problems}"
    )


# --- RC5-03 ---
def test_check_reviewer_signals_every_findings_token_checked():
    """TC-CATALOG-03: pubs={'findings:security'}, line names two lens tokens
    (#findings:security #findings:ux) - the unpublished 'ux' lens must be
    flagged. Every #findings:<lens> token is checked, not just the first."""
    problems = check_catalog._check_reviewer_signals(
        "test-reviewer",
        _sig_stage("#findings:security #findings:ux"),
        {"findings:security"},
    )
    matched = [p for p in problems if "ux" in p]
    assert matched, (
        f"the unpublished 'ux' lens token must be flagged even though 'security' "
        f"(the first token) is published; problems={problems}"
    )


# --- RC5-04 ---
def test_check_reviewer_signals_fully_consistent_line_clean_and_findings():
    """TC-CATALOG-04: pubs={'clean','findings:security'}, line has both matching
    tokens - no problems."""
    problems = check_catalog._check_reviewer_signals(
        "test-reviewer",
        _sig_stage("#clean #findings:security"),
        {"clean", "findings:security"},
    )
    assert (
        problems == []
    ), f"a fully consistent signal line must not be flagged; problems={problems}"


# --- RC5-05 ---
def test_check_reviewer_signals_multiple_valid_lens_tokens_all_pass():
    """TC-CATALOG-05: pubs={'findings:security','findings:ux'}, line names both
    matching lens tokens - no problems."""
    problems = check_catalog._check_reviewer_signals(
        "test-reviewer",
        _sig_stage("#findings:security #findings:ux"),
        {"findings:security", "findings:ux"},
    )
    assert (
        problems == []
    ), f"multiple valid lens tokens must all pass; problems={problems}"


# --- RC5-06 ---
def test_check_reviewer_signals_bare_findings_satisfies_family():
    """TC-CATALOG-06: pubs={'findings:security'}, line has bare '#findings' (no
    lens) - the family-aware check treats a bare #findings token as satisfying
    the family requirement; no 'lacks #findings' problem."""
    problems = check_catalog._check_reviewer_signals(
        "test-reviewer", _sig_stage("#findings"), {"findings:security"}
    )
    family_problems = [p for p in problems if "lacks `#findings`" in p]
    assert not family_problems, (
        f"a bare '#findings' token must satisfy the findings family requirement; "
        f"problems={family_problems}"
    )


# --- RC5-07 ---
def test_check_reviewer_signals_missing_findings_token_still_flagged():
    """TC-CATALOG-07: pubs={'findings:security'}, line has only '#clean' (no
    #findings or #findings:* token at all) - the family check must still fire."""
    problems = check_catalog._check_reviewer_signals(
        "test-reviewer", _sig_stage("#clean"), {"findings:security"}
    )
    matched = [p for p in problems if "lacks `#findings`" in p]
    assert matched, (
        f"a line with no #findings token at all must still be flagged when the "
        f"stage publishes findings:*; problems={problems}"
    )


# --- RC5-08 ---
def test_check_reviewer_signals_decorated_token_recognized():
    """TC-CATALOG-08: pubs={'clean'}, line has a bracket/punctuation-decorated
    '#clean' token ('[#clean]' and '#clean,') - the tokenizer must still
    recognize a decorated token, not just a bare-word match."""
    for decorated in ("[#clean]", "#clean,"):
        problems = check_catalog._check_reviewer_signals(
            "test-reviewer", _sig_stage(decorated), {"clean"}
        )
        clean_problems = [p for p in problems if "clean" in p]
        assert not clean_problems, (
            f"a decorated token {decorated!r} must still whole-token-satisfy a "
            f"published 'clean' signal; problems={clean_problems}"
        )


# --- RC5-INT-01 ---
def test_check_catalog_real_catalog_clean_after_signal_rewrite():
    """TC-CATALOG-INT-01: python3 hooks/check_catalog.py against the real
    generated/catalog.json exits 0 - the token-matching rewrite introduces no
    reviewer signal-line regressions."""
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "check_catalog.py")],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    assert result.returncode == 0, (
        f"hooks/check_catalog.py must exit 0 against the real catalog; "
        f"got {result.returncode}; stdout={result.stdout!r} stderr={result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# RC4-D: four reviewers gain #clean in frontmatter (real catalog)
# ---------------------------------------------------------------------------


# --- RC4-D01 ---
def test_real_catalog_acceptance_reviewer_publishes_clean():
    """acceptance-reviewer has 'clean' in signals.publishes after RC4."""
    cat = _real_catalog()
    pubs = cat["stages"]["acceptance-reviewer"]["signals"]["publishes"]
    assert "clean" in pubs, f"acceptance-reviewer must publish 'clean', got {pubs}"


# --- RC4-D02 ---
def test_real_catalog_reuse_reviewer_publishes_clean():
    """reuse-reviewer has 'clean' in signals.publishes after RC4."""
    cat = _real_catalog()
    pubs = cat["stages"]["reuse-reviewer"]["signals"]["publishes"]
    assert "clean" in pubs, f"reuse-reviewer must publish 'clean', got {pubs}"


# --- RC4-D03 ---
def test_real_catalog_plan_adherence_reviewer_publishes_clean():
    """plan-adherence-reviewer has 'clean' in signals.publishes after RC4."""
    cat = _real_catalog()
    pubs = cat["stages"]["plan-adherence-reviewer"]["signals"]["publishes"]
    assert "clean" in pubs, f"plan-adherence-reviewer must publish 'clean', got {pubs}"


# --- RC4-D04 ---
def test_real_catalog_security_reviewer_publishes_clean():
    """security-reviewer has 'clean' in signals.publishes after RC4."""
    cat = _real_catalog()
    pubs = cat["stages"]["security-reviewer"]["signals"]["publishes"]
    assert "clean" in pubs, f"security-reviewer must publish 'clean', got {pubs}"


# --- RC4-D05 ---
def test_check_catalog_no_orphan_clean_error_after_rc4():
    """check_catalog.check(real_catalog) has no 'no publisher for clean' orphan error
    after the four reviewers gain #clean in frontmatter."""
    problems = check_catalog.check(_real_catalog())
    clean_orphan = [p for p in problems if "clean" in p and "no publisher" in p]
    assert (
        not clean_orphan
    ), f"no orphan-publisher error for 'clean' expected after RC4; got {clean_orphan}"


# ---------------------------------------------------------------------------
# RC4-E: release version bump to 1.2.18
# ---------------------------------------------------------------------------


# --- RC4-E01 ---
def test_plugin_json_version_1_2_18():
    """plugin.json version must be '1.3.4'."""
    plugin_path = Path(__file__).resolve().parents[2] / ".claude-plugin" / "plugin.json"
    data = json.loads(plugin_path.read_text(encoding="utf-8"))
    assert (
        data["version"] == "1.3.4"
    ), f"plugin.json version must be '1.3.4', got {data['version']!r}"


# --- RC4-E02 ---
def test_marketplace_json_version_1_2_18_matches_plugin():
    """marketplace.json version must be '1.3.4' and equal plugin.json."""
    base = Path(__file__).resolve().parents[2] / ".claude-plugin"
    plugin_ver = json.loads((base / "plugin.json").read_text(encoding="utf-8"))[
        "version"
    ]
    market_ver = json.loads((base / "marketplace.json").read_text(encoding="utf-8"))[
        "metadata"
    ]["version"]
    assert (
        market_ver == "1.3.4"
    ), f"marketplace.json version must be '1.3.4', got {market_ver!r}"
    assert (
        market_ver == plugin_ver
    ), f"marketplace.json version {market_ver!r} must equal plugin.json {plugin_ver!r}"


# --- RC4-E03 ---
def test_changelog_contains_1_2_18():
    """CHANGELOG.md must contain '## 1.2.18' after RC4."""
    changelog_path = Path(__file__).resolve().parents[2] / "CHANGELOG.md"
    content = changelog_path.read_text(encoding="utf-8")
    assert (
        "## 1.2.18" in content
    ), "CHANGELOG.md must contain '## 1.2.18' after the RC4 version bump"


# ---------------------------------------------------------------------------
# RC4-F: idempotency + no-drift (extends RC3-D)
# ---------------------------------------------------------------------------


# --- RC4-F01 ---
def test_build_catalog_idempotent_with_output_template():
    """build_catalog() twice yields byte-identical JSON (sort_keys) with output_template populated."""
    first = json.dumps(_gen_catalog.build_catalog(), sort_keys=True)
    second = json.dumps(_gen_catalog.build_catalog(), sort_keys=True)
    assert first == second, "build_catalog() must be idempotent"
    # Verify output_template is present so the idempotency check is meaningful
    cat = _gen_catalog.build_catalog()
    for name, stage in cat["stages"].items():
        assert (
            "output_template" in stage
        ), f"{name}: output_template missing from build_catalog() output"


# --- RC4-F02 ---
def test_catalog_no_drift_from_committed_with_output_template():
    """committed generated/catalog.json == build_catalog() output byte-for-byte,
    including the output_template field (must be regenerated+committed after RC4)."""
    committed_path = Path(__file__).resolve().parents[2] / "generated" / "catalog.json"
    committed = json.loads(committed_path.read_text(encoding="utf-8"))
    live = _gen_catalog.build_catalog()
    assert json.dumps(live, sort_keys=True) == json.dumps(
        committed, sort_keys=True
    ), "build_catalog() output differs from committed catalog.json - regenerate after RC4"


# ---------------------------------------------------------------------------
# RC4-G: doctrine prose anchors (observable)
# ---------------------------------------------------------------------------


# --- RC4-G01 ---
def test_workflow_convergence_region_references_signals_published():
    """WORKFLOW.md convergence region references SIGNALS_PUBLISHED as the token
    the orchestrator reads for convergence."""
    workflow_path = Path(__file__).resolve().parents[2] / "WORKFLOW.md"
    text = workflow_path.read_text(encoding="utf-8")
    # Find the paragraph containing the convergence clause
    assert (
        "came back `clean`" in text
    ), "WORKFLOW.md must contain the convergence phrase 'came back `clean`'"
    # The SIGNALS_PUBLISHED token must appear near enough to the convergence directive
    # to be the referenced mechanism (present anywhere in WORKFLOW.md is the minimal bar)
    assert "SIGNALS_PUBLISHED" in text, (
        "WORKFLOW.md must reference 'SIGNALS_PUBLISHED' as the convergence token "
        "the orchestrator reads"
    )


# --- RC4-G02 ---
def test_reviewer_contract_base_output_format_contains_signals_published():
    """doctrine/reviewer-contract.md Base output format block contains 'SIGNALS_PUBLISHED:'."""
    contract_path = (
        Path(__file__).resolve().parents[2] / "doctrine" / "reviewer-contract.md"
    )
    text = contract_path.read_text(encoding="utf-8")
    assert "SIGNALS_PUBLISHED:" in text, (
        "doctrine/reviewer-contract.md Base output format block must contain "
        "'SIGNALS_PUBLISHED:'"
    )


# --- RC4-G03 ---
def test_reviewer_contract_has_published_signal_mapping_subsection():
    """doctrine/reviewer-contract.md contains the published-signal-mapping subsection
    describing pass/warn -> #clean, fail -> #findings:<lens>, partial -> #findings:acceptance.
    """
    contract_path = (
        Path(__file__).resolve().parents[2] / "doctrine" / "reviewer-contract.md"
    )
    text = contract_path.read_text(encoding="utf-8")
    # pass/warn maps to #clean
    assert (
        "#clean" in text
    ), "reviewer-contract.md must document #clean signal in the signal-mapping subsection"
    # fail maps to #findings:<lens>
    assert (
        "#findings:" in text
    ), "reviewer-contract.md must document #findings:<lens> in the signal-mapping subsection"
    # partial maps to #findings:acceptance
    assert (
        "#findings:acceptance" in text
    ), "reviewer-contract.md must document #findings:acceptance in the signal-mapping subsection"


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
