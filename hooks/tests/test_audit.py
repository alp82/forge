"""Tests for hooks/audit.py.

audit.py exists and these tests are green.

CONTRACT:
  - build_scorecard(root) -> {"overall": int, "categories": {name: {"score": int,
    "fixes": [str,...]}}, "top_fixes": [str,...]}
  - 5 category names: "tool/agent coverage", "context efficiency",
    "quality gates", "memory persistence", "security guardrails"
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


def test_a02_shape_categories_has_exactly_five_names():
    """A-02: categories has exactly the 5 required category names."""
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
    gen = root / "generated"
    gen.mkdir()
    (gen / "catalog.json").write_text(json.dumps({"stages": {}}))
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
