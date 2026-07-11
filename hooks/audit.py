#!/usr/bin/env python3
"""Deterministic self-audit: score the plugin against eight health categories.

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

# Exactly the eight category names the contract pins.
CATEGORIES = (
    "tool/agent coverage",
    "context efficiency",
    "quality gates",
    "memory persistence",
    "security guardrails",
    "doctrine integrity",
    "doctrine hygiene",
    "why-anchor coverage",
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
    ("extend it not restate", "CLAUDE.md"),
    ("artifacts on disk, handles in context", "WORKFLOW.md"),
    ("one card grammar, and the banner is the order", "doctrine/render-card.md"),
    ("<state> ▶ <next action>", "doctrine/render-card.md"),
    ("re-spawns the stage once at `opus`", "WORKFLOW.md"),
    ("shown, not told", "agents/explainer-prototyper.md"),
    ("description carries the tradeoff; preview carries the evidence", "WORKFLOW.md"),
)

# Catalog stages that mark a present quality gate (test chain + review lenses).
QUALITY_GATE_HINTS = ("test-plan", "test-verifier", "reviewer")

# Doctrine subtrees the hygiene + why-anchor lenses scan for instruction lines.
DOCTRINE_LENS_DIRS = ("agents", "doctrine")

# All-caps strength markers that make a directive line load-bearing.
STRENGTH_MARKERS = ("MUST", "NEVER", "ALWAYS", "REQUIRED", "HARD")

# Rationale markers that anchor a directive to its why.
# Matched as whole words/phrases over punctuation-stripped tokens (see
# _has_rationale), so lookalike substrings ("torso", "sincerely", "also")
# never count.
RATIONALE_MARKERS = (
    "because",
    # word-bounded "so" subsumes the former "so that" / "so as to" phrase markers
    "so",
    "to avoid",
    "otherwise",
    "since",
    "rationale",
    "which keeps",
    "which prevents",
)

# Instruction lines shorter than this (after normalization) are too trivial to
# count as a meaningful cross-file duplicate.
HYGIENE_MIN_LEN = 24


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


def _coverage_routes_points(stages, fixes):
    """Routes component: 25 pts scaled by the fraction of stages carrying `routes`."""
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
    return routed * 25 // len(stages)


def _coverage_coherence_points(catalog, fixes):
    """Coherence component: 15 pts iff check_catalog.check finds no problems."""
    try:
        problems = check_catalog.check(catalog)
    except Exception:
        fixes.append("catalog coherence check could not run - inspect check_catalog.py")
        return 0
    if problems:
        fixes.append("resolve catalog coherence problems (run check_catalog.py)")
        return 0
    return 15


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

    # Breadth: saturates at 40 stages (the live repo carries ~47).
    breadth = min(60, len(stages) * 60 // 40)
    routes_pts = _coverage_routes_points(stages, fixes)
    coherence_pts = _coverage_coherence_points(catalog, fixes)
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


def _gate_catalog_points(catalog, ok, fixes):
    """Catalog component: 12 pts per present test/review gate stage, capped at 36."""
    stages = {}
    if ok and catalog is not None:
        stages = catalog.get("stages") or {}
        if not isinstance(stages, dict):
            stages = {}
    gate_stages = sorted(n for n in stages if any(h in n for h in QUALITY_GATE_HINTS))
    if not gate_stages:
        fixes.append("no test or review stages in the catalog - add the quality gates")
    return min(36, len(gate_stages) * 12)


def _gate_verify_points(root, hooks_text, fixes):
    """Verify-hook component: 16 pts each for registered + present verify-build/tests."""
    score = 0
    if "verify-build" in hooks_text and (root / "hooks" / "verify-build.py").is_file():
        score += 16
    else:
        fixes.append("register the build verification Stop hook (verify-build)")
    if "verify-tests" in hooks_text and (root / "hooks" / "verify-tests.py").is_file():
        score += 16
    else:
        fixes.append("register the test verification Stop hook (verify-tests)")
    return score


def _score_quality_gates(root, catalog, ok, hooks_text):
    """Catalog test/review stages + verify-build/verify-tests + reviewer count in hooks."""
    fixes = []
    score = _gate_catalog_points(catalog, ok, fixes)
    score += _gate_verify_points(root, hooks_text, fixes)

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


def _score_security(root, hooks_text, catalog, ok):
    """Git-write guard (block-git-writes.sh present + registered) + ship gate (ship-gate stage + ship-executor ship-ready lock); four 25-pt sub-checks."""
    fixes = []
    score = 0
    if (root / "hooks" / "block-git-writes.sh").is_file():
        score += 25
    else:
        fixes.append("restore hooks/block-git-writes.sh - the git-write guard")

    if "block-git-writes" in hooks_text:
        score += 25
    else:
        fixes.append("register block-git-writes.sh as a PreToolUse Bash hook")

    stages = catalog.get("stages", {}) if ok else {}
    if not isinstance(stages, dict):
        stages = {}
    if ok and "ship-gate" in stages:
        score += 25
    else:
        fixes.append(
            "register the ship-gate stage - the convergence-gated ship decision"
        )

    # lock entries are dicts {while, until} with BARE topics (no '#'); a gen-catalog representation change must update this check.
    executor = stages.get("ship-executor", {}) if ok else {}
    locks = executor.get("lock", []) or []
    has_ship_lock = any(
        lk.get("while") == "ship-ready" and lk.get("until") == "ship-approved"
        for lk in locks
    )
    if ok and has_ship_lock:
        score += 25
    else:
        fixes.append(
            "hold ship-executor with a {while:ship-ready, until:ship-approved} lock"
        )
    return _clamp(score), fixes


def _score_doctrine_integrity(root):
    """Every pinned doctrine phrase still present in its file. All-or-nothing."""
    problems = [
        f"add the pinned phrase '{phrase}' back to {relpath}"
        for phrase, relpath in DOCTRINE_PHRASES
        if phrase not in _read_file(root, relpath)
    ]
    return (100, []) if not problems else (0, problems)


def _normalize_instruction(line):
    """Lowercase, strip punctuation, collapse whitespace. '' for a too-trivial line."""
    lowered = "".join(c if c.isalnum() or c.isspace() else " " for c in line.lower())
    collapsed = " ".join(lowered.split())
    return collapsed if len(collapsed) >= HYGIENE_MIN_LEN else ""


def _is_cross_reference(line):
    """An explicit cross-reference line ('See doctrine/...') is excluded from dup checks."""
    return line.strip().lower().startswith("see doctrine/")


# Phrase fragments that identify mandated-contract restatements. These appear
# verbatim in multiple agents by design (Input Template Contract and Reviewer Contract).
# NOTE: naked-substring matches - a doctrine reword without updating this list silently re-flags these as duplicates.
_MANDATED_CONTRACT_FRAGMENTS = (
    # Input Template Contract: required-slot parse + error stop.
    "first step: parse required slots",
    "first step: parse `<confirmed_intent>`",
    "first step: parse `<system_plan>`",
    "on a missing required slot, emit `input_error: missing <slot>` and stop",
    # Reviewer Contract: shared opener line.
    "follows the reviewer contract in your doctrine block",
    # Artifact handles: in-body handle-read line, repeated across the 5 plan
    # consumers plus reviewer-contract.md by design (one canonical wording).
    "holds a handle line rather than the block",
    # Clarify loop (clarifier): the merged intent+requirements loop's canonical
    # protocol wording. Kept here so a future re-split can't silently re-duplicate it.
    "exit conditions for the main agent",
    "convergence governs the route, not a budget",
    # Visual-prototyper pair (design-, ux-prototyper): both emit browser-openable
    # spec artifacts under identical constraints inside self-contained prompts.
    "vanilla html + js works if needed",
    "one sentence under the button telling the user to paste the spec",
    "a sandbox file must run by opening it in a browser",
    # Domain-prototyper trio (code-, data-, performance-prototyper): shared
    # tracer-bullet ground rules restated per self-contained prompt by design.
    "one prototype - the standard tracer bullet",
    "one prototype per file in",
    "use the project's language and runtime",
    # Severity-ranking reviewer trio (architecture-, quality-, simplicity-reviewer):
    # each carries its own tier list, so the ranking rule rides with it verbatim.
    "rank findings highest tier first",
)


def _is_mandated_contract(line):
    """Return True when a line is a mandated-contract restatement, not an accidental dup."""
    lowered = line.strip().lower()
    return any(frag in lowered for frag in _MANDATED_CONTRACT_FRAGMENTS)


def _instruction_lines(text):
    """Yield (source_lineno, line) pairs for prose instruction lines only.

    Skips YAML frontmatter and fenced blocks - they are structural scaffolding the
    agent family shares by design, not duplicated doctrine. source_lineno is the
    true 1-based line number in the original file so callers can report accurate
    locations without needing to account for stripped frontmatter or fenced blocks.

    The leading `---`-delimited frontmatter (stage contract, tools, signals) and any
    ``` ... ``` fenced block (the verbatim `## Input`/`## Output` templates with their
    shared slot and contract-field lines) are excluded from yielded pairs."""
    lines = text.splitlines()
    i = 0
    # Strip a leading frontmatter block.
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            i += 1
        i += 1  # skip the closing fence
    in_fence = False
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence:
            yield i + 1, line  # i + 1 converts 0-based index to 1-based line number
        i += 1


def _read_md(path):
    """Return file text or None on read failure (missing/non-utf8)."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None


def _doctrine_lens_files(root):
    """Sorted (relpath, text_or_None) pairs for every agents/ + doctrine/ markdown file.

    text is None when the file could not be read (missing/non-utf8) - the caller
    counts such a file conservatively as failing, never raising."""
    out = []
    for subdir in DOCTRINE_LENS_DIRS:
        d = root / subdir
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.md")):
            out.append((f"{subdir}/{path.name}", _read_md(path)))
    return out


def _build_line_frequency_map(files):
    """Phase 1: map each normalized instruction line to the set of files containing it.

    Excludes cross-reference lines, mandated-contract restatements, and lines that
    normalize to the empty string or below HYGIENE_MIN_LEN. Unreadable files
    (text is None) are skipped here; callers handle them separately."""
    line_files = {}
    for relpath, text in files:
        if text is None:
            continue
        for _lineno, raw in _instruction_lines(text):
            if _is_cross_reference(raw):
                continue
            if _is_mandated_contract(raw):
                continue
            norm = _normalize_instruction(raw)
            if not norm:
                continue
            line_files.setdefault(norm, {})[relpath] = raw.strip()
    return line_files


def _score_from_frequency_map(line_files, unreadable):
    """Phase 2: compute (score, offenders) from the frequency map + unreadable list."""
    total, duplicated, offenders = 0, 0, []
    for norm, where in sorted(line_files.items()):
        total += 1
        if len(where) > 1:
            duplicated += 1
            paths = sorted(where)
            first_text = where[paths[0]]
            offenders.append(f"'{first_text}' duplicated across {', '.join(paths)}")
    # Unreadable files count as failing items so a corrupt file degrades the score.
    for relpath in unreadable:
        total += 1
        duplicated += 1
        offenders.append(f"could not read {relpath} - counted as a hygiene failure")
    if total == 0:
        return 100, []
    score = (total - duplicated) * 100 // total
    return _clamp(score), offenders


def _score_doctrine_hygiene(root):
    """Graduated: fraction of instruction lines NOT duplicated verbatim across files.

    Normalizes each instruction line; flags one whose normalized form exactly
    matches a line in a DIFFERENT agents/ or doctrine/ file. Cross-reference and
    mandated-contract lines are excluded. Unreadable files count their absence
    conservatively as a failing item. Returns (int_score, offender_list)."""
    files = _doctrine_lens_files(root)
    unreadable = [relpath for relpath, text in files if text is None]
    line_files = _build_line_frequency_map(files)
    return _score_from_frequency_map(line_files, unreadable)


def _clean_tokens(line):
    """Tokenize a line: backticks to spaces, split, strip surrounding punctuation.

    Shared by _is_load_bearing and _has_rationale so both check whole
    words/phrases against the same normalized token stream.
    """
    tokens = line.replace("`", " ").split()
    # Strip surrounding punctuation so "REQUIRED." and "MUST," are recognized.
    return [t.strip(".,;:!?()[]\"'") for t in tokens]


def _is_load_bearing(line):
    """A directive line carrying an all-caps strength marker as a whole word."""
    return any(m in set(_clean_tokens(line)) for m in STRENGTH_MARKERS)


def _has_rationale(line):
    """A line carrying a rationale marker as a whole word or phrase.

    Joins the shared tokenization's tokens with single spaces and pads both
    ends so one boundary check covers single-word and multi-word markers.
    """
    clean_tokens = _clean_tokens(line.lower())
    padded = " " + " ".join(clean_tokens) + " "
    return any(f" {m} " in padded for m in RATIONALE_MARKERS)


def _is_anchor_excluded(line):
    """Skip headings (lstrip starts with '#') and list-headers (stripped ends with ':')."""
    stripped = line.lstrip()
    if stripped.startswith("#"):
        return True
    if line.rstrip().endswith(":"):
        return True
    return False


def _score_why_anchor(root):
    """Graduated: fraction of load-bearing directives anchored to a rationale.

    A directive is anchored when it or an adjacent line carries a rationale marker.
    Only prose instruction lines are scored - YAML frontmatter and fenced blocks
    (output-contract MUST lines, shared slot lines) are excluded via _instruction_lines.
    Heading lines and list-header lines (ending with ':') are also excluded.
    Unreadable files count their MUST-like content conservatively as failing.
    Returns (int_score, offender_list)."""
    total, anchored, offenders = 0, 0, []
    for relpath, text in _doctrine_lens_files(root):
        if text is None:
            # Conservative: an unreadable file counts as one failing directive.
            total += 1
            offenders.append(f"could not read {relpath} - counted as unanchored")
            continue
        # Filter to prose-only instruction lines (drops frontmatter and fenced blocks).
        # Each element is a (source_lineno, line) pair where source_lineno is the
        # true 1-based line number in the original file.
        prose_pairs = list(_instruction_lines(text))
        for idx, (source_lineno, line) in enumerate(prose_pairs):
            if _is_anchor_excluded(line):
                continue
            if not _is_load_bearing(line):
                continue
            total += 1
            # Anchored by a rationale on the directive's own line or the line that
            # continues it. Forward-only: a preceding line belongs to its own
            # directive, so its rationale must not leak onto this one.
            neighbors = [line]
            if idx + 1 < len(prose_pairs):
                neighbors.append(prose_pairs[idx + 1][1])
            if any(_has_rationale(n) for n in neighbors):
                anchored += 1
            else:
                offenders.append(f"{relpath}:{source_lineno} - {line.strip()}")

    if total == 0:
        return 100, []
    score = anchored * 100 // total
    return _clamp(score), offenders


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
    category_results["security guardrails"] = _score_security(
        root, hooks_text, catalog, ok
    )
    category_results["doctrine integrity"] = _score_doctrine_integrity(root)
    category_results["doctrine hygiene"] = _score_doctrine_hygiene(root)
    category_results["why-anchor coverage"] = _score_why_anchor(root)

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
