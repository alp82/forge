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
import render_route
import check_catalog


def S(routes, req=(), opt=(), out=(), sub=(), pub=(), guard=None):
    """Build a normalized catalog stage entry (matches gen-catalog output shape)."""
    s = {
        "routes": list(routes),
        "data": {"input": {"required": list(req), "optional": list(opt)}, "output": list(out)},
        "signals": {"subscribes": list(sub), "publishes": list(pub)},
    }
    if guard:
        s["guard"] = guard
    return s


CATALOG = {"stages": {
    "scan":  S(["build", "talk"], req=["intent"], out=["reuse-map"],
               sub=["build"], pub=["missing-infra", "scope-shift"]),
    "impl":  S(["build"], req=["plan", "tests"], out=["diff"],
               sub=["plan-ready"], pub=["code-written", "scope-shift"]),
    "sec":   S(["build", "spike"], req=["diff"], out=["findings"],
               sub=["auth-surface"], pub=["findings:security", "scope-shift"], guard="sticky"),
    "proto": S(["build"], req=["intent"], out=["tracer"],
               sub=["missing-infra"], pub=["scope-shift"]),
    # optional `reuse-map`: plan runs without it, but orders after scan when scan is present
    "plan":  S(["build"], req=["intent"], opt=["reuse-map"], out=["blueprint"],
               sub=["plan-needed"], pub=["plan-ready", "scope-shift"]),
    # three single-purpose stages on the same signal to exercise the routes filter
    "buildonly": S(["build"], sub=["ping"], pub=["scope-shift"]),
    "spikeonly": S(["spike"], sub=["ping"], pub=["scope-shift"]),
    "both":      S(["build", "spike"], sub=["ping"], pub=["scope-shift"]),
}}


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
    assert set(grown["route"]) == {"scan", "proto"}        # proto joins via missing-infra
    shrunk = r(["build"], available=["intent"])
    assert shrunk["route"] == ["scan"]                     # signal gone -> proto drops


def test_sticky_guard_persists_across_recompose():
    prev = r(["build", "auth-surface"], available=["intent", "diff"])
    assert "sec" in prev["route"]
    now = r(["build"], available=["intent", "diff"])       # auth-surface gone
    assert "sec" not in now["route"]                       # would drop...
    merged = route.merge_sticky(CATALOG, prev["route"], now)
    assert "sec" in merged["route"]                        # ...but sticky keeps it


def test_deterministic_same_input_same_route():
    a = r(["plan-ready", "auth-surface"], available=["plan", "tests"])
    b = r(["plan-ready", "auth-surface"], available=["plan", "tests"])
    assert a == b


def _real_catalog():
    return route.load_catalog(Path(__file__).resolve().parents[2] / "generated" / "catalog.json")


def test_real_catalog_build_spine():
    cat = _real_catalog()
    assert set(cat["stages"]) >= {
        "implementer", "reuse-scanner", "security-reviewer", "discuss", "spike-build"}
    res = route.compute_route(cat, {"build"}, available={"confirmed-intent"})
    assert "reuse-scanner" in res["route"]
    assert "discuss" not in res["route"]      # talk-only stage stays off the build path


def test_real_catalog_routes_filter_on_spike():
    cat = _real_catalog()
    res = route.compute_route(cat, {"spike", "code-written"},
                              available={"confirmed-intent", "diff"})
    assert "spike-build" in res["route"]
    assert "correctness-reviewer" in res["route"]      # routes include spike
    assert "quality-reviewer" not in res["route"]      # build-only lens, filtered off spike
    assert res["dropped"].get("quality-reviewer") == "off-path"


def test_real_catalog_talk_path():
    cat = _real_catalog()
    res = route.compute_route(cat, {"talk", "ambiguous"},
                              available={"request", "triage-read"})
    assert "discuss" in res["route"]
    assert "interviewer" in res["route"]               # ambiguous + talk
    # discuss optionally consumes interviewer's confirmed-intent -> orders after it
    assert res["route"].index("interviewer") < res["route"].index("discuss")


def test_real_catalog_coherence():
    # the coherence gate, run against the real catalog: no orphan subscribes, every required
    # input has a producer or seed, scope-shift + routes on every stage
    assert check_catalog.check(_real_catalog()) == []


def test_render_full_and_delta():
    res = r(["build", "missing-infra"], available=["intent"])
    full = render_route.render_full(res, CATALOG, route_type="build")
    assert "build" in full and "proto" in full and "#missing-infra" in full
    prev = r(["build"], available=["intent"])
    delta = render_route.render_delta(prev["route"], res)
    assert "+proto" in delta


def test_family_prefix_subscribe_matches_qualified():
    cat = {"stages": {
        "fix": S(["build"], req=["findings"], out=["diff"],
                 sub=["findings"], pub=["code-written", "scope-shift"]),
    }}
    assert "fix" in route.compute_route(cat, {"findings:correctness"}, available={"findings"})["route"]
    assert "fix" in route.compute_route(cat, {"findings"}, available={"findings"})["route"]


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
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
