// forge enforcement plugin for opencode - the whole adapter's hook layer in one
// ESM module, no dependencies (runs under opencode's Bun; tests run it under node).
//
// Four hooks, one per declared capability (see ../capabilities.json):
//   chat.message        - session-start-injection (full): append the forge banner
//                         part to a main session's first message
//   tool.execute.before - tool-guard (full): throw to block destructive git commands
//   tool.execute.after  - change-tracking (full): arm the per-session change marker
//   event               - stop-gate (degraded): session.idle -> reactive review
//                         nudge via client.session.prompt; post-hoc, cannot block
//                         the session from ending
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

// Version stamp baked into the plugin artifact itself, so a half-failed
// re-paste cannot pair agreeing stamps with a stale plugin. Mirror-guarded by
// adapters/claude-code/hooks/tests/test_release_version.py against
// .claude-plugin/plugin.json - bump them together.
export const FORGE_VERSION = "2.1.0";

// ---------------------------------------------------------------------------
// classifyGitCommand - faithful JS port of the reference guard
// adapters/claude-code/hooks/block-git-writes.sh (segment splitting + pattern
// families). Both directions of the reference's documented behavior carry
// over: its position-based allows AND its accepted err-safe false positives.
// ---------------------------------------------------------------------------

// Shared optional run of git global options between `git` and its subcommand.
// -c and -C are the only arg-taking shorts (consume one extra token); every
// other long option is arg-less or =value form; every other short is treated
// as arg-less - an unknown future global option is absorbed without consuming
// the verb token.
const GOPT =
  "(?:\\s+(?:-c\\s+\\S+|-C\\s+\\S+|--[A-Za-z][A-Za-z-]*(?:=\\S*)?|-[A-Za-z]))*";

// Every pattern below is anchored at ^git and applied to a normalized pipeline
// segment whose first real token resolved to git. Splitting (further down) is
// quote-blind on parens/braces/backticks/`;`/`|`/`&`/newline, which cuts both
// ways, same as the reference: false-positive direction (errs safe, accepted) -
// a quoted string containing a separator plus a git command still blocks, e.g.
// a commit message containing `; git push --force` or a literal `(`/backtick
// immediately before a blocked verb; false-negative direction (accepted
// residual, not fixed) - a quoted separator argument can split a destructive
// command's own flags into a non-git segment. Accepted bypasses (a shell-aware
// tokenizer is out of scope): quote-splitting (`"git" push`), IFS tricks, and
// interpreter/wrapper indirection - `bash x.sh`, `env git ...`,
// `command git ...`, `timeout ...`, `sudo ...`, `xargs git ...` resolve their
// first token to the wrapper, not git, and pass.
const BLOCKED_VERBS = new RegExp(
  "^git" +
    GOPT +
    "\\s+(?:cherry-pick|rebase|reset|merge|revert|restore|rm|mv|apply|am|clean|pull|filter-branch)(?:\\s|$)",
);
// Destructive `git push` forms: force/delete flags (long forms, bundled short
// clusters containing f/d), whitespace-led `+` refspecs (force-push), and
// whitespace-led `:` empty-source refspecs (remote-branch delete). The
// `[^;&|]*` idiom predates segment pre-splitting - segments can no longer
// contain `;`, `&`, or `|` - kept as defense in depth, same as the reference.
const BLOCKED_PUSH_DESTRUCTIVE = new RegExp(
  "^git" +
    GOPT +
    "\\s+push(?:\\s[^;&|]*)?(?:\\s(?:--force|--force-with-lease|--delete|--mirror|--prune)(?:=\\S*)?(?:\\s|$)|(?:^|\\s)-[A-Za-z0-9]*[fd][A-Za-z0-9]*(?:\\s|$)|\\s\\+\\S|\\s:\\S)",
);
// `git tag <name>` (create) and `git tag -d`/`-a`/`-s`/`-f`/`-m` (delete/sign/force)
const BLOCKED_TAG = new RegExp("^git" + GOPT + "\\s+tag\\s+(?:[^-\\s]|-[adsfm])");
// `git branch -D|-d|-m|-M` (delete/rename)
const BLOCKED_BRANCH = new RegExp("^git" + GOPT + "\\s+branch\\s+-[DdmM]");
// `git checkout` forms that discard working-tree changes: `[<ref>] -- <path>`,
// force checkout (`-f`/`--force` as its own token; `-b` stays allowed), a bare
// `.` pathspec, and `--pathspec-from-file` (pathspecs smuggled via file/stdin).
const BLOCKED_CHECKOUT = new RegExp(
  "^git" +
    GOPT +
    "\\s+checkout(?:\\s[^;&|]*)?\\s(?:--\\s|(?:-f|--force|\\.)(?:\\s|$)|--pathspec-from-file(?:=|\\s|$))",
);
// Ref surgery: `git reflog expire|delete`, `git update-ref` (blocked
// unconditionally - no read-only form), `git worktree remove --force|-f`
// (including bundled short clusters like -ff).
const BLOCKED_REF_SURGERY = new RegExp(
  "^git" +
    GOPT +
    "\\s+(?:reflog\\s+(?:expire|delete)|update-ref(?:\\s|$)|worktree\\s+remove(?:\\s[^;&|]*)?\\s(?:--force|-[A-Za-z]*f[A-Za-z]*)(?:\\s|$))",
);
// Mutating stash (bare `git stash`, push/pop/drop/clear/-u, ...) stays
// blocked; read-only `git stash list|show` is a separate allow-pattern
// checked first in the loop below, same as the reference.
const BLOCKED_STASH = new RegExp("^git" + GOPT + "\\s+stash(?:\\s|$)");
const STASH_READONLY = new RegExp("^git" + GOPT + "\\s+stash\\s+(?:list|show)(?:\\s|$)");

const BLOCKED_ALL = [
  BLOCKED_VERBS,
  BLOCKED_TAG,
  BLOCKED_BRANCH,
  BLOCKED_CHECKOUT,
  BLOCKED_REF_SURGERY,
  BLOCKED_PUSH_DESTRUCTIVE,
  BLOCKED_STASH,
];

// Quote-tolerant leading env-assignment (`FOO="a b" git ...`), stripped before
// quotes are dropped so the value's spaces cannot break first-token resolution.
const ENV_ASSIGN_RE = /^[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|'[^']*'|[^\s])*\s+/;
// Shell reserved words that can prefix a git invocation without being its own
// command (`if git pull; then ...`, `exec git reset --hard`): stripped
// iteratively so `if FOO=x git ...` still resolves.
const RESERVED_WORD_RE = /^(?:if|then|elif|else|do|while|until|!|time|exec|coproc)\s+/;

/**
 * Classify a bash command line: block the dangerous, allow the forward.
 * Splits into pipeline segments (covers `;`, `|`, `&&`, `||`, `$(`, backticks,
 * brace/paren groups, and newlines) and judges each by its first real token,
 * so text that merely mentions a blocked command (commit messages, echo
 * strings, grep arguments) passes.
 * @param {string} command
 * @returns {{ blocked: boolean, reason?: string }}
 */
export function classifyGitCommand(command) {
  if (typeof command !== "string" || command.length === 0) return { blocked: false };

  const segments = command.split(/[|&;(){}`\n]/);
  for (let seg of segments) {
    seg = seg.replace(/^\s+/, "");
    for (;;) {
      const env = seg.match(ENV_ASSIGN_RE);
      if (env) {
        seg = seg.slice(env[0].length);
        continue;
      }
      const reserved = seg.match(RESERVED_WORD_RE);
      if (reserved) {
        seg = seg.slice(reserved[0].length);
        continue;
      }
      break;
    }
    const first = seg.split(/\s/, 1)[0];
    if (first === "git") {
      // fall through
    } else if (first.endsWith("/git")) {
      // Path invocation: normalize `/usr/bin/git push` to `git push`.
      seg = "git" + seg.slice(first.length);
    } else {
      continue;
    }
    // Drop quote characters so a blocked flag directly followed by a closing
    // quote (the quote-blind-split residual above) still matches its pattern.
    seg = seg.replace(/["']/g, "");
    if (STASH_READONLY.test(seg)) continue;
    if (BLOCKED_ALL.some((re) => re.test(seg))) {
      return {
        blocked: true,
        reason:
          "This git command rewrites or destroys history/state and is user-only. " +
          "Forward ops (add/commit/push) are allowed; this one is blocked: " +
          command +
          ". If you explicitly want it, surface the exact command for the user to run.",
      };
    }
  }
  return { blocked: false };
}

// ---------------------------------------------------------------------------
// Two-stamp drift check - the stamp-nag convention reused from
// adapters/claude-code/hooks/session-start.sh: the install writes the same
// version into both copied surfaces (this plugin's FORGE_VERSION const + the
// skills copy's .forge-version file); at startup the plugin compares the two
// and nags on drift. Local-consistency only - no network calls.
// ---------------------------------------------------------------------------

/**
 * @param {string} pluginVersion
 * @param {string | null | undefined} skillsStamp
 * @returns {string | null} one-line nag, or null when the stamps agree
 */
export function stampNag(pluginVersion, skillsStamp) {
  if (skillsStamp === pluginVersion) return null;
  return "Installed forge surfaces disagree (plugin " + pluginVersion + ", skills " +
    (skillsStamp ?? "unstamped") + ") - re-run the install paste.";
}

/**
 * The injected session-start context. States only what the prose already
 * states - no new doctrine (contract paragraph 5: prose is tier-invariant).
 * @param {string | null} nag
 * @returns {string}
 */
export function buildBanner(nag) {
  let banner =
    "## forge\n\n" +
    '- Every code-modifying request enters via the forge skill - "small/mechanical/one-line" is not a bypass.\n' +
    "- The flow: ~/.config/opencode/skills/forge/SKILL.md (crossfire is the standalone review verb).\n" +
    "- Stage spawns use the forge-mini/forge-standard/forge-large/forge-ultra subagents.";
  if (nag) banner += "\n- " + nag;
  return banner;
}

// --- git-block log, same policy as the reference hook (rotate at ~1MB) -----

const LOG_MAX_BYTES = 1048576;
const LOG_KEEP_BYTES = 524288;

function logBlocked(command) {
  try {
    const dir = path.join(os.homedir(), ".config/opencode/forge");
    fs.mkdirSync(dir, { recursive: true });
    const logFile = path.join(dir, "git-block.log");
    try {
      const stat = fs.statSync(logFile);
      if (stat.size > LOG_MAX_BYTES) {
        const tail = fs.readFileSync(logFile).subarray(-LOG_KEEP_BYTES);
        fs.writeFileSync(logFile, tail);
      }
    } catch {
      // no log yet - nothing to rotate
    }
    fs.appendFileSync(logFile, "[" + new Date().toISOString() + "] BLOCKED: " + command + "\n");
  } catch {
    // Logging must never break the block itself.
  }
}

// ---------------------------------------------------------------------------
// The plugin. opencode auto-loads this file from ~/.config/opencode/plugins/
// at startup and calls the default export with its fixed argument shape.
// FORGE_STAMP_PATH is the test seam: plugin.test.mjs points it at a temp file
// so the drift wiring is exercised without touching a real install.
// ---------------------------------------------------------------------------

// opencode's built-in tool ids, verified against the source registry
// (packages/opencode/src/tool/ on the dev branch, 2026-07-18): the shell tool
// keeps id "bash" for compatibility (shell/id.ts), file mutation is
// "edit" / "write" / "apply_patch".
const GUARDED_SHELL_TOOL = "bash";
const CHANGE_TOOLS = new Set(["edit", "write", "apply_patch"]);

export default async function ForgePlugin({ client, directory }) {
  const stampPath =
    process.env.FORGE_STAMP_PATH ??
    path.join(os.homedir(), ".config/opencode/skills/forge/.forge-version");
  let skillsStamp = null;
  try {
    skillsStamp = fs.readFileSync(stampPath, "utf8").trim();
  } catch {
    skillsStamp = null;
  }
  const banner = buildBanner(stampNag(FORGE_VERSION, skillsStamp));

  // Session state is in-memory; an opencode restart resets it. Acceptable
  // degradation at the guarded tier, documented in ../README.md.
  const seenSessions = new Set();
  const changedSessions = new Set();
  const nudgedSessions = new Set();
  const childSessions = new Set();
  const mainSessions = new Set();

  async function isChildSession(sessionID) {
    if (childSessions.has(sessionID)) return true;
    if (mainSessions.has(sessionID)) return false;
    // Parentage unknown (created before this plugin loaded): ask the server.
    try {
      const res = await client.session.get({ path: { id: sessionID } });
      const info = res?.data ?? res;
      const isChild = Boolean(info?.parentID);
      (isChild ? childSessions : mainSessions).add(sessionID);
      return isChild;
    } catch {
      // Unknowable: treat as main - a spurious banner/nudge beats a silently
      // unguarded session.
      return false;
    }
  }

  return {
    // session-start-injection: once per main session, on its first message.
    "chat.message": async (input, output) => {
      const sessionID =
        input?.sessionID ?? output?.message?.sessionID ?? output?.message?.session_id;
      if (sessionID === undefined || seenSessions.has(sessionID)) return;
      seenSessions.add(sessionID);
      // Child sessions get no banner: a stage worker's inputs arrive only
      // through its spawn prompt and named files (contract paragraph 2), and
      // the entry-rule doctrine would misdirect it.
      if (await isChildSession(sessionID)) return;
      output.parts.push({ type: "text", text: banner, synthetic: true });
    },

    // tool-guard: throw aborts the tool call before it executes.
    "tool.execute.before": async (input, output) => {
      if (input?.tool !== GUARDED_SHELL_TOOL) return;
      const command = output?.args?.command ?? input?.args?.command;
      const result = classifyGitCommand(command ?? "");
      if (result.blocked) {
        logBlocked(command);
        throw new Error(result.reason);
      }
    },

    // change-tracking: arm the per-session marker the idle nudge reads.
    "tool.execute.after": async (input) => {
      if (CHANGE_TOOLS.has(input?.tool)) changedSessions.add(input.sessionID);
    },

    // stop-gate (degraded): reactive idle nudge - post-hoc, cannot block the
    // session from ending. Once per session, hard: the nudge itself idles
    // again and must not loop.
    event: async ({ event }) => {
      if (event?.type === "session.created") {
        const info = event.properties?.info;
        if (info?.id !== undefined) {
          (info.parentID ? childSessions : mainSessions).add(info.id);
        }
        return;
      }
      if (event?.type !== "session.idle") return;
      const sessionID = event.properties?.sessionID;
      if (sessionID === undefined) return;
      if (!changedSessions.has(sessionID) || nudgedSessions.has(sessionID)) return;
      if (await isChildSession(sessionID)) return;
      nudgedSessions.add(sessionID);
      await client.session.prompt({
        path: { id: sessionID },
        body: {
          parts: [
            {
              type: "text",
              text: "forge review reminder: before you consider this session done, confirm the three owed checks - tests green, build clean, review wave run.",
            },
          ],
        },
      });
    },
  };
}
