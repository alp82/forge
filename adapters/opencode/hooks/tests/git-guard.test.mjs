// Parity suite for classifyGitCommand(command) -> { blocked: boolean, reason?: string },
// the JS port of adapters/claude-code/hooks/block-git-writes.sh's segment classifier.
//
// The corpus below is lifted from adapters/claude-code/hooks/tests/test_block_git_writes.py
// per plan.md step 2's explicit list, not re-derived: destructive verbs, force/delete
// push forms, and the position-based allows the reference guard's TC-97/TC-99/TC-106
// pin (a blocked verb inside a commit message, echo string, or grep argument is not the
// command's own first token, so it passes) plus the quote-blind err-safe residual family
// (TC-derived-residual-conservative / -paren-in-commit-message / command-substitution
// pair) that must stay BLOCK - both directions of the reference's documented behavior,
// mirrored exactly per challenge.md's TC-99 fix.
import { test } from "node:test";
import assert from "node:assert/strict";
import ForgePlugin from "../forge.js";

// classifyGitCommand is not a module export (opencode's loader rejects
// non-default exports); it rides as a property on the default export.
const { classifyGitCommand } = ForgePlugin;

const BLOCK_REASON_PREFIX =
  "This git command rewrites or destroys history/state and is user-only.";

// [case id, command, expected blocked]
const CASES = [
  // Destructive verbs / force-push / ref-mutation forms named in plan.md step 2.
  ["reset --hard", "git reset --hard", true],
  ["push --force", "git push --force", true],
  ["push +main refspec", "git push origin +main", true],
  ["checkout -- .", "git checkout -- .", true],
  ["rebase -i", "git rebase -i", true],
  ["clean -fd", "git clean -fd", true],
  ["bare stash (mutating)", "git stash", true],
  ["global -C option, reset --hard", "git -C /x reset --hard", true],
  ["reserved-word if prefix", "if git pull; then :; fi", true],
  ["path-qualified /usr/bin/git", "/usr/bin/git reset --hard", true],

  // Forward ops and read-only forms stay allowed.
  ["add + commit forward chain", 'git add -A && git commit -m "revert the widget"', false],
  ["plain push", "git push origin main", false],
  ["read-only log", "git log", false],
  ["read-only stash list", "git stash list", false],

  // Position-based allows (TC-97/TC-99/TC-106 parity): a blocked verb only
  // appears inside a commit message, echo string, or grep argument, never as
  // the command's own first token, so the guard must not fire.
  ["echo of a blocked command (TC-99)", 'echo "git push --force"', false],
  [
    "commit message mentioning a blocked verb (TC-97)",
    'git commit -m "explain why git push --force is blocked"',
    false,
  ],
  ["grep argument mentioning a blocked verb (TC-106)", 'grep -r "git rebase" docs/', false],

  // Quote-blind err-safe residual family: segment-splitting on `;`, `(`, `$(`,
  // and backticks is quote-blind, so these accepted false positives must stay
  // BLOCK - this is the reference's documented, non-regressed direction.
  [
    "separator inside a quoted commit message",
    'git commit -m "run cleanup; git push --force"',
    true,
  ],
  [
    "paren inside a quoted commit message",
    'git commit -m "explanation (git push --force)"',
    true,
  ],
  ["dollar command substitution", "echo $(git push --force)", true],
  ["backtick command substitution", "echo `git push --force`", true],
];

for (const [label, command, expectedBlocked] of CASES) {
  test(`classifyGitCommand: ${label} -> ${expectedBlocked ? "blocked" : "allowed"} (${command})`, () => {
    const result = classifyGitCommand(command);
    assert.equal(
      result.blocked,
      expectedBlocked,
      `expected blocked=${expectedBlocked} for command=${JSON.stringify(command)}; got ${JSON.stringify(result)}`,
    );
    if (expectedBlocked) {
      assert.ok(
        typeof result.reason === "string" && result.reason.startsWith(BLOCK_REASON_PREFIX),
        `expected a reason starting with the reference hook's user-facing text; got ${JSON.stringify(result.reason)}`,
      );
    }
  });
}
