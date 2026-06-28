"""Tests for the briefs change.

RED tests (1-6): fail until doctrine/briefs.md and the audit.py
DOCTRINE_PHRASES entry and the DOCTRINE_MAP wiring in user-context-injector.sh
all land together.

GREEN-now regression guards (7-8): pass against the current repo and must stay
green after the implementation lands.

Conventions mirror test_audit.py: import paths, REAL_REPO_ROOT, helper style.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # hooks/
import audit
import check_catalog

REAL_REPO_ROOT = Path(__file__).resolve().parents[2]

# The leitwort canary phrase for the briefs doctrine file.
BRIEFS_ANCHOR = (
    "the overview comes first; the brief is details on demand, pulled never pushed."
)

# The four agents that must receive briefs doctrine.
BRIEFS_AGENTS = ("discuss", "interviewer", "plan-challenger", "plan-arbiter")


# ---------------------------------------------------------------------------
# RED 1 - Canary entry present in DOCTRINE_PHRASES
# ---------------------------------------------------------------------------


def test_briefs_r01_doctrine_phrases_contains_briefs_entry():
    """RED-1: audit.DOCTRINE_PHRASES contains the briefs canary tuple.

    Fails until the implementer adds:
        ("the overview comes first; the brief is details on demand, pulled never pushed.",
         "doctrine/briefs.md")
    to DOCTRINE_PHRASES in hooks/audit.py.
    """
    target = (BRIEFS_ANCHOR, "doctrine/briefs.md")
    assert target in audit.DOCTRINE_PHRASES, (
        f"DOCTRINE_PHRASES must contain {target!r}; "
        f"current entries: {audit.DOCTRINE_PHRASES!r}"
    )


# ---------------------------------------------------------------------------
# RED 2 - Canary count (exactly 5 entries, not 4, not 6)
# ---------------------------------------------------------------------------


def test_briefs_r02_doctrine_phrases_length_is_five():
    """RED-2: audit.DOCTRINE_PHRASES has exactly 9 entries after the RC4
    briefs label pair, the artifact-handles canary, and the render-card canary are added.

    Guards against dropping the briefs entries below the expected count.
    """
    assert len(audit.DOCTRINE_PHRASES) == 9, (
        f"DOCTRINE_PHRASES must have exactly 9 entries (5 existing + the two "
        f"RC4 briefs labels + the artifact-handles canary + the render-card canary); got "
        f"{len(audit.DOCTRINE_PHRASES)}: {audit.DOCTRINE_PHRASES!r}"
    )


# ---------------------------------------------------------------------------
# RED 3 - Doctrine file exists and contains the leitwort
# ---------------------------------------------------------------------------


def test_briefs_r03_briefs_md_exists_with_leitwort():
    """RED-3: doctrine/briefs.md exists in the real repo and contains
    the leitwort substring.

    Fails until the implementer creates the file.
    """
    target_file = REAL_REPO_ROOT / "doctrine" / "briefs.md"
    assert target_file.is_file(), (
        f"doctrine/briefs.md must exist at {target_file}; " f"file does not exist yet"
    )
    content = target_file.read_text(encoding="utf-8")
    assert BRIEFS_ANCHOR in content, (
        f"doctrine/briefs.md must contain the leitwort "
        f"{BRIEFS_ANCHOR!r}; file exists but phrase is absent"
    )


# ---------------------------------------------------------------------------
# RED 4 - Live-repo doctrine integrity stays 100
# ---------------------------------------------------------------------------


def test_briefs_r04_live_repo_doctrine_integrity_score_100():
    """RED-4: build_scorecard(REAL_REPO_ROOT) doctrine integrity score == 100.

    Mirrors test_h19. Fails until BOTH doctrine/briefs.md exists AND
    the matching DOCTRINE_PHRASES entry is added (the canary check will fail
    otherwise).
    """
    result = audit.build_scorecard(REAL_REPO_ROOT)
    assert (
        "doctrine integrity" in result["categories"]
    ), "'doctrine integrity' must be in live-repo scorecard categories"
    score = result["categories"]["doctrine integrity"]["score"]
    assert score == 100, (
        f"live repo 'doctrine integrity' must score 100; got {score}. "
        f"RED until doctrine/briefs.md exists and its DOCTRINE_PHRASES "
        f"canary entry lands in audit.py."
    )


# ---------------------------------------------------------------------------
# RED 5 - DOCTRINE_MAP wires briefs to all four target agents
# ---------------------------------------------------------------------------


def test_briefs_r05_doctrine_map_wires_briefs_to_all_four_agents():
    """RED-5: hooks/user-context-injector.sh DOCTRINE_MAP block contains
    'briefs' in the entry for each of discuss, interviewer,
    plan-challenger, and plan-arbiter.

    Currently discuss and interviewer have no DOCTRINE_MAP entry; plan-challenger
    and plan-arbiter have only 'code-doctrine'. Fails until all four are wired.
    """
    injector = REAL_REPO_ROOT / "hooks" / "user-context-injector.sh"
    assert injector.is_file(), f"user-context-injector.sh not found at {injector}"
    content = injector.read_text(encoding="utf-8")

    # Parse the DOCTRINE_MAP block: find lines like [agent-name]="token1 token2 ..."
    import re

    # Match bash associative-array assignment lines inside the DOCTRINE_MAP block.
    # Pattern: [agent-name]="space-separated tokens"
    map_entries = {}
    for m in re.finditer(r'^\s*\[([^\]]+)\]="([^"]*)"', content, re.MULTILINE):
        map_entries[m.group(1)] = m.group(2)

    for agent in BRIEFS_AGENTS:
        assert agent in map_entries, (
            f"DOCTRINE_MAP in user-context-injector.sh has no entry for '{agent}'; "
            f"current keys include: {sorted(map_entries.keys())!r}"
        )
        tokens = map_entries[agent].split()
        assert "briefs" in tokens, (
            f"DOCTRINE_MAP['{agent}'] must include 'briefs'; "
            f"current value: {map_entries[agent]!r}"
        )


# ---------------------------------------------------------------------------
# RED 6 - Leitwort defined exactly once (one-home rule)
# ---------------------------------------------------------------------------


def test_briefs_r06_leitwort_appears_in_exactly_one_file():
    """RED-6: the leitwort substring appears in exactly one file across
    agents/*.md + doctrine/*.md + WORKFLOW.md, and that file is
    doctrine/briefs.md (WORKFLOW.md only cross-references it).

    Fails now because the leitwort appears in zero files (the doctrine file
    does not exist yet). After implementation, exactly one file must contain it.
    """
    search_paths = (
        list((REAL_REPO_ROOT / "agents").glob("*.md"))
        + list((REAL_REPO_ROOT / "doctrine").glob("*.md"))
        + [REAL_REPO_ROOT / "WORKFLOW.md"]
    )

    files_containing_leitwort = []
    for path in search_paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if BRIEFS_ANCHOR in text:
            files_containing_leitwort.append(path)

    assert len(files_containing_leitwort) == 1, (
        f"The leitwort {BRIEFS_ANCHOR!r} must appear in exactly ONE file "
        f"(doctrine/briefs.md); "
        f"found in {len(files_containing_leitwort)} file(s): "
        f"{[str(p) for p in files_containing_leitwort]!r}"
    )

    sole_file = files_containing_leitwort[0]
    expected = REAL_REPO_ROOT / "doctrine" / "briefs.md"
    assert sole_file == expected, (
        f"The leitwort must live exclusively in doctrine/briefs.md; "
        f"found instead in {sole_file}"
    )

    # Separately assert WORKFLOW.md does NOT contain it (cross-reference only).
    workflow_path = REAL_REPO_ROOT / "WORKFLOW.md"
    try:
        workflow_text = workflow_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        workflow_text = ""
    assert BRIEFS_ANCHOR not in workflow_text, (
        f"WORKFLOW.md must NOT contain the leitwort verbatim (it may only "
        f"cross-reference briefs.md); leitwort found in WORKFLOW.md"
    )


# ---------------------------------------------------------------------------
# GREEN 7 - Briefs target agents do not have Write in tools
# ---------------------------------------------------------------------------


def test_briefs_g07_briefs_agents_have_no_write_tool():
    """GREEN-7 (regression guard): discuss, interviewer, plan-challenger, and
    plan-arbiter do not have 'Write' in their YAML frontmatter tools: line.

    Passes now. Would fail if the implementer accidentally adds Write while
    wiring the doctrine (the orchestrator, not these agents, writes docs).
    """
    import re

    for agent_name in BRIEFS_AGENTS:
        agent_file = REAL_REPO_ROOT / "agents" / f"{agent_name}.md"
        assert (
            agent_file.is_file()
        ), f"agents/{agent_name}.md does not exist - cannot verify tool list"
        content = agent_file.read_text(encoding="utf-8")

        # Extract the tools: line from YAML frontmatter (between the first two ---).
        tools_line = None
        for line in content.splitlines():
            if re.match(r"^tools\s*:", line):
                tools_line = line
                break

        if tools_line is None:
            # No tools line means no tools - Write is absent, which is fine.
            continue

        # Split the tool list and check for Write.
        after_colon = tools_line.split(":", 1)[1]
        tools = [t.strip() for t in after_colon.split(",")]
        assert "Write" not in tools, (
            f"agents/{agent_name}.md must NOT have 'Write' in its tools list; "
            f"got tools line: {tools_line!r}. The orchestrator writes .briefs/ "
            f"docs, not these doctrine-only agents."
        )


# ---------------------------------------------------------------------------
# GREEN 8 - Catalog valid and stage count unchanged
# ---------------------------------------------------------------------------


def test_briefs_g08_catalog_valid_and_stage_count_unchanged():
    """GREEN-8 (regression guard): generated/catalog.json has no orphaned signals
    and the stage count equals the pinned value at test-write time (50).

    Passes now. Would fail if the implementer accidentally adds new stages or
    breaks signal wiring.

    Stage count pinned at: 50 (read from generated/catalog.json on 2026-06-25).
    """
    PINNED_STAGE_COUNT = 50

    catalog_path = REAL_REPO_ROOT / "generated" / "catalog.json"
    assert catalog_path.is_file(), f"generated/catalog.json not found at {catalog_path}"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))

    # check_catalog.check returns orphaned signal names; empty means clean.
    orphans = check_catalog.check(catalog)
    assert orphans == [], (
        f"generated/catalog.json has orphaned signals: {orphans!r}. "
        f"Signal wiring must remain coherent."
    )

    stage_count = len(catalog.get("stages", {}))
    assert stage_count == PINNED_STAGE_COUNT, (
        f"generated/catalog.json stage count changed: expected {PINNED_STAGE_COUNT}, "
        f"got {stage_count}. If a new stage was intentionally added, update the "
        f"pinned count in this test."
    )
