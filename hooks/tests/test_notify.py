"""Tests for hooks/notify.sh's macOS notification branch (osascript escaping).

plan-guard-hook-bug-fixes.md steps 9/10: the macOS branch's `-e` argument to
osascript interpolates the raw message/title into an AppleScript string
literal, which breaks (or, worse, lets AppleScript syntax leak) when the text
contains a double quote or a backslash. The fix escapes backslashes first,
then double quotes, then flattens embedded newlines (a raw newline would
split the single-line `-e` source) before interpolation.

These tests run notify.sh as a subprocess via a restricted-PATH stub bin dir
containing a fake osascript (captures its argv to a file) plus symlinks to
the real jq and cat, with notify-send absent so the script's Linux branch is
skipped and the macOS branch runs even on this Linux host - the technique
mirrors test_auto_format_script.py:99-140.

Against the current (unescaped) script, case (a) is expected to FAIL: the raw
quote and backslash reach osascript unescaped.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

NOTIFY_SH = Path(__file__).resolve().parent.parent / "notify.sh"

# Resolved once, absolute: the restricted-PATH stub bin dir used to force the
# macOS branch does not contain a bash symlink, so a bare "bash" argv[0]
# would fail to resolve via the child's PATH.
BASH_PATH = shutil.which("bash") or "/bin/bash"


def run_notify(payload, tmp_path, raw_input=None):
    """Run notify.sh with a restricted PATH forcing the macOS (osascript) branch.

    payload is a dict serialized to JSON and piped on stdin, unless raw_input
    is given - then raw_input is piped verbatim instead (e.g. non-JSON stdin)
    and payload is ignored. Returns the captured osascript argv as a list of
    lines (each argv item on its own line), read from the OSA_CAPTURE file
    the fake osascript writes to.
    """
    stub_bin = Path(tmp_path) / "bin"
    stub_bin.mkdir(parents=True)
    capture_file = Path(tmp_path) / "osa_capture.txt"

    # Fake osascript: shebang uses an absolute /bin/sh path since PATH is
    # restricted, and appends each argv item as its own line to OSA_CAPTURE
    # so the captured -e script's exact text (including embedded escapes) is
    # observable without re-parsing shell quoting.
    fake_osascript = stub_bin / "osascript"
    fake_osascript.write_text(
        "#!/bin/sh\n"
        'for arg in "$@"; do\n'
        '  printf %s\\\\n "$arg" >> "$OSA_CAPTURE"\n'
        "done\n"
    )
    fake_osascript.chmod(0o755)

    for tool in ("jq", "cat"):
        real = shutil.which(tool)
        assert real, f"{tool} must be resolvable on this host to build the stub PATH"
        (stub_bin / tool).symlink_to(real)

    env = {
        **os.environ,
        "PATH": str(stub_bin),
        "OSA_CAPTURE": str(capture_file),
    }
    # Explicitly remove notify-send from PATH resolution by using only the
    # restricted stub_bin - notify-send is absent there, forcing the macOS
    # branch even on this Linux host.
    stdin_text = raw_input if raw_input is not None else json.dumps(payload)
    result = subprocess.run(
        [BASH_PATH, str(NOTIFY_SH)],
        input=stdin_text,
        capture_output=True,
        text=True,
        env=env,
    )
    assert (
        result.returncode == 0
    ), f"notify.sh must exit 0; got {result.returncode}; stderr={result.stderr!r}"
    assert capture_file.exists(), (
        f"expected the fake osascript to have been invoked and to have written "
        f"{capture_file}; stderr={result.stderr!r}"
    )
    return capture_file.read_text().splitlines()


def test_notify_escapes_quote_and_backslash_in_message(tmp_path):
    """A message containing a double quote and a backslash reaches osascript
    with the quote escaped as \\" and the backslash escaped as \\\\, correctly
    embedded in the 'display notification' AppleScript sentence."""
    payload = {"message": 'he said "hi" and C:\\path'}
    argv = run_notify(payload, tmp_path)
    script = "\n".join(argv)
    assert '\\"hi\\"' in script, (
        f'expected the double quote to be escaped as \\" in the captured '
        f"-e script; got {script!r}"
    )
    assert "C:\\\\path" in script, (
        f"expected the backslash to be escaped as \\\\ in the captured "
        f"-e script; got {script!r}"
    )
    assert "display notification" in script, (
        f"expected the escaped text embedded in a 'display notification' "
        f"sentence; got {script!r}"
    )


def test_notify_missing_message_defaults_to_needs_your_attention(tmp_path):
    """A payload with no .message field defaults the body to 'Needs your attention'."""
    payload = {}
    argv = run_notify(payload, tmp_path)
    script = "\n".join(argv)
    assert "Needs your attention" in script, (
        f"expected the default body 'Needs your attention' in the captured "
        f"-e script; got {script!r}"
    )


def test_notify_embedded_newline_flattened_to_single_line(tmp_path):
    """A message containing an embedded newline arrives at osascript as a single
    line - the newline is flattened to a space so the -e source stays one line."""
    payload = {"message": "line one\nline two"}
    argv = run_notify(payload, tmp_path)
    # Each argv item was captured on its own output line by the fake
    # osascript; a raw newline surviving inside the -e argument would
    # split that single argv item across two captured lines instead of
    # producing "line one line two" on one captured line.
    assert any("line one line two" in line for line in argv), (
        f"expected the embedded newline flattened to a space within a "
        f"single captured argv line; got argv={argv!r}"
    )
    assert not any(
        line.strip() == "line one" for line in argv
    ), f"the newline must not survive as a literal line break; got argv={argv!r}"


def test_notify_message_jq_collapse_behavior_unchanged(tmp_path):
    """The double-jq-parse collapse (scout quick win) preserves behavior:
    missing/null .message -> default text; present-but-empty stays empty;
    non-JSON garbage input -> default text."""
    # null .message -> default
    argv = run_notify({"message": None}, tmp_path / "null-message")
    assert any(
        "Needs your attention" in line for line in argv
    ), f"null .message must default to 'Needs your attention'; got argv={argv!r}"

    # present-but-empty .message -> stays empty (not defaulted)
    argv = run_notify({"message": ""}, tmp_path / "empty-message")
    script = "\n".join(argv)
    assert "Needs your attention" not in script, (
        f"a present-but-empty .message must stay empty, not default; "
        f"got argv={argv!r}"
    )


def test_notify_non_json_input_defaults_to_needs_your_attention(tmp_path):
    """Non-JSON garbage on stdin defaults the body to 'Needs your attention'
    (jq's parse failure is treated the same as a missing .message field)."""
    argv = run_notify(None, tmp_path, raw_input="not valid json{{{")
    script = "\n".join(argv)
    assert "Needs your attention" in script, (
        f"non-JSON stdin must default the body to 'Needs your attention'; "
        f"got captured script={script!r}"
    )
