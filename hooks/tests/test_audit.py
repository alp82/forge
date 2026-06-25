"""Tests for hooks/audit.py.

audit.py exists and these tests are green.

CONTRACT:
  - build_scorecard(root) -> {"overall": int, "categories": {name: {"score": int,
    "fixes": [str,...]}}, "top_fixes": [str,...]}
  - 8 category names: "tool/agent coverage", "context efficiency",
    "quality gates", "memory persistence", "security guardrails",
    "doctrine integrity", "doctrine hygiene", "why-anchor coverage"
  - Deterministic: same input -> identical scorecard
  - Fail-open: missing or malformed catalog yields a valid scorecard without raising
  - top_fixes: worst-category-first, deterministic tie-break by category name ascending
  - main(): prints human scorecard + SCORECARD_JSON line, calls sys.exit(0) on every path
  - imports check_catalog.check guarded so a check() exception cannot escape
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # hooks/
import audit
import check_catalog

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

CATEGORY_NAMES = {
    "tool/agent coverage",
    "context efficiency",
    "quality gates",
    "memory persistence",
    "security guardrails",
    "doctrine integrity",
    "doctrine hygiene",
    "why-anchor coverage",
}

# A minimal valid catalog - stages dict has representative entries
_FULL_CATALOG = {
    "stages": {
        "triage": {
            "routes": ["code"],
            "data": {"input": {"required": [], "optional": []}, "output": []},
            "signals": {"subscribes": [], "publishes": ["scope-shift"]},
        },
        "code-implementer": {
            "routes": ["code"],
            "data": {
                "input": {"required": ["approved-plan"], "optional": []},
                "output": ["diff"],
            },
            "signals": {
                "subscribes": ["plan-ready"],
                "publishes": ["code-written", "scope-shift"],
            },
            "guard": "sticky",
        },
        "security-reviewer": {
            "routes": ["code"],
            "data": {
                "input": {"required": ["diff"], "optional": []},
                "output": ["findings"],
            },
            "signals": {
                "subscribes": ["code-written"],
                "publishes": ["findings:security", "scope-shift"],
            },
        },
        "test-plan": {
            "routes": ["code"],
            "data": {
                "input": {"required": [], "optional": []},
                "output": ["test-cases"],
            },
            "signals": {
                "subscribes": ["needs-tests"],
                "publishes": ["test-cases-ready", "scope-shift"],
            },
        },
    }
}

# A catalog that lacks quality-gate-related stages
_CATALOG_WITHOUT_QUALITY_GATES = {
    "stages": {
        "triage": {
            "routes": ["code"],
            "data": {"input": {"required": [], "optional": []}, "output": []},
            "signals": {"subscribes": [], "publishes": ["scope-shift"]},
        },
    }
}

# A catalog where one specific category is clearly low
_CATALOG_EMPTY_STAGES = {"stages": {}}


def _write_stub_catalog(root):
    """Write a minimal stub generated/catalog.json under root (a Path)."""
    gen = root / "generated"
    gen.mkdir(exist_ok=True)
    (gen / "catalog.json").write_text(json.dumps({"stages": {}}), encoding="utf-8")


def _make_repo_root(catalog_dict):
    """Create a temp dir with generated/catalog.json populated from catalog_dict."""
    root = tempfile.mkdtemp()
    gen = Path(root) / "generated"
    gen.mkdir()
    (gen / "catalog.json").write_text(json.dumps(catalog_dict))
    return Path(root)


REAL_REPO_ROOT = Path(__file__).resolve().parents[2]

# Path to the script under test
AUDIT_PY = Path(__file__).resolve().parents[1] / "audit.py"


# ---------------------------------------------------------------------------
# Group A - Determinism and shape
# ---------------------------------------------------------------------------


def test_a01_determinism_same_input_same_output():
    """A-01: build_scorecard called twice on the same fixture returns equal dicts."""
    root = _make_repo_root(_FULL_CATALOG)
    try:
        first = audit.build_scorecard(root)
        second = audit.build_scorecard(root)
        assert (
            first == second
        ), f"build_scorecard must be deterministic; first={first!r}, second={second!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a02_shape_top_level_keys():
    """A-02: result has exactly {overall, categories, top_fixes}."""
    root = _make_repo_root(_FULL_CATALOG)
    try:
        result = audit.build_scorecard(root)
        assert set(result.keys()) == {
            "overall",
            "categories",
            "top_fixes",
        }, f"expected top-level keys {{overall, categories, top_fixes}}, got {set(result.keys())}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a02_shape_overall_is_int():
    """A-02: overall is an int."""
    root = _make_repo_root(_FULL_CATALOG)
    try:
        result = audit.build_scorecard(root)
        assert isinstance(
            result["overall"], int
        ), f"overall must be int, got {type(result['overall'])}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a02_shape_categories_has_exactly_eight_names():
    """A-02: categories has exactly the 8 required category names."""
    root = _make_repo_root(_FULL_CATALOG)
    try:
        result = audit.build_scorecard(root)
        assert (
            set(result["categories"].keys()) == CATEGORY_NAMES
        ), f"expected categories {CATEGORY_NAMES}, got {set(result['categories'].keys())}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a02_shape_each_category_has_score_and_fixes():
    """A-02: each category has 'score' (int) and 'fixes' (list)."""
    root = _make_repo_root(_FULL_CATALOG)
    try:
        result = audit.build_scorecard(root)
        for name, cat in result["categories"].items():
            assert "score" in cat, f"category '{name}' missing 'score' key"
            assert "fixes" in cat, f"category '{name}' missing 'fixes' key"
            assert isinstance(
                cat["score"], int
            ), f"category '{name}' score must be int, got {type(cat['score'])}"
            assert isinstance(
                cat["fixes"], list
            ), f"category '{name}' fixes must be list, got {type(cat['fixes'])}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a02_shape_top_fixes_is_list():
    """A-02: top_fixes is a list."""
    root = _make_repo_root(_FULL_CATALOG)
    try:
        result = audit.build_scorecard(root)
        assert isinstance(
            result["top_fixes"], list
        ), f"top_fixes must be list, got {type(result['top_fixes'])}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a03_insertion_order_independence():
    """A-03: two catalogs identical except dict insertion order produce equal scorecards."""
    stages_order_a = {
        "triage": _FULL_CATALOG["stages"]["triage"],
        "code-implementer": _FULL_CATALOG["stages"]["code-implementer"],
        "security-reviewer": _FULL_CATALOG["stages"]["security-reviewer"],
        "test-plan": _FULL_CATALOG["stages"]["test-plan"],
    }
    stages_order_b = {
        "test-plan": _FULL_CATALOG["stages"]["test-plan"],
        "security-reviewer": _FULL_CATALOG["stages"]["security-reviewer"],
        "code-implementer": _FULL_CATALOG["stages"]["code-implementer"],
        "triage": _FULL_CATALOG["stages"]["triage"],
    }
    root_a = _make_repo_root({"stages": stages_order_a})
    root_b = _make_repo_root({"stages": stages_order_b})
    try:
        result_a = audit.build_scorecard(root_a)
        result_b = audit.build_scorecard(root_b)
        assert result_a == result_b, (
            "scorecards must be equal regardless of dict insertion order; "
            f"result_a={result_a!r}, result_b={result_b!r}"
        )
    finally:
        shutil.rmtree(root_a, ignore_errors=True)
        shutil.rmtree(root_b, ignore_errors=True)


# ---------------------------------------------------------------------------
# Group B - Fail-open
# ---------------------------------------------------------------------------


def test_b01_missing_catalog_does_not_raise():
    """B-01: build_scorecard where generated/catalog.json is absent -> no raise."""
    root = Path(tempfile.mkdtemp())
    # Do NOT create generated/catalog.json
    try:
        result = audit.build_scorecard(root)
        assert (
            "overall" in result
        ), "missing catalog: result must still have 'overall' key"
        assert isinstance(
            result["overall"], int
        ), f"missing catalog: overall must be int, got {type(result['overall'])}"
    except Exception as exc:
        raise AssertionError(
            f"build_scorecard must not raise on missing catalog, got {type(exc).__name__}: {exc}"
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_b01_missing_catalog_all_category_scores_are_ints():
    """B-01: missing catalog -> every category score is still an int."""
    root = Path(tempfile.mkdtemp())
    try:
        result = audit.build_scorecard(root)
        for name, cat in result.get("categories", {}).items():
            assert isinstance(cat.get("score"), int), (
                f"missing catalog: category '{name}' score must be int, "
                f"got {type(cat.get('score'))}"
            )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_b03_malformed_catalog_does_not_raise():
    """B-03: malformed catalog.json -> no raise, result has 'overall'."""
    root = Path(tempfile.mkdtemp())
    gen = root / "generated"
    gen.mkdir()
    (gen / "catalog.json").write_text("not valid json {{{")
    try:
        result = audit.build_scorecard(root)
        assert (
            "overall" in result
        ), "malformed catalog: result must still have 'overall' key"
        assert isinstance(
            result["overall"], int
        ), f"malformed catalog: overall must be int, got {type(result['overall'])}"
    except Exception as exc:
        raise AssertionError(
            f"build_scorecard must not raise on malformed catalog, got {type(exc).__name__}: {exc}"
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_b03_malformed_catalog_all_category_scores_are_ints():
    """B-03: malformed catalog.json -> every category score is still an int."""
    root = Path(tempfile.mkdtemp())
    gen = root / "generated"
    gen.mkdir()
    (gen / "catalog.json").write_text("not valid json {{{")
    try:
        result = audit.build_scorecard(root)
        for name, cat in result.get("categories", {}).items():
            assert isinstance(cat.get("score"), int), (
                f"malformed catalog: category '{name}' score must be int, "
                f"got {type(cat.get('score'))}"
            )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_b05_check_catalog_exception_does_not_escape():
    """B-05: monkeypatching check_catalog.check to raise RuntimeError ->
    build_scorecard still returns a dict with 'overall', no exception escapes."""
    import check_catalog

    root = _make_repo_root(_FULL_CATALOG)
    try:
        with mock.patch.object(
            check_catalog, "check", side_effect=RuntimeError("boom")
        ):
            try:
                result = audit.build_scorecard(root)
                assert (
                    "overall" in result
                ), "check() raised: result must still have 'overall' key"
            except Exception as exc:
                raise AssertionError(
                    f"build_scorecard must guard check() exceptions; "
                    f"got {type(exc).__name__}: {exc}"
                )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_b_subprocess_live_repo_exits_0_with_parseable_json():
    """B-subprocess: run audit.py against the live repo -> returncode == 0 and
    stdout contains a parseable JSON block."""
    result = subprocess.run(
        ["python3", str(AUDIT_PY)],
        capture_output=True,
        text=True,
        cwd=str(REAL_REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"audit.py must exit 0; got {result.returncode}; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    # Find the SCORECARD_JSON line and parse the remainder.
    stdout = result.stdout
    scorecard_line = None
    for line in stdout.splitlines():
        if line.startswith("SCORECARD_JSON "):
            scorecard_line = line[len("SCORECARD_JSON ") :]
            break
    assert (
        scorecard_line is not None
    ), f"stdout must contain a 'SCORECARD_JSON ' line; got {stdout!r}"
    try:
        parsed = json.loads(scorecard_line)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"SCORECARD_JSON value is not parseable: {exc}; raw={scorecard_line!r}"
        )
    assert (
        "overall" in parsed
    ), f"parsed SCORECARD_JSON must have 'overall' key; got {parsed!r}"


# ---------------------------------------------------------------------------
# Group C - Scoring
# ---------------------------------------------------------------------------


def test_c_coverage_floor_real_repo():
    """C-coverage-floor: build_scorecard(REAL_REPO_ROOT) -> 'tool/agent coverage' >= 80."""
    result = audit.build_scorecard(REAL_REPO_ROOT)
    score = result["categories"]["tool/agent coverage"]["score"]
    assert (
        score >= 80
    ), f"real repo 'tool/agent coverage' score must be >= 80, got {score}"


def test_c_empty_coverage_low_score():
    """C-empty-coverage: empty stages catalog -> 'tool/agent coverage' <= 20."""
    root = _make_repo_root(_CATALOG_EMPTY_STAGES)
    try:
        result = audit.build_scorecard(root)
        score = result["categories"]["tool/agent coverage"]["score"]
        assert (
            score <= 20
        ), f"empty stages: 'tool/agent coverage' must be <= 20, got {score}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_c_monotonic_quality_gates():
    """C-monotonic-quality: catalog WITH quality-gate stages scores strictly higher
    on 'quality gates' than one WITHOUT."""
    # Catalog with quality gates: has test-plan, correctness-reviewer etc.
    catalog_with = {
        "stages": {
            "test-plan": {
                "routes": ["code"],
                "data": {
                    "input": {"required": [], "optional": []},
                    "output": ["test-cases"],
                },
                "signals": {
                    "subscribes": ["needs-tests"],
                    "publishes": ["test-cases-ready", "scope-shift"],
                },
            },
            "test-verifier": {
                "routes": ["code"],
                "data": {
                    "input": {"required": ["tests"], "optional": []},
                    "output": [],
                },
                "signals": {
                    "subscribes": ["tests-red"],
                    "publishes": ["tests-ready", "scope-shift"],
                },
            },
            "correctness-reviewer": {
                "routes": ["code"],
                "data": {
                    "input": {"required": ["diff"], "optional": []},
                    "output": ["findings"],
                },
                "signals": {
                    "subscribes": ["code-written"],
                    "publishes": ["needs-tests", "scope-shift"],
                },
            },
        }
    }
    catalog_without = {"stages": {}}

    root_with = _make_repo_root(catalog_with)
    root_without = _make_repo_root(catalog_without)
    try:
        score_with = audit.build_scorecard(root_with)["categories"]["quality gates"][
            "score"
        ]
        score_without = audit.build_scorecard(root_without)["categories"][
            "quality gates"
        ]["score"]
        assert score_with > score_without, (
            f"'quality gates' must score strictly higher WITH relevant stages "
            f"({score_with}) than WITHOUT ({score_without})"
        )
    finally:
        shutil.rmtree(root_with, ignore_errors=True)
        shutil.rmtree(root_without, ignore_errors=True)


def test_c_overall_bounds():
    """C-overall-bounds: overall is an int between min and max category scores (inclusive)."""
    root = _make_repo_root(_FULL_CATALOG)
    try:
        result = audit.build_scorecard(root)
        scores = [cat["score"] for cat in result["categories"].values()]
        overall = result["overall"]
        assert isinstance(overall, int), f"overall must be int, got {type(overall)}"
        assert min(scores) <= overall <= max(scores), (
            f"overall ({overall}) must be in [{min(scores)}, {max(scores)}]; "
            f"category scores={scores}"
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_c_range_all_category_scores():
    """C-range: every category score is in [0, 100]."""
    root = _make_repo_root(_FULL_CATALOG)
    try:
        result = audit.build_scorecard(root)
        for name, cat in result["categories"].items():
            score = cat["score"]
            assert (
                0 <= score <= 100
            ), f"category '{name}' score {score} is out of [0, 100]"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_c_range_on_empty_catalog():
    """C-range: every category score in [0, 100] even with an empty catalog."""
    root = _make_repo_root(_CATALOG_EMPTY_STAGES)
    try:
        result = audit.build_scorecard(root)
        for name, cat in result["categories"].items():
            score = cat["score"]
            assert (
                0 <= score <= 100
            ), f"empty catalog: category '{name}' score {score} is out of [0, 100]"
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# Group D - top_fixes ordering
# ---------------------------------------------------------------------------


def _find_category_for_fix(result, fix_str):
    """Return the category name whose fixes list contains fix_str."""
    for name, cat in result["categories"].items():
        if fix_str in cat["fixes"]:
            return name
    return None


def _lowest_scoring_category(result):
    """Return the name of the category with the lowest score (alpha tie-break)."""
    cats = result["categories"]
    return min(cats.keys(), key=lambda n: (cats[n]["score"], n))


def test_d01_worst_category_fix_is_first_in_top_fixes():
    """D-01: the category that scores lowest has its fix at top_fixes[0]."""
    # Use the empty-stages fixture: tool/agent coverage should be lowest
    root = _make_repo_root(_CATALOG_EMPTY_STAGES)
    try:
        result = audit.build_scorecard(root)
        top_fixes = result["top_fixes"]
        if not top_fixes:
            # If no fixes at all, the invariant is vacuously satisfied only if no category
            # has a non-empty fixes list
            all_fixes = [
                f for cat in result["categories"].values() for f in cat["fixes"]
            ]
            assert (
                all_fixes == []
            ), "top_fixes is empty but categories have fixes; ordering invariant violated"
            return

        # Find which category the first fix belongs to
        first_fix = top_fixes[0]
        owning_category = _find_category_for_fix(result, first_fix)
        assert (
            owning_category is not None
        ), f"top_fixes[0]={first_fix!r} does not belong to any category"
        # That category must have the lowest score
        lowest = _lowest_scoring_category(result)
        assert owning_category == lowest, (
            f"top_fixes[0] belongs to '{owning_category}' (score "
            f"{result['categories'][owning_category]['score']}), but the lowest-scoring "
            f"category is '{lowest}' (score {result['categories'][lowest]['score']})"
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_d02_tie_broken_by_category_name_ascending():
    """D-02: when two categories are tied for lowest, the alphabetically-earlier
    category's fix precedes the later one in top_fixes."""
    # Force a tie by using missing catalog (fail-open degrades multiple categories equally)
    root = Path(tempfile.mkdtemp())
    # No generated/catalog.json - multiple categories degrade to the same low score
    try:
        result = audit.build_scorecard(root)
        top_fixes = result["top_fixes"]
        if len(top_fixes) < 2:
            # Cannot test tie-break with fewer than 2 fixes - skip only if no tie exists
            cats = result["categories"]
            scores = [cat["score"] for cat in cats.values()]
            tied = [n for n in cats if cats[n]["score"] == min(scores)]
            if len(tied) < 2:
                return  # no tie to assert
            # There is a tie but top_fixes is too short - fail
            raise AssertionError(
                f"tie exists among {tied} but top_fixes has only {len(top_fixes)} entries"
            )

        # Reconstruct ordering via category scores
        cats = result["categories"]
        scores = [cat["score"] for cat in cats.values()]
        if min(scores) == sorted(scores)[1]:
            # There is a tie at the minimum
            tied_names = sorted(
                [n for n in cats if cats[n]["score"] == min(scores)]
            )  # ascending alpha
            if (
                len(tied_names) >= 2
                and cats[tied_names[0]]["fixes"]
                and cats[tied_names[1]]["fixes"]
            ):
                earlier_fix = cats[tied_names[0]]["fixes"][0]
                later_fix = cats[tied_names[1]]["fixes"][0]
                assert top_fixes.index(earlier_fix) < top_fixes.index(later_fix), (
                    f"tie-break: fix for '{tied_names[0]}' must precede fix for "
                    f"'{tied_names[1]}' in top_fixes; top_fixes={top_fixes!r}"
                )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_d03_all_tied_order_ascending_by_name():
    """D-03: when all categories are tied (empty stages), top_fixes are ordered
    by ascending category name."""
    root = _make_repo_root(_CATALOG_EMPTY_STAGES)
    try:
        result = audit.build_scorecard(root)
        cats = result["categories"]
        scores = [cat["score"] for cat in cats.values()]

        # Only assert ordering if all categories are actually tied
        if len(set(scores)) != 1:
            return  # not all tied; ordering tested by D-01/D-02

        # Build expected order: categories sorted ascending by name, flattened fixes
        sorted_names = sorted(cats.keys())
        expected_order = [f for name in sorted_names for f in cats[name]["fixes"]]

        top_fixes = result["top_fixes"]
        # top_fixes must be a prefix-compatible reordering of expected_order
        # (only fixes that appear in top_fixes need to be checked)
        for i, fix in enumerate(top_fixes):
            assert (
                fix in expected_order
            ), f"top_fixes[{i}]={fix!r} not found in any category fixes"
        # Check that the relative order of fixes from different categories respects alpha order
        for i, fix_i in enumerate(top_fixes):
            cat_i = _find_category_for_fix(result, fix_i)
            for j, fix_j in enumerate(top_fixes):
                if i >= j:
                    continue
                cat_j = _find_category_for_fix(result, fix_j)
                if cat_i != cat_j and cat_i is not None and cat_j is not None:
                    assert cat_i <= cat_j, (
                        f"top_fixes ordering violated: fix from '{cat_i}' at index {i} "
                        f"precedes fix from '{cat_j}' at index {j}, but '{cat_i}' > '{cat_j}' "
                        f"alphabetically; all categories tied so order must be ascending by name"
                    )
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# Group E - Regression tests for targeted fixes
# ---------------------------------------------------------------------------


def test_e01_malformed_shape_does_not_raise():
    """E-01: catalog with a non-dict stage value -> no raise, all scores are ints."""
    malformed = {"stages": {"x": "not-a-dict"}}
    root = _make_repo_root(malformed)
    try:
        result = audit.build_scorecard(root)
        assert isinstance(result, dict), "result must be a dict"
        assert "overall" in result, "result must have 'overall' key"
        for name, cat in result["categories"].items():
            assert isinstance(
                cat["score"], int
            ), f"category '{name}' score must be int when stage is malformed"
    except Exception as exc:
        raise AssertionError(
            f"build_scorecard must not raise on malformed stage shape, "
            f"got {type(exc).__name__}: {exc}"
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_e02_stage_missing_routes_fix_appears():
    """E-02: a stage dict with no 'routes' key -> its fix appears in coverage fixes."""
    no_routes = {"stages": {"my-stage": {"data": {}, "signals": {}}}}
    root = _make_repo_root(no_routes)
    try:
        result = audit.build_scorecard(root)
        coverage_fixes = result["categories"]["tool/agent coverage"]["fixes"]
        matching = [f for f in coverage_fixes if "my-stage" in f and "missing" in f]
        assert matching, (
            f"expected a fix mentioning 'my-stage' and 'missing' in coverage fixes; "
            f"got {coverage_fixes!r}"
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_e03_check_catalog_returns_problems_degrades_coherence():
    """E-03: check_catalog.check() returning problems -> coherence degraded + fix appears."""
    root = _make_repo_root(_FULL_CATALOG)
    try:
        with mock.patch.object(check_catalog, "check", return_value=["a problem"]):
            result = audit.build_scorecard(root)
        coverage_fixes = result["categories"]["tool/agent coverage"]["fixes"]
        assert any("coherence" in f for f in coverage_fixes), (
            f"expected a coherence fix when check() returns problems; "
            f"got {coverage_fixes!r}"
        )
        score = result["categories"]["tool/agent coverage"]["score"]
        assert (
            score < 100
        ), f"coverage score must be degraded when coherence fails, got {score}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# Group F - Fail-open regressions: non-dict top-level and non-dict stages
# ---------------------------------------------------------------------------


def _write_catalog_raw(root, text):
    """Write raw text to root/generated/catalog.json."""
    gen = root / "generated"
    gen.mkdir(exist_ok=True)
    (gen / "catalog.json").write_text(text)


def _assert_fail_open(root, label):
    """Helper: build_scorecard must not raise and every score must be an int."""
    try:
        result = audit.build_scorecard(root)
    except Exception as exc:
        raise AssertionError(
            f"build_scorecard must not raise for {label}; "
            f"got {type(exc).__name__}: {exc}"
        ) from exc
    assert isinstance(result, dict), f"{label}: result must be a dict"
    assert "overall" in result, f"{label}: result must have 'overall' key"
    assert isinstance(
        result["overall"], int
    ), f"{label}: overall must be int, got {type(result['overall'])}"
    for name, cat in result.get("categories", {}).items():
        assert isinstance(cat.get("score"), int), (
            f"{label}: category '{name}' score must be int, "
            f"got {type(cat.get('score'))}"
        )
    return result


def test_f01_top_level_list_catalog_no_raise():
    """F-01: catalog.json containing a JSON array -> no raise, all scores are ints."""
    root = Path(tempfile.mkdtemp())
    try:
        _write_catalog_raw(root, "[1, 2, 3]")
        _assert_fail_open(root, "top-level list catalog")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_f01_top_level_list_subprocess_exits_0():
    """F-01 subprocess: audit.py with a top-level list catalog.json exits 0."""
    root = Path(tempfile.mkdtemp())
    try:
        _write_catalog_raw(root, "[1, 2, 3]")
        result = subprocess.run(
            ["python3", str(AUDIT_PY)],
            capture_output=True,
            text=True,
            cwd=str(root),
            input=json.dumps({"path": str(root)}),
        )
        assert result.returncode == 0, (
            f"audit.py must exit 0 for top-level list catalog; "
            f"got {result.returncode}; stderr={result.stderr!r}"
        )
        assert (
            "SCORECARD_JSON" in result.stdout
        ), f"stdout must contain SCORECARD_JSON; got {result.stdout!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_f02_top_level_string_catalog_no_raise():
    """F-02: catalog.json containing a bare JSON string -> no raise, all scores are ints."""
    root = Path(tempfile.mkdtemp())
    try:
        _write_catalog_raw(root, '"hello"')
        _assert_fail_open(root, "top-level string catalog")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_f03_top_level_int_catalog_no_raise():
    """F-03: catalog.json containing a bare JSON integer -> no raise, all scores are ints."""
    root = Path(tempfile.mkdtemp())
    try:
        _write_catalog_raw(root, "42")
        _assert_fail_open(root, "top-level int catalog")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_f04_stages_is_list_no_raise():
    """F-04: catalog {'stages': [1, 2]} (stages not a dict) -> no raise, all scores are ints."""
    root = Path(tempfile.mkdtemp())
    try:
        _write_catalog_raw(root, json.dumps({"stages": [1, 2]}))
        _assert_fail_open(root, "stages-is-list catalog")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_f04_stages_is_list_scores_degrade_gracefully():
    """F-04: stages-as-list catalog -> 'tool/agent coverage' scores 0 (no stages)."""
    root = Path(tempfile.mkdtemp())
    try:
        _write_catalog_raw(root, json.dumps({"stages": [1, 2]}))
        result = _assert_fail_open(root, "stages-is-list catalog")
        score = result["categories"]["tool/agent coverage"]["score"]
        assert (
            score == 0
        ), f"stages-is-list: 'tool/agent coverage' must score 0, got {score}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# Group G - Health-signal-inversion regression
# ---------------------------------------------------------------------------


def _make_repo_with_hooks(
    hooks_json_content, include_verify_build=True, include_verify_tests=True
):
    """Create a temp repo dir with hooks/hooks.json and optional verify-*.py files."""
    root = Path(tempfile.mkdtemp())
    hooks_dir = root / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "hooks.json").write_text(json.dumps(hooks_json_content))
    if include_verify_build:
        (hooks_dir / "verify-build.py").write_text("# stub")
    if include_verify_tests:
        (hooks_dir / "verify-tests.py").write_text("# stub")
    # Provide an empty generated/catalog.json so catalog path doesn't interfere.
    _write_stub_catalog(root)
    return root


def test_g01_verify_build_file_absent_lower_score():
    """G-01: hooks.json registers 'verify-build' but verify-build.py is absent
    -> 'quality gates' score is strictly lower than when the file is present."""
    hooks_text = {"hooks": ["verify-build", "verify-tests"]}

    root_present = _make_repo_with_hooks(
        hooks_text, include_verify_build=True, include_verify_tests=True
    )
    root_absent = _make_repo_with_hooks(
        hooks_text, include_verify_build=False, include_verify_tests=True
    )
    try:
        score_present = audit.build_scorecard(root_present)["categories"][
            "quality gates"
        ]["score"]
        score_absent = audit.build_scorecard(root_absent)["categories"][
            "quality gates"
        ]["score"]
        assert score_present > score_absent, (
            f"'quality gates' score with verify-build.py present ({score_present}) "
            f"must be strictly higher than when absent ({score_absent}); "
            f"the .is_file() check must be part of the condition"
        )
        # Also verify a fix surfaces when the file is absent.
        fixes_absent = audit.build_scorecard(root_absent)["categories"][
            "quality gates"
        ]["fixes"]
        assert any("verify-build" in f for f in fixes_absent), (
            f"expected a fix mentioning 'verify-build' when file is absent; "
            f"got {fixes_absent!r}"
        )
    finally:
        shutil.rmtree(root_present, ignore_errors=True)
        shutil.rmtree(root_absent, ignore_errors=True)


def test_g02_verify_tests_file_absent_lower_score():
    """G-02: hooks.json registers 'verify-tests' but verify-tests.py is absent
    -> 'quality gates' score is strictly lower than when the file is present."""
    hooks_text = {"hooks": ["verify-build", "verify-tests"]}

    root_present = _make_repo_with_hooks(
        hooks_text, include_verify_build=True, include_verify_tests=True
    )
    root_absent = _make_repo_with_hooks(
        hooks_text, include_verify_build=True, include_verify_tests=False
    )
    try:
        score_present = audit.build_scorecard(root_present)["categories"][
            "quality gates"
        ]["score"]
        score_absent = audit.build_scorecard(root_absent)["categories"][
            "quality gates"
        ]["score"]
        assert score_present > score_absent, (
            f"'quality gates' score with verify-tests.py present ({score_present}) "
            f"must be strictly higher than when absent ({score_absent}); "
            f"the .is_file() check must be part of the condition"
        )
        fixes_absent = audit.build_scorecard(root_absent)["categories"][
            "quality gates"
        ]["fixes"]
        assert any("verify-tests" in f for f in fixes_absent), (
            f"expected a fix mentioning 'verify-tests' when file is absent; "
            f"got {fixes_absent!r}"
        )
    finally:
        shutil.rmtree(root_present, ignore_errors=True)
        shutil.rmtree(root_absent, ignore_errors=True)


# ---------------------------------------------------------------------------
# Group H - Doctrine integrity scorer (_score_doctrine_integrity)
# ---------------------------------------------------------------------------


def _get_phrase_for(relpath):
    """Return the canary phrase paired to relpath from audit.DOCTRINE_PHRASES (dynamic)."""
    for phrase, rel in audit.DOCTRINE_PHRASES:
        if rel == relpath:
            return phrase
    return None


def _make_doctrine_root(
    tmp_path,
    workflow_content=None,
    code_doctrine_content=None,
    claude_md_content=None,
    briefs_content=None,
    include_workflow=True,
    include_code_doctrine=True,
    include_claude_md=True,
    include_briefs=True,
):
    """Build a minimal repo root in tmp_path with controlled doctrine files.

    workflow_content, code_doctrine_content, and claude_md_content default to
    strings that contain all required phrases when not specified.  Pass a custom
    string to control presence/absence of individual phrases.  Pass
    include_workflow=False / include_code_doctrine=False / include_claude_md=False
    to omit the file entirely.

    claude_md_content defaults to a string that includes the canary phrase read
    dynamically from audit.DOCTRINE_PHRASES, so tests remain robust to the exact
    token choice.
    """
    if workflow_content is None:
        workflow_content = (
            "# WORKFLOW\n"
            "trivial code: only when est-size > S blah blah\n"
            "auto-publish iff the plan touches <=1 file AND est-size <= S\n"
        )
    if code_doctrine_content is None:
        code_doctrine_content = (
            "# code-doctrine\n"
            "Each task must have ONE runnable check before work starts.\n"
        )
    if claude_md_content is None:
        # Build content that includes the canary phrase dynamically.
        canary = _get_phrase_for("CLAUDE.md")
        if canary is not None:
            claude_md_content = f"# Doctrine hygiene\n{canary}\n"
        else:
            # If no CLAUDE.md entry exists yet, write a placeholder (will fail
            # phrase checks, which is correct for a not-yet-implemented test).
            claude_md_content = "# CLAUDE.md\n(placeholder - no canary phrase found)\n"
    if briefs_content is None:
        # Build content that includes the briefs leitwort dynamically,
        # mirroring the claude_md default so a green-path root scores 100.
        leitwort = _get_phrase_for("doctrine/briefs.md")
        if leitwort is not None:
            briefs_content = f"# Briefs\n{leitwort}\n"
        else:
            briefs_content = "# briefs\n(placeholder - no leitwort phrase found)\n"

    if include_workflow:
        (tmp_path / "WORKFLOW.md").write_text(workflow_content, encoding="utf-8")

    doctrine_dir = tmp_path / "doctrine"
    doctrine_dir.mkdir(exist_ok=True)
    if include_code_doctrine:
        (doctrine_dir / "code-doctrine.md").write_text(
            code_doctrine_content, encoding="utf-8"
        )
    if include_briefs:
        (doctrine_dir / "briefs.md").write_text(briefs_content, encoding="utf-8")

    if include_claude_md:
        (tmp_path / "CLAUDE.md").write_text(claude_md_content, encoding="utf-8")

    # Provide a stub catalog so other scorers do not interfere.
    _write_stub_catalog(tmp_path)

    return tmp_path


def test_h01_scorer_is_callable():
    """H-01: audit._score_doctrine_integrity exists and is callable."""
    assert callable(
        audit._score_doctrine_integrity
    ), "_score_doctrine_integrity must be a callable on the audit module"


def test_h02_scorer_accepts_root_returns_tuple(tmp_path):
    """H-02: _score_doctrine_integrity(root) returns (int, list)."""
    root = _make_doctrine_root(tmp_path)
    result = audit._score_doctrine_integrity(root)
    assert (
        isinstance(result, tuple) and len(result) == 2
    ), f"expected (int, list) 2-tuple, got {result!r}"
    score, fixes = result
    assert isinstance(score, int), f"score must be int, got {type(score)}"
    assert isinstance(fixes, list), f"fixes must be list, got {type(fixes)}"


def test_h03_green_path_all_phrases_present(tmp_path):
    """H-03: WORKFLOW.md has both est-size phrases, code-doctrine.md has ONE runnable check
    -> score 100 and empty fixes list."""
    root = _make_doctrine_root(tmp_path)
    score, fixes = audit._score_doctrine_integrity(root)
    assert score == 100, f"all phrases present: expected score 100, got {score}"
    assert fixes == [], f"all phrases present: expected empty fixes, got {fixes!r}"


def test_h04_missing_workflow_est_size_lte_s_phrase_gives_zero(tmp_path):
    """H-04: WORKFLOW.md missing 'est-size <= S' -> score 0 and non-empty fixes."""
    root = _make_doctrine_root(
        tmp_path,
        workflow_content=(
            "# WORKFLOW\n"
            "trivial code: only when est-size > S blah blah\n"
            # 'est-size <= S' intentionally absent
        ),
    )
    score, fixes = audit._score_doctrine_integrity(root)
    assert score == 0, f"missing 'est-size <= S': expected score 0, got {score}"
    assert len(fixes) > 0, "missing 'est-size <= S': expected non-empty fixes"


def test_h05_missing_workflow_est_size_gt_s_phrase_gives_zero(tmp_path):
    """H-05: WORKFLOW.md missing 'est-size > S' -> score 0 and non-empty fixes."""
    root = _make_doctrine_root(
        tmp_path,
        workflow_content=(
            "# WORKFLOW\n"
            # 'est-size > S' intentionally absent
            "auto-publish iff the plan touches <=1 file AND est-size <= S\n"
        ),
    )
    score, fixes = audit._score_doctrine_integrity(root)
    assert score == 0, f"missing 'est-size > S': expected score 0, got {score}"
    assert len(fixes) > 0, "missing 'est-size > S': expected non-empty fixes"


def test_h06_missing_one_runnable_check_phrase_gives_zero(tmp_path):
    """H-06: doctrine/code-doctrine.md missing 'ONE runnable check' -> score 0 and non-empty fixes."""
    root = _make_doctrine_root(
        tmp_path,
        code_doctrine_content=(
            "# code-doctrine\n"
            "Each task must have a runnable check before work starts.\n"
            # 'ONE runnable check' intentionally absent
        ),
    )
    score, fixes = audit._score_doctrine_integrity(root)
    assert score == 0, f"missing 'ONE runnable check': expected score 0, got {score}"
    assert len(fixes) > 0, "missing 'ONE runnable check': expected non-empty fixes"


def test_h07_all_phrases_absent_score_zero(tmp_path):
    """H-07: all three required phrases absent -> score 0."""
    root = _make_doctrine_root(
        tmp_path,
        workflow_content="# WORKFLOW\nno relevant phrases here\n",
        code_doctrine_content="# code-doctrine\nno relevant phrases here\n",
    )
    score, fixes = audit._score_doctrine_integrity(root)
    assert score == 0, f"all phrases absent: expected score 0, got {score}"


def test_h12_all_phrases_absent_exactly_five_fixes(tmp_path):
    """H-12: all required phrases absent -> one problem string per table entry (5 entries)."""
    root = _make_doctrine_root(
        tmp_path,
        workflow_content="# WORKFLOW\nno relevant phrases here\n",
        code_doctrine_content="# code-doctrine\nno relevant phrases here\n",
        claude_md_content="# CLAUDE.md\nno relevant phrases here\n",
        briefs_content="# briefs\nno relevant phrases here\n",
    )
    _, fixes = audit._score_doctrine_integrity(root)
    assert len(fixes) == len(audit.DOCTRINE_PHRASES), (
        f"all phrases absent: expected one fix per pinned phrase "
        f"({len(audit.DOCTRINE_PHRASES)}), got {len(fixes)}: {fixes!r}"
    )


def test_h08_missing_lte_fix_mentions_phrase_and_file(tmp_path):
    """H-08: missing 'est-size <= S' -> a fix string contains both phrase and 'WORKFLOW.md'."""
    root = _make_doctrine_root(
        tmp_path,
        workflow_content=(
            "# WORKFLOW\n"
            "trivial code: only when est-size > S blah blah\n"
            # 'est-size <= S' intentionally absent
        ),
    )
    _, fixes = audit._score_doctrine_integrity(root)
    matching = [f for f in fixes if "est-size <= S" in f and "WORKFLOW.md" in f]
    assert matching, (
        f"missing 'est-size <= S': expected a fix containing both 'est-size <= S' "
        f"and 'WORKFLOW.md'; got fixes={fixes!r}"
    )


def test_h08b_missing_est_size_gt_fix_mentions_phrase_and_file(tmp_path):
    """H-08b: missing 'est-size > S' -> a fix string contains both phrase and 'WORKFLOW.md'."""
    root = _make_doctrine_root(
        tmp_path,
        workflow_content=(
            "# WORKFLOW\n"
            # 'est-size > S' intentionally absent
            "auto-publish iff the plan touches <=1 file AND est-size <= S\n"
        ),
    )
    _, fixes = audit._score_doctrine_integrity(root)
    matching = [f for f in fixes if "est-size > S" in f and "WORKFLOW.md" in f]
    assert matching, (
        f"missing 'est-size > S': expected a fix containing both 'est-size > S' "
        f"and 'WORKFLOW.md'; got fixes={fixes!r}"
    )


def test_h09_missing_one_runnable_check_fix_mentions_phrase_and_file(tmp_path):
    """H-09: missing 'ONE runnable check' -> a fix string contains phrase and file path."""
    root = _make_doctrine_root(
        tmp_path,
        code_doctrine_content="# code-doctrine\nno relevant phrases here\n",
    )
    _, fixes = audit._score_doctrine_integrity(root)
    matching = [
        f
        for f in fixes
        if "ONE runnable check" in f and "doctrine/code-doctrine.md" in f
    ]
    assert matching, (
        f"missing 'ONE runnable check': expected a fix containing both "
        f"'ONE runnable check' and 'doctrine/code-doctrine.md'; got fixes={fixes!r}"
    )


def test_h10_workflow_md_absent_no_raise_score_zero(tmp_path):
    """H-10: WORKFLOW.md file entirely absent -> no raise, score 0, non-empty fixes."""
    root = _make_doctrine_root(tmp_path, include_workflow=False)
    try:
        score, fixes = audit._score_doctrine_integrity(root)
    except Exception as exc:
        raise AssertionError(
            f"_score_doctrine_integrity must not raise when WORKFLOW.md is absent; "
            f"got {type(exc).__name__}: {exc}"
        ) from exc
    assert score == 0, f"WORKFLOW.md absent: expected score 0, got {score}"
    assert len(fixes) > 0, "WORKFLOW.md absent: expected non-empty fixes"


def test_h10c_non_utf8_file_no_raise(tmp_path):
    """H-10c: doctrine/WORKFLOW.md contains invalid UTF-8 bytes -> _score_doctrine_integrity
    does NOT raise, returns score 0, and fixes is non-empty."""
    root = _make_doctrine_root(tmp_path)
    # Overwrite WORKFLOW.md with bytes that are not valid UTF-8.
    (root / "WORKFLOW.md").write_bytes(b"\xff\xfe not utf-8")
    try:
        score, fixes = audit._score_doctrine_integrity(root)
    except Exception as exc:
        raise AssertionError(
            f"_score_doctrine_integrity must not raise on non-UTF-8 file; "
            f"got {type(exc).__name__}: {exc}"
        ) from exc
    assert score == 0, f"non-UTF-8 WORKFLOW.md: expected score 0, got {score}"
    assert len(fixes) > 0, "non-UTF-8 WORKFLOW.md: expected non-empty fixes"


def test_h11_code_doctrine_absent_no_raise_score_zero(tmp_path):
    """H-11: doctrine/code-doctrine.md absent -> no raise, score 0, non-empty fixes."""
    root = _make_doctrine_root(tmp_path, include_code_doctrine=False)
    try:
        score, fixes = audit._score_doctrine_integrity(root)
    except Exception as exc:
        raise AssertionError(
            f"_score_doctrine_integrity must not raise when code-doctrine.md is absent; "
            f"got {type(exc).__name__}: {exc}"
        ) from exc
    assert score == 0, f"code-doctrine.md absent: expected score 0, got {score}"
    assert len(fixes) > 0, "code-doctrine.md absent: expected non-empty fixes"


def test_h13_read_text_raises_does_not_raise_returns_zero(tmp_path):
    """H-13: monkeypatch Path.read_text to raise OSError -> _score_doctrine_integrity
    does NOT raise, returns score 0, and fixes is non-empty (all phrases read as missing
    because _read_file swallows the OSError and returns "").
    """
    root = _make_doctrine_root(tmp_path)
    with mock.patch.object(Path, "read_text", side_effect=OSError("injected")):
        try:
            score, fixes = audit._score_doctrine_integrity(root)
        except Exception as exc:
            raise AssertionError(
                f"_score_doctrine_integrity must not propagate when read_text raises; "
                f"got {type(exc).__name__}: {exc}"
            ) from exc
    assert score == 0, f"read_text raises: expected score 0, got {score}"
    assert (
        len(fixes) > 0
    ), f"read_text raises: expected non-empty fixes (all phrases missing); got {fixes!r}"


def test_h14_read_text_raises_build_scorecard_still_returns_all_keys(tmp_path):
    """H-14: monkeypatch Path.read_text to raise -> build_scorecard still returns a dict
    with all required keys and 'doctrine integrity' score is int 0 (no sentinel assertion -
    OSError is swallowed by _read_file, all phrases read as missing, score degrades to 0).
    """
    root = _make_doctrine_root(tmp_path)
    with mock.patch.object(Path, "read_text", side_effect=OSError("injected")):
        try:
            result = audit.build_scorecard(root)
        except Exception as exc:
            raise AssertionError(
                f"build_scorecard must not raise when read_text raises; "
                f"got {type(exc).__name__}: {exc}"
            ) from exc
    assert isinstance(result, dict), "result must be a dict"
    assert "overall" in result, "result must have 'overall' key"
    assert "categories" in result, "result must have 'categories' key"
    assert "doctrine integrity" in result.get(
        "categories", {}
    ), "result['categories'] must contain 'doctrine integrity'"
    di_score = result["categories"]["doctrine integrity"]["score"]
    assert isinstance(
        di_score, int
    ), f"'doctrine integrity' score must be int, got {type(di_score)}"
    assert (
        di_score == 0
    ), f"'doctrine integrity' score must be 0 when read_text raises, got {di_score}"


def test_h15_build_scorecard_categories_has_eight_entries(tmp_path):
    """H-15: build_scorecard(root)['categories'] has exactly 8 entries."""
    root = _make_doctrine_root(tmp_path)
    result = audit.build_scorecard(root)
    assert len(result["categories"]) == 8, (
        f"expected exactly 8 category entries, got {len(result['categories'])}: "
        f"{list(result['categories'].keys())}"
    )


def test_h16_build_scorecard_includes_doctrine_integrity(tmp_path):
    """H-16: build_scorecard(root)['categories'] includes 'doctrine integrity'."""
    root = _make_doctrine_root(tmp_path)
    result = audit.build_scorecard(root)
    assert "doctrine integrity" in result["categories"], (
        f"'doctrine integrity' must be in categories; "
        f"got {list(result['categories'].keys())}"
    )


def test_h17_doctrine_integrity_entry_has_score_and_fixes(tmp_path):
    """H-17: 'doctrine integrity' entry has score (int) and fixes (list)."""
    root = _make_doctrine_root(tmp_path)
    result = audit.build_scorecard(root)
    cat = result["categories"].get("doctrine integrity", {})
    assert "score" in cat, "'doctrine integrity' category missing 'score' key"
    assert "fixes" in cat, "'doctrine integrity' category missing 'fixes' key"
    assert isinstance(
        cat["score"], int
    ), f"'doctrine integrity' score must be int, got {type(cat['score'])}"
    assert isinstance(
        cat["fixes"], list
    ), f"'doctrine integrity' fixes must be list, got {type(cat['fixes'])}"


def test_h18_doctrine_integrity_score_in_range(tmp_path):
    """H-18: 'doctrine integrity' score is in [0, 100]."""
    root = _make_doctrine_root(tmp_path)
    result = audit.build_scorecard(root)
    score = result["categories"]["doctrine integrity"]["score"]
    assert 0 <= score <= 100, f"'doctrine integrity' score {score} is out of [0, 100]"


def test_h19_live_repo_doctrine_integrity_score_100():
    """H-19: build_scorecard(REAL_REPO_ROOT)['categories']['doctrine integrity']['score'] == 100.
    RED until BOTH _score_doctrine_integrity is implemented AND M1 adds
    'ONE runnable check' to doctrine/code-doctrine.md."""
    result = audit.build_scorecard(REAL_REPO_ROOT)
    assert (
        "doctrine integrity" in result["categories"]
    ), "'doctrine integrity' must be in live-repo scorecard categories"
    score = result["categories"]["doctrine integrity"]["score"]
    assert score == 100, (
        f"live repo 'doctrine integrity' must score 100; got {score} "
        f"(RED until scorer is wired AND 'ONE runnable check' is in code-doctrine.md)"
    )


def test_h20_subprocess_live_repo_exits_0_with_doctrine_integrity():
    """H-20: audit.py subprocess on live repo still exits 0."""
    result = subprocess.run(
        ["python3", str(AUDIT_PY)],
        capture_output=True,
        text=True,
        cwd=str(REAL_REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"audit.py must exit 0; got {result.returncode}; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_h21_subprocess_scorecard_json_has_doctrine_integrity():
    """H-21: SCORECARD_JSON from audit.py subprocess has 'doctrine integrity' nested under categories."""
    result = subprocess.run(
        ["python3", str(AUDIT_PY)],
        capture_output=True,
        text=True,
        cwd=str(REAL_REPO_ROOT),
    )
    scorecard_line = None
    for line in result.stdout.splitlines():
        if line.startswith("SCORECARD_JSON "):
            scorecard_line = line[len("SCORECARD_JSON ") :]
            break
    assert (
        scorecard_line is not None
    ), f"stdout must contain a 'SCORECARD_JSON ' line; got {result.stdout!r}"
    parsed = json.loads(scorecard_line)
    assert "doctrine integrity" in parsed.get("categories", {}), (
        f"parsed SCORECARD_JSON must have 'doctrine integrity' under categories; "
        f"got categories={list(parsed.get('categories', {}).keys())}"
    )


# ---------------------------------------------------------------------------
# Canary + DOCTRINE_PHRASES tests
# ---------------------------------------------------------------------------


def test_phrases_length_is_five():
    """PHRASES-01: audit.DOCTRINE_PHRASES has exactly 5 entries (4 prior + briefs)."""
    assert len(audit.DOCTRINE_PHRASES) == 5, (
        f"DOCTRINE_PHRASES must have exactly 5 entries "
        f"(3 originals + CLAUDE.md + briefs); "
        f"got {len(audit.DOCTRINE_PHRASES)}: {audit.DOCTRINE_PHRASES!r}"
    )


def test_phrases_exactly_one_claude_md_entry():
    """PHRASES-02: exactly one DOCTRINE_PHRASES entry is paired to 'CLAUDE.md'."""
    claude_entries = [
        (phrase, relpath)
        for phrase, relpath in audit.DOCTRINE_PHRASES
        if relpath == "CLAUDE.md"
    ]
    assert len(claude_entries) == 1, (
        f"expected exactly one DOCTRINE_PHRASES entry paired to 'CLAUDE.md'; "
        f"got {claude_entries!r} from {audit.DOCTRINE_PHRASES!r}"
    )


def test_phrases_claude_md_canary_is_nonempty():
    """PHRASES-03: the CLAUDE.md canary phrase is a non-empty string."""
    canary = _get_phrase_for("CLAUDE.md")
    assert (
        canary is not None
    ), "no DOCTRINE_PHRASES entry is paired to 'CLAUDE.md' - implementer must add one"
    assert (
        len(canary.strip()) > 0
    ), f"CLAUDE.md canary phrase must be a non-empty string; got {canary!r}"


def test_phrases_canary_absent_doctrine_integrity_scores_zero(tmp_path):
    """PHRASES-04: CLAUDE.md present but with the 4th canary phrase removed ->
    _score_doctrine_integrity returns 0 and the fix mentions the phrase and CLAUDE.md.
    """
    canary = _get_phrase_for("CLAUDE.md")
    assert (
        canary is not None
    ), "no CLAUSE.md phrase in DOCTRINE_PHRASES - RED by missing impl"

    # Write CLAUDE.md WITHOUT the canary phrase.
    root = _make_doctrine_root(
        tmp_path,
        claude_md_content="# Doctrine hygiene\nno canary here\n",
    )
    score, fixes = audit._score_doctrine_integrity(root)
    assert score == 0, f"CLAUDE.md missing canary phrase: expected score 0, got {score}"
    matching = [f for f in fixes if canary in f and "CLAUDE.md" in f]
    assert matching, (
        f"expected a fix mentioning the canary phrase {canary!r} and 'CLAUDE.md'; "
        f"got fixes={fixes!r}"
    )


def test_phrases_canary_present_prose_reword_still_100(tmp_path):
    """PHRASES-05: CLAUDE.md has the canary phrase present (even inside a reworded sentence) ->
    _score_doctrine_integrity still returns 100 (substring match, not exact-line match).
    """
    canary = _get_phrase_for("CLAUDE.md")
    assert (
        canary is not None
    ), "no CLAUSE.md phrase in DOCTRINE_PHRASES - RED by missing impl"

    root = _make_doctrine_root(
        tmp_path,
        # The canary token is present inside extra prose - should still pass.
        claude_md_content=(
            "# Doctrine hygiene\n"
            f"This section ensures {canary} is preserved as a load-bearing canary.\n"
        ),
    )
    score, fixes = audit._score_doctrine_integrity(root)
    assert score == 100, (
        f"CLAUDE.md with canary phrase present (inside prose): expected score 100, "
        f"got {score}; fixes={fixes!r}"
    )


def test_phrases_claude_md_absent_scores_zero(tmp_path):
    """PHRASES-06: CLAUDE.md file entirely absent -> _score_doctrine_integrity returns 0,
    no raise, and fixes mentions the missing canary."""
    canary = _get_phrase_for("CLAUDE.md")
    assert (
        canary is not None
    ), "no CLAUSE.md phrase in DOCTRINE_PHRASES - RED by missing impl"

    root = _make_doctrine_root(tmp_path, include_claude_md=False)
    try:
        score, fixes = audit._score_doctrine_integrity(root)
    except Exception as exc:
        raise AssertionError(
            f"_score_doctrine_integrity must not raise when CLAUDE.md is absent; "
            f"got {type(exc).__name__}: {exc}"
        ) from exc
    assert score == 0, f"CLAUDE.md absent: expected score 0, got {score}"
    matching = [f for f in fixes if "CLAUDE.md" in f]
    assert (
        matching
    ), f"expected a fix mentioning 'CLAUDE.md' when it is absent; got fixes={fixes!r}"


# ---------------------------------------------------------------------------
# Group I - Doctrine hygiene scorer (_score_doctrine_hygiene)
# ---------------------------------------------------------------------------


def _make_hygiene_root(tmp_path, agents_files=None, doctrine_files=None):
    """Build a temp root with agents/ and doctrine/ dirs populated from dicts.

    agents_files: {filename: content_str} - written into agents/
    doctrine_files: {filename: content_str} - written into doctrine/
    Both default to empty dicts (no files).
    """
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(exist_ok=True)
    doctrine_dir = tmp_path / "doctrine"
    doctrine_dir.mkdir(exist_ok=True)

    for fname, content in (agents_files or {}).items():
        (agents_dir / fname).write_text(content, encoding="utf-8")

    for fname, content in (doctrine_files or {}).items():
        (doctrine_dir / fname).write_text(content, encoding="utf-8")

    _write_stub_catalog(tmp_path)
    return tmp_path


def test_i01_scorer_is_callable():
    """I-01: audit._score_doctrine_hygiene exists and is callable."""
    assert callable(
        audit._score_doctrine_hygiene
    ), "_score_doctrine_hygiene must be a callable on the audit module"


def test_i02_scorer_returns_int_list_tuple(tmp_path):
    """I-02: _score_doctrine_hygiene(root) returns (int, list)."""
    root = _make_hygiene_root(tmp_path)
    result = audit._score_doctrine_hygiene(root)
    assert (
        isinstance(result, tuple) and len(result) == 2
    ), f"expected (int, list) 2-tuple, got {result!r}"
    score, offenders = result
    assert isinstance(score, int), f"score must be int, got {type(score)}"
    assert isinstance(offenders, list), f"offenders must be list, got {type(offenders)}"


def test_i03_clean_root_scores_100(tmp_path):
    """I-03: agents/ and doctrine/ have no cross-file duplicates -> score 100, empty offenders."""
    root = _make_hygiene_root(
        tmp_path,
        agents_files={
            "alpha.md": (
                "# Alpha Agent\n"
                "MUST produce a unique output specific to alpha.\n"
                "This line is alpha-only.\n"
            ),
            "beta.md": (
                "# Beta Agent\n"
                "MUST produce a unique output specific to beta.\n"
                "This line is beta-only.\n"
            ),
        },
        doctrine_files={
            "gamma.md": ("# Gamma Doctrine\n" "Guidance exclusive to gamma.\n"),
        },
    )
    score, offenders = audit._score_doctrine_hygiene(root)
    assert (
        score == 100
    ), f"no cross-file duplicates: expected score 100, got {score}; offenders={offenders!r}"
    assert (
        offenders == []
    ), f"no cross-file duplicates: expected empty offenders, got {offenders!r}"


def test_i04_one_cross_file_duplicate_degrades_score(tmp_path):
    """I-04: one instruction line duplicated across agents/ and doctrine/ -> score < 100
    and offenders list names both files."""
    shared_line = "MUST validate all inputs before processing."
    root = _make_hygiene_root(
        tmp_path,
        agents_files={
            "agent-one.md": (
                "# Agent One\n" f"{shared_line}\n" "Unique line for agent-one only.\n"
            ),
        },
        doctrine_files={
            "doctrine-one.md": (
                "# Doctrine One\n"
                f"{shared_line}\n"
                "Unique line for doctrine-one only.\n"
            ),
        },
    )
    score, offenders = audit._score_doctrine_hygiene(root)
    assert score < 100, f"one cross-file duplicate: expected score < 100, got {score}"
    # Both files must be named in the offenders.
    offender_text = " ".join(str(o) for o in offenders)
    assert (
        "agent-one.md" in offender_text
    ), f"offenders must name 'agent-one.md'; got offenders={offenders!r}"
    assert (
        "doctrine-one.md" in offender_text
    ), f"offenders must name 'doctrine-one.md'; got offenders={offenders!r}"


def test_i05_proportional_degradation(tmp_path):
    """I-05: k of N instruction lines duplicated -> score proportional to (N-k)/N."""
    unique_line_a = "Unique directive for file-a only, no match elsewhere."
    unique_line_b = "Unique directive for file-b only, also no match elsewhere."
    dup_line_1 = "MUST sanitize user input on every entry point always."
    dup_line_2 = "NEVER expose internal error messages to end users directly."

    root = _make_hygiene_root(
        tmp_path,
        agents_files={
            "file-a.md": (
                "# File A\n" f"{unique_line_a}\n" f"{dup_line_1}\n" f"{dup_line_2}\n"
            ),
        },
        doctrine_files={
            "file-b.md": (
                "# File B\n" f"{unique_line_b}\n" f"{dup_line_1}\n" f"{dup_line_2}\n"
            ),
        },
    )
    score, offenders = audit._score_doctrine_hygiene(root)
    # Score must be strictly between 0 and 100 (some unique, some duplicated).
    assert (
        0 < score < 100
    ), f"k-of-N partial duplicates: expected score in (0, 100), got {score}"
    assert (
        len(offenders) > 0
    ), f"k-of-N partial duplicates: expected non-empty offenders, got {offenders!r}"


def test_i06_cross_reference_lines_excluded(tmp_path):
    """I-06: lines starting 'See doctrine/...' are explicit cross-references and must
    NOT be flagged as duplicates even if identical across files."""
    cross_ref = "See doctrine/SIGNALS.md for the canonical signal vocabulary."
    root = _make_hygiene_root(
        tmp_path,
        agents_files={
            "agent-x.md": (
                "# Agent X\n"
                "MUST perform unique action for agent-x.\n"
                f"{cross_ref}\n"
            ),
        },
        doctrine_files={
            "doctrine-x.md": (
                "# Doctrine X\n" "Guidance exclusive to doctrine-x.\n" f"{cross_ref}\n"
            ),
        },
    )
    score, offenders = audit._score_doctrine_hygiene(root)
    assert score == 100, (
        f"cross-reference lines must be excluded from duplicate check; "
        f"score={score}, offenders={offenders!r}"
    )
    assert (
        offenders == []
    ), f"cross-reference lines must not appear in offenders; got {offenders!r}"


def test_i07_missing_file_fail_open_no_raise(tmp_path):
    """I-07: agents/ dir missing entirely -> no raise, score is conservative (0 or low),
    offenders is a list."""
    # Do NOT create agents/ dir - just an empty root.
    root = tmp_path
    _write_stub_catalog(root)
    try:
        score, offenders = audit._score_doctrine_hygiene(root)
    except Exception as exc:
        raise AssertionError(
            f"_score_doctrine_hygiene must not raise when agents/ is absent; "
            f"got {type(exc).__name__}: {exc}"
        ) from exc
    assert isinstance(
        score, int
    ), f"score must be int even with missing dir; got {type(score)}"
    assert isinstance(offenders, list), f"offenders must be list; got {type(offenders)}"


def test_i08_non_utf8_file_fail_open(tmp_path):
    """I-08: an agents/ file with invalid UTF-8 bytes -> no raise, conservative score
    (the file's items count as failing), offenders is non-empty."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    bad_file = agents_dir / "corrupt.md"
    bad_file.write_bytes(b"\xff\xfe MUST do something important\n")

    # Also write a normal doctrine file with the same instruction.
    doctrine_dir = tmp_path / "doctrine"
    doctrine_dir.mkdir()
    (doctrine_dir / "normal.md").write_text(
        "# Normal\nMUST do something important\n", encoding="utf-8"
    )
    _write_stub_catalog(tmp_path)

    try:
        score, offenders = audit._score_doctrine_hygiene(tmp_path)
    except Exception as exc:
        raise AssertionError(
            f"_score_doctrine_hygiene must not raise on non-UTF-8 file; "
            f"got {type(exc).__name__}: {exc}"
        ) from exc
    assert isinstance(
        score, int
    ), f"score must be int even with non-UTF-8 file; got {type(score)}"
    assert isinstance(offenders, list), f"offenders must be list; got {type(offenders)}"
    # Conservative: the non-readable file's items count as failing.
    assert (
        score < 100
    ), f"non-UTF-8 file: score must be conservative (< 100), got {score}"


def test_i09_build_scorecard_includes_doctrine_hygiene(tmp_path):
    """I-09: build_scorecard(root)['categories'] includes 'doctrine hygiene'."""
    root = _make_hygiene_root(tmp_path)
    result = audit.build_scorecard(root)
    assert "doctrine hygiene" in result["categories"], (
        f"'doctrine hygiene' must be in categories; "
        f"got {list(result['categories'].keys())}"
    )


def test_i10_build_scorecard_doctrine_hygiene_degrades_on_duplicate(tmp_path):
    """I-10: build_scorecard with a cross-file duplicate -> 'doctrine hygiene' < 100."""
    shared_line = "MUST always sanitize external inputs without exception."
    root = _make_hygiene_root(
        tmp_path,
        agents_files={
            "agt.md": f"# Agt\n{shared_line}\nUnique for agt.\n",
        },
        doctrine_files={
            "doc.md": f"# Doc\n{shared_line}\nUnique for doc.\n",
        },
    )
    result = audit.build_scorecard(root)
    score = result["categories"]["doctrine hygiene"]["score"]
    assert (
        score < 100
    ), f"cross-file duplicate: 'doctrine hygiene' must score < 100, got {score}"


# ---------------------------------------------------------------------------
# Group J - Why-anchor coverage scorer (_score_why_anchor)
# ---------------------------------------------------------------------------


def _make_why_anchor_root(tmp_path, agents_files=None, doctrine_files=None):
    """Build a temp root for why-anchor tests."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(exist_ok=True)
    doctrine_dir = tmp_path / "doctrine"
    doctrine_dir.mkdir(exist_ok=True)

    for fname, content in (agents_files or {}).items():
        (agents_dir / fname).write_text(content, encoding="utf-8")

    for fname, content in (doctrine_files or {}).items():
        (doctrine_dir / fname).write_text(content, encoding="utf-8")

    _write_stub_catalog(tmp_path)
    return tmp_path


def test_j01_scorer_is_callable():
    """J-01: audit._score_why_anchor exists and is callable."""
    assert callable(
        audit._score_why_anchor
    ), "_score_why_anchor must be a callable on the audit module"


def test_j02_scorer_returns_int_list_tuple(tmp_path):
    """J-02: _score_why_anchor(root) returns (int, list)."""
    root = _make_why_anchor_root(tmp_path)
    result = audit._score_why_anchor(root)
    assert (
        isinstance(result, tuple) and len(result) == 2
    ), f"expected (int, list) 2-tuple, got {result!r}"
    score, offenders = result
    assert isinstance(score, int), f"score must be int, got {type(score)}"
    assert isinstance(offenders, list), f"offenders must be list, got {type(offenders)}"


def test_j03_all_anchored_scores_100(tmp_path):
    """J-03: all load-bearing directives have an adjacent rationale marker -> score 100."""
    root = _make_why_anchor_root(
        tmp_path,
        agents_files={
            "agent-anchored.md": (
                "# Anchored Agent\n"
                "MUST validate inputs because invalid data corrupts state.\n"
                "NEVER expose secrets so that attackers cannot access credentials.\n"
                "ALWAYS log requests to avoid losing audit trail.\n"
            ),
        },
    )
    score, offenders = audit._score_why_anchor(root)
    assert (
        score == 100
    ), f"all directives anchored: expected score 100, got {score}; offenders={offenders!r}"
    assert (
        offenders == []
    ), f"all directives anchored: expected empty offenders, got {offenders!r}"


def test_j04_one_unanchored_of_n_scores_proportionally(tmp_path):
    """J-04: 1 of N directives unanchored -> score == int((N-1)/N*100) and offenders has that directive."""
    # 4 directives: 3 anchored, 1 not.
    root = _make_why_anchor_root(
        tmp_path,
        agents_files={
            "mixed.md": (
                "# Mixed\n"
                "MUST validate inputs because data integrity is required.\n"
                "NEVER skip tests since regressions will break production.\n"
                "ALWAYS document public APIs so that users understand the contract.\n"
                "REQUIRED to finish before deadline.\n"  # unanchored - no rationale marker
            ),
        },
    )
    score, offenders = audit._score_why_anchor(root)
    n = 4
    expected_score = int((n - 1) / n * 100)
    assert (
        score == expected_score
    ), f"1 of {n} unanchored: expected score {expected_score}, got {score}"
    assert (
        len(offenders) == 1
    ), f"1 of {n} unanchored: expected exactly 1 offender, got {len(offenders)}: {offenders!r}"
    offender_text = str(offenders[0])
    assert (
        "REQUIRED" in offender_text or "finish before deadline" in offender_text
    ), f"offender must reference the unanchored directive text; got {offenders!r}"


def test_j05_none_anchored_scores_zero(tmp_path):
    """J-05: no load-bearing directives have a rationale marker -> score 0."""
    root = _make_why_anchor_root(
        tmp_path,
        agents_files={
            "bare.md": (
                "# Bare Directives\n"
                "MUST do alpha.\n"
                "NEVER do beta.\n"
                "ALWAYS do gamma.\n"
                "HARD limit on delta.\n"
            ),
        },
    )
    score, offenders = audit._score_why_anchor(root)
    assert score == 0, f"no anchored directives: expected score 0, got {score}"
    assert (
        len(offenders) > 0
    ), f"no anchored directives: expected non-empty offenders, got {offenders!r}"


def test_j06_adjacent_line_rationale_counts(tmp_path):
    """J-06: rationale on the immediately adjacent line (not the same line) -> counts as anchored."""
    root = _make_why_anchor_root(
        tmp_path,
        agents_files={
            "adjacent.md": (
                "# Adjacent\n"
                "MUST encrypt all data at rest.\n"
                "This is required because plaintext storage risks data breach.\n"
            ),
        },
    )
    score, offenders = audit._score_why_anchor(root)
    assert (
        score == 100
    ), f"adjacent rationale line: expected score 100, got {score}; offenders={offenders!r}"


def test_j07_missing_file_fail_open(tmp_path):
    """J-07: agents/ dir absent -> no raise, score is int, offenders is list."""
    root = tmp_path
    _write_stub_catalog(root)
    try:
        score, offenders = audit._score_why_anchor(root)
    except Exception as exc:
        raise AssertionError(
            f"_score_why_anchor must not raise when agents/ is absent; "
            f"got {type(exc).__name__}: {exc}"
        ) from exc
    assert isinstance(score, int), f"score must be int; got {type(score)}"
    assert isinstance(offenders, list), f"offenders must be list; got {type(offenders)}"


def test_j08_non_utf8_file_fail_open(tmp_path):
    """J-08: agents/ file with invalid UTF-8 -> no raise, score conservative (< 100 or 100 if no directives found),
    offenders is a list; the file's directives count as failing (conservative)."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    bad_file = agents_dir / "corrupt.md"
    # Bytes that include a MUST-like marker but are invalid UTF-8.
    bad_file.write_bytes(b"\xff\xfe MUST do something\n")
    _write_stub_catalog(tmp_path)

    try:
        score, offenders = audit._score_why_anchor(tmp_path)
    except Exception as exc:
        raise AssertionError(
            f"_score_why_anchor must not raise on non-UTF-8 file; "
            f"got {type(exc).__name__}: {exc}"
        ) from exc
    assert isinstance(score, int), f"score must be int; got {type(score)}"
    assert isinstance(offenders, list), f"offenders must be list; got {type(offenders)}"
    # The corrupt file's items count as failing - conservative means it's in offenders.
    assert (
        score < 100
    ), "fail-open: corrupt file counts as a failing directive (score < 100)"


def test_j09_build_scorecard_includes_why_anchor(tmp_path):
    """J-09: build_scorecard(root)['categories'] includes 'why-anchor coverage'."""
    root = _make_why_anchor_root(tmp_path)
    result = audit.build_scorecard(root)
    assert "why-anchor coverage" in result["categories"], (
        f"'why-anchor coverage' must be in categories; "
        f"got {list(result['categories'].keys())}"
    )


def test_j10_build_scorecard_why_anchor_present_with_score_and_fixes(tmp_path):
    """J-10: 'why-anchor coverage' category has score (int) and fixes (list)."""
    root = _make_why_anchor_root(tmp_path)
    result = audit.build_scorecard(root)
    cat = result["categories"].get("why-anchor coverage", {})
    assert "score" in cat, "'why-anchor coverage' category missing 'score' key"
    assert "fixes" in cat, "'why-anchor coverage' category missing 'fixes' key"
    assert isinstance(
        cat["score"], int
    ), f"'why-anchor coverage' score must be int, got {type(cat['score'])}"
    assert isinstance(
        cat["fixes"], list
    ), f"'why-anchor coverage' fixes must be list, got {type(cat['fixes'])}"


# ---------------------------------------------------------------------------
# Shape: 8 categories, overall = sum//8, _render has 8 sorted lines
# ---------------------------------------------------------------------------


def test_shape_overall_is_sum_divided_by_eight(tmp_path):
    """SHAPE-01: overall == sum(category scores) // 8."""
    root = _make_doctrine_root(tmp_path)
    result = audit.build_scorecard(root)
    scores = [cat["score"] for cat in result["categories"].values()]
    assert len(scores) == 8, f"expected 8 category scores, got {len(scores)}: {scores}"
    expected_overall = sum(scores) // 8
    assert result["overall"] == expected_overall, (
        f"overall must be sum(scores) // 8 = {expected_overall}; "
        f"got {result['overall']}; scores={scores}"
    )


def test_shape_render_has_eight_category_lines(tmp_path):
    """SHAPE-02: _render(scorecard) output contains exactly 8 alpha-sorted category lines."""
    root = _make_doctrine_root(tmp_path)
    scorecard = audit.build_scorecard(root)
    rendered = audit._render(scorecard)
    lines = rendered.splitlines()
    # Category lines are indented with score then name (the format is "  NNN  name").
    category_lines = [l for l in lines if l.startswith("  ") and "  " in l.strip()]
    # More precisely: count lines that match the "  <3-digit score>  <name>" pattern.
    import re

    score_lines = [l for l in lines if re.match(r"^\s+\d+\s+\S", l)]
    assert len(score_lines) == 8, (
        f"_render must produce exactly 8 category score lines; "
        f"got {len(score_lines)}:\n" + "\n".join(score_lines)
    )
    # Verify they are alpha-sorted by extracting category names.
    names_in_render = []
    for l in score_lines:
        parts = l.strip().split(None, 1)
        if len(parts) == 2:
            names_in_render.append(parts[1])
    assert names_in_render == sorted(
        names_in_render
    ), f"category lines in _render must be alpha-sorted; got {names_in_render!r}"


# ---------------------------------------------------------------------------
# Group K - Live-repo floor tests (regression guard)
# ---------------------------------------------------------------------------


def test_k01_live_repo_why_anchor_coverage_score_gt_0():
    """K-01: build_scorecard(REAL_REPO_ROOT)['categories']['why-anchor coverage']['score'] > 0.

    Guards the '0 slipped through green' gap - the why-anchor scorer must detect
    at least some anchored directives in the live plugin repo after F1 recalibration."""
    result = audit.build_scorecard(REAL_REPO_ROOT)
    score = result["categories"]["why-anchor coverage"]["score"]
    assert score > 0, (
        f"live repo 'why-anchor coverage' must score > 0; got {score}. "
        f"The scorer is failing to detect anchored directives - check _score_why_anchor, "
        f"_is_load_bearing, and RATIONALE_MARKERS."
    )


def test_k02_live_repo_doctrine_hygiene_score_gt_0():
    """K-02: build_scorecard(REAL_REPO_ROOT)['categories']['doctrine hygiene']['score'] > 0.

    Guards against a total-collapse of the hygiene scorer - at least some instruction
    lines in the live repo must be non-duplicated."""
    result = audit.build_scorecard(REAL_REPO_ROOT)
    score = result["categories"]["doctrine hygiene"]["score"]
    assert score > 0, (
        f"live repo 'doctrine hygiene' must score > 0; got {score}. "
        f"The scorer is collapsing - check _score_doctrine_hygiene and "
        f"_build_line_frequency_map."
    )
