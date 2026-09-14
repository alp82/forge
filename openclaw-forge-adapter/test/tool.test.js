import test from "node:test";
import assert from "node:assert/strict";
import { createClassifyTool } from "../tool.js";

test("classifier tool uses OpenClaw execute signature", async () => {
  const tool = createClassifyTool();
  const result = await tool.execute("call-1", {
    text: "Design a plugin architecture with security review and tests",
  });

  assert.equal(result.content[0].type, "text");
  assert.ok(["L", "XL"].includes(result.details.tier));
  assert.equal(JSON.parse(result.content[0].text).tier, result.details.tier);
});
