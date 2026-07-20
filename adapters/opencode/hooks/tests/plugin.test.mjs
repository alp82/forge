// Plugin-shape tests for adapters/opencode/hooks/forge.js's default export
// (ForgePlugin) and its stampNag helper, per plan.md step 2.
//
// Uses a stub opencode `client` (only `session.prompt` / `session.get` are
// called by the plugin) and points the FORGE_STAMP_PATH env-var seam at a
// temp file per plan.md step 1 / challenge.md's testability concern, so
// nothing here ever touches a real HOME or a dev machine's live install.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import ForgePlugin from "../forge.js";

// stampNag and FORGE_VERSION are not module exports (opencode's loader rejects
// non-default exports); they ride as properties on the default export.
const { stampNag, FORGE_VERSION } = ForgePlugin;

function makeClient(promptCalls, sessionGet) {
  return {
    session: {
      prompt: async (args) => {
        promptCalls.push(args);
      },
      get: sessionGet ?? (async () => ({})),
    },
  };
}

async function makePlugin({ stampContent, sessionGet } = {}) {
  const dir = mkdtempSync(join(tmpdir(), "forge-stamp-"));
  const stampPath = join(dir, ".forge-version");
  if (stampContent !== undefined) {
    writeFileSync(stampPath, stampContent);
  }
  process.env.FORGE_STAMP_PATH = stampPath;
  const promptCalls = [];
  const client = makeClient(promptCalls, sessionGet);
  const plugin = await ForgePlugin({ client, directory: dir });
  return { plugin, promptCalls, dir };
}

async function registerChild(plugin, { childID, parentID }) {
  await plugin.event({
    event: {
      type: "session.created",
      properties: { info: { id: childID, parentID } },
    },
  });
}

test("hooks object exposes exactly the four required keys", async () => {
  const { plugin } = await makePlugin();
  assert.deepEqual(
    Object.keys(plugin).sort(),
    ["chat.message", "event", "tool.execute.after", "tool.execute.before"].sort(),
  );
});

test("injects the banner exactly once per main session across two chat.message calls", async () => {
  const { plugin } = await makePlugin();
  const sessionID = "ses_main_banner_once";
  const output1 = { message: {}, parts: [] };
  await plugin["chat.message"]({ sessionID }, output1);
  const output2 = { message: {}, parts: [] };
  await plugin["chat.message"]({ sessionID }, output2);

  assert.equal(output1.parts.length, 1, "first chat.message call must append one banner part");
  assert.equal(
    output2.parts.length,
    0,
    "second chat.message call for the same session must not append another banner",
  );
  const bannerText = output1.parts[0].text ?? output1.parts[0];
  assert.match(
    bannerText,
    /forge skill/i,
    "banner must carry the entry-rule doctrine naming the forge skill",
  );
});

test("child sessions receive no banner", async () => {
  const { plugin } = await makePlugin();
  await registerChild(plugin, { childID: "ses_child_nobanner", parentID: "ses_main_parent1" });
  const output = { message: {}, parts: [] };
  await plugin["chat.message"]({ sessionID: "ses_child_nobanner" }, output);
  assert.equal(
    output.parts.length,
    0,
    "a child session must not receive the forge banner (contract § 2 isolation)",
  );
});

test("chat.message skips the banner for a child session whose session.created event never reached this plugin instance", async () => {
  // Race/restart case: the child session predates this plugin's session.created
  // listener (e.g. plugin reloaded mid-run), so childSessions is empty and the
  // banner hook must fall back to client.session.get's parentID, exactly like
  // the idle/nudge path already does (forge.js:258-273, 285).
  const sessionID = "ses_child_predates_plugin";
  const { plugin } = await makePlugin({
    sessionGet: async ({ path }) => {
      assert.equal(path.id, sessionID);
      return { data: { id: sessionID, parentID: "ses_main_unseen_parent" } };
    },
  });
  const output = { message: {}, parts: [] };
  await plugin["chat.message"]({ sessionID }, output);
  assert.equal(
    output.parts.length,
    0,
    "a child session must not receive the banner even when session.created was missed",
  );
});

test("tool.execute.before blocks a destructive git command on the bash tool and throws", async () => {
  const { plugin } = await makePlugin();
  await assert.rejects(
    () =>
      plugin["tool.execute.before"](
        { tool: "bash", sessionID: "ses_main_guard" },
        { args: { command: "git reset --hard" } },
      ),
    /git/i,
    "a blocked git command must throw and abort the tool call",
  );
});

test("tool.execute.before allows a non-destructive git command on the bash tool", async () => {
  const { plugin } = await makePlugin();
  await assert.doesNotReject(() =>
    plugin["tool.execute.before"](
      { tool: "bash", sessionID: "ses_main_guard_allow" },
      { args: { command: "git status" } },
    ),
  );
});

test("tool.execute.before ignores non-bash tools even with a destructive-looking command", async () => {
  const { plugin } = await makePlugin();
  await assert.doesNotReject(() =>
    plugin["tool.execute.before"](
      { tool: "edit", sessionID: "ses_main_guard_nonbash" },
      { args: { command: "git reset --hard" } },
    ),
  );
});

test("nudges an idle changed main session exactly once", async () => {
  const { plugin, promptCalls } = await makePlugin();
  const sessionID = "ses_main_nudge_once";
  await plugin["tool.execute.after"]({ sessionID, tool: "edit" }, {});
  await plugin.event({ event: { type: "session.idle", properties: { sessionID } } });
  assert.equal(promptCalls.length, 1, "expected exactly one nudge after the first idle following a change");

  await plugin.event({ event: { type: "session.idle", properties: { sessionID } } });
  assert.equal(promptCalls.length, 1, "a second idle for the same session must not re-nudge");
});

test("does not nudge an idle session with no recorded change", async () => {
  const { plugin, promptCalls } = await makePlugin();
  await plugin.event({
    event: { type: "session.idle", properties: { sessionID: "ses_main_unchanged" } },
  });
  assert.equal(promptCalls.length, 0, "an unchanged session must never be nudged");
});

test("child sessions are never nudged even after a change", async () => {
  const { plugin, promptCalls } = await makePlugin();
  await registerChild(plugin, { childID: "ses_child_nonudge", parentID: "ses_main_parent2" });
  await plugin["tool.execute.after"]({ sessionID: "ses_child_nonudge", tool: "write" }, {});
  await plugin.event({
    event: { type: "session.idle", properties: { sessionID: "ses_child_nonudge" } },
  });
  assert.equal(promptCalls.length, 0, "a child session must never receive the idle nudge");
});

test("banner carries no drift nag when the skills stamp matches FORGE_VERSION", async () => {
  const { plugin } = await makePlugin({ stampContent: FORGE_VERSION });
  const output = { message: {}, parts: [] };
  await plugin["chat.message"]({ sessionID: "ses_main_stamp_match" }, output);
  const bannerText = output.parts[0].text ?? output.parts[0];
  assert.doesNotMatch(bannerText, /disagree/i, "a matching stamp must not produce a drift nag");
});

test("banner carries a drift nag when the skills stamp differs from FORGE_VERSION", async () => {
  const { plugin } = await makePlugin({ stampContent: "0.0.1" });
  const output = { message: {}, parts: [] };
  await plugin["chat.message"]({ sessionID: "ses_main_stamp_diff" }, output);
  const bannerText = output.parts[0].text ?? output.parts[0];
  assert.match(bannerText, /disagree/i, "a differing stamp must produce a drift nag");
});

test("stampNag truth table", () => {
  assert.equal(stampNag("2.1.0", "2.1.0"), null, "matching stamps: no nag");
  assert.match(stampNag("2.1.0", "2.0.0"), /re-run the install paste/, "differing stamps: nag");
  assert.match(stampNag("2.1.0", null), /re-run the install paste/, "missing stamp: nag");
  assert.match(stampNag("2.1.0", undefined), /re-run the install paste/, "undefined stamp: nag");
});
