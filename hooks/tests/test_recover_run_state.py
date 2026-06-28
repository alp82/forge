"""Tests for hooks/recover-run-state.sh - a SessionStart hook (startup/resume/compact).

CONTRACT:
  - Reads {"source": "startup"|"resume"|"compact", "session_id": "...", "cwd": "...",
    "transcript_path": "..."} on STDIN.
  - ALWAYS exits 0.
  - stdout is EITHER empty OR one valid JSON object carrying
    hookSpecificOutput.additionalContext.
  - Never crashes, never exits non-zero, never prints anything but that legal JSON.
  - On startup/resume: ALWAYS injects the write-path
    <cwd>/.alp-river/runs/<session_id>/run-state.json into additionalContext.
  - On startup/resume with a valid, non-converged candidate: ALSO injects a recovery
    offer naming the candidate's mid_run_stage and route.
  - On compact: emits the workflow anchor (file-first from run-state.json when present,
    falls back to transcript scrape when absent).

Guard behaviour:
  G1 = jq-parseable JSON AND schema_version==1
  G2 = cwd field matches the payload cwd
  G4 = now - mtime(run-state.json) <= RIVER_STATE_MAX_AGE_SECONDS (default 86400)
  CONVERGED-SKIP = route empty AND pending_gate empty/absent -> never offered
  PRUNE = dirs older than max-age are deleted during the scan pass

G3 per-path binding:
  resume -> looks ONLY at runs/<session_id>/run-state.json (own dir)
  startup -> SCANS runs/*/run-state.json, picks freshest that passes guards;
             session-equality is NOT required (new session_id must recover old state)

All tests are RED until the implementer creates hooks/recover-run-state.sh.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "recover-run-state.sh"

# Default canonical mid_run_stage used by write_state and assertion helpers.
_DEFAULT_MID_RUN_STAGE = "code-planner"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def write_state(runs_dir, sid, cwd_str, **overrides):
    """Create runs_dir/sid/run-state.json with canonical valid fields updated by overrides.

    Canonical defaults:
      schema_version=1, run_id=sid, cwd=cwd_str, route="code", live=["code"],
      available=[], ran=[], premises="p", mid_run_stage="code-planner",
      pending_gate="", pending_gate_question="", artifact_index={}

    Age is set via os.utime by the caller (mtime is the freshness signal; no written_at).

    Returns the Path to the written run-state.json file.
    """
    sid_dir = Path(runs_dir) / sid
    sid_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "schema_version": 1,
        "run_id": sid,
        "cwd": cwd_str,
        "route": "code",
        "live": ["code"],
        "available": [],
        "ran": [],
        "premises": "p",
        "mid_run_stage": _DEFAULT_MID_RUN_STAGE,
        "pending_gate": "",
        "pending_gate_question": "",
        "artifact_index": {},
    }
    state.update(overrides)
    state_file = sid_dir / "run-state.json"
    state_file.write_text(json.dumps(state), encoding="utf-8")
    return state_file


def run_recover(source, sid, cwd, transcript_path="", env=None):
    """Invoke recover-run-state.sh via bash with the given payload on STDIN.

    Returns the subprocess.CompletedProcess result.
    """
    payload = json.dumps(
        {
            "source": source,
            "session_id": sid,
            "cwd": cwd,
            "transcript_path": transcript_path,
        }
    )
    return subprocess.run(
        ["bash", str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
    )


def offered(r, mid_run_stage=_DEFAULT_MID_RUN_STAGE):
    """Assert the recovery offer IS present: mid_run_stage in stdout AND returncode==0."""
    assert (
        r.returncode == 0
    ), f"expected returncode 0, got {r.returncode}; stderr={r.stderr!r}"
    assert mid_run_stage in r.stdout, (
        f"expected recovery offer with '{mid_run_stage}' in stdout; "
        f"got stdout={r.stdout!r}"
    )


def not_offered(r, mid_run_stage=_DEFAULT_MID_RUN_STAGE):
    """Assert no recovery offer: mid_run_stage NOT in stdout AND returncode==0."""
    assert (
        r.returncode == 0
    ), f"expected returncode 0, got {r.returncode}; stderr={r.stderr!r}"
    assert mid_run_stage not in r.stdout, (
        f"expected NO recovery offer in stdout; '{mid_run_stage}' must be absent; "
        f"got stdout={r.stdout!r}"
    )


# ---------------------------------------------------------------------------
# Guard matrix (resume, direct dir present)
# ---------------------------------------------------------------------------


def test_rr_s1_fresh_state_offered():
    """RR-S1: resume with a fresh (mtime now) run-state.json -> recovery offer present."""
    tmp = Path(tempfile.mkdtemp())
    try:
        cwd_str = str(tmp)
        runs_dir = tmp / ".alp-river" / "runs"
        sid = "session-s1"
        state_file = write_state(runs_dir, sid, cwd_str)
        t = time.time()
        os.utime(state_file, (t, t))
        r = run_recover("resume", sid, cwd_str)
        offered(r)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rr_s2_30s_old_offered():
    """RR-S2: resume with run-state.json 30s old -> offered (well within default max age)."""
    tmp = Path(tempfile.mkdtemp())
    try:
        cwd_str = str(tmp)
        runs_dir = tmp / ".alp-river" / "runs"
        sid = "session-s2"
        state_file = write_state(runs_dir, sid, cwd_str)
        t = time.time() - 30
        os.utime(state_file, (t, t))
        r = run_recover("resume", sid, cwd_str)
        offered(r)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rr_s3_25h_old_not_offered():
    """RR-S3: resume with run-state.json 25h old (mtime now-90000) -> not offered (G4 stale)."""
    tmp = Path(tempfile.mkdtemp())
    try:
        cwd_str = str(tmp)
        runs_dir = tmp / ".alp-river" / "runs"
        sid = "session-s3"
        state_file = write_state(runs_dir, sid, cwd_str)
        t = time.time() - 90000  # 25 hours; default max age is 86400s
        os.utime(state_file, (t, t))
        r = run_recover("resume", sid, cwd_str)
        not_offered(r)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rr_s4_wrong_cwd_not_offered():
    """RR-S4: run-state.json cwd="/different/path" -> not offered (G2 cwd mismatch)."""
    tmp = Path(tempfile.mkdtemp())
    try:
        cwd_str = str(tmp)
        runs_dir = tmp / ".alp-river" / "runs"
        sid = "session-s4"
        state_file = write_state(runs_dir, sid, cwd_str, cwd="/different/path")
        t = time.time()
        os.utime(state_file, (t, t))
        r = run_recover("resume", sid, cwd_str)
        not_offered(r)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rr_s5_wrong_schema_version_not_offered():
    """RR-S5: run-state.json schema_version=99 -> not offered (G1 schema_version must be 1)."""
    tmp = Path(tempfile.mkdtemp())
    try:
        cwd_str = str(tmp)
        runs_dir = tmp / ".alp-river" / "runs"
        sid = "session-s5"
        state_file = write_state(runs_dir, sid, cwd_str, schema_version=99)
        t = time.time()
        os.utime(state_file, (t, t))
        r = run_recover("resume", sid, cwd_str)
        not_offered(r)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rr_s7_missing_route_field_not_offered():
    """RR-S7: run-state.json with required field 'route' deleted -> not offered."""
    tmp = Path(tempfile.mkdtemp())
    try:
        cwd_str = str(tmp)
        runs_dir = tmp / ".alp-river" / "runs"
        sid = "session-s7"
        sid_dir = runs_dir / sid
        sid_dir.mkdir(parents=True, exist_ok=True)
        # Canonical state with 'route' deliberately omitted.
        state = {
            "schema_version": 1,
            "run_id": sid,
            "cwd": cwd_str,
            # "route" absent
            "live": ["code"],
            "available": [],
            "ran": [],
            "premises": "p",
            "mid_run_stage": _DEFAULT_MID_RUN_STAGE,
            "pending_gate": "",
            "pending_gate_question": "",
            "artifact_index": {},
        }
        state_file = sid_dir / "run-state.json"
        state_file.write_text(json.dumps(state), encoding="utf-8")
        t = time.time()
        os.utime(state_file, (t, t))
        r = run_recover("resume", sid, cwd_str)
        not_offered(r)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rr_malformed_json_not_offered_and_exits_0():
    """RR-MALFORMED: run-state.json = invalid JSON -> not offered AND returncode==0.

    Validate-on-read must never crash the hook; the hook exits 0 regardless.
    """
    tmp = Path(tempfile.mkdtemp())
    try:
        cwd_str = str(tmp)
        runs_dir = tmp / ".alp-river" / "runs"
        sid = "session-malformed"
        sid_dir = runs_dir / sid
        sid_dir.mkdir(parents=True, exist_ok=True)
        state_file = sid_dir / "run-state.json"
        state_file.write_text("{not valid json", encoding="utf-8")
        t = time.time()
        os.utime(state_file, (t, t))
        r = run_recover("resume", sid, cwd_str)
        assert r.returncode == 0, (
            f"RR-MALFORMED: hook must exit 0 on malformed JSON; "
            f"got returncode={r.returncode}; stderr={r.stderr!r}"
        )
        assert _DEFAULT_MID_RUN_STAGE not in r.stdout, (
            f"RR-MALFORMED: no recovery offer expected for malformed JSON; "
            f"got stdout={r.stdout!r}"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# G3 per-path binding (the headline cases)
# ---------------------------------------------------------------------------


def test_rr_resume_direct_offered():
    """RR-RESUME-DIRECT: write_state(sid_a); resume(sid_a) -> offered.

    Resume locates its own dir directly and surfaces the candidate.
    """
    tmp = Path(tempfile.mkdtemp())
    try:
        cwd_str = str(tmp)
        runs_dir = tmp / ".alp-river" / "runs"
        sid_a = "session-resume-direct-a"
        state_file = write_state(runs_dir, sid_a, cwd_str)
        t = time.time()
        os.utime(state_file, (t, t))
        r = run_recover("resume", sid_a, cwd_str)
        offered(r)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rr_resume_miss_not_offered():
    """RR-RESUME-MISS: only runs/sid_b/ exists; resume(sid_a) -> not offered.

    Resume must look ONLY at its own session dir. Another session's dir must not
    be used as a recovery candidate on resume.
    """
    tmp = Path(tempfile.mkdtemp())
    try:
        cwd_str = str(tmp)
        runs_dir = tmp / ".alp-river" / "runs"
        sid_a = "session-resume-miss-a"
        sid_b = "session-resume-miss-b"
        state_file = write_state(runs_dir, sid_b, cwd_str)
        t = time.time()
        os.utime(state_file, (t, t))
        # sid_a has no dir; only sid_b exists.
        r = run_recover("resume", sid_a, cwd_str)
        not_offered(r)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rr_startup_scan_offered():
    """RR-STARTUP-SCAN: only runs/sid_b/ exists (valid, same cwd, fresh);
    startup(sid_NEW) where sid_NEW matches no dir -> offered.

    This is the G3 load-bearing hard-kill case. Startup MUST scan all runs/ dirs;
    session-equality is NOT required. A brand-new session_id must still recover a
    prior session's run-state.json via freshest-scan. If the hook required
    session-equality on startup, recovery (the headline feature) would silently
    never fire for any fresh Claude session.
    """
    tmp = Path(tempfile.mkdtemp())
    try:
        cwd_str = str(tmp)
        runs_dir = tmp / ".alp-river" / "runs"
        sid_existing = "session-scan-existing"
        sid_new = "session-scan-brand-new"
        state_file = write_state(runs_dir, sid_existing, cwd_str)
        t = time.time()
        os.utime(state_file, (t, t))
        # sid_new has no dir; startup must scan and find sid_existing.
        r = run_recover("startup", sid_new, cwd_str)
        offered(r)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Converged-skip + prune + write-path
# ---------------------------------------------------------------------------


def test_rr_converged_not_offered():
    """RR-CONVERGED: state with route="" AND pending_gate="" -> not offered even though
    fresh and otherwise valid (a converged state is never a recovery candidate)."""
    tmp = Path(tempfile.mkdtemp())
    try:
        cwd_str = str(tmp)
        runs_dir = tmp / ".alp-river" / "runs"
        sid = "session-converged"
        state_file = write_state(runs_dir, sid, cwd_str, route="", pending_gate="")
        t = time.time()
        os.utime(state_file, (t, t))
        r = run_recover("resume", sid, cwd_str)
        not_offered(r)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rr_prune_stale_dir_removed():
    """RR-PRUNE: a run dir with mtime now-90000 (25h, beyond default 86400s max-age) ->
    after a run_recover startup pass that dir no longer exists (pruned during read pass).
    """
    tmp = Path(tempfile.mkdtemp())
    try:
        cwd_str = str(tmp)
        runs_dir = tmp / ".alp-river" / "runs"
        sid_old = "session-prune-old"
        sid_current = "session-prune-current"
        state_file = write_state(runs_dir, sid_old, cwd_str)
        t = time.time() - 90000  # 25h old -> beyond 86400s default
        os.utime(state_file, (t, t))
        # Trigger scan+prune as a fresh startup with a different session id.
        r = run_recover("startup", sid_current, cwd_str)
        assert (
            r.returncode == 0
        ), f"RR-PRUNE: hook must exit 0; got {r.returncode}; stderr={r.stderr!r}"
        old_dir = runs_dir / sid_old
        assert not old_dir.exists(), (
            f"RR-PRUNE: stale runs/{sid_old}/ must be deleted after the scan pass; "
            f"dir still exists at {old_dir}"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rr_writepath_always_emitted():
    """RR-WRITEPATH-ALWAYS: startup with NO runs/ dir at all -> stdout still contains
    the write path '.alp-river/runs/<session_id>/run-state.json' AND no recovery offer.

    The orchestrator must always learn where to persist; stdout is never empty on
    startup/resume even when no candidate exists.
    """
    tmp = Path(tempfile.mkdtemp())
    try:
        cwd_str = str(tmp)
        sid = "session-writepath"
        # No .alp-river/runs/ dir created at all.
        r = run_recover("startup", sid, cwd_str)
        assert (
            r.returncode == 0
        ), f"RR-WRITEPATH-ALWAYS: hook must exit 0; got {r.returncode}; stderr={r.stderr!r}"
        expected_fragment = f".alp-river/runs/{sid}/run-state.json"
        assert expected_fragment in r.stdout, (
            f"RR-WRITEPATH-ALWAYS: stdout must contain write-path fragment "
            f"'{expected_fragment}'; got stdout={r.stdout!r}"
        )
        assert _DEFAULT_MID_RUN_STAGE not in r.stdout, (
            f"RR-WRITEPATH-ALWAYS: no recovery offer expected when no runs/ dir exists; "
            f"got stdout={r.stdout!r}"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Read-back + isolation + env + compact
# ---------------------------------------------------------------------------


def test_rr_readback_route_and_stage_in_stdout():
    """RR-READBACK: valid candidate with route="talk", mid_run_stage="discuss" ->
    offered AND stdout contains both "talk" and "discuss"."""
    tmp = Path(tempfile.mkdtemp())
    try:
        cwd_str = str(tmp)
        runs_dir = tmp / ".alp-river" / "runs"
        sid = "session-readback"
        state_file = write_state(
            runs_dir, sid, cwd_str, route="talk", mid_run_stage="discuss"
        )
        t = time.time()
        os.utime(state_file, (t, t))
        r = run_recover("resume", sid, cwd_str)
        offered(r, mid_run_stage="discuss")
        assert (
            "talk" in r.stdout
        ), f"RR-READBACK: stdout must contain route 'talk'; got stdout={r.stdout!r}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rr_isolation_resume_surfaces_own_session_only():
    """RR-ISOLATION: two pre-seeded runs; resume on each session surfaces only its own stage.

    Specifically:
      resume(sid_a) -> 'code-planner' present, 'code-implementer' absent.
      resume(sid_b) -> 'code-implementer' present, 'code-planner' absent.
    """
    tmp = Path(tempfile.mkdtemp())
    try:
        cwd_str = str(tmp)
        runs_dir = tmp / ".alp-river" / "runs"
        sid_a = "session-iso-a"
        sid_b = "session-iso-b"
        t = time.time()
        state_a = write_state(runs_dir, sid_a, cwd_str, mid_run_stage="code-planner")
        os.utime(state_a, (t, t))
        state_b = write_state(
            runs_dir, sid_b, cwd_str, mid_run_stage="code-implementer"
        )
        os.utime(state_b, (t, t))

        r_a = run_recover("resume", sid_a, cwd_str)
        offered(r_a, mid_run_stage="code-planner")
        assert "code-implementer" not in r_a.stdout, (
            f"RR-ISOLATION: resume(sid_a) must NOT surface sid_b's stage 'code-implementer'; "
            f"got stdout={r_a.stdout!r}"
        )

        r_b = run_recover("resume", sid_b, cwd_str)
        offered(r_b, mid_run_stage="code-implementer")
        assert "code-planner" not in r_b.stdout, (
            f"RR-ISOLATION: resume(sid_b) must NOT surface sid_a's stage 'code-planner'; "
            f"got stdout={r_b.stdout!r}"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rr_env_override_max_age():
    """RR-ENV-OVERRIDE: a 300s-old state with RIVER_STATE_MAX_AGE_SECONDS=60 ->
    not offered (300 > 60 so the state is stale under the custom max age)."""
    tmp = Path(tempfile.mkdtemp())
    try:
        cwd_str = str(tmp)
        runs_dir = tmp / ".alp-river" / "runs"
        sid = "session-env-override"
        state_file = write_state(runs_dir, sid, cwd_str)
        t = time.time() - 300  # 300s old
        os.utime(state_file, (t, t))
        env = os.environ.copy()
        env["RIVER_STATE_MAX_AGE_SECONDS"] = "60"
        r = run_recover("resume", sid, cwd_str, env=env)
        not_offered(r)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rr_compact_file_present_reanchors_from_file():
    """RR-COMPACT-FILE: source="compact", runs/<sid>/run-state.json present with sentinel
    values route="talk" and mid_run_stage="discuss" -> stdout contains BOTH sentinels.

    "talk" and "discuss" are confirmed absent from the workflow-anchor text, so their
    presence in stdout proves the hook opened and re-anchored from the file rather than
    merely emitting the anchor alone. The workflow anchor always contains "code" (in
    /alp-river:go), so asserting "code" is a false-green - sentinel values are required.
    """
    tmp = Path(tempfile.mkdtemp())
    try:
        cwd_str = str(tmp)
        runs_dir = tmp / ".alp-river" / "runs"
        sid = "session-compact-file"
        state_file = write_state(
            runs_dir, sid, cwd_str, route="talk", mid_run_stage="discuss"
        )
        t = time.time()
        os.utime(state_file, (t, t))
        r = run_recover("compact", sid, cwd_str)
        assert (
            r.returncode == 0
        ), f"RR-COMPACT-FILE: hook must exit 0; got {r.returncode}; stderr={r.stderr!r}"
        assert "talk" in r.stdout, (
            f"RR-COMPACT-FILE: stdout must contain sentinel route 'talk' re-anchored from the file; "
            f"got stdout={r.stdout!r}"
        )
        assert "discuss" in r.stdout, (
            f"RR-COMPACT-FILE: stdout must contain sentinel mid_run_stage 'discuss' re-anchored from the file; "
            f"got stdout={r.stdout!r}"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rr_compact_no_file_no_transcript_emits_anchor():
    """RR-COMPACT-DEGRADED: source="compact", NO run-state.json AND transcript_path="" ->
    returncode==0 AND stdout is non-empty (the workflow anchor always emits on compact).

    Worst-case degraded path: no file, no transcript. The hook must not exit non-zero or
    produce empty stdout even in this fully-degraded state.
    """
    tmp = Path(tempfile.mkdtemp())
    try:
        cwd_str = str(tmp)
        sid = "session-compact-no-file-no-transcript"
        # No .alp-river/runs/ dir, transcript_path explicitly empty.
        r = run_recover("compact", sid, cwd_str, transcript_path="")
        assert (
            r.returncode == 0
        ), f"RR-COMPACT-DEGRADED: hook must exit 0; got {r.returncode}; stderr={r.stderr!r}"
        assert r.stdout.strip(), (
            f"RR-COMPACT-DEGRADED: stdout must be non-empty (workflow anchor emitted even "
            f"when no run-state.json or transcript exists); got stdout={r.stdout!r}"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Array-route fix pins + coverage gaps
# ---------------------------------------------------------------------------


def test_rr_converged_empty_array_route_not_offered():
    """RR-ARRAY-CONVERGED: route=[] (empty JSON array) AND pending_gate="" -> not offered.

    PINS the array-aware fix in candidate_ok: an empty-array route is converged.
    Before the fix, the string representation of [] was truthy and the state was
    wrongly surfaced as a live recovery candidate. The state dict is written
    directly (json.dump) to guarantee route serializes as a real JSON array, not
    a string.
    """
    tmp = Path(tempfile.mkdtemp())
    try:
        cwd_str = str(tmp)
        runs_dir = tmp / ".alp-river" / "runs"
        sid = "session-array-converged"
        sid_dir = runs_dir / sid
        sid_dir.mkdir(parents=True, exist_ok=True)
        state = {
            "schema_version": 1,
            "run_id": sid,
            "cwd": cwd_str,
            "route": [],
            "live": [],
            "available": [],
            "ran": [],
            "premises": "p",
            "mid_run_stage": _DEFAULT_MID_RUN_STAGE,
            "pending_gate": "",
            "pending_gate_question": "",
            "artifact_index": {},
        }
        state_file = sid_dir / "run-state.json"
        state_file.write_text(json.dumps(state), encoding="utf-8")
        t = time.time()
        os.utime(state_file, (t, t))
        r = run_recover("resume", sid, cwd_str)
        not_offered(r)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rr_populated_array_route_rendered_joined():
    """RR-ARRAY-JOINED: route=["triage", "clarify"] (JSON array), mid_run_stage="discuss",
    fresh -> resume -> offered AND stdout contains the joined form "triage, clarify".

    PINS the render fix in build_offer: the array is flattened via join(", ") for display,
    not dumped as a raw JSON blob like '["triage"'. The state dict is written directly to
    guarantee route serializes as a real JSON array.
    """
    tmp = Path(tempfile.mkdtemp())
    try:
        cwd_str = str(tmp)
        runs_dir = tmp / ".alp-river" / "runs"
        sid = "session-array-joined"
        sid_dir = runs_dir / sid
        sid_dir.mkdir(parents=True, exist_ok=True)
        state = {
            "schema_version": 1,
            "run_id": sid,
            "cwd": cwd_str,
            "route": ["triage", "clarify"],
            "live": ["triage"],
            "available": [],
            "ran": [],
            "premises": "p",
            "mid_run_stage": "discuss",
            "pending_gate": "",
            "pending_gate_question": "",
            "artifact_index": {},
        }
        state_file = sid_dir / "run-state.json"
        state_file.write_text(json.dumps(state), encoding="utf-8")
        t = time.time()
        os.utime(state_file, (t, t))
        r = run_recover("resume", sid, cwd_str)
        offered(r, mid_run_stage="discuss")
        assert "triage, clarify" in r.stdout, (
            f"RR-ARRAY-JOINED: stdout must contain the joined route 'triage, clarify', "
            f"not a raw JSON blob; got stdout={r.stdout!r}"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rr_plan_approval_offer_includes_plan_handle():
    """RR-PLAN-GATE: pending_gate="plan-approval" with an artifact_index entry for
    "@approved-plan" -> resume -> offered AND stdout contains the plan file path.

    Pins the plan-gate re-emit branch in build_offer (the block that appends the
    plan handle path when pending_gate=="plan-approval"). This branch had zero
    coverage before.
    """
    tmp = Path(tempfile.mkdtemp())
    try:
        cwd_str = str(tmp)
        runs_dir = tmp / ".alp-river" / "runs"
        sid = "session-plan-gate"
        plan_path = "/tmp/some/plan-durability.md"
        state_file = write_state(
            runs_dir,
            sid,
            cwd_str,
            route="code",
            mid_run_stage="code-planner",
            pending_gate="plan-approval",
            artifact_index={"@approved-plan": plan_path},
        )
        t = time.time()
        os.utime(state_file, (t, t))
        r = run_recover("resume", sid, cwd_str)
        offered(r, mid_run_stage="code-planner")
        assert plan_path in r.stdout, (
            f"RR-PLAN-GATE: stdout must contain the plan path '{plan_path}' "
            f"emitted by the plan-approval gate branch; got stdout={r.stdout!r}"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rr_compact_file_wrong_schema_falls_back_to_anchor():
    """RR-COMPACT-SCHEMA-ANCHOR: source="compact", runs/<sid>/run-state.json present but
    schema_version=99 -> reanchor_from_file rejects it -> returncode==0, stdout is
    non-empty (workflow anchor emitted), and the transcript sentinel is absent (no scrape).

    Pins the reject-and-degrade path in reanchor_from_file: an invalid file is rejected
    and the hook degrades to anchor-only plus the preserve-manually note. The transcript
    sentinel "talk-from-transcript" is absent from workflow-anchor text and must NOT appear
    in stdout, proving no transcript scrape took place.
    """
    tmp = Path(tempfile.mkdtemp())
    try:
        cwd_str = str(tmp)
        runs_dir = tmp / ".alp-river" / "runs"
        sid = "session-compact-schema-anchor"

        # Write a run-state.json that will fail G1 (schema_version != 1).
        sid_dir = runs_dir / sid
        sid_dir.mkdir(parents=True, exist_ok=True)
        bad_state = {
            "schema_version": 99,
            "run_id": sid,
            "cwd": cwd_str,
            "route": "code",
            "mid_run_stage": "code-planner",
            "pending_gate": "",
        }
        state_file = sid_dir / "run-state.json"
        state_file.write_text(json.dumps(bad_state), encoding="utf-8")
        t = time.time()
        os.utime(state_file, (t, t))

        r = run_recover("compact", sid, cwd_str)
        assert r.returncode == 0, (
            f"RR-COMPACT-SCHEMA-ANCHOR: hook must exit 0; "
            f"got {r.returncode}; stderr={r.stderr!r}"
        )
        assert r.stdout.strip(), (
            f"RR-COMPACT-SCHEMA-ANCHOR: stdout must be non-empty (workflow anchor emitted "
            f"even when run-state.json has wrong schema); got stdout={r.stdout!r}"
        )
        assert "talk-from-transcript" not in r.stdout, (
            f"RR-COMPACT-SCHEMA-ANCHOR: transcript sentinel must be absent (no scrape "
            f"occurs when file is rejected); got stdout={r.stdout!r}"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rr_startup_scan_picks_freshest_of_multiple():
    """RR-STARTUP-FRESHEST: two valid same-cwd candidates seeded under different run dirs -
    an older one (mtime now-3600, mid_run_stage="old-stage") and a newer one
    (mtime now, mid_run_stage="new-stage") -> startup with a brand-new session_id ->
    offered AND stdout contains "new-stage" AND "old-stage" is absent.

    Pins the freshest-by-mtime selection in the startup scan: when multiple valid
    candidates exist the hook must prefer the one with the highest mtime.
    """
    tmp = Path(tempfile.mkdtemp())
    try:
        cwd_str = str(tmp)
        runs_dir = tmp / ".alp-river" / "runs"

        sid_old = "session-multi-old"
        sid_new_prior = "session-multi-new"
        sid_brand_new = "session-multi-brand-new"

        state_old = write_state(runs_dir, sid_old, cwd_str, mid_run_stage="old-stage")
        t_old = time.time() - 3600
        os.utime(state_old, (t_old, t_old))

        state_new = write_state(
            runs_dir, sid_new_prior, cwd_str, mid_run_stage="new-stage"
        )
        t_new = time.time()
        os.utime(state_new, (t_new, t_new))

        r = run_recover("startup", sid_brand_new, cwd_str)
        offered(r, mid_run_stage="new-stage")
        assert "old-stage" not in r.stdout, (
            f"RR-STARTUP-FRESHEST: 'old-stage' must be absent from stdout when the newer "
            f"candidate wins freshest-by-mtime selection; got stdout={r.stdout!r}"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
