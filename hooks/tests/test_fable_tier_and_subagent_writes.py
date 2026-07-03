"""Tests for the fable-tier-and-subagent-writes change.

Source plan: .alp-river/artifacts/plan-fable-tier-and-subagent-writes.md

Two orthogonal changes bundled in one release:
  (1) Fable graduation - every `model: opus` agent (20 files) plus every prose
      reference to "opus" as the top model tier moves to `model: fable`.
  (2) `.alp-river/` writes leave the orchestrator - a new off-route
      `run-state-writer` subagent owns the per-turn run-state.json write, and
      `code-planner` (producer-writes) owns the plan-<slug>.md write.
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

# The 20 agent files that graduate from model: opus to model: fable.
GRADUATED_AGENTS = (
    "test-review",
    "plan-challenger",
    "code-implementer",
    "interviewer",
    "requirements-clarifier",
    "plan-arbiter",
    "assumptions",
    "architecture-reviewer",
    "quality-reviewer",
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
    "interviewer": "high",
    "requirements-clarifier": "high",
    "plan-arbiter": "max",
    "assumptions": "high",
    "architecture-reviewer": "high",
    "quality-reviewer": "high",
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

# README.md model-table line numbers that must read "fable" (1-indexed).
README_FABLE_TABLE_LINES = (
    208,
    209,
    228,
    240,
    241,
    242,
    243,
    244,
    258,
    270,
    283,
    285,
    289,
    291,
    297,
    314,
    315,
    340,
)


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
    """TC-02: each of the 20 named agents now declares `model: fable`."""
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
    """TC-10: all 18 specified README.md model-table lines read 'fable'."""
    lines = (REAL_REPO_ROOT / "README.md").read_text(encoding="utf-8").splitlines()
    offenders = []
    for lineno in README_FABLE_TABLE_LINES:
        text = lines[lineno - 1] if lineno - 1 < len(lines) else ""
        if "fable" not in text:
            offenders.append((lineno, text))
    assert (
        offenders == []
    ), f"README.md lines must read 'fable'; offending (lineno, text): {offenders!r}"


def test_a11_red_readme_line_313_setup_agent_fable():
    """TC-11: README.md line 328 prose reads "setup-agent (fable)"."""
    lines = (REAL_REPO_ROOT / "README.md").read_text(encoding="utf-8").splitlines()
    line_328 = lines[327] if len(lines) > 327 else ""
    assert (
        "setup-agent" in line_328 and "(fable)" in line_328
    ), f"README.md line 328 must read 'setup-agent (fable)'; got: {line_328!r}"


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
    returns matches ONLY in README.md, and only at the two out-of-scope main-session
    lines (73, 77)."""
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
    opus_linenos = [
        i + 1 for i, line in enumerate(readme_lines) if "opus" in line.lower()
    ]
    assert opus_linenos == [73, 77], (
        f"README.md must mention 'opus' only on lines 73 and 77 (main-session "
        f"recommendation, out of scope); got lines: {opus_linenos!r}"
    )


def test_a18_green_readme_main_session_opus_lines_untouched():
    """TC-18 (negative / scope boundary, regression guard): README.md lines 73 and
    77 (main-session Opus recommendation) are NOT touched by this change."""
    lines = (REAL_REPO_ROOT / "README.md").read_text(encoding="utf-8").splitlines()
    line_73 = lines[72] if len(lines) > 72 else ""
    line_77 = lines[76] if len(lines) > 76 else ""
    assert (
        "Opus at high effort" in line_73
    ), f"README.md:73 must still say 'Opus at high effort'; got: {line_73!r}"
    assert (
        "Opus at high effort" in line_77
    ), f"README.md:77 must still say 'Opus at high effort'; got: {line_77!r}"


# ---------------------------------------------------------------------------
# Group B - Change 2: run-state-writer subagent
# ---------------------------------------------------------------------------

RUN_STATE_WRITER_PATH = REAL_REPO_ROOT / "agents" / "run-state-writer.md"

RUN_STATE_WRITER_INPUT_SLOTS = (
    "WRITE_PATH",
    "RUN_ID",
    "CWD",
    "ROUTE",
    "LIVE",
    "AVAILABLE",
    "RAN",
    "PREMISES",
    "MID_RUN_STAGE",
    "PENDING_GATE",
    "PENDING_GATE_QUESTION",
    "ARTIFACT_INDEX",
)


def test_b01_red_run_state_writer_file_exists():
    """TC-19: agents/run-state-writer.md exists."""
    assert (
        RUN_STATE_WRITER_PATH.is_file()
    ), f"agents/run-state-writer.md must exist at {RUN_STATE_WRITER_PATH}"


def test_b02_red_run_state_writer_frontmatter():
    """TC-20: frontmatter has name/model/effort/tools/description as specified.

    Per plan-audit-fix-batch.md step 2, `tools:` must grant both Read and Write,
    in that order (TC-WRITER-01) - a prior Read is what permits the Write tool
    to overwrite an existing run-state.json; the write remains a full overwrite
    (agents/run-state-writer.md:59). A regression back to `tools: Write` alone
    must trip this assertion (TC-WRITER-02).
    """
    content = _read("agents/run-state-writer.md")
    assert re.search(
        r"^name:\s*run-state-writer\s*$", content, re.MULTILINE
    ), "run-state-writer.md must declare 'name: run-state-writer'"
    assert re.search(
        r"^model:\s*sonnet\s*$", content, re.MULTILINE
    ), "run-state-writer.md must declare 'model: sonnet'"
    assert re.search(
        r"^effort:\s*medium\s*$", content, re.MULTILINE
    ), "run-state-writer.md must declare 'effort: medium'"
    tools_match = re.search(r"^tools:\s*(.+)$", content, re.MULTILINE)
    assert tools_match is not None, "run-state-writer.md must declare a 'tools:' line"
    tools = [t.strip() for t in tools_match.group(1).split(",")]
    assert tools == [
        "Read",
        "Write",
    ], f"run-state-writer.md tools must be exactly ['Read', 'Write'], in that order; got: {tools!r}"
    desc_match = re.search(r"^description:\s*(.+)$", content, re.MULTILINE)
    assert (
        desc_match is not None
    ), "run-state-writer.md must declare a 'description:' line"
    description = desc_match.group(1).lower()
    assert (
        "off-route" in description or "per-turn" in description
    ), f"description must name it an off-route per-turn serializer; got: {description!r}"


def test_b02b_red_run_state_writer_write_section_read_first_mandate():
    """## Write section instructs reading an existing file at <WRITE_PATH>
    first, then writing the full overwrite (agents/run-state-writer.md:59)."""
    content = _read("agents/run-state-writer.md")
    section = _section(content, "## Write", "## Output")
    assert (
        "Read it first" in section
    ), "## Write section must instruct reading an existing file first"
    assert (
        "full overwrite" in section
    ), "## Write section must instruct writing the full overwrite"


def test_b03_red_run_state_writer_has_no_stage_key():
    """TC-21: frontmatter has no `stage:` key - excludes it from gen-catalog.py /
    check_catalog.py, same shape as setup-agent."""
    content = _read("agents/run-state-writer.md")
    frontmatter = content.split("---")[1]
    assert not re.search(
        r"^stage:\s*$", frontmatter, re.MULTILINE
    ), "agents/run-state-writer.md frontmatter must NOT declare a 'stage:' key"


def test_b04_red_leitwort_faithful_scribe_repeated():
    """TC-22: body contains the leitwort "faithful scribe", restated at the write
    step (appears more than once)."""
    content = _read("agents/run-state-writer.md")
    count = content.count("faithful scribe")
    assert count >= 2, (
        f"agents/run-state-writer.md must contain the leitwort 'faithful scribe' "
        f"more than once (anchor + restated at the write step); found {count} occurrence(s)"
    )


def test_b05_red_mandate_sole_writer_fire_and_forget_1to1():
    """TC-23: body states the mandate - sole writer of run-state.json, runs every
    loop turn fire-and-forget, serializes each slot 1:1 into the same-named key."""
    content = _read("agents/run-state-writer.md")
    assert "run-state.json" in content, "must name run-state.json"
    assert "sole writer" in content, "must state the sole-writer mandate"
    assert (
        "fire-and-forget" in content or "fire and forget" in content
    ), "must state it runs fire-and-forget"
    assert (
        "1:1" in content or "one-to-one" in content or "1-to-1" in content
    ), "must state the 1:1 slot-to-key serialization"


def test_b06_red_cross_references_workflow_loop_step4_not_restated():
    """TC-24: body cross-references WORKFLOW.md loop step 4 for schema/types rather
    than restating the full field list verbatim."""
    content = _read("agents/run-state-writer.md")
    assert (
        "WORKFLOW.md" in content and "step 4" in content
    ), "run-state-writer.md must cross-reference WORKFLOW.md loop step 4"
    # The full field list is owned canonically by WORKFLOW.md; the agent must not
    # restate the complete verbatim schema block.
    full_schema_block = (
        "{schema_version, run_id, cwd, route, live, available, ran, premises, "
        "mid_run_stage, pending_gate, pending_gate_question, artifact_index}"
    )
    assert (
        full_schema_block not in content
    ), "run-state-writer.md must not duplicate WORKFLOW.md's full verbatim schema block"


def test_b07_red_schema_version_always_integer_1():
    """TC-25: body states schema_version is always integer 1."""
    content = _read("agents/run-state-writer.md")
    assert "schema_version" in content, "must mention schema_version"
    assert re.search(r"schema_version.{0,40}\b1\b", content, re.DOTALL) or re.search(
        r"\b1\b.{0,40}schema_version", content, re.DOTALL
    ), "must state schema_version is always integer 1"


def test_b08_red_escaping_and_typed_empty_emission_documented():
    """TC-26: body documents escaping discipline and typed-empty emission."""
    content = _read("agents/run-state-writer.md")
    assert "escape" in content.lower(), "must document escaping discipline"
    for empty in ('""', "[]", "{}"):
        assert empty in content, f"must document the typed-empty emission {empty!r}"


def test_b09_red_input_block_lists_exact_slots():
    """TC-27: ## Input fenced block lists exactly the 12 specified slots."""
    content = _read("agents/run-state-writer.md")
    section = _section(content, "## Input", "## ")
    for slot in RUN_STATE_WRITER_INPUT_SLOTS:
        assert (
            f"<{slot}>" in section
        ), f"## Input block must declare <{slot}>; section={section!r}"


def test_b09b_red_writer_input_slots_match_workflow_step4_schema():
    """Schema-sync canary (assumptions finding): the writer's data slots (its
    ## Input slots minus the WRITE_PATH control slot) equal WORKFLOW.md loop
    step 4's canonical snapshot schema keys minus schema_version (which the
    writer synthesizes as the literal integer 1, not a passed-in slot).

    The field set is materialized in three places - WORKFLOW step 4, the
    writer's slot list, and this suite's RUN_STATE_WRITER_INPUT_SLOTS tuple -
    with no cross-check today. Adding a schema field to WORKFLOW.md without
    also adding the matching slot to run-state-writer.md would silently drop
    it from every persisted snapshot with nothing failing; this test trips on
    that divergence.
    """
    content = _read("agents/run-state-writer.md")
    section = _section(content, "## Input", "## ")
    writer_slots = set(re.findall(r"<([A-Z_]+)>", section))
    writer_data_slots = {s.lower() for s in writer_slots if s != "WRITE_PATH"}

    workflow = _read("WORKFLOW.md")
    # Anchor on the literal brace list itself (not surrounding prose, which may
    # be reworded) - the same pinned schema block test_d04 pins verbatim.
    schema_match = re.search(r"\{([a-z_, ]+)\}", workflow)
    assert (
        schema_match is not None
    ), "WORKFLOW.md must contain the brace-delimited step-4 snapshot schema list"
    workflow_keys = {k.strip() for k in schema_match.group(1).split(",")}
    workflow_data_keys = workflow_keys - {"schema_version"}

    assert writer_data_slots == workflow_data_keys, (
        "run-state-writer.md's ## Input data slots must set-equal WORKFLOW.md "
        "loop step 4's schema keys (minus schema_version, which the writer "
        f"synthesizes); writer={sorted(writer_data_slots)!r} "
        f"workflow={sorted(workflow_data_keys)!r}"
    )

    # Cross-check against this suite's own pinned tuple too, so a drift in the
    # tuple itself (used by test_b09) is caught the same way.
    tuple_data_slots = {
        s.lower() for s in RUN_STATE_WRITER_INPUT_SLOTS if s != "WRITE_PATH"
    }
    assert tuple_data_slots == workflow_data_keys, (
        "RUN_STATE_WRITER_INPUT_SLOTS (minus WRITE_PATH) must set-equal "
        f"WORKFLOW.md's schema keys (minus schema_version); "
        f"tuple={sorted(tuple_data_slots)!r} workflow={sorted(workflow_data_keys)!r}"
    )


def test_b10_red_missing_slot_failure_mode_documented():
    """TC-28 (failure mode): body documents the standard first step - parse
    required slots; on a missing required slot emit INPUT_ERROR: missing <slot>
    and stop."""
    content = _read("agents/run-state-writer.md")
    assert (
        "INPUT_ERROR: missing" in content
    ), "run-state-writer.md must document 'INPUT_ERROR: missing <slot>' on a missing slot"


def test_b11_red_output_block_documents_success_and_error_paths():
    """TC-29 (failure mode): ## Output (strict) block specifies both the success
    (WROTE) and error (STATUS: ok|error - reason) paths."""
    content = _read("agents/run-state-writer.md")
    section = content[_locate(content, "## Output") :]
    assert "WRITE_RESULT" in section, "## Output block must define WRITE_RESULT"
    assert "WROTE" in section, "## Output block must document the success (WROTE) path"
    assert (
        "STATUS:" in section and "ok" in section and "error" in section
    ), "## Output block must document 'STATUS: ok|error - reason'"


def test_b12_green_injector_not_wired_to_run_state_writer():
    """TC-30 (regression guard, true both before and after this change):
    hooks/user-context-injector.sh is not special-cased for run-state-writer -
    it falls through the terminal `*)` case."""
    content = _read("hooks/user-context-injector.sh")
    assert (
        "run-state-writer" not in content
    ), "hooks/user-context-injector.sh must not special-case 'run-state-writer'"


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
#           run-state-writer.md and bumping 20 model: fields. The verifier stage
#           runs this grep/diff directly per the plan's ## Testing section.


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


def test_d01_red_loop_step4_dispatches_run_state_writer():
    """TC-40: loop step 4 states the orchestrator DISPATCHES run-state-writer (not
    a direct Write) as the HARD REQUIRED step-4 action."""
    section = _loop_step4_section()
    assert (
        "run-state-writer" in section
    ), "loop step 4 must name the run-state-writer subagent"
    assert (
        "dispatch" in section.lower()
    ), "loop step 4 must state the orchestrator DISPATCHES run-state-writer"
    assert (
        "HARD REQUIRED step-4 action" in section
    ), "loop step 4 must still name the write dispatch as the HARD REQUIRED step-4 action"


def test_d02_red_loop_step4_fire_and_forget_background_no_handle_no_watchdog():
    """TC-41 / TC-53: dispatch is fire-and-forget in the background
    (Agent(run_in_background: true)), explicitly no handle, no watchdog."""
    section = _loop_step4_section()
    assert (
        "run_in_background: true" in section
    ), "loop step 4 must document Agent(run_in_background: true) for the dispatch"
    assert (
        "fire-and-forget" in section or "fire and forget" in section
    ), "loop step 4 must state the dispatch is fire-and-forget"
    assert (
        "no handle" in section.lower() and "no watchdog" in section.lower()
    ), "loop step 4 must carry the explicit 'no handle, no watchdog' tradeoff sentence"


def test_d03_red_loop_step4_escaping_sentence_names_run_state_writer():
    """TC-42: escaping-burden sentence now reads "the run-state-writer authors
    this JSON" (was "the orchestrator...")."""
    section = _loop_step4_section()
    assert (
        "the run-state-writer authors this JSON" in section
    ), "loop step 4 must read 'the run-state-writer authors this JSON'"
    assert (
        "the orchestrator authors this JSON" not in section
    ), "loop step 4 must no longer read 'the orchestrator authors this JSON'"


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


def test_d05_red_loop_step4_no_orchestrator_own_write_tool_clause():
    """TC-44 (negative): loop step 4 no longer contains the removed clause."""
    section = _loop_step4_section()
    assert (
        "orchestrator performs the Write through its OWN Write tool" not in section
    ), (
        "loop step 4 must no longer contain the removed 'orchestrator performs the "
        "Write through its OWN Write tool' clause"
    )


def test_d06_red_durability_dispatches_subagent_not_own_write_tool():
    """TC-45: ## Durability states the orchestrator dispatches the run-state-writer
    subagent, not "writes it... through its own Write tool"."""
    section = _durability_section()
    assert "dispatches the `run-state-writer` subagent" in section or (
        "dispatches" in section and "run-state-writer" in section
    ), "## Durability must state the orchestrator dispatches the run-state-writer subagent"
    assert (
        "through its own Write tool" not in section
    ), "## Durability must no longer say the orchestrator writes it through its own Write tool"


def test_d07_red_durability_where_to_point_the_writer():
    """TC-46: "so the orchestrator learns where to persist" reworded to
    "...where to point the writer"."""
    section = _durability_section()
    assert (
        "where to point the writer" in section
    ), "## Durability must read '...where to point the writer'"
    assert (
        "the orchestrator learns where to persist" not in section
    ), "## Durability must no longer read 'the orchestrator learns where to persist'"


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


def test_e01_red_recover_run_state_context_string_reworded():
    """TC-54: the injected context string names the run-state-writer dispatch."""
    content = _read("hooks/recover-run-state.sh")
    assert "dispatch the run-state-writer subagent" in content, (
        "hooks/recover-run-state.sh must inject a context string naming the "
        "run-state-writer dispatch"
    )
    assert (
        "loop step 4" in content
    ), "hooks/recover-run-state.sh injected context must still reference loop step 4"


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
    for forbidden in ("run-state-writer", "code-planner", ".md", "agents/"):
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
    for term in ("run-state-writer", "who writes", "writer identity"):
        assert term.lower() not in entry.lower(), (
            f"the 1.3.3 CHANGELOG entry must not mention the writer-identity change "
            f"({term!r} found); entry={entry!r}"
        )


def test_f05_red_readme_latest_updates_gains_1_3_3_entry():
    """TC-63: README.md ## 📰 Latest updates gains a condensed **1.3.3** entry at
    the top, matching the section's existing style."""
    content = _read("README.md")
    section = _section(content, "## 📰 Latest updates", "Full history in")
    assert (
        "**1.3.3**" in section
    ), "README.md ## 📰 Latest updates must gain a '**1.3.3**' entry"
    first_entry_idx = section.index("**1.3.3**")
    other_entry_match = re.search(r"\*\*1\.3\.\d+\*\*", section[first_entry_idx + 1 :])
    if other_entry_match:
        assert (
            other_entry_match.start() > 0
        ), "the '**1.3.3**' entry must be the first (topmost) entry in Latest updates"


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
