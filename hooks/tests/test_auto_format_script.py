"""Content and behaviour checks on hooks/auto-format.sh (Group F, TC-FMT-01..05).

The change-marker rollout moves auto-format.sh to run async (see
test_hooks_config.py) and hardens its npx invocations against network
downloads via --no-install. These are string-presence checks against the
script's source plus one end-to-end run against a project where neither
prettier nor biome resolves locally.

RED until hooks/auto-format.sh is updated to:
  - invoke prettier and biome format via `npx --no-install ...`
  - document, in its header comment, that its PostToolUse registration is
    async/fire-and-forget with log-only failure surfacing
  - note in the emit_failures comment that its output is not injected when
    registered async
  - still exit 0 overall and append a FAIL line to the debug log when no
    formatter resolves locally
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

AUTO_FORMAT_SH = Path(__file__).resolve().parents[1] / "auto-format.sh"


def _read():
    return AUTO_FORMAT_SH.read_text()


# ---------------------------------------------------------------------------
# TC-FMT-01/02: --no-install on the prettier and biome format invocations
# ---------------------------------------------------------------------------


def test_prettier_invocation_uses_no_install():
    text = _read()
    assert "npx --no-install prettier" in text, (
        "expected the prettier invocation line to include 'npx --no-install prettier'; "
        "a bare 'npx prettier' can silently download an npm package on a miss"
    )


def test_biome_format_invocation_uses_no_install():
    text = _read()
    assert "npx --no-install @biomejs/biome format" in text, (
        "expected the biome format invocation line to include "
        "'npx --no-install @biomejs/biome format'"
    )


# ---------------------------------------------------------------------------
# TC-FMT-03/04: header + emit_failures comments document async registration
# ---------------------------------------------------------------------------


def test_header_documents_async_fire_and_forget_and_log_only_surfacing():
    text = _read()
    header = text.split("set -euo pipefail", 1)[0]
    lower = header.lower()
    assert "async" in lower, (
        "header comment must state the hook's PostToolUse registration is async "
        "/ fire-and-forget"
    )
    assert "log" in lower, (
        "header comment must state failures surface via the log (log-only), not "
        "back to the agent, under async registration"
    )
    # Step-6 header truth-up: under async registration the EXIT trap's
    # hookSpecificOutput.additionalContext is never injected back to the agent,
    # so the current header's claim that failures are "surfaced back to the
    # agent via hookSpecificOutput.additionalContext" is false and must be
    # removed. The corrected header states failure surfacing is log-only.
    assert "additionalcontext" not in lower, (
        "header comment must no longer claim failures are surfaced back to the "
        "agent via hookSpecificOutput.additionalContext; under async registration "
        "that output is not injected, so surfacing is log-only"
    )


def test_emit_failures_comment_notes_output_not_injected_under_async():
    text = _read()
    assert "emit_failures" in text, "expected an emit_failures function"
    # Grab the region around the emit_failures definition to scope the comment check.
    idx = text.index("emit_failures")
    region = text[max(0, idx - 400) : idx + 400]
    assert "async" in region.lower(), (
        "the emit_failures comment must note that under async registration its "
        f"JSON output is not injected back to the agent; region={region!r}"
    )


# ---------------------------------------------------------------------------
# TC-FMT-05: no local formatter resolvable -> exit 0, FAIL line appended to log
# ---------------------------------------------------------------------------


def test_no_local_formatter_exits_zero_and_logs_fail():
    project = tempfile.mkdtemp()
    fake_home = tempfile.mkdtemp()
    try:
        subprocess.run(["git", "init", "-q", project], check=True, capture_output=True)
        target = Path(project) / "app.js"
        target.write_text("const x=1\n")
        # A package.json with a "prettier" key signals prettier is configured,
        # but PATH restriction below means npx --no-install cannot resolve it -
        # this drives the FAIL branch without needing a real prettier install.
        (Path(project) / "package.json").write_text(
            '{"name": "x", "version": "0.0.1", "prettier": {}}'
        )
        payload = f'{{"tool_input": {{"file_path": "{target}"}}}}'

        fake_bin = tempfile.mkdtemp()
        for tool in (
            "bash",
            "sh",
            "cat",
            "dirname",
            "realpath",
            "mkdir",
            "stat",
            "tail",
            "date",
            "npx",
            "node",
            "jq",
            "git",
            "grep",
        ):
            real = shutil.which(tool)
            if real:
                (Path(fake_bin) / tool).symlink_to(real)
        env = {**os.environ, "HOME": fake_home, "PATH": fake_bin}

        result = subprocess.run(
            ["bash", str(AUTO_FORMAT_SH)],
            input=payload,
            capture_output=True,
            text=True,
            env=env,
            cwd=project,
        )
        assert result.returncode == 0, (
            f"auto-format.sh must exit 0 even when no formatter resolves locally; "
            f"got {result.returncode}; stderr={result.stderr!r}"
        )
        log_file = Path(fake_home) / ".claude" / "debug" / "auto-format.log"
        assert log_file.exists(), f"expected a debug log at {log_file}"
        assert "FAIL" in log_file.read_text(), (
            "expected a FAIL line appended to the debug log when prettier is "
            "configured but not locally resolvable"
        )
    finally:
        shutil.rmtree(project, ignore_errors=True)
        shutil.rmtree(fake_home, ignore_errors=True)
