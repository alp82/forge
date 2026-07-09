"""Tests for the fable-tier-and-subagent-writes change.

Source plan: .alp-river/artifacts/plan-fable-tier-and-subagent-writes.md

Two orthogonal changes bundled in one release:
  (1) Fable graduation - every `model: opus` agent (20 files) plus every prose
      reference to "opus" as the top model tier moves to `model: fable`.
  (2) `.alp-river/` writes leave the orchestrator - a new off-route run-state
      writer subagent owned the per-turn run-state.json write (that agent has
      since been deleted: the orchestrator now writes the snapshot with its
      native Write tool - Group B pins the deletion), and `code-planner`
      (producer-writes) owns the plan-<slug>.md write.
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

Conventions mirror test_briefs.py / test_artifact_handles.py: REAL_REPO_ROOT via
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
    elsewhere in prose, e.g. "the same ... follow (`doctrine/briefs.md:15`,
    ### Artifact handles)" - a plain substring search would lock onto that
    inline mention instead of the real heading). A non-heading marker is
    matched as a plain substring.
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
# Group A - Change 1: Fable graduation
# ---------------------------------------------------------------------------

# The 16 agent files that graduate from model: opus to model: fable
# (originally 20; interviewer + requirements-clarifier merged into clarifier,
# and assumptions + architecture-reviewer + quality-reviewer dropped in the
# review-wave reviewer consolidation).
GRADUATED_AGENTS = (
    "test-review",
    "plan-challenger",
    "code-implementer",
    "clarifier",
    "plan-arbiter",
    "correctness-reviewer",
    "security-reviewer",
    "discuss",
    "code-planner",
    "capture-agent",
    "code-investigator",
    "system-planner",
    "setup-agent",
    "adr-drafter",
    "ux-prototyper",
    "design-prototyper",
)

# Pinned pre-edit `effort:` value per graduated agent - captured from the repo
# before this change lands. Model moves to fable; effort must NOT move.
GRADUATED_AGENT_EFFORT = {
    "test-review": "high",
    "plan-challenger": "max",
    "code-implementer": "high",
    "clarifier": "high",
    "plan-arbiter": "max",
    "correctness-reviewer": "high",
    "security-reviewer": "high",
    "discuss": "high",
    "code-planner": "max",
    "capture-agent": "high",
    "code-investigator": "high",
    "system-planner": "max",
    "setup-agent": "high",
    "adr-drafter": "high",
    "ux-prototyper": "high",
    "design-prototyper": "high",
}

# Leading names of README.md model-table rows that must read "fable". Content
# anchored (row located by its leading `| name |` cell) so the assertion
# survives README edits above these rows.
README_FABLE_TABLE_ROWS = (
    "clarifier",
    "code-investigator",
    "design-prototyper",
    "ux-prototyper",
    "code-planner",
    "plan-challenger",
    "plan-arbiter",
    "test-review",
    "code-implementer",
    "correctness",
    "shape",
    "security",
    "capture-agent",
    "adr-drafter",
    "system-planner",
)


def _readme_table_row(content, name):
    """Locate a README.md table row by its leading `| name |` cell and return
    the full row text, so callers can assert on the row's other cells without
    pinning a line number."""
    m = re.search(r"^\|\s*" + re.escape(name) + r"\s*\|.*$", content, re.MULTILINE)
    assert m is not None, f"README.md table row for {name!r} not found"
    return m.group(0)


def test_a01_red_no_model_opus_remains_in_agents():
    """TC-01: no agents/*.md file declares `model: opus` anymore."""
    offenders = []
    for path in (REAL_REPO_ROOT / "agents").glob("*.md"):
        content = path.read_text(encoding="utf-8")
        if re.search(r"^model:\s*opus\s*$", content, re.MULTILINE):
            offenders.append(path.name)
    assert (
        offenders == []
    ), f"agents/ must contain no 'model: opus' frontmatter; still present in: {offenders!r}"


def test_a02_red_all_graduated_agents_declare_model_fable():
    """TC-02: each of the 16 named agents now declares `model: fable`."""
    offenders = []
    for name in GRADUATED_AGENTS:
        content = _read(f"agents/{name}.md")
        if not re.search(r"^model:\s*fable\s*$", content, re.MULTILINE):
            offenders.append(name)
    assert (
        offenders == []
    ), f"agents/{{name}}.md must declare 'model: fable'; still missing in: {offenders!r}"


def test_a03_green_effort_lines_unchanged_for_graduated_agents():
    """TC-03 (regression guard): each graduated agent's `effort:` line matches its
    pinned pre-edit value - the model bump must not disturb effort."""
    offenders = []
    for name, expected_effort in GRADUATED_AGENT_EFFORT.items():
        content = _read(f"agents/{name}.md")
        m = re.search(r"^effort:\s*(\S+)\s*$", content, re.MULTILINE)
        actual = m.group(1) if m else None
        if actual != expected_effort:
            offenders.append((name, expected_effort, actual))
    assert offenders == [], (
        f"effort lines must stay unchanged by the model graduation; "
        f"mismatches (name, expected, actual): {offenders!r}"
    )


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


def test_a06_red_workflow_adr_drafter_descriptor_fable():
    """TC-06: WORKFLOW.md's adr-drafter descriptor reads "(read-only, fable)"."""
    content = _read("WORKFLOW.md")
    assert (
        "(read-only, fable)" in content
    ), "WORKFLOW.md must describe adr-drafter as '(read-only, fable)'"


def test_a07_red_model_tiering_has_explicit_fable_assignment_rule():
    """TC-07: ## Model Tiering names fable as the top tier and states an explicit
    assignment rule: fable iff generative planning / adversarial judgment / intent
    extraction; mechanical/analytical stays sonnet; classification/lookups haiku."""
    content = _read("WORKFLOW.md")
    section = _section(content, "## Model Tiering", "## Instruction-to-hook")
    assert (
        "`fable`" in section or "fable" in section
    ), "## Model Tiering must name 'fable' as the top-tier model"
    assert not re.search(
        r"`opus`", section
    ), "## Model Tiering must no longer name 'opus' as a tier"
    # Rule must be explicit enough to distinguish the three tiers by job type.
    for term in ("generative planning", "adversarial judgment", "intent"):
        assert (
            term in section
        ), f"## Model Tiering must state the fable-assignment rule mentioning {term!r}"
    assert (
        "sonnet" in section and "haiku" in section
    ), "## Model Tiering must still name sonnet and haiku as the other active tiers"


def test_a08_red_model_tiering_no_opus_tier_named():
    """TC-08: ## Model Tiering no longer names opus anywhere in its body."""
    content = _read("WORKFLOW.md")
    section = _section(content, "## Model Tiering", "## Instruction-to-hook")
    assert (
        "opus" not in section.lower()
    ), f"## Model Tiering must not mention 'opus' in any case; section={section!r}"


def test_a09_green_model_tiering_effort_paragraph_unchanged():
    """TC-09 (regression guard): the effort paragraph (haiku does not honor effort)
    is textually unchanged by this edit."""
    content = _read("WORKFLOW.md")
    pinned = (
        "It is model-gated: `haiku` does not honor\n"
        "effort, so the haiku classification stages (`triage`, `prototype-identifier`,\n"
        "`health-checker`) carry no `effort` line."
    )
    assert pinned in content, (
        "WORKFLOW.md ## Model Tiering effort paragraph must remain byte-identical; "
        f"pinned text not found: {pinned!r}"
    )


def test_a10_red_readme_model_table_rows_read_fable():
    """TC-10: all 15 specified README.md model-table rows read 'fable'."""
    content = _read("README.md")
    offenders = []
    for name in README_FABLE_TABLE_ROWS:
        row = _readme_table_row(content, name)
        if "fable" not in row:
            offenders.append((name, row))
    assert (
        offenders == []
    ), f"README.md rows must read 'fable'; offending (name, row): {offenders!r}"


def test_a11_red_readme_setup_agent_fable():
    """TC-11: README.md's setup-agent aside prose reads "setup-agent` (fable)"."""
    content = _read("README.md")
    assert (
        "`setup-agent` (fable)" in content
    ), "README.md must contain the aside prose '`setup-agent` (fable)'"


def test_a12_red_readme_no_opus_table_rows():
    """TC-12: `grep -n "| opus |" README.md` returns empty."""
    content = _read("README.md")
    matches = [line for line in content.splitlines() if "| opus |" in line]
    assert (
        matches == []
    ), f"README.md must have no '| opus |' table rows; found: {matches!r}"


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


def test_a14_red_adr_command_fable():
    """TC-14: commands/adr.md:28 reads "(fable, read-only)"."""
    content = _read("commands/adr.md")
    assert (
        "(fable, read-only)" in content
    ), "commands/adr.md must contain '(fable, read-only)'"


def test_a15_red_catalog_doc_example_fable():
    """TC-15: doctrine/CATALOG.md:37 example frontmatter reads `model: fable`."""
    lines = (
        (REAL_REPO_ROOT / "doctrine" / "CATALOG.md")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    line_37 = lines[36] if len(lines) > 36 else ""
    assert re.search(
        r"model:\s*fable", line_37
    ), f"doctrine/CATALOG.md line 37 must read 'model: fable'; got: {line_37!r}"


def test_a16_red_glossary_tier_definition_fable():
    """TC-16: docs/GLOSSARY.md:276 tier definition reads "(haiku/sonnet/fable)"."""
    content = _read("docs/GLOSSARY.md")
    assert (
        "(haiku/sonnet/fable)" in content
    ), "docs/GLOSSARY.md must contain the tier definition '(haiku/sonnet/fable)'"


def test_a17_red_opus_sweep_only_readme_main_session_lines():
    """TC-17: `grep -rn "opus" agents/ commands/ doctrine/ docs/ WORKFLOW.md README.md`
    returns matches ONLY in README.md, and only on the two out-of-scope main-session
    lines (identified by content - each carries "high effort" - not by line number)."""
    targets = [
        REAL_REPO_ROOT / "agents",
        REAL_REPO_ROOT / "commands",
        REAL_REPO_ROOT / "doctrine",
        REAL_REPO_ROOT / "docs",
    ]
    offenders = []
    for target in targets:
        for path in target.rglob("*.md"):
            content = path.read_text(encoding="utf-8")
            if "opus" in content.lower():
                offenders.append(str(path.relative_to(REAL_REPO_ROOT)))
    for name in ("WORKFLOW.md",):
        content = _read(name)
        if "opus" in content.lower():
            offenders.append(name)
    assert offenders == [], (
        f"'opus' must not remain outside README.md's main-session lines; "
        f"found it in: {offenders!r}"
    )

    readme_lines = (
        (REAL_REPO_ROOT / "README.md").read_text(encoding="utf-8").splitlines()
    )
    opus_lines = [line for line in readme_lines if "opus" in line.lower()]
    assert len(opus_lines) == 2, (
        f"README.md must mention 'opus' on exactly two lines (the main-session "
        f"recommendation, out of scope); got: {opus_lines!r}"
    )
    assert all("high effort" in line.lower() for line in opus_lines), (
        f"every README.md line mentioning 'opus' must be the main-session "
        f"'high effort' recommendation; got: {opus_lines!r}"
    )


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

RUN_STATE_SCHEMA_KEYS = (
    "schema_version",
    "run_id",
    "cwd",
    "route",
    "live",
    "available",
    "ran",
    "premises",
    "mid_run_stage",
    "pending_gate",
    "pending_gate_question",
    "artifact_index",
)


def test_b01_agent_file_deleted():
    """The off-route snapshot-writer agent file no longer exists - the agent is
    deleted, its dispatch responsibility folded into the orchestrator's own
    native Write."""
    assert not (
        REAL_REPO_ROOT / "agents" / (NEEDLE + ".md")
    ).exists(), f"agents/{NEEDLE}.md must be deleted"


def test_b02_repo_tracked_grep_clean():
    """A repo-wide tracked-files grep for the agent-name needle finds no
    matches anywhere, except the two historical carriers explicitly excluded
    by design (TODO.md, CHANGELOG.md)."""
    result = subprocess.run(
        ["git", "grep", "-l", "-F", NEEDLE],
        cwd=str(REAL_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    allowed = {"TODO.md", "CHANGELOG.md"}
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


def test_b09b_run_state_schema_sync_canary():
    """Schema-sync drift canary: WORKFLOW.md's brace-delimited step-4 snapshot
    schema keys equal RUN_STATE_SCHEMA_KEYS exactly, and the recovery hook's
    validate-on-read `has("...")` field checks are a non-empty subset of the
    same schema keys. This trips if a future edit adds/removes a schema key in
    only one of the two locations."""
    workflow = _read("WORKFLOW.md")
    schema_match = re.search(r"\{([a-z_, ]+)\}", workflow)
    assert (
        schema_match is not None
    ), "WORKFLOW.md must contain the brace-delimited step-4 snapshot schema list"
    workflow_keys = {k.strip() for k in schema_match.group(1).split(",")}
    assert workflow_keys == set(RUN_STATE_SCHEMA_KEYS), (
        "WORKFLOW.md's schema keys must set-equal RUN_STATE_SCHEMA_KEYS; "
        f"workflow={sorted(workflow_keys)!r} expected={sorted(RUN_STATE_SCHEMA_KEYS)!r}"
    )

    hook_content = _read("hooks/recover-run-state.sh")
    hook_fields = set(re.findall(r'has\("([a-z_]+)"\)', hook_content))
    assert hook_fields, (
        'hooks/recover-run-state.sh must contain at least one has("...") '
        "validate-on-read field check"
    )
    assert hook_fields <= set(RUN_STATE_SCHEMA_KEYS), (
        'hooks/recover-run-state.sh\'s has("...") field checks must be a subset '
        f"of RUN_STATE_SCHEMA_KEYS; hook_fields={sorted(hook_fields)!r} "
        f"expected_superset={sorted(RUN_STATE_SCHEMA_KEYS)!r}"
    )


def test_b12_green_injector_not_wired_to_run_state_writer():
    """TC-30 (regression guard, true both before and after this change):
    hooks/user-context-injector.sh is not special-cased for the deleted
    off-route snapshot-writer agent - it falls through the terminal `*)` case."""
    content = _read("hooks/user-context-injector.sh")
    assert (
        NEEDLE not in content
    ), f"hooks/user-context-injector.sh must not special-case {NEEDLE!r}"


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


def _loop_step4_section():
    content = _read("WORKFLOW.md")
    return _section(content, "4. **Update.**", "Repeat until **convergence**")


def _durability_section():
    content = _read("WORKFLOW.md")
    return _section(content, "## Durability", "## Locks")


def _artifact_handles_section():
    content = _read("WORKFLOW.md")
    return _section(content, "### Artifact handles", "## Revision Contract")


def test_d01_loop_step4_orchestrator_native_write():
    """TC-40 (retargeted): loop step 4 states the orchestrator's own native
    Write (not a dispatch) as the HARD REQUIRED step-4 action, and no longer
    names the deleted agent."""
    section = _loop_step4_section()
    assert (
        "native Write" in section
    ), "loop step 4 must name the orchestrator's native Write"
    assert (
        "HARD REQUIRED step-4 action" in section
    ), "loop step 4 must still name the write as the HARD REQUIRED step-4 action"
    assert (
        NEEDLE not in section
    ), f"loop step 4 must no longer name the deleted {NEEDLE} agent"


def test_d02_loop_step4_read_first_overwrite_no_dispatch_caveats():
    """TC-41 / TC-53 (retargeted): the read-first-then-overwrite note now
    addresses the orchestrator directly, and every dispatch-era caveat
    (fire-and-forget, background handle, watchdog, DISPATCHES language) is
    gone."""
    section = _loop_step4_section()
    assert (
        "Read it once first" in section
    ), "loop step 4 must instruct the orchestrator to Read it once first"
    assert (
        "full overwrite" in section
    ), "loop step 4 must instruct writing the full overwrite"
    assert (
        "fire-and-forget" not in section
    ), "loop step 4 must no longer state the write is fire-and-forget"
    assert (
        "run_in_background: true" not in section
    ), "loop step 4 must no longer document Agent(run_in_background: true)"
    assert (
        "no handle" not in section.lower()
    ), "loop step 4 must no longer carry the 'no handle' dispatch caveat"
    assert (
        "no watchdog" not in section.lower()
    ), "loop step 4 must no longer carry the 'no watchdog' dispatch caveat"
    assert (
        "DISPATCHES" not in section
    ), "loop step 4 must no longer name a dispatch (DISPATCHES) for the persist step"


def test_d03_loop_step4_escaping_sentence_names_orchestrator():
    """TC-42 (retargeted): escaping-burden sentence reads "the orchestrator
    authors this JSON" (the agent-attributed phrasing is gone with the
    dispatch)."""
    section = _loop_step4_section()
    assert (
        "the orchestrator authors this JSON" in section
    ), "loop step 4 must read 'the orchestrator authors this JSON'"
    assert (NEEDLE + " authors this JSON") not in section, (
        f"loop step 4 must no longer attribute JSON-authoring to the deleted "
        f"{NEEDLE} agent"
    )


def test_d04_green_loop_step4_schema_and_scoping_sentences_preserved():
    """TC-43 (regression guard): schema/types/no-written_at/path/durability-scoping
    sentences are preserved verbatim."""
    section = _loop_step4_section()
    pinned = (
        "{schema_version, run_id, cwd, route, live, available, ran, premises, "
        "mid_run_stage, pending_gate, pending_gate_question, artifact_index}"
    )
    assert (
        pinned in section
    ), f"loop step 4 must preserve the verbatim schema block {pinned!r}"
    assert (
        "There is no `written_at` field, freshness is the FILE's mtime, set by the OS on each write."
        in section
    ), "loop step 4 must preserve the no-written_at sentence verbatim"
    assert (
        "<cwd>/.alp-river/runs/<run-id>/run-state.json" in section
    ), "loop step 4 must preserve the per-run write path verbatim"
    assert (
        "Durability rests on this write being a hard step-4 action AND on "
        "`already_run`/`live`/`available` accuracy" in section
    ), "loop step 4 must preserve the durability-scoping sentence verbatim"


def test_d05_loop_step4_failed_write_best_effort():
    """TC-44 (retargeted): rewritten step 4 carries the best-effort failed-Write
    policy with no retry clause - the next turn's hard step-4 write
    supersedes - and no longer carries any dispatch-era retry/ownership
    language."""
    section = _loop_step4_section()
    assert (
        "the next turn's hard step-4 write supersedes it" in section
    ), "loop step 4 must state the next turn's hard step-4 write supersedes a failed write"
    assert (
        "paid deliberately" not in section
    ), "loop step 4 must no longer carry the 'paid deliberately' dispatch-trade sentence"
    assert (
        "re-dispatches" not in section
    ), "loop step 4 must no longer mention re-dispatching a failed write"
    assert (
        "NEVER writes or edits" not in section
    ), "loop step 4 must no longer contain the removed 'NEVER writes or edits' prohibition"


def test_d06_durability_orchestrator_own_write_tool_not_dispatch():
    """TC-45 (retargeted): ## Durability states the orchestrator writes the
    snapshot with its own Write tool as the HARD REQUIRED step-4 action, no
    longer naming a dispatch to the deleted agent."""
    section = _durability_section()
    assert (
        "writes the snapshot with its own Write tool" in section
    ), "## Durability must state the orchestrator writes the snapshot with its own Write tool"
    assert (
        "HARD REQUIRED step-4 action" in section
    ), "## Durability must still name the write as the HARD REQUIRED step-4 action"
    assert ("dispatches the `" + NEEDLE) not in section, (
        f"## Durability must no longer say the orchestrator dispatches the "
        f"deleted {NEEDLE} subagent"
    )
    assert (
        NEEDLE not in section
    ), f"## Durability must no longer mention the deleted {NEEDLE} agent anywhere"


def test_d07_durability_where_to_persist():
    """TC-46 (retargeted): "...where to point the writer" reworded to "...where
    to persist" now that the orchestrator itself is the writer."""
    section = _durability_section()
    assert (
        "where to persist" in section
    ), "## Durability must read '...where to persist'"
    assert (
        "where to point the writer" not in section
    ), "## Durability must no longer read 'where to point the writer'"


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


def test_d11_red_briefs_scoping_clause_bounds_precedent_to_briefs_dir():
    """TC-50: doctrine/briefs.md "Who writes the brief" gains a scoping clause
    bounding the orchestrator-writes-the-doc precedent to .briefs/ render
    artifacts only, cross-referencing WORKFLOW.md."""
    content = _read("doctrine/briefs.md")
    section = _section(content, "## Who writes the brief", "## Brief trigger")
    assert (
        ".briefs/" in section
    ), "doctrine/briefs.md 'Who writes the brief' must scope the precedent to .briefs/"
    assert ".alp-river/" in section, (
        "doctrine/briefs.md 'Who writes the brief' must note .alp-river/ writes are "
        "performed by subagents (out of the precedent's scope)"
    )
    assert (
        "WORKFLOW.md" in section
    ), "doctrine/briefs.md 'Who writes the brief' must cross-reference WORKFLOW.md"


def test_d12_green_briefs_canary_labels_untouched():
    """TC-51 (canary regression): the two pinned labels remain textually untouched."""
    content = _read("doctrine/briefs.md")
    assert (
        "See it in plain words" in content
    ), "doctrine/briefs.md must still carry the pinned label 'See it in plain words'"
    assert (
        "See it as an interactive doc" in content
    ), "doctrine/briefs.md must still carry the pinned label 'See it as an interactive doc'"


def test_d13_red_orchestrator_writes_the_doc_precedent_scoped_to_briefs():
    """TC-52 (acceptance criterion 6, direct): the 'orchestrator-writes-the-doc'
    precedent no longer appears in WORKFLOW.md (both .alp-river/ call-sites
    repointed), and still appears in doctrine/briefs.md (its one true home)."""
    workflow = _read("WORKFLOW.md")
    briefs = _read("doctrine/briefs.md")
    assert "orchestrator-writes-the-doc" not in workflow, (
        "WORKFLOW.md must no longer claim the 'orchestrator-writes-the-doc' precedent "
        "for .alp-river/ writes (both loop step 4 and ### Artifact handles repoint it)"
    )
    assert "orchestrator-writes-the-doc" in briefs, (
        "doctrine/briefs.md must still carry the 'orchestrator-writes-the-doc' precedent "
        "(scoped to .briefs/ render artifacts)"
    )


# ---------------------------------------------------------------------------
# Group E - recover-run-state.sh reword
# ---------------------------------------------------------------------------


def test_e01_recover_hook_names_orchestrator_write():
    """TC-54 (retargeted): the injected context string names the
    orchestrator's own Write tool for the run-state snapshot, still
    references loop step 4, and no longer names the deleted agent."""
    content = _read("hooks/recover-run-state.sh")
    assert (
        "write the canonical run-state snapshot with your own Write tool" in content
    ), (
        "hooks/recover-run-state.sh must inject a context string naming the "
        "orchestrator's own Write tool for the run-state snapshot"
    )
    assert (
        "loop step 4" in content
    ), "hooks/recover-run-state.sh injected context must still reference loop step 4"
    assert (
        NEEDLE not in content
    ), f"hooks/recover-run-state.sh must no longer name the deleted {NEEDLE} agent"


def test_e02_green_write_path_fragment_unchanged():
    """TC-55 (regression guard): the computed write_path expression and the
    .alp-river/runs/<sid>/run-state.json path fragment are unchanged."""
    content = _read("hooks/recover-run-state.sh")
    assert (
        'write_path="${project_cwd}/.alp-river/runs/${session_id}/run-state.json"'
        in content
    ), "hooks/recover-run-state.sh write_path computation must remain byte-identical"


# TC-56 (hooks/tests/test_recover_run_state.py::test_rr_writepath_always_emitted
# passes after the reword) is exercised by the existing regression suite -
# it is not duplicated here; running `pytest hooks/tests/` covers it.


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
#   TC-67  hooks/tests/test_briefs.py              (green after briefs.md scoping clause)
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
