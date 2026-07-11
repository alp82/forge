"""plan-arbiter feature tests (RED before implementation).

Tests the catalog, router, injector, and agent-file invariants introduced by the
plan-arbiter feature. The feature does not exist yet - all tests here are expected
to FAIL now and go green after implementation.

Groups:
  A - router behavior (compute_route)
  B - catalog coherence (check_catalog / SEED model)
  C - stage contract shape (catalog fields + frontmatter)
  D - injector wiring (user-context-injector.sh)
  E - prose / agent file (agents/plan-arbiter.md)
  F - catalog-regen canary (generated/catalog.json)
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # hooks/
import check_catalog
import route

# ---------------------------------------------------------------------------
# Helpers shared by all groups
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]  # repo root


def _real_catalog():
    return route.load_catalog(ROOT / "generated" / "catalog.json")


def S(routes, req=(), opt=(), out=(), sub=(), pub=(), guard=None, lock=None):
    """Minimal stage builder - mirrors the one in test_route.py."""
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


# ---------------------------------------------------------------------------
# GROUP A - router behavior
# ---------------------------------------------------------------------------


# --- TC-A01 ---
def test_A01_plan_arbiter_absent_on_non_armed_baseline():
    """Non-armed baseline: intent-confirmed live but not critiques-ready -> plan-arbiter
    must NOT appear in route."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "intent-confirmed"},
        available={"confirmed-intent"},
    )
    assert "plan-arbiter" not in res["route"], (
        "plan-arbiter must NOT be in route when critiques-ready is absent; "
        f"route={res['route']}"
    )


# --- TC-A02 ---
def test_A02_plan_arbiter_triggered_by_plans_challenged():
    """With critiques-ready live and competing-plans + plan-critiques available,
    plan-arbiter is in route and triggered_by maps to critiques-ready."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "critiques-ready"},
        available={"competing-plans", "plan-critiques"},
    )
    assert "plan-arbiter" in res["route"], (
        "plan-arbiter must be in route when critiques-ready is live; "
        f"route={res['route']}, dropped={res.get('dropped', {})}"
    )
    triggered = res.get("triggered_by", {}).get("plan-arbiter")
    assert (
        triggered == "critiques-ready"
    ), f"plan-arbiter must be triggered_by critiques-ready, got {triggered!r}"


# --- TC-A03 ---
def test_A03_arbiter_ordering_is_orchestrator_phased_in_doctrine():
    """Arbiter ordering is enforced by orchestrator phasing, not the router DAG.
    doctrine/multi-plan.md must exist and document the co-publish contract: the
    orchestrator seeds competing-plans + plan-critiques into available AND publishes
    critiques-ready in one atomic step, after the per-plan critique phase.
    """
    doctrine_path = ROOT / "doctrine" / "multi-plan.md"
    assert doctrine_path.exists(), (
        f"doctrine/multi-plan.md must exist to document the orchestrator-phasing "
        f"co-publish contract; path checked: {doctrine_path}"
    )
    text = doctrine_path.read_text(encoding="utf-8")
    # The co-publish contract requires that critiques-ready co-occurs with
    # competing-plans and plan-critiques in a seed-and-publish / atomic-recompose sentence.
    pattern = re.compile(
        r"critiques-ready.{0,300}competing-plans.{0,300}plan-critiques"
        r"|competing-plans.{0,300}plan-critiques.{0,300}critiques-ready",
        re.DOTALL | re.IGNORECASE,
    )
    assert pattern.search(text), (
        "doctrine/multi-plan.md must document the orchestrator co-publish contract: "
        "critiques-ready co-occurring with competing-plans and plan-critiques in a "
        "seed-and-publish / atomic-recompose sentence"
    )


# --- TC-A04 / TC-A05 / TC-A06 ---
@pytest.mark.parametrize(
    "path",
    ["system", "sketch", "talk"],
    ids=["TC-A04", "TC-A05", "TC-A06"],
)
def test_A04_A05_A06_plan_arbiter_off_non_code_paths(path):
    """Non-code path + critiques-ready -> plan-arbiter NOT in route (off-path); dropped==off-path."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {path, "critiques-ready"},
        available={"competing-plans", "plan-critiques"},
    )
    assert (
        "plan-arbiter" not in res["route"]
    ), f"plan-arbiter must not appear on {path} path"
    assert res.get("dropped", {}).get("plan-arbiter") == "off-path", (
        f"plan-arbiter must be dropped as off-path on {path}; "
        f"dropped={res.get('dropped', {})}"
    )


# --- TC-A07 ---
def test_A07_plan_arbiter_dropped_unsatisfiable_when_no_artifacts():
    """critiques-ready live but NO artifacts available -> plan-arbiter dropped as
    unsatisfiable-input (required inputs cannot be produced)."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "critiques-ready"},
        available=set(),
    )
    assert (
        "plan-arbiter" not in res["route"]
    ), "plan-arbiter must not be in route when required artifacts are absent"
    assert res.get("dropped", {}).get("plan-arbiter") == "unsatisfiable-input", (
        f"plan-arbiter must be dropped as unsatisfiable-input when artifacts absent; "
        f"dropped={res.get('dropped', {})}"
    )


# --- TC-A08 ---
def test_A08_plan_arbiter_dropped_unsatisfiable_when_only_competing_plans():
    """critiques-ready live + only competing-plans (missing plan-critiques) ->
    plan-arbiter dropped as unsatisfiable-input."""
    cat = _real_catalog()
    res = route.compute_route(
        cat,
        {"code", "critiques-ready"},
        available={"competing-plans"},
    )
    assert (
        "plan-arbiter" not in res["route"]
    ), "plan-arbiter must not be in route when plan-critiques is absent"
    assert res.get("dropped", {}).get("plan-arbiter") == "unsatisfiable-input", (
        f"plan-arbiter must be dropped as unsatisfiable-input when plan-critiques absent; "
        f"dropped={res.get('dropped', {})}"
    )


# ---------------------------------------------------------------------------
# GROUP B - catalog coherence (SEED model)
# ---------------------------------------------------------------------------


# --- TC-B01 ---
def test_B01_critiques_ready_in_seed_signals():
    """critiques-ready must be present in check_catalog.SEED_SIGNALS."""
    assert (
        "critiques-ready" in check_catalog.SEED_SIGNALS
    ), f"critiques-ready must be in SEED_SIGNALS; got {check_catalog.SEED_SIGNALS}"


# --- TC-B02 ---
def test_B02_competing_plans_in_seed_artifacts():
    """competing-plans must be present in check_catalog.SEED_ARTIFACTS."""
    assert (
        "competing-plans" in check_catalog.SEED_ARTIFACTS
    ), f"competing-plans must be in SEED_ARTIFACTS; got {check_catalog.SEED_ARTIFACTS}"


# --- TC-B03 ---
def test_B03_plan_critiques_in_seed_artifacts():
    """plan-critiques must be present in check_catalog.SEED_ARTIFACTS."""
    assert (
        "plan-critiques" in check_catalog.SEED_ARTIFACTS
    ), f"plan-critiques must be in SEED_ARTIFACTS; got {check_catalog.SEED_ARTIFACTS}"


# --- TC-B04 ---
def test_B04_real_catalog_check_clean_after_regen():
    """check_catalog.check(real_catalog) == [] after plan-arbiter is added and catalog
    is regenerated."""
    assert (
        check_catalog.check(_real_catalog()) == []
    ), "check_catalog.check() must return [] for the real catalog after regen"


# --- TC-B05 ---
def test_B05_check_flags_orphan_when_seeds_absent():
    """Failure-mode canary: a synthetic catalog with a plan-arbiter-shaped stage that
    subscribes critiques-ready and requires competing-plans + plan-critiques, but those
    terms are NOT in the seed sets of a locally-patched check module -> check() returns
    non-empty, naming the orphan signals/artifacts.

    The test constructs its own minimal catalog and patches check_catalog's SEED_SIGNALS
    and SEED_ARTIFACTS locally to empty sets to prove the orphan logic fires correctly,
    regardless of what the real seeds contain after implementation.
    """
    synthetic_catalog = {
        "stages": {
            "plan-arbiter": S(
                ["code"],
                req=["competing-plans", "plan-critiques"],
                out=[],
                sub=["critiques-ready"],
                pub=["plan-approved", "scope-shift"],
            )
        }
    }

    # Temporarily clear seeds so the orphan-detection logic has nothing to exempt
    original_signals = check_catalog.SEED_SIGNALS
    original_artifacts = check_catalog.SEED_ARTIFACTS
    try:
        check_catalog.SEED_SIGNALS = set()
        check_catalog.SEED_ARTIFACTS = set()
        problems = check_catalog.check(synthetic_catalog)
    finally:
        check_catalog.SEED_SIGNALS = original_signals
        check_catalog.SEED_ARTIFACTS = original_artifacts

    assert (
        len(problems) > 0
    ), "check() must return non-empty problems when seeds are absent"
    assert any(
        "critiques-ready" in p for p in problems
    ), f"check() must name critiques-ready as an orphan subscribe; problems={problems}"
    orphan_artifacts = {"competing-plans", "plan-critiques"}
    for art in orphan_artifacts:
        assert any(
            art in p for p in problems
        ), f"check() must flag orphan required artifact '{art}'; problems={problems}"


# --- TC-B06 ---
def test_B06_catalog_has_41_stages():
    """After the review-wave consolidation (12 lenses -> 5 always-on), the
    interviewer + requirements-clarifier merge into clarifier, and the
    capture-agent + adr-drafter removal, the catalog must have 41 stages."""
    cat = _real_catalog()
    assert (
        len(cat["stages"]) == 41
    ), f"expected 41 stages after the capture-agent and adr-drafter removal, got {len(cat['stages'])}"


# --- TC-B07 ---
def test_B07_plan_arbiter_in_real_catalog():
    """plan-arbiter must be present as a key in real_catalog['stages']."""
    cat = _real_catalog()
    assert (
        "plan-arbiter" in cat["stages"]
    ), "plan-arbiter must be a key in the real catalog stages"


# ---------------------------------------------------------------------------
# GROUP C - stage contract shape
# ---------------------------------------------------------------------------

_ARBITER_MD = ROOT / "agents" / "plan-arbiter.md"


def _read_arbiter_md():
    """Read agents/plan-arbiter.md, failing the test if the file is absent."""
    if not _ARBITER_MD.exists():
        pytest.fail(f"agents/plan-arbiter.md does not exist yet (expected red)")
    return _ARBITER_MD.read_text(encoding="utf-8")


def _parse_frontmatter(text):
    """Extract the YAML frontmatter block between the first pair of --- delimiters."""
    import yaml  # stdlib-adjacent; available in the test env

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "---"), None)
    if end is None:
        return {}
    fm_text = "\n".join(lines[1:end])
    return yaml.safe_load(fm_text) or {}


# --- TC-C01 ---
def test_C01_arbiter_frontmatter_model_effort_routes_tools():
    """agents/plan-arbiter.md frontmatter: model==fable, effort==medium, routes==[code],
    tools list excludes Edit and Write."""
    text = _read_arbiter_md()
    fm = _parse_frontmatter(text)

    assert (
        fm.get("model") == "fable"
    ), f"plan-arbiter frontmatter model must be 'fable', got {fm.get('model')!r}"
    assert (
        fm.get("effort") == "medium"
    ), f"plan-arbiter frontmatter effort must be 'medium', got {fm.get('effort')!r}"
    stage = fm.get("stage", {})
    assert stage.get("routes") == [
        "code"
    ], f"plan-arbiter stage.routes must be ['code'], got {stage.get('routes')!r}"
    tools_raw = fm.get("tools", "")
    if isinstance(tools_raw, list):
        tools = [t.strip() for t in tools_raw]
    else:
        tools = [t.strip() for t in str(tools_raw).split(",")]
    assert (
        "Edit" not in tools
    ), f"plan-arbiter tools must NOT include Edit (read-only stage); tools={tools}"
    assert (
        "Write" not in tools
    ), f"plan-arbiter tools must NOT include Write (read-only stage); tools={tools}"


# --- TC-C02 ---
def test_C02_arbiter_catalog_signals():
    """Catalog plan-arbiter signals: subscribes contains critiques-ready; publishes
    contains plan-approved and scope-shift."""
    cat = _real_catalog()
    s = cat["stages"].get("plan-arbiter")
    assert s is not None, "plan-arbiter must exist in real catalog"
    subs = s["signals"]["subscribes"]
    pubs = s["signals"]["publishes"]
    assert (
        "critiques-ready" in subs
    ), f"plan-arbiter must subscribe critiques-ready; got {subs}"
    assert (
        "plan-approved" in pubs
    ), f"plan-arbiter must publish plan-approved; got {pubs}"
    assert "scope-shift" in pubs, f"plan-arbiter must publish scope-shift; got {pubs}"


# --- TC-C03 ---
def test_C03_arbiter_catalog_required_inputs():
    """Catalog plan-arbiter data.input.required contains competing-plans and plan-critiques."""
    cat = _real_catalog()
    s = cat["stages"].get("plan-arbiter")
    assert s is not None, "plan-arbiter must exist in real catalog"
    req = s["data"]["input"]["required"]
    assert (
        "competing-plans" in req
    ), f"plan-arbiter required inputs must contain competing-plans; got {req}"
    assert (
        "plan-critiques" in req
    ), f"plan-arbiter required inputs must contain plan-critiques; got {req}"


# --- TC-C04 ---
def test_C04_arbiter_catalog_input_template_non_empty():
    """Catalog plan-arbiter input_template must be non-empty."""
    cat = _real_catalog()
    s = cat["stages"].get("plan-arbiter")
    assert s is not None, "plan-arbiter must exist in real catalog"
    template = s.get("input_template", "")
    assert (
        template and template.strip()
    ), "plan-arbiter input_template must be non-empty"


# --- TC-C05 ---
def test_C05_code_planner_optional_planning_lens():
    """Catalog code-planner data.input.optional contains planning-lens."""
    cat = _real_catalog()
    s = cat["stages"].get("code-planner")
    assert s is not None, "code-planner must exist in real catalog"
    opt = s["data"]["input"]["optional"]
    assert (
        "planning-lens" in opt
    ), f"code-planner optional inputs must contain planning-lens; got {opt}"


# --- TC-C06 ---
def test_C06_code_planner_md_contains_planning_lens_slot():
    """agents/code-planner.md ## Input block contains the literal <PLANNING_LENS>."""
    planner_md = ROOT / "agents" / "code-planner.md"
    if not planner_md.exists():
        pytest.fail("agents/code-planner.md does not exist")
    text = planner_md.read_text(encoding="utf-8")
    assert (
        "<PLANNING_LENS>" in text
    ), "agents/code-planner.md must contain the literal <PLANNING_LENS> slot"


# --- TC-C07 ---
def test_C07_plan_challenger_optional_critique_only():
    """Catalog plan-challenger data.input.optional contains critique-only."""
    cat = _real_catalog()
    s = cat["stages"].get("plan-challenger")
    assert s is not None, "plan-challenger must exist in real catalog"
    opt = s["data"]["input"]["optional"]
    assert (
        "critique-only" in opt
    ), f"plan-challenger optional inputs must contain critique-only; got {opt}"


# --- TC-C08 ---
def test_C08_plan_challenger_md_contains_critique_only_slot():
    """agents/plan-challenger.md ## Input block contains the literal <CRITIQUE_ONLY>."""
    challenger_md = ROOT / "agents" / "plan-challenger.md"
    if not challenger_md.exists():
        pytest.fail("agents/plan-challenger.md does not exist")
    text = challenger_md.read_text(encoding="utf-8")
    assert (
        "<CRITIQUE_ONLY>" in text
    ), "agents/plan-challenger.md must contain the literal <CRITIQUE_ONLY> slot"


# --- TC-C09 ---
def test_C09_arbiter_and_challenger_same_routes():
    """plan-arbiter routes == plan-challenger routes == ['code']."""
    cat = _real_catalog()
    arbiter = cat["stages"].get("plan-arbiter")
    assert arbiter is not None, "plan-arbiter must exist in real catalog"
    challenger = cat["stages"].get("plan-challenger")
    assert challenger is not None, "plan-challenger must exist in real catalog"
    assert arbiter["routes"] == [
        "code"
    ], f"plan-arbiter routes must be ['code'], got {arbiter['routes']}"
    assert challenger["routes"] == [
        "code"
    ], f"plan-challenger routes must be ['code'], got {challenger['routes']}"
    assert (
        arbiter["routes"] == challenger["routes"]
    ), "plan-arbiter and plan-challenger must have identical routes"


# --- TC-C10 ---
def test_C10_challenger_critique_only_section_states_both_behaviors():
    """agents/plan-challenger.md ## Critique-only mode section states BOTH behaviors:
    it omits the CHALLENGE_QUESTIONS picker AND never publishes #plan-approved."""
    challenger_md = ROOT / "agents" / "plan-challenger.md"
    if not challenger_md.exists():
        pytest.fail("agents/plan-challenger.md does not exist")
    text = challenger_md.read_text(encoding="utf-8")

    # Extract the critique-only section (from the ## Critique-only mode heading to the next
    # ## heading). Anchor with ^ so the cross-reference on line 23 ("see `## Critique-only
    # mode`") is not mistaken for the actual heading.
    section_m = re.search(
        r"^##\s+Critique-only mode\b(.*?)(?=\n^##|\Z)",
        text,
        re.DOTALL | re.IGNORECASE | re.MULTILINE,
    )
    assert (
        section_m
    ), "agents/plan-challenger.md must contain a '## Critique-only mode' section"
    section = section_m.group(1)

    # Behavior 1: omits the CHALLENGE_QUESTIONS picker
    omit_pattern = re.compile(
        r"omit.{0,60}CHALLENGE_QUESTIONS|CHALLENGE_QUESTIONS.{0,60}omit",
        re.DOTALL | re.IGNORECASE,
    )
    assert omit_pattern.search(section), (
        "agents/plan-challenger.md ## Critique-only mode must state that the "
        "CHALLENGE_QUESTIONS picker is omitted in critique-only mode"
    )

    # Behavior 2: never publishes #plan-approved
    never_publish_pattern = re.compile(
        r"never.{0,60}plan-approved|plan-approved.{0,60}never",
        re.DOTALL | re.IGNORECASE,
    )
    assert never_publish_pattern.search(section), (
        "agents/plan-challenger.md ## Critique-only mode must state that #plan-approved "
        "is NEVER published in critique-only mode"
    )


# ---------------------------------------------------------------------------
# GROUP D - injector wiring (user-context-injector.sh)
# ---------------------------------------------------------------------------

_INJECTOR = ROOT / "hooks" / "user-context-injector.sh"


def _injector_text():
    if not _INJECTOR.exists():
        pytest.fail(f"hooks/user-context-injector.sh does not exist at {_INJECTOR}")
    return _INJECTOR.read_text(encoding="utf-8")


# --- TC-D01 ---
def test_D01_injector_has_plan_arbiter_case_arm():
    """user-context-injector.sh contains plan-arbiter as a recognized case arm
    (not just in the terminal `*) exit 0`)."""
    text = _injector_text()
    # The arm must appear inside a case pattern before the terminal *)
    # Pattern: plan-arbiter appears in a | or standalone case arm before the *)
    # We look for plan-arbiter adjacent to a ) in a case arm context
    arm_pattern = re.compile(r"\bplan-arbiter\b(?=\||\))", re.MULTILINE)
    assert arm_pattern.search(text), (
        "user-context-injector.sh must have plan-arbiter as a recognized case arm "
        "(matching pattern: plan-arbiter followed by | or ))"
    )


# --- TC-D03 ---
def test_D03_doctrine_map_has_plan_arbiter_with_code_doctrine():
    """DOCTRINE_MAP in user-context-injector.sh has a [plan-arbiter]= entry that
    contains the string 'code-doctrine'."""
    text = _injector_text()
    pattern = re.compile(r'\[plan-arbiter\]="([^"]+)"')
    # Search specifically in the DOCTRINE_MAP block
    # Extract DOCTRINE_MAP block and search within it
    doctrine_block_m = re.search(r"declare -A DOCTRINE_MAP=\((.*?)\)", text, re.DOTALL)
    assert doctrine_block_m, "DOCTRINE_MAP block not found in user-context-injector.sh"
    doctrine_block = doctrine_block_m.group(1)
    entry_m = pattern.search(doctrine_block)
    assert entry_m, "DOCTRINE_MAP must have a [plan-arbiter]= entry"
    assert "code-doctrine" in entry_m.group(1), (
        f"DOCTRINE_MAP [plan-arbiter]= must contain 'code-doctrine'; "
        f"got {entry_m.group(1)!r}"
    )


# ---------------------------------------------------------------------------
# GROUP E - prose / agent file (agents/plan-arbiter.md)
# ---------------------------------------------------------------------------


# --- TC-E01 ---
def test_E01_arbiter_md_contains_tiebreak_ordering():
    """agents/plan-arbiter.md contains the tie-break ordering in document order:
    correctness ... grounding ... simpler ... validation ... token (re.DOTALL search).
    """
    text = _read_arbiter_md()
    pattern = re.compile(
        r"correctness.*?grounding.*?simpler.*?validation.*?token",
        re.DOTALL | re.IGNORECASE,
    )
    assert pattern.search(text), (
        "agents/plan-arbiter.md must contain the tie-break ordering: "
        "correctness > grounding > simpler > validation > token (in that order)"
    )


# --- TC-E02 ---
def test_E02_arbiter_md_contains_decision_vocabulary():
    """agents/plan-arbiter.md contains 'Adopt', 'Hybrid', and 'Revise-first'."""
    text = _read_arbiter_md()
    for term in ("Adopt", "Hybrid", "Revise-first"):
        assert (
            term in text
        ), f"agents/plan-arbiter.md must contain the decision term '{term}'"


# --- TC-E03 ---
def test_E03_arbiter_md_frontmatter_required_fields():
    """agents/plan-arbiter.md frontmatter has name, model, effort, tools, and stage
    with nested routes/data/signals."""
    text = _read_arbiter_md()
    fm = _parse_frontmatter(text)

    assert (
        fm.get("name") == "plan-arbiter"
    ), f"frontmatter name must be 'plan-arbiter', got {fm.get('name')!r}"
    assert "model" in fm, "frontmatter must have 'model'"
    assert "effort" in fm, "frontmatter must have 'effort'"
    assert "tools" in fm, "frontmatter must have 'tools'"
    stage = fm.get("stage", {})
    assert "routes" in stage, "frontmatter stage must have 'routes'"
    assert "data" in stage, "frontmatter stage must have 'data'"
    assert "signals" in stage, "frontmatter stage must have 'signals'"


# ---------------------------------------------------------------------------
# GROUP F - catalog-regen canary
# ---------------------------------------------------------------------------


# --- TC-F01 ---
def test_F01_generated_catalog_has_no_approaches_literal():
    """generated/catalog.json contains neither the literal '<APPROACHES>' nor the
    bare word APPROACHES (regex \\bAPPROACHES\\b)."""
    catalog_path = ROOT / "generated" / "catalog.json"
    if not catalog_path.exists():
        pytest.fail(f"generated/catalog.json not found at {catalog_path}")
    raw = catalog_path.read_text(encoding="utf-8")
    assert "<APPROACHES>" not in raw, (
        "generated/catalog.json must NOT contain the literal '<APPROACHES>' - "
        "replace with a plan-arbiter-appropriate slot name"
    )
    assert not re.search(
        r"\bAPPROACHES\b", raw
    ), "generated/catalog.json must NOT contain the bare word APPROACHES"


# --- TC-F02 ---
def test_F02_code_planner_input_template_has_no_approaches():
    """Catalog code-planner input_template contains neither '<APPROACHES>' nor bare APPROACHES."""
    cat = _real_catalog()
    s = cat["stages"].get("code-planner")
    assert s is not None, "code-planner must exist in real catalog"
    template = s.get("input_template", "")
    assert (
        "<APPROACHES>" not in template
    ), "code-planner input_template must NOT contain '<APPROACHES>'"
    assert not re.search(
        r"\bAPPROACHES\b", template
    ), "code-planner input_template must NOT contain the bare word APPROACHES"


# --- TC-F03 ---
def test_F03_plan_arbiter_input_template_has_competing_plans_slot():
    """Positive control: catalog plan-arbiter input_template contains '<COMPETING_PLANS>'
    (so F01 cannot pass vacuously on an empty template)."""
    cat = _real_catalog()
    s = cat["stages"].get("plan-arbiter")
    assert s is not None, "plan-arbiter must exist in real catalog"
    template = s.get("input_template", "")
    assert "<COMPETING_PLANS>" in template, (
        "plan-arbiter input_template must contain '<COMPETING_PLANS>' "
        "(positive control to prevent F01 passing vacuously on an empty template)"
    )
