"""Tests for the fable-tier-and-subagent-writes change.

Source plan: .alp-river/artifacts/plan-fable-tier-and-subagent-writes.md

Two orthogonal changes bundled in one release:
  (1) Fable graduation - every `model: opus` agent (20 files) plus every prose
      reference to "opus" as the top model tier moves to `model: fable`.
  (2) `.alp-river/` plan-artifact writes: `code-planner` (producer-writes) owns
      the plan-<slug>.md write; Group B pins the deletion of the old off-route
      snapshot-writer agent.
  (3) Release stamp - 1.3.2 -> 1.3.3, plugin.json + marketplace.json + CHANGELOG.md
      + README "Latest updates".

RED tests are grouped A-F below and fail until the corresponding edit lands.
GREEN tests (suffixed `_green_`) are regression guards: they pass today AND
must stay green after the implementation lands - they pin content this change
must NOT touch.

Not every acceptance-criterion prose sentence earns a permanent test here; the
plan's own ## Testing section (grep sweeps, `pytest hooks/tests/`,
`python3 hooks/check_catalog.py`, `python3 hooks/audit.py`,
`git diff --stat generated/catalog.json`) is the one-shot verification
checklist the verifier stage runs directly - duplicating all of it as
permanent prose-assertion tests would bloat the suite for no durable value.

Conventions mirror test_artifact_handles.py: REAL_REPO_ROOT via
Path(__file__).resolve().parents[2]; insert hooks/ on sys.path; import audit and
check_catalog.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # hooks/
import audit
import check_catalog

REAL_REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(relpath):
    path = REAL_REPO_ROOT / relpath
    assert path.is_file(), f"{relpath} not found at {path}"
    return path.read_text(encoding="utf-8")


def _locate(content, marker, from_pos=0):
    """Find `marker` in content, starting from from_pos.

    A `#`-prefixed marker is treated as a heading and matched only at the START
    of a line (many WORKFLOW.md headings are also cross-referenced inline
    elsewhere in prose, e.g. "decides-vs-performs (### Artifact handles)" - a
    plain substring search would lock onto that inline mention instead of the
    real heading). A non-heading marker is matched as a plain substring.
    """
    if marker.startswith("#"):
        m = re.compile(r"^" + re.escape(marker), re.MULTILINE).search(content, from_pos)
        assert (
            m is not None
        ), f"heading marker {marker!r} not found from position {from_pos}"
        return m.start()
    idx = content.index(marker, from_pos)
    return idx


def _section(content, start_marker, end_marker):
    """Return the substring of content between start_marker (inclusive) and the
    next occurrence of end_marker (exclusive), each resolved via _locate so a
    heading marker binds to its real heading line, not an inline cross-reference.
    Fails loudly if either marker is missing, so a reworded heading surfaces as
    a clear test failure."""
    start = _locate(content, start_marker)
    end = _locate(content, end_marker, start + len(start_marker))
    return content[start:end]


# ---------------------------------------------------------------------------
# Group A - model retier (1.3.14). Originally the RED tests for the 1.3.3 fable
# graduation; the 1.3.14 retier repurposed them to pin the post-retier state:
# fable is reserved for four deep stages at medium effort, every other stage that
# was on fable moved to opus, and effort: max is retired from the repo while xhigh
# is admitted to the doctrine's enumerated effort set.
# ---------------------------------------------------------------------------

# The four deep generative/adversarial stages that stay on model: fable after the
# 1.3.14 retier: the code planner, the plan challenger, the plan arbiter, and the
# code implementer. Every other stage that was on fable moved to model: opus.
FABLE_STAGES = (
    "code-planner",
    "plan-challenger",
    "plan-arbiter",
    "code-implementer",
)

# Post-retier (model, effort) pairing per stage the retier touched. The old premise
# ("model moves to fable; effort must NOT move") is dead: this map now guards the
# post-retier model+effort pairing - fable reserved for the four deep stages at
# medium, everything else moved to opus at its job-matched effort (analysis, the
# review lenses, and the intent loops at high).
RETIERED_STAGE_TIERS = {
    "code-planner": ("fable", "medium"),
    "plan-challenger": ("fable", "medium"),
    "plan-arbiter": ("fable", "medium"),
    "code-implementer": ("fable", "medium"),
    "system-planner": ("opus", "high"),
    "code-investigator": ("opus", "high"),
    "correctness-reviewer": ("opus", "high"),
    "shape-reviewer": ("opus", "high"),
    "security-reviewer": ("opus", "high"),
    "test-review": ("opus", "high"),
    "clarifier": ("opus", "high"),
    "discuss": ("opus", "high"),
    "design-prototyper": ("opus", "high"),
    "ux-prototyper": ("opus", "high"),
}

# The stages that must now declare model: opus - the retiered agents whose model
# moved off fable.
OPUS_AGENTS = tuple(
    name for name, (model, _effort) in RETIERED_STAGE_TIERS.items() if model == "opus"
)

# Leading names of README.md model-table rows that must read "fable" - reduced by
# the retier to the four stages that stay on fable. Content anchored (row located
# by its leading `| name |` cell) so the assertion survives README edits above.
README_FABLE_TABLE_ROWS = (
    "code-planner",
    "plan-challenger",
    "plan-arbiter",
    "code-implementer",
)

# Sibling tuple: README.md model-table rows that must now read "opus" after the
# retier. The review-lens rows carry their short lens names (correctness, shape,
# security).
README_OPUS_TABLE_ROWS = (
    "clarifier",
    "code-investigator",
    "design-prototyper",
    "ux-prototyper",
    "test-review",
    "system-planner",
    "correctness",
    "shape",
    "security",
)


def _readme_table_row(content, name):
    """Locate a README.md table row by its leading `| name |` cell and return
    the full row text, so callers can assert on the row's other cells without
    pinning a line number."""
    m = re.search(r"^\|\s*" + re.escape(name) + r"\s*\|.*$", content, re.MULTILINE)
    assert m is not None, f"README.md table row for {name!r} not found"
    return m.group(0)


def test_a01_agents_model_opus_set_is_exactly_the_retiered_stages():
    """The set of agents/*.md files declaring `model: opus` equals exactly the
    stages the retier moved to opus - no more, no fewer."""
    opus_files = set()
    for path in (REAL_REPO_ROOT / "agents").glob("*.md"):
        content = path.read_text(encoding="utf-8")
        if re.search(r"^model:\s*opus\s*$", content, re.MULTILINE):
            opus_files.add(path.stem)
    assert opus_files == set(OPUS_AGENTS), (
        f"agents/ 'model: opus' set must equal the retiered opus stages; "
        f"got {sorted(opus_files)!r} expected {sorted(OPUS_AGENTS)!r}"
    )


def test_a02_only_the_four_deep_stages_declare_model_fable():
    """Exactly the four deep stages declare `model: fable`, and no other agent does."""
    fable_files = set()
    for path in (REAL_REPO_ROOT / "agents").glob("*.md"):
        content = path.read_text(encoding="utf-8")
        if re.search(r"^model:\s*fable\s*$", content, re.MULTILINE):
            fable_files.add(path.stem)
    assert fable_files == set(FABLE_STAGES), (
        f"agents/ 'model: fable' set must equal the four deep stages; "
        f"got {sorted(fable_files)!r} expected {sorted(FABLE_STAGES)!r}"
    )


def test_a03_retiered_agents_model_and_effort_match_pairing():
    """Each retiered agent's frontmatter (model, effort) matches its post-retier
    pinned pairing."""
    offenders = []
    for name, expected in RETIERED_STAGE_TIERS.items():
        content = _read(f"agents/{name}.md")
        mm = re.search(r"^model:\s*(\S+)\s*$", content, re.MULTILINE)
        em = re.search(r"^effort:\s*(\S+)\s*$", content, re.MULTILINE)
        got = (mm.group(1) if mm else None, em.group(1) if em else None)
        if got != expected:
            offenders.append((name, expected, got))
    assert offenders == [], (
        f"retiered agents' (model, effort) must match the pinned pairing; "
        f"mismatches (name, expected, actual): {offenders!r}"
    )


def test_a03b_effort_max_retired_from_agents():
    """`effort: max` is retired from the repo - no agents/*.md declares it."""
    offenders = []
    for path in (REAL_REPO_ROOT / "agents").glob("*.md"):
        content = path.read_text(encoding="utf-8")
        if re.search(r"^effort:\s*max\s*$", content, re.MULTILINE):
            offenders.append(path.name)
    assert (
        offenders == []
    ), f"no agents/*.md may declare 'effort: max'; still present in: {offenders!r}"


def test_a04_green_fixer_model_stays_sonnet():
    """TC-04 (edge case, regression guard): agents/fixer.md frontmatter model
    stays 'sonnet' - fixer itself is not graduated, only its L/XL override target."""
    content = _read("agents/fixer.md")
    assert re.search(
        r"^model:\s*sonnet\s*$", content, re.MULTILINE
    ), "agents/fixer.md frontmatter 'model:' must stay 'sonnet'"


def test_a05_red_fixer_body_overrides_to_fable():
    """TC-05: agents/fixer.md body prose reads "overrides to fable" (was "opus")."""
    content = _read("agents/fixer.md")
    assert (
        "overrides to fable" in content
    ), "agents/fixer.md must contain the body prose 'overrides to fable'"
    assert (
        "overrides to opus" not in content
    ), "agents/fixer.md must no longer contain 'overrides to opus'"


def test_a07_model_tiering_names_all_four_tiers_and_job_matched_effort():
    """## Model Tiering names all four active tiers (fable, opus, sonnet, haiku),
    states effort is matched to the job, and reserves fable for the deep
    generative/adversarial stages."""
    content = _read("WORKFLOW.md")
    section = _section(content, "## Model Tiering", "## Instruction-to-hook")
    for tier in ("`fable`", "`opus`", "`sonnet`", "`haiku`"):
        assert tier in section, f"## Model Tiering must name {tier} as an active tier"
    assert (
        "generative and adversarial" in section
    ), "## Model Tiering must reserve fable for the deep generative/adversarial stages"
    assert (
        "matched to the JOB" in section
    ), "## Model Tiering must state effort is matched to the JOB, not the model"


def test_a08_model_tiering_enumerates_xhigh_and_marks_both_reserve_rungs_unused():
    """## Model Tiering enumerates the effort levels including `xhigh` (kept in the
    doctrine's set) and documents both reserve rungs (`xhigh` and `max`) as not
    currently declared by any stage, each with its own reason."""
    content = _read("WORKFLOW.md")
    section = _section(content, "## Model Tiering", "## Instruction-to-hook")
    for level in ("`low`", "`medium`", "`high`", "`xhigh`", "`max`"):
        assert level in section, f"## Model Tiering must enumerate effort level {level}"
    assert (
        "neither is currently declared by any stage" in section
    ), "## Model Tiering must document that neither xhigh nor max is declared by any stage"
    assert (
        "held in reserve as the documented best setting for coding and agentic work"
        in section
    ), "## Model Tiering must name xhigh as held in reserve as the best coding setting"
    assert (
        "prone to overthinking with diminishing returns" in section
    ), "## Model Tiering must document max as avoided for overthinking with diminishing returns"


def test_a09_green_model_tiering_effort_paragraph_tail_pinned():
    """Regression guard: the effort paragraph's model-gating tail (haiku does not
    honor effort) is pinned byte-identical to the retiered Step-2 wording."""
    content = _read("WORKFLOW.md")
    pinned = (
        "It is model-gated: `haiku` does not honor effort, so the haiku "
        "classification stages (`triage`, `prototype-identifier`, "
        "`health-checker`) carry no `effort` line."
    )
    assert pinned in content, (
        "WORKFLOW.md ## Model Tiering effort paragraph tail must remain byte-identical; "
        f"pinned text not found: {pinned!r}"
    )


def test_a10_readme_fable_rows_read_fable_and_opus_rows_read_opus():
    """The four README.md fable rows read 'fable'; the retiered rows read 'opus'."""
    content = _read("README.md")
    fable_offenders = [
        (name, _readme_table_row(content, name))
        for name in README_FABLE_TABLE_ROWS
        if "fable" not in _readme_table_row(content, name)
    ]
    assert (
        fable_offenders == []
    ), f"README.md rows must read 'fable'; offending: {fable_offenders!r}"
    opus_offenders = [
        (name, _readme_table_row(content, name))
        for name in README_OPUS_TABLE_ROWS
        if "opus" not in _readme_table_row(content, name)
    ]
    assert (
        opus_offenders == []
    ), f"README.md rows must read 'opus'; offending: {opus_offenders!r}"


def test_a12_readme_fable_table_rows_are_exactly_the_four():
    """No README.md model-table row reads 'fable' except the four deep stages -
    every other stage-table row must have been retiered off fable."""
    content = _read("README.md")
    fable_rows = [
        line
        for line in content.splitlines()
        if line.startswith("|") and "| fable |" in line
    ]
    row_names = [line.split("|")[1].strip() for line in fable_rows]
    assert set(row_names) == set(README_FABLE_TABLE_ROWS), (
        f"README.md '| fable |' rows must be exactly the four deep stages; "
        f"got {sorted(row_names)!r} expected {sorted(README_FABLE_TABLE_ROWS)!r}"
    )


def test_a13_green_readme_discuss_still_absent_from_model_table():
    """TC-13 (edge case, regression guard): README.md gains no model-table row for
    'discuss' - it has none today (Talk section renders flat) and must stay absent."""
    content = _read("README.md")
    offenders = [
        line for line in content.splitlines() if re.match(r"^\|\s*discuss\s*\|", line)
    ]
    assert (
        offenders == []
    ), f"README.md must not gain a '| discuss | ... |' model-table row; found: {offenders!r}"


def test_a15_catalog_doc_example_matches_security_reviewer_model():
    """doctrine/CATALOG.md's schema example uses security-reviewer, so its example
    `model:` line must track security-reviewer's real frontmatter model - opus after
    the retier."""
    content = _read("doctrine/CATALOG.md")
    assert re.search(
        r"^model:\s*opus\s*$", content, re.MULTILINE
    ), "doctrine/CATALOG.md schema example must read 'model: opus'"
    assert re.search(
        r"^model:\s*opus\s*$", _read("agents/security-reviewer.md"), re.MULTILINE
    ), "the doc example must match security-reviewer's real 'model: opus'"


def test_a17_agent_model_sweep_fable_only_four_rest_opus():
    """Whole-agents sweep: every agents/*.md declares a model; the only files on
    fable are the four deep stages and the opus set equals exactly the retiered
    stages - nothing regressed onto the wrong tier."""
    fable_files = set()
    opus_files = set()
    for path in (REAL_REPO_ROOT / "agents").glob("*.md"):
        content = path.read_text(encoding="utf-8")
        m = re.search(r"^model:\s*(\S+)\s*$", content, re.MULTILINE)
        assert m is not None, f"{path.name} must declare a 'model:' line"
        model = m.group(1)
        if model == "fable":
            fable_files.add(path.stem)
        elif model == "opus":
            opus_files.add(path.stem)
    assert fable_files == set(
        FABLE_STAGES
    ), f"only the four deep stages may be on fable; got {sorted(fable_files)!r}"
    assert opus_files == set(
        OPUS_AGENTS
    ), f"the opus set must equal the retiered stages; got {sorted(opus_files)!r}"


def test_a18_green_readme_main_session_opus_lines_untouched():
    """TC-18 (negative / scope boundary, regression guard): README.md's
    main-session Opus recommendation prose is NOT touched by this change."""
    content = _read("README.md")
    assert (
        "Set your main session model to **Opus at high effort**" in content
    ), "README.md must still say 'Set your main session model to **Opus at high effort**'"
    assert (
        "Run the main session on a top-tier model like Opus at high effort." in content
    ), (
        "README.md must still say 'Run the main session on a top-tier model like "
        "Opus at high effort.'"
    )


# ---------------------------------------------------------------------------
# Group B - run-state snapshot write ownership (agent deleted; orchestrator
# native Write)
# ---------------------------------------------------------------------------

# Split literal so this test module is never itself a grep hit for the needle
# it asserts is gone from the rest of the repo.
NEEDLE = "run-state-" "writer"


def test_b01_agent_file_deleted():
    """The off-route snapshot-writer agent file no longer exists - the agent is
    deleted, its dispatch responsibility folded into the orchestrator's own
    native Write."""
    assert not (
        REAL_REPO_ROOT / "agents" / (NEEDLE + ".md")
    ).exists(), f"agents/{NEEDLE}.md must be deleted"


def test_b02_repo_tracked_grep_clean():
    """A repo-wide tracked-files grep for the agent-name needle finds no
    matches anywhere, except the three historical carriers explicitly excluded
    by design (TODO.md, CHANGELOG.md, docs/research/pipeline-audit.md)."""
    result = subprocess.run(
        ["git", "grep", "-l", "-F", NEEDLE],
        cwd=str(REAL_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    allowed = {"TODO.md", "CHANGELOG.md", "docs/research/pipeline-audit.md"}
    if result.returncode == 1:
        return  # no tracked carrier at all - clean
    assert result.returncode == 0, (
        f"git grep must exit 0 or 1; got {result.returncode}; "
        f"stderr={result.stderr!r}"
    )
    matched_paths = {line for line in result.stdout.splitlines() if line}
    offenders = matched_paths - allowed
    assert offenders == set(), (
        f"repo-wide grep for the agent-name needle must find no matches outside "
        f"{allowed!r}; offending paths: {sorted(offenders)!r}"
    )


def test_b13_green_check_catalog_exits_clean():
    """TC-32 (regression guard): python3 hooks/check_catalog.py exits clean today
    and must stay clean - adding an off-route agent must not disturb the catalog."""
    result = subprocess.run(
        [sys.executable, str(REAL_REPO_ROOT / "hooks" / "check_catalog.py")],
        capture_output=True,
        text=True,
        cwd=str(REAL_REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"hooks/check_catalog.py must exit 0; got {result.returncode}; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


# Verification checklist item (not a durable pytest - requires a git baseline
# taken immediately before the edit lands, which a static test cannot assert):
#   TC-31: `git diff --stat generated/catalog.json` shows no change after adding
#           the (now-deleted) off-route snapshot-writer agent file and bumping
#           20 model: fields. The verifier stage runs this grep/diff directly
#           per the plan's ## Testing section.


# ---------------------------------------------------------------------------
# Group C - Change 2: code-planner producer-writes
# ---------------------------------------------------------------------------


def test_c01_red_code_planner_tools_gains_write():
    """TC-33: agents/code-planner.md frontmatter tools: includes Write alongside
    Glob, Grep, Read, WebSearch, WebFetch."""
    content = _read("agents/code-planner.md")
    tools_match = re.search(r"^tools:\s*(.+)$", content, re.MULTILINE)
    assert tools_match is not None, "code-planner.md must declare a 'tools:' line"
    tools = {t.strip() for t in tools_match.group(1).split(",")}
    expected = {"Glob", "Grep", "Read", "WebSearch", "WebFetch", "Write"}
    assert (
        expected <= tools
    ), f"code-planner.md tools must include {expected!r}; got {tools!r}"


def test_c02_red_input_block_gains_artifact_offload_slot():
    """TC-34: ## Input block gains <ARTIFACT_OFFLOAD> slot."""
    content = _read("agents/code-planner.md")
    assert (
        "<ARTIFACT_OFFLOAD>" in content
    ), "code-planner.md must declare an <ARTIFACT_OFFLOAD> input slot"


def test_c02b_red_catalog_code_planner_input_template_gains_artifact_offload_slot():
    """TC-34 (compiled artifact): generated/catalog.json's code-planner stage
    input_template also contains the <ARTIFACT_OFFLOAD> slot - the compiled
    artifact the orchestrator actually reads at runtime, not just the source
    agents/code-planner.md markdown checked by test_c02. A hand-edit of the
    source without re-running gen-catalog.py would silently break the offload
    path while test_c02 alone stays green."""
    catalog_path = REAL_REPO_ROOT / "generated" / "catalog.json"
    assert catalog_path.is_file(), f"generated/catalog.json not found at {catalog_path}"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    stages = catalog.get("stages", {})
    assert (
        "code-planner" in stages
    ), "stage 'code-planner' missing from generated/catalog.json stages"
    tmpl = stages["code-planner"].get("input_template", "")
    assert "<ARTIFACT_OFFLOAD>" in tmpl, (
        "stages['code-planner'].input_template must contain '<ARTIFACT_OFFLOAD>'; "
        f"template starts with: {tmpl[:120]!r}"
    )


def test_c03_red_process_documents_offload_write_step():
    """TC-35: ## Process documents writing the verbatim <APPROVED_PLAN> block to
    <ARTIFACT_OFFLOAD> when it is a path and the block clears the size threshold."""
    content = _read("agents/code-planner.md")
    assert (
        "RIVER_ARTIFACT_OFFLOAD_CHARS" in content
    ), "code-planner.md must reference the RIVER_ARTIFACT_OFFLOAD_CHARS threshold"
    assert (
        "<APPROVED_PLAN>" in content
    ), "code-planner.md must still emit <APPROVED_PLAN>"


def test_c04_red_edge_offload_none_no_write():
    """TC-36 (edge case): documented behavior when <ARTIFACT_OFFLOAD> = "none" -
    no Write occurs, block still returned inline."""
    content = _read("agents/code-planner.md")
    slot_line_match = re.search(r"^.*<ARTIFACT_OFFLOAD>.*$", content, re.MULTILINE)
    assert (
        slot_line_match is not None
    ), "code-planner.md must declare an <ARTIFACT_OFFLOAD> input slot"
    assert '"none"' in slot_line_match.group(0), (
        'the <ARTIFACT_OFFLOAD> slot description must document the "none" case; '
        f"got: {slot_line_match.group(0)!r}"
    )


def test_c05_red_edge_revise_overwrite_in_place():
    """TC-38 (edge case): documented behavior on Revise / re-split with the same
    path - overwrite-in-place, not append or duplicate."""
    content = _read("agents/code-planner.md")
    assert (
        "overwrite" in content.lower()
    ), "code-planner.md must document overwrite-in-place behavior on a Revise/re-split"


def test_c06_green_output_data_contract_unchanged():
    """TC-39 (regression guard): the catalog's code-planner data.output still
    declares '@approved-plan' - the block is always returned inline regardless of
    offload outcome, so the output contract is unchanged."""
    catalog_path = REAL_REPO_ROOT / "generated" / "catalog.json"
    assert catalog_path.is_file(), f"generated/catalog.json not found at {catalog_path}"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    stage = catalog.get("stages", {}).get("code-planner", {})
    output = stage.get("data", {}).get("output", [])
    assert (
        "approved-plan" in output
    ), f"code-planner's catalog output must still include 'approved-plan'; got {output!r}"


# ---------------------------------------------------------------------------
# Group D - WORKFLOW.md / doctrine write-responsibility rewrite
# ---------------------------------------------------------------------------


def _artifact_handles_section():
    content = _read("WORKFLOW.md")
    return _section(content, "### Artifact handles", "## Revision Contract")


def test_d08_red_artifact_handles_decides_vs_performs_split():
    """TC-47: ### Artifact handles Write-timing states orchestrator DECIDES the
    offload and code-planner PERFORMS the write."""
    section = _artifact_handles_section()
    assert (
        "code-planner" in section
    ), "### Artifact handles write-timing must name code-planner as the write performer"
    assert (
        "decides" in section.lower() or "DECIDES" in section
    ), "### Artifact handles must state the orchestrator DECIDES the offload"
    assert (
        "performs" in section.lower() or "PERFORMS" in section
    ), "### Artifact handles must state code-planner PERFORMS the write"


def test_d09_red_artifact_handles_no_sole_writer_clause():
    """TC-48 (negative): ### Artifact handles no longer contains the removed
    "orchestrator is the sole writer" clause."""
    section = _artifact_handles_section()
    assert (
        "orchestrator is the sole writer" not in section
    ), "### Artifact handles must no longer contain the removed sole-writer clause"


def test_d10_red_artifact_handles_milestone_paragraph_collapsed():
    """TC-49: the milestone-boundary paragraph collapses to: Revise/re-split
    reuses the same path -> overwrite in place; absent a re-split nothing
    rewrites."""
    section = _artifact_handles_section()
    assert (
        "overwrite" in section.lower()
    ), "### Artifact handles must state the file overwrites in place on a re-split"
    assert (
        "re-split" in section
    ), "### Artifact handles must mention re-split in the collapsed milestone paragraph"


# ---------------------------------------------------------------------------
# Group F - Change 3: release stamp
# ---------------------------------------------------------------------------


def test_f02_red_changelog_gains_1_3_3_entry():
    """TC-60: CHANGELOG.md gains a "## 1.3.3 - 2026-07-02" entry."""
    content = _read("CHANGELOG.md")
    assert (
        "## 1.3.3 - 2026-07-02" in content
    ), "CHANGELOG.md must gain a '## 1.3.3 - 2026-07-02' entry"


def test_f03_red_changelog_1_3_3_entry_has_outcome_only_bullet():
    """TC-61: the 1.3.3 entry contains a bullet on the model-tier outcome,
    outcome-only phrasing (no internal agent/file names)."""
    content = _read("CHANGELOG.md")
    start = content.index("## 1.3.3 - 2026-07-02")
    next_heading = content.find("\n## ", start + 1)
    entry = content[start:] if next_heading == -1 else content[start:next_heading]
    assert re.search(
        r"^- ", entry, re.MULTILINE
    ), "the 1.3.3 CHANGELOG entry must contain at least one bullet"
    for forbidden in ("run-state-" "writer", "code-planner", ".md", "agents/"):
        assert forbidden not in entry, (
            f"the 1.3.3 CHANGELOG entry must be outcome-only prose, no internal "
            f"names like {forbidden!r}; entry={entry!r}"
        )


def test_f04_red_changelog_1_3_3_entry_no_writer_identity_bullet():
    """TC-62 (edge case / negative): the 1.3.3 entry contains no bullet about the
    writer-identity change - it is invisible to users and earns no bullet."""
    content = _read("CHANGELOG.md")
    start = content.index("## 1.3.3 - 2026-07-02")
    next_heading = content.find("\n## ", start + 1)
    entry = content[start:] if next_heading == -1 else content[start:next_heading]
    for term in ("run-state-" "writer", "who writes", "writer identity"):
        assert term.lower() not in entry.lower(), (
            f"the 1.3.3 CHANGELOG entry must not mention the writer-identity change "
            f"({term!r} found); entry={entry!r}"
        )


def test_f05_readme_latest_updates_topmost_entry_is_current_version():
    """TC-63, re-pinned at 1.3.10: README.md ## 📰 Latest updates rolls (it keeps
    the last three releases), so instead of pinning a literal version this asserts
    the topmost entry matches the shipped plugin.json version - the durable form
    of the original 'gains a condensed **1.3.7** entry at the top' contract."""
    version = json.loads(
        (REAL_REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )["version"]
    content = _read("README.md")
    section = _section(content, "## 📰 Latest updates", "Full history in")
    first_entry_match = re.search(r"\*\*(\d+\.\d+\.\d+)\*\*", section)
    assert first_entry_match, "README.md ## 📰 Latest updates must contain an entry"
    assert first_entry_match.group(1) == version, (
        f"the topmost Latest updates entry must match plugin.json version "
        f"{version!r}; got {first_entry_match.group(1)!r}"
    )


def test_f06_red_changelog_gains_1_3_5_entry():
    """CHANGELOG.md gains a "## 1.3.5 - 2026-07-03" entry (release stamp for the
    deleted-writer-agent removal)."""
    content = _read("CHANGELOG.md")
    assert (
        "## 1.3.5 - 2026-07-03" in content
    ), "CHANGELOG.md must gain a '## 1.3.5 - 2026-07-03' entry"


def test_f07_red_changelog_1_3_5_entry_has_outcome_only_bullet():
    """The 1.3.5 entry contains a bullet on the direct-write outcome,
    outcome-only phrasing (no internal agent/file names)."""
    content = _read("CHANGELOG.md")
    start = content.index("## 1.3.5 - 2026-07-03")
    next_heading = content.find("\n## ", start + 1)
    entry = content[start:] if next_heading == -1 else content[start:next_heading]
    assert re.search(
        r"^- ", entry, re.MULTILINE
    ), "the 1.3.5 CHANGELOG entry must contain at least one bullet"
    for forbidden in (NEEDLE, "code-planner", ".md", "agents/"):
        assert forbidden not in entry, (
            f"the 1.3.5 CHANGELOG entry must be outcome-only prose, no internal "
            f"names like {forbidden!r}; entry={entry!r}"
        )


def test_f08_red_changelog_1_3_5_entry_no_writer_identity_bullet():
    """(edge case / negative): the 1.3.5 entry contains no bullet naming the
    deleted writer agent - it is invisible to users and earns no bullet."""
    content = _read("CHANGELOG.md")
    start = content.index("## 1.3.5 - 2026-07-03")
    next_heading = content.find("\n## ", start + 1)
    entry = content[start:] if next_heading == -1 else content[start:next_heading]
    for term in (NEEDLE, "who writes", "writer identity"):
        assert term.lower() not in entry.lower(), (
            f"the 1.3.5 CHANGELOG entry must not mention the writer-identity change "
            f"({term!r} found); entry={entry!r}"
        )


def test_f09_red_readme_latest_updates_topmost_and_last_three():
    """Re-pinned at 1.3.11: README.md ## 📰 Latest updates keeps exactly the last
    three entries with the shipped plugin.json version topmost - the durable form
    (matching test_f05's re-pin) of the original 'gains a **1.3.9** entry at the
    top' contract, which went stale once 1.3.9 rolled to the window's tail."""
    version = json.loads(
        (REAL_REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )["version"]
    content = _read("README.md")
    section = _section(content, "## 📰 Latest updates", "Full history in")
    entries = re.findall(r"\*\*(\d+\.\d+\.\d+)\*\*", section)
    assert (
        len(entries) == 3
    ), f"Latest updates must keep exactly the last three entries; found {entries!r}"
    assert entries[0] == version, (
        f"the topmost Latest updates entry must match plugin.json version "
        f"{version!r}; got {entries[0]!r}"
    )


# ---------------------------------------------------------------------------
# Group G - Regression gates (whole-suite) - one-shot verification checklist
# ---------------------------------------------------------------------------
#
# These acceptance-level gates are run directly by the verifier stage per the
# plan's ## Testing section rather than re-implemented as meta-pytest here
# (a pytest test that shells out to `pytest hooks/tests/` would be circular):
#
#   TC-64  pytest hooks/tests/                    (full suite green)
#   TC-65  hooks/tests/test_audit.py               (doctrine-integrity canaries intact)
#   TC-66  hooks/tests/test_artifact_handles.py    (green after ### Artifact handles rewrite)
#   TC-68  python3 hooks/check_catalog.py          (clean) - pinned above as test_b13
#   TC-69  python3 hooks/audit.py                  (exits 0, doctrine-integrity unchanged)
#   TC-70  git diff --stat generated/catalog.json  (no change) - see TC-31 note above


def test_g01_green_audit_py_subprocess_exits_0_on_live_repo():
    """TC-69 (regression guard, partial): python3 hooks/audit.py exits 0 against
    the live repo today and must keep exiting 0 after this change."""
    result = subprocess.run(
        [sys.executable, str(REAL_REPO_ROOT / "hooks" / "audit.py")],
        capture_output=True,
        text=True,
        cwd=str(REAL_REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"hooks/audit.py must exit 0; got {result.returncode}; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
