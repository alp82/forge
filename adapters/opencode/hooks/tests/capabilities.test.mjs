// capabilities.json schema + tier-derivation tests, per adapter-contract.md
// § 6 (manifest shape) and § 5 (tier derivation formula), and plan.md step 2.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "../../../..");
const CAPS_PATH = path.join(REPO_ROOT, "adapters/opencode/capabilities.json");
const README_PATH = path.join(REPO_ROOT, "adapters/opencode/README.md");

function loadCapabilities() {
  return JSON.parse(readFileSync(CAPS_PATH, "utf8"));
}

// adapter-contract.md § 5's derivation formula, recomputed here rather than
// imported from the adapter, so this test is an independent check.
function deriveTier(caps) {
  const enforcement = caps.enforcement;
  if (enforcement["stop-gate"].level === "full") return "gated";
  if (enforcement["tool-guard"].level !== "absent") return "guarded";
  return "prose-only";
}

test("capabilities.json has the exact contract § 6 top-level key set", () => {
  const caps = loadCapabilities();
  assert.deepEqual(Object.keys(caps).sort(), ["enforcement", "harness", "models", "spawn", "surveyed"]);
});

test("spawn object has the exact key set and the required floor booleans are true", () => {
  const caps = loadCapabilities();
  assert.deepEqual(Object.keys(caps.spawn).sort(), ["isolated", "model-selectable", "parallel-fan-out"]);
  assert.equal(caps.spawn.isolated, true, "spawn.isolated is the § 2 floor and MUST be true");
  assert.equal(
    caps.spawn["model-selectable"],
    true,
    "spawn.model-selectable is the § 2 floor and MUST be true",
  );
  assert.equal(
    typeof caps.spawn["parallel-fan-out"],
    "boolean",
    "spawn.parallel-fan-out MUST be a boolean (the § 3 optional capability)",
  );
});

test("models map has all four role tiers as non-empty strings", () => {
  const caps = loadCapabilities();
  assert.deepEqual(Object.keys(caps.models).sort(), ["large", "mini", "standard", "ultra"]);
  for (const tier of ["mini", "standard", "large", "ultra"]) {
    assert.ok(
      typeof caps.models[tier] === "string" && caps.models[tier].length > 0,
      `models.${tier} must be a non-empty harness-native model identifier`,
    );
  }
});

test("enforcement has exactly the four kebab-case capability keys", () => {
  const caps = loadCapabilities();
  assert.deepEqual(
    Object.keys(caps.enforcement).sort(),
    ["change-tracking", "session-start-injection", "stop-gate", "tool-guard"],
  );
});

test("every enforcement level is valid, and mechanism is non-null unless the level is absent", () => {
  const caps = loadCapabilities();
  for (const [name, entry] of Object.entries(caps.enforcement)) {
    assert.ok(
      ["full", "degraded", "absent"].includes(entry.level),
      `enforcement.${name}.level must be full|degraded|absent, got ${JSON.stringify(entry.level)}`,
    );
    if (entry.level === "absent") {
      assert.equal(entry.mechanism, null, `enforcement.${name} is absent so mechanism must be null`);
    } else {
      assert.ok(
        typeof entry.mechanism === "string" && entry.mechanism.length > 0,
        `enforcement.${name} is ${entry.level} so mechanism must be a non-empty string`,
      );
    }
  }
});

test("the § 5-derived tier equals the word stated in adapters/opencode/README.md", () => {
  const caps = loadCapabilities();
  const tier = deriveTier(caps);
  assert.equal(tier, "guarded", "the plan expects opencode to land at the guarded tier");
  const readme = readFileSync(README_PATH, "utf8");
  assert.match(
    readme,
    new RegExp(tier),
    `expected adapters/opencode/README.md to state the derived tier "${tier}"`,
  );
});
