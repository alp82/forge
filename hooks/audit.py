#!/usr/bin/env python3
"""Deterministic self-audit: score the plugin against six health categories.

Mirrors the verify-build.py shape - stdlib only, fail-open, always exits 0. The
score is a pure function of repo facts (catalog stages, doctrine files, registered
hooks); no wall-clock, no randomness, sorted iteration only, so the same repo state
always yields the same scorecard.

build_scorecard(root) returns the machine shape; main() reads an optional catalog
path from stdin, prints a stable human scorecard plus a SCORECARD_JSON line, and
exits 0 on every path. A missing/malformed catalog degrades the affected categories
(still an int score + a fix action) and never raises.
"""

import json
import sys
from pathlib import Path

# Ensure check_catalog resolves regardless of cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_catalog

ROOT = Path(__file__).resolve().parent.parent

# Exactly the six category names the contract pins.
CATEGORIES = (
    "tool/agent coverage",
    "context efficiency",
    "quality gates",
    "memory persistence",
    "security guardrails",
    "doctrine integrity",
)

# Pinned doctrine phrases: each entry is (phrase, repo-relative-path).
# A phrase is considered present if it appears anywhere in the named file
# (whole-file substring check). This catches deletion of the pinned literal
# but not a one-sided reword when the same phrase also appears elsewhere.
# These phrases are load-bearing canaries - their presence confirms doctrine
# integrity; adding or renaming them here requires updating the source file too.
DOCTRINE_PHRASES = (
    ("est-size > S", "WORKFLOW.md"),
    ("est-size <= S", "WORKFLOW.md"),
    ("ONE runnable check", "doctrine/code-doctrine.md"),
)

# Catalog stages that mark a present quality gate (test chain + review lenses).
QUALITY_GATE_HINTS = ("test-plan", "test-verifier", "reviewer")


def _read_file(root, relpath):
    try:
        return (root / relpath).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return ""


def _load_catalog(root):
    """Read root/generated/catalog.json. Returns (catalog_or_None, ok)."""
    try:
        text = (root / "generated" / "catalog.json").read_text(encoding="utf-8")
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            return None, False
        return parsed, True
    except (OSError, ValueError):
        return None, False


def _clamp(score):
    return max(0, min(100, int(score)))


def _score_catalog_coverage(catalog, ok):
    """Catalog stage count + every stage carries routes + input_template coherence."""
    fixes = []
    if not ok or catalog is None:
        return 0, ["restore generated/catalog.json so coverage can be scored"]
    stages = catalog.get("stages") or {}
    if not isinstance(stages, dict):
        stages = {}
    if not stages:
        return 0, ["no stages in catalog - regenerate it from the agent definitions"]

    count = len(stages)
    # Breadth: saturates at 40 stages (the live repo carries ~47).
    breadth = min(60, count * 60 // 40)

    routed = 0
    for name in sorted(stages):
        stage = stages[name]
        if not isinstance(stage, dict):
            fixes.append(f"stage '{name}' is malformed")
            continue
        if stage.get("routes") or []:
            routed += 1
        else:
            fixes.append(f"stage '{name}' is missing `routes`")
    routes_pts = routed * 25 // count

    coherence_pts = 15
    try:
        problems = check_catalog.check(catalog)
        if problems:
            coherence_pts = 0
            fixes.append("resolve catalog coherence problems (run check_catalog.py)")
    except Exception:
        coherence_pts = 0
        fixes.append("catalog coherence check could not run - inspect check_catalog.py")

    return _clamp(breadth + routes_pts + coherence_pts), fixes


def _score_context(root):
    """Injection knobs + doctrine-slice coherence (workflow + signal vocabulary)."""
    fixes = []
    score = 0
    if (root / "hooks" / "inject-workflow.sh").is_file():
        score += 35
    else:
        fixes.append("register the workflow injector hook (inject-workflow.sh)")
    if (root / "WORKFLOW.md").is_file():
        score += 35
    else:
        fixes.append("restore WORKFLOW.md - the doctrine slice agents load on demand")
    if (root / "doctrine" / "SIGNALS.md").is_file():
        score += 30
    else:
        fixes.append("restore doctrine/SIGNALS.md - the signal vocabulary")
    return _clamp(score), fixes


def _score_quality_gates(root, catalog, ok, hooks_text):
    """Catalog test/review stages + verify-build/verify-tests + reviewer count in hooks."""
    fixes = []
    score = 0

    stages = {}
    if ok and catalog is not None:
        stages = catalog.get("stages") or {}
        if not isinstance(stages, dict):
            stages = {}
    gate_stages = sorted(n for n in stages if any(h in n for h in QUALITY_GATE_HINTS))
    # Catalog component: 12 points per present gate stage, capped at 36.
    score += min(36, len(gate_stages) * 12)
    if not gate_stages:
        fixes.append("no test or review stages in the catalog - add the quality gates")

    verify_build_file = root / "hooks" / "verify-build.py"
    verify_tests_file = root / "hooks" / "verify-tests.py"

    if "verify-build" in hooks_text and verify_build_file.is_file():
        score += 16
    else:
        fixes.append("register the build verification Stop hook (verify-build)")
    if "verify-tests" in hooks_text and verify_tests_file.is_file():
        score += 16
    else:
        fixes.append("register the test verification Stop hook (verify-tests)")

    reviewers = 0
    agents_dir = root / "agents"
    if agents_dir.is_dir():
        reviewers = sum(1 for p in sorted(agents_dir.glob("*review*.md")))
    # Review-lens breadth: 4 points per reviewer agent, capped at 32.
    score += min(32, reviewers * 4)
    if reviewers == 0:
        fixes.append("no reviewer agents found - wire in the review lenses")

    return _clamp(score), fixes


def _score_memory(root):
    """doctrine/MEMORY-CONVENTIONS.md present + reflect memory section present."""
    fixes = []
    score = 0
    if (root / "doctrine" / "MEMORY-CONVENTIONS.md").is_file():
        score += 50
    else:
        fixes.append(
            "add doctrine/MEMORY-CONVENTIONS.md - the memory convention reference"
        )

    memory_section = False
    reflect = root / "commands" / "reflect.md"
    try:
        if "## Memory" in reflect.read_text(encoding="utf-8"):
            memory_section = True
    except OSError:
        pass
    if memory_section:
        score += 50
    else:
        fixes.append(
            "add a Memory section to /reflect to audit memory against conventions"
        )
    return _clamp(score), fixes


def _score_security(root, hooks_text):
    """block-git-writes.sh present + registered in hooks.json."""
    fixes = []
    score = 0
    if (root / "hooks" / "block-git-writes.sh").is_file():
        score += 50
    else:
        fixes.append("restore hooks/block-git-writes.sh - the git-write guard")

    if "block-git-writes" in hooks_text:
        score += 50
    else:
        fixes.append("register block-git-writes.sh as a PreToolUse Bash hook")
    return _clamp(score), fixes


def _score_doctrine_integrity(root):
    """Every pinned doctrine phrase still present in its file. All-or-nothing."""
    problems = [
        f"add the pinned phrase '{phrase}' back to {relpath}"
        for phrase, relpath in DOCTRINE_PHRASES
        if phrase not in _read_file(root, relpath)
    ]
    return (100, []) if not problems else (0, problems)


def build_scorecard(root):
    """Pure scorecard over repo facts. Fail-open: never raises, every score an int."""
    root = Path(root)
    catalog, ok = _load_catalog(root)

    # Read hooks.json once; pass text to scorers that need it.
    hooks_text = ""
    hooks_json = root / "hooks" / "hooks.json"
    try:
        hooks_text = hooks_json.read_text(encoding="utf-8")
    except OSError:
        pass

    category_results = {}
    cov_score, cov_fixes = _score_catalog_coverage(catalog, ok)
    category_results["tool/agent coverage"] = (cov_score, cov_fixes)
    category_results["context efficiency"] = _score_context(root)
    category_results["quality gates"] = _score_quality_gates(
        root, catalog, ok, hooks_text
    )
    category_results["memory persistence"] = _score_memory(root)
    category_results["security guardrails"] = _score_security(root, hooks_text)
    category_results["doctrine integrity"] = _score_doctrine_integrity(root)

    categories = {}
    for name in CATEGORIES:
        score, fixes = category_results[name]
        categories[name] = {"score": _clamp(score), "fixes": list(fixes)}

    scores = [categories[n]["score"] for n in CATEGORIES]
    overall = sum(scores) // len(scores)

    # worst-category-score first, alpha tie-break by category name.
    ordered = sorted(CATEGORIES, key=lambda n: (categories[n]["score"], n))
    top_fixes = [fix for name in ordered for fix in categories[name]["fixes"]]

    return {"overall": overall, "categories": categories, "top_fixes": top_fixes}


def _render(scorecard):
    """Stable human-readable scorecard, sorted by category name."""
    lines = [f"alp-river self-audit - overall {scorecard['overall']}/100", ""]
    for name in sorted(scorecard["categories"]):
        cat = scorecard["categories"][name]
        lines.append(f"  {cat['score']:3d}  {name}")
    lines.append("")
    if scorecard["top_fixes"]:
        lines.append("Top fixes (worst category first):")
        for fix in scorecard["top_fixes"]:
            lines.append(f"  - {fix}")
    else:
        lines.append("No fixes - all categories clean.")
    return "\n".join(lines)


def main():
    # Optional stdin: a catalog/repo path, or empty to audit the plugin root.
    raw = ""
    try:
        raw = sys.stdin.read().strip()
    except (OSError, ValueError):
        raw = ""

    root = ROOT
    if raw:
        try:
            payload = json.loads(raw)
            candidate = payload.get("path") if isinstance(payload, dict) else None
        except (json.JSONDecodeError, ValueError):
            candidate = raw
        if candidate:
            p = Path(candidate)
            if p.is_dir():
                root = p

    scorecard = build_scorecard(root)
    print(_render(scorecard))
    print("SCORECARD_JSON " + json.dumps(scorecard, sort_keys=True))
    sys.exit(0)


if __name__ == "__main__":
    main()
