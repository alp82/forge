"""Tests for hooks/block-git-writes.sh - a PreToolUse(Bash) hook.

CONTRACT:
  - Reads {"tool_name":"Bash","tool_input":{"command":"<cmd>"}} on stdin.
  - ALLOW: exit 0 with NO '"decision":"block"' in stdout.
  - BLOCK: stdout contains a JSON object with '"decision":"block"' (exit 0).
  - A non-Bash tool_name exits 0 immediately (ALLOW).

These cases assert POST-narrowing behavior. Against the current
(over-blocking) script, TC-01..TC-15 (ALLOW/boundary) are expected to FAIL -
that is the correct red state. The implementer makes them green by narrowing
the blocked_verbs regex so that safe git verbs (add, commit, push without
force/delete flags) and non-git commands are permitted.

TC-71..TC-88 (plan-audit-fix-batch.md steps 5/6) assert POST-hardening
behavior for three additional guard gaps: a `checkout <ref> -- <pathspec>`
form (ref before the `--` separator, which silently discards edits and was
previously only caught in the narrower `checkout -- <pathspec>` shape), the
`filter-branch` verb, and ref-surgery verbs/flags (`reflog expire`,
`update-ref -d`, `worktree remove --force`/`-f`). Against the current
(pre-hardening) script, the new BLOCK cases in that range are expected to
FAIL - that is the correct red state. The implementer makes them green by
broadening the blocked-command patterns; the paired ALLOW/boundary cases in
the same range must stay green throughout, pinning that the hardening does
not sweep in explicitly out-of-scope forms (`reflog delete`, `update-ref`
without `-d`, `worktree remove` without a force flag).

TC-89..TC-96 (security-lens residual-gap follow-up) adopt two forms that
TC-87/TC-88 had previously pinned as out-of-scope: `reflog delete <ref>@{...}`
and a bare two-arg `update-ref <ref> <sha>` overwrite are now BLOCK, since
scope has been expanded to cover them. The range also adds BLOCK coverage for
`update-ref --stdin` (batch ref surgery), `worktree remove -ff` (a bundled
short force flag), and four working-tree-discard `checkout` forms (`checkout
.`, `checkout -f <ref>`, `checkout --force <ref>`,
`checkout --pathspec-from-file=- .`), plus the `git -C <dir>` global-option
variant of `update-ref --stdin`. TC-96 pins `git show-ref` as ALLOW (read-only
ref inspection that must not be swept in by the update-ref patterns). Against
the current (pre-hardening) script, the new/flipped BLOCK cases in this range
are expected to FAIL - that is the correct red state.

TC-97..TC-108 (plan-guard-hook-bug-fixes.md step 3) move the guard from
substring-anywhere matching to position-based matching: a blocked verb must
be the first real token of a command/pipeline segment, not merely present
anywhere in the command text. Against the current (substring-anywhere)
script, ALLOW cases TC-97/TC-98/TC-99/TC-100/TC-101/TC-106 are expected to
FAIL (the current script still blocks them on a substring hit inside a
commit message, echo string, or grep argument, and does not yet carve out
read-only `git stash list`/`show`), as is BLOCK case TC-108 (the current
script does not yet resolve a path-qualified `/usr/bin/git` invocation to
`git`) - that is the correct red state. TC-102/TC-103/TC-104/TC-105/TC-107
pin no-regression (mutating stash, multi-segment `&&`/`|` chains, and
env-prefix stripping) and are expected to stay green throughout.
TC-derived-quoted-env pins that quote-tolerant env-assignment stripping
still resolves `FOO="a b" git push --force` to `git` (BLOCK).
TC-derived-residual-conservative pins the documented residual limitation
that a quoted commit message containing a separator plus a blocked git
command still blocks (segment-splitting is quote-blind, per plan
Out-of-Scope item 3) - this must stay BLOCK before and after the fix.

TC-derived-reserved-word-* (security-lens follow-up, round 1) pin that a
leading shell reserved word (`if`, `for ... do`, `exec`, `!`) does not
shadow a destructive git command's first token - the guard strips these
before resolving the first real token. TC-derived-paren-in-commit-message,
TC-derived-command-substitution-dollar, and
TC-derived-command-substitution-backtick (test-gap follow-up, round 1) pin
that parens and backticks are also separator characters: a commit message
containing a literal `(` before a blocked verb still blocks (quote-blind
residual, accepted), and a destructive git command inside `$(...)` or
backtick command substitution still blocks (the intended, non-residual
direction of that same splitting).
"""

import json
import shutil
import subprocess
from pathlib import Path

HOOK_PATH = Path(__file__).resolve().parent.parent / "block-git-writes.sh"

# Resolved once, absolute: a restricted PATH passed via run_guard's env kwarg
# must not break bash's own resolution (a bare "bash" argv[0] is looked up
# via the child's PATH, which a restricted-PATH test deliberately narrows).
BASH_PATH = shutil.which("bash") or "/bin/bash"


def run_guard(command=None, tool_name="Bash", env=None):
    """Invoke the hook as a subprocess with the given tool_name and command.

    Builds the stdin JSON and returns the captured stdout string.
    For non-Bash tool_names, command may be omitted (None).
    env, when given, is forwarded to subprocess.run (e.g. a restricted PATH
    for jq-absent testing); the hook itself is always launched via the
    pre-resolved absolute BASH_PATH so a restricted PATH cannot break its
    own resolution.
    """
    tool_input = {}
    if command is not None:
        tool_input["command"] = command
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    result = subprocess.run(
        [BASH_PATH, str(HOOK_PATH)],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.stdout


# ---------------------------------------------------------------------------
# Parametrized cases
# ---------------------------------------------------------------------------
# Each entry: (case_id, tool_name, command_or_None, expected_block_bool)
# expected_block_bool=True  -> '"decision":"block"' must appear in stdout (BLOCK)
# expected_block_bool=False -> '"decision":"block"' must NOT appear in stdout (ALLOW)

CASES = [
    # ALLOW cases (TC-01..TC-09): safe git verbs and non-git commands
    ("TC-01", "Bash", "git add -A", False),
    ("TC-02", "Bash", "git add src/foo.ts", False),
    ("TC-03", "Bash", 'git commit -m "msg"', False),
    ("TC-04", "Bash", "git commit --amend --no-edit", False),
    ("TC-05", "Bash", "git push", False),
    ("TC-06", "Bash", "git push -u origin feat/x", False),
    ("TC-07", "Bash", "git push origin HEAD", False),
    ("TC-08", "Bash", "ls", False),
    ("TC-09", "Bash", "cat README.md", False),
    # ALLOW cases: non-Bash tool_name (TC-10, TC-11) - no command
    ("TC-10", "Read", None, False),
    ("TC-11", "Write", None, False),
    # BOUNDARY: must NOT block (TC-12..TC-15)
    ("TC-12", "Bash", "git push origin local:remote", False),
    ("TC-13", "Bash", "git push origin main:main", False),
    ("TC-14", "Bash", "git push -u origin feat/x --tags", False),
    ("TC-15", "Bash", 'git push origin HEAD -m "fix: bump version to 1.2+3"', False),
    # BLOCK: force/delete push (TC-16..TC-25)
    ("TC-16", "Bash", "git push --force", True),
    ("TC-17", "Bash", "git push --force-with-lease", True),
    ("TC-18", "Bash", "git push -f origin main", True),
    ("TC-19", "Bash", "git push -fu origin main", True),
    ("TC-20", "Bash", "git push -uf origin main", True),
    ("TC-21", "Bash", "git push origin +HEAD:main", True),
    ("TC-22", "Bash", "git push origin +main", True),
    ("TC-23", "Bash", "git push --delete origin branch", True),
    ("TC-24", "Bash", "git push -d origin branch", True),
    ("TC-25", "Bash", "git push origin :branch", True),
    # BLOCK: still-blocked verbs (TC-26..TC-35)
    ("TC-26", "Bash", "git reset --hard", True),
    ("TC-27", "Bash", "git rebase -i HEAD~3", True),
    ("TC-28", "Bash", "git clean -fd", True),
    ("TC-29", "Bash", "git checkout -- file.txt", True),
    ("TC-30", "Bash", "git branch -D feature", True),
    ("TC-31", "Bash", "git cherry-pick abc", True),
    ("TC-32", "Bash", "git stash", True),
    ("TC-33", "Bash", "git merge origin/main", True),
    ("TC-34", "Bash", "git revert HEAD", True),
    ("TC-35", "Bash", "git pull", True),
    # BLOCK: --mirror, --prune, and equals form of --force-with-lease (TC-36..TC-39)
    ("TC-36", "Bash", "git push --mirror", True),
    ("TC-37", "Bash", "git push --mirror origin", True),
    ("TC-38", "Bash", "git push --prune origin refs/heads/*", True),
    ("TC-39", "Bash", "git push --force-with-lease=main origin main", True),
    # ALLOW: --force-if-includes (inert modifier) and chained commands (TC-40..TC-43)
    ("TC-40", "Bash", "git push --force-if-includes origin main", False),
    ("TC-41", "Bash", "git push origin main && grep -rf pat .", False),
    ("TC-42", "Bash", "git push origin main && cp -f a b", False),
    ("TC-43", "Bash", "git push origin main; ls -d dirs", False),
    # BLOCK: tag create and delete (TC-44..TC-45)
    ("TC-44", "Bash", "git tag v1.0.0", True),
    ("TC-45", "Bash", "git tag -d v1.0.0", True),
    # BLOCK: branch delete and rename (TC-46..TC-47)
    ("TC-46", "Bash", "git branch -d feature", True),
    ("TC-47", "Bash", "git branch -m old new", True),
    # BLOCK: global-option bypass cases (TC-48..TC-54)
    ("TC-48", "Bash", "git -C /repo push --force", True),
    ("TC-49", "Bash", "git -c x=y reset --hard", True),
    ("TC-50", "Bash", "git --no-pager push --force", True),
    ("TC-51", "Bash", "git -C /repo branch -D main", True),
    ("TC-52", "Bash", "git -C /repo push origin :main", True),
    ("TC-53", "Bash", "git -p push --force", True),
    ("TC-54", "Bash", "git -c a.b=c push --delete origin x", True),
    # ALLOW: global-option prefix with safe verbs (TC-55..TC-60)
    ("TC-55", "Bash", "git -C /repo status", False),
    ("TC-56", "Bash", "git -c x=y add -A", False),
    ("TC-57", "Bash", 'git -C /repo commit -m "x"', False),
    ("TC-58", "Bash", "git --no-pager log", False),
    ("TC-59", "Bash", "git -C /repo push origin feat/x", False),
    ("TC-60", "Bash", "git -C /repo push", False),
    # BLOCK: previously-unlisted global options must not bypass the guard (TC-61..TC-67)
    ("TC-61", "Bash", "git --exec-path=/x push --force", True),
    ("TC-62", "Bash", "git --config-env=X=Y push --force", True),
    ("TC-63", "Bash", "git --no-advice push --force", True),
    ("TC-64", "Bash", "git --super-prefix=x push --force", True),
    ("TC-65", "Bash", "git --attr-source=x reset --hard", True),
    ("TC-66", "Bash", "git -C /repo --exec-path=/x push --force", True),
    ("TC-67", "Bash", "git -c x=y --exec-path=/y push --force", True),
    # ALLOW: unlisted global options with safe verbs must not be over-blocked (TC-68..TC-70)
    ("TC-68", "Bash", "git --no-advice push origin feat/x", False),
    ("TC-69", "Bash", "git --exec-path=/x status", False),
    ("TC-70", "Bash", "git --no-advice add -A", False),
    # BLOCK: broadened checkout - ref before the `--` pathspec separator (TC-71..TC-73)
    ("TC-71", "Bash", "git checkout HEAD -- f", True),
    ("TC-72", "Bash", "git checkout main~2 -- src/", True),
    ("TC-73", "Bash", "git -C /repo checkout HEAD -- file", True),
    # BLOCK: filter-branch verb (TC-74..TC-75)
    ("TC-74", "Bash", "git filter-branch -f --env-filter x", True),
    ("TC-75", "Bash", "git -c x=y filter-branch --tree-filter x", True),
    # BLOCK: ref surgery - reflog expire, update-ref -d, worktree remove --force/-f (TC-76..TC-79)
    ("TC-76", "Bash", "git reflog expire --expire=now --all", True),
    ("TC-77", "Bash", "git update-ref -d refs/heads/x", True),
    ("TC-78", "Bash", "git worktree remove --force ../wt", True),
    ("TC-79", "Bash", "git worktree remove -f ../wt", True),
    # ALLOW: boundaries the ref-surgery hardening must not sweep in (TC-80..TC-88)
    ("TC-80", "Bash", "git checkout main", False),
    ("TC-81", "Bash", "git checkout -b feat/x", False),
    ("TC-82", "Bash", "git reflog", False),
    ("TC-83", "Bash", "git reflog show", False),
    ("TC-84", "Bash", "git worktree list", False),
    ("TC-85", "Bash", "git worktree remove wt", False),
    ("TC-86", "Bash", "git log --oneline -- src/", False),
    # FLIPPED to BLOCK: scope now covers these (previously pinned ALLOW/out-of-scope)
    ("TC-87", "Bash", "git reflog delete <ref>@{stamp}", True),
    ("TC-88", "Bash", "git update-ref refs/heads/x abc123", True),
    # BLOCK: security-lens residual-gap follow-up - update-ref/worktree/checkout (TC-89..TC-95)
    ("TC-89", "Bash", "git update-ref --stdin", True),
    ("TC-90", "Bash", "git worktree remove -ff ../wt", True),
    ("TC-91", "Bash", "git checkout .", True),
    ("TC-92", "Bash", "git checkout -f main", True),
    ("TC-93", "Bash", "git checkout --force main", True),
    ("TC-94", "Bash", "git checkout --pathspec-from-file=- .", True),
    ("TC-95", "Bash", "git -C /repo update-ref --stdin", True),
    # ALLOW: read-only ref inspection must not match update-ref patterns (TC-96)
    ("TC-96", "Bash", "git show-ref", False),
    # ALLOW: position-based matching - blocked verb only appears inside a
    # commit message, echo string, or grep argument, never as the actual
    # command being run (TC-97..TC-101, TC-106)
    (
        "TC-97",
        "Bash",
        'git commit -m "explain why git push --force is blocked"',
        False,
    ),
    (
        "TC-98",
        "Bash",
        'git commit -m "note: git reset --hard is user-only"',
        False,
    ),
    ("TC-99", "Bash", 'echo "git push --force"', False),
    ("TC-100", "Bash", "git stash list", False),
    ("TC-101", "Bash", "git stash show -p", False),
    ("TC-106", "Bash", 'grep -r "git rebase" docs/', False),
    # BLOCK: no-regression at the edge of the stash read-only carve-out
    # (TC-102, TC-103)
    ("TC-102", "Bash", "git stash pop", True),
    ("TC-103", "Bash", "git stash -u", True),
    # BLOCK: no-regression - destructive command in a later segment of a
    # multi-segment pipeline (TC-104, TC-105)
    ("TC-104", "Bash", "ls && git push --force", True),
    ("TC-105", "Bash", "echo hi | git apply", True),
    # BLOCK: env-prefix stripping and path-qualified invocation still
    # resolve the first real token to git (TC-107, TC-108)
    ("TC-107", "Bash", "GIT_TRACE=1 git reset --hard", True),
    ("TC-108", "Bash", "/usr/bin/git push --force", True),
    # BLOCK: quote-tolerant env-assignment stripping still resolves the
    # first real token to git (Implementation Step 2)
    ("TC-derived-quoted-env", "Bash", 'FOO="a b" git push --force', True),
    # BLOCK: documented residual limitation (## Out of Scope item 3) -
    # segment-splitting is quote-blind, so a commit message that itself
    # contains a separator plus a blocked git command still blocks; this
    # is a regression guard against "fixing" a documented non-fix.
    (
        "TC-derived-residual-conservative",
        "Bash",
        'git commit -m "run cleanup; git push --force"',
        True,
    ),
    # BLOCK: security-lens follow-up (round 1) - leading shell reserved
    # words must not shadow a destructive git command's first token.
    (
        "TC-derived-reserved-word-if",
        "Bash",
        "if git pull; then :; fi",
        True,
    ),
    (
        "TC-derived-reserved-word-for-do",
        "Bash",
        'for f in a b; do git checkout -- "$f"; done',
        True,
    ),
    (
        "TC-derived-reserved-word-exec",
        "Bash",
        "exec git reset --hard",
        True,
    ),
    (
        "TC-derived-reserved-word-bang",
        "Bash",
        "! git reset --hard",
        True,
    ),
    # BLOCK: security-lens follow-up (round 2) - `coproc` prefixes-and-executes
    # like `exec`/`time` and must not shadow the destructive verb either.
    (
        "TC-derived-reserved-word-coproc",
        "Bash",
        "coproc git reset --hard",
        True,
    ),
    # ALLOW: test-gap follow-up (round 2) - reserved-word stripping must only
    # strip the reserved word itself, not widen the blocked-verb match to
    # swallow safe verbs that happen to follow one.
    (
        "TC-derived-reserved-word-allow-if",
        "Bash",
        "if git status; then :; fi",
        False,
    ),
    (
        "TC-derived-reserved-word-allow-exec",
        "Bash",
        "exec git add -A",
        False,
    ),
    # BLOCK: test-gap follow-up (round 2) - env-assignment stripping and
    # reserved-word stripping interleave (documented at block-git-writes.sh
    # around the reserved_word_re comment): a leading reserved word followed
    # by an env assignment must still resolve to the destructive verb.
    (
        "TC-derived-reserved-word-env-interleave",
        "Bash",
        "if FOO=x git reset --hard; then :; fi",
        True,
    ),
    # BLOCK: test-gap follow-up (round 2) - vocabulary coverage for the
    # remaining reserved words in the alternation (`then`, `elif`, `else`,
    # `while`, `until`, `time`) that were listed but never exercised.
    (
        "TC-derived-reserved-word-then",
        "Bash",
        "if true; then git reset --hard; fi",
        True,
    ),
    (
        "TC-derived-reserved-word-elif",
        "Bash",
        "if false; then :; elif git reset --hard; then :; fi",
        True,
    ),
    (
        "TC-derived-reserved-word-else",
        "Bash",
        "if false; then :; else git reset --hard; fi",
        True,
    ),
    (
        "TC-derived-reserved-word-while",
        "Bash",
        "while git reset --hard; do :; done",
        True,
    ),
    (
        "TC-derived-reserved-word-until",
        "Bash",
        "until git reset --hard; do :; done",
        True,
    ),
    (
        "TC-derived-reserved-word-time",
        "Bash",
        "time git reset --hard",
        True,
    ),
    # BLOCK: test-gap follow-up (round 1) - a commit message containing a
    # literal `(` immediately before a blocked verb splits into a segment
    # starting with the destructive command; same accepted residual family
    # as TC-derived-residual-conservative (quote-blind splitting on parens).
    (
        "TC-derived-paren-in-commit-message",
        "Bash",
        'git commit -m "explanation (git push --force)"',
        True,
    ),
    # BLOCK: test-gap follow-up (round 1) - command substitution and
    # backtick substitution are separator characters, so a destructive git
    # command inside either form must still split into its own segment.
    (
        "TC-derived-command-substitution-dollar",
        "Bash",
        "echo $(git push --force)",
        True,
    ),
    (
        "TC-derived-command-substitution-backtick",
        "Bash",
        "echo `git push --force`",
        True,
    ),
]


def _case_ids():
    return [entry[0] for entry in CASES]


import pytest


@pytest.mark.parametrize(
    "case_id,tool_name,command,expected_block", CASES, ids=_case_ids()
)
def test_block_git_writes(case_id, tool_name, command, expected_block):
    """Each case asserts ALLOW or BLOCK behavior of block-git-writes.sh."""
    out = run_guard(command=command, tool_name=tool_name)
    block_marker = '"decision":"block"'
    if expected_block:
        assert block_marker in out, (
            f"{case_id}: expected BLOCK for tool_name={tool_name!r} command={command!r}; "
            f"stdout did not contain {block_marker!r}; got stdout={out!r}"
        )
    else:
        assert block_marker not in out, (
            f"{case_id}: expected ALLOW for tool_name={tool_name!r} command={command!r}; "
            f"stdout must not contain {block_marker!r}; got stdout={out!r}"
        )


# ---------------------------------------------------------------------------
# jq-absent fail-open (plan-guard-hook-bug-fixes.md step 1 / step 4)
# ---------------------------------------------------------------------------
# Reverses the prior fail-closed policy: a machine with no jq on PATH now gets
# a logged warning and an ALLOW, not a total block of every Bash call. This
# test is self-contained (does not go through run_guard) so it can assert on
# returncode and stderr as well as stdout, and builds its own restricted-PATH
# stub bin dir - the technique mirrors test_auto_format_script.py:99-140.


def test_jq_absent_fail_open(tmp_path):
    """No jq on PATH: exit 0, no block decision, and a jq warning on stderr.

    Against the current (fail-closed) script this is expected to FAIL - a
    missing jq currently produces a block_static BLOCK decision on stdout,
    not a warn-and-allow.
    """
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    # jq is deliberately excluded from the stub PATH; mkdir and date are the
    # only external binaries block-git-writes.sh needs before it would reach
    # its jq check.
    for tool in ("mkdir", "date"):
        real = shutil.which(tool)
        assert real, f"{tool} must be resolvable on this host to build the stub PATH"
        (stub_bin / tool).symlink_to(real)
    home = tmp_path / "home"
    home.mkdir()

    payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": "git push --force"}}
    )
    result = subprocess.run(
        [BASH_PATH, str(HOOK_PATH)],
        input=payload,
        capture_output=True,
        text=True,
        env={"PATH": str(stub_bin), "HOME": str(home)},
    )
    assert result.returncode == 0, (
        f"expected exit 0 when jq is absent (fail-open); "
        f"got {result.returncode}; stderr={result.stderr!r}"
    )
    assert '"decision":"block"' not in result.stdout, (
        f"expected no block decision when jq is absent (fail-open); "
        f"got stdout={result.stdout!r}"
    )
    assert "jq" in result.stderr, (
        f"expected a warning naming jq on stderr when jq is absent; "
        f"got stderr={result.stderr!r}"
    )


def test_jq_present_parse_failure_stays_fail_closed(tmp_path):
    """jq present but the hook payload is malformed JSON: stays fail-closed (BLOCK).

    Negative control for the jq-absent fail-open change: fail-open covers only
    the "jq missing" case (plan Out of Scope item 2). A genuinely unparseable
    payload with jq present and working is a different anomaly and must still
    block via block_static. This already holds against the current script
    (the jq-parse-failure paths are untouched by the fix) and must stay green.
    """
    result = subprocess.run(
        [BASH_PATH, str(HOOK_PATH)],
        input="not valid json{{{",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"expected exit 0 (block decision emitted, not a crash); "
        f"got {result.returncode}; stderr={result.stderr!r}"
    )
    assert '"decision":"block"' in result.stdout, (
        f"expected a BLOCK decision when jq cannot parse the hook input "
        f"(fail-closed); got stdout={result.stdout!r}"
    )
