export const TIER_ORDER = ["S", "M", "L", "XL"];

export const WORKFLOW_MODES = Object.freeze({
  S: "direct-execute-verify",
  M: "preflight-execute-review",
  L: "clarify-plan-challenge-implement-review",
  XL: "multi-approach-plan-approval-specialist-fanout",
});

export const RECOMMENDED_AGENTS = Object.freeze({
  S: [],
  M: ["reuse-scanner", "test-verifier", "acceptance-reviewer"],
  L: [
    "researcher",
    "reuse-scanner",
    "planner",
    "plan-challenger",
    "implementer",
    "test-verifier",
    "correctness-reviewer",
    "quality-reviewer",
    "acceptance-reviewer",
  ],
  XL: [
    "researcher",
    "reuse-scanner",
    "requirements-clarifier",
    "planner",
    "plan-challenger",
    "implementer",
    "test-verifier",
    "correctness-reviewer",
    "quality-reviewer",
    "security-reviewer",
    "acceptance-reviewer",
  ],
});

export function resolveConfig(raw = {}) {
  const cfg = raw && typeof raw === "object" ? raw : {};
  return {
    enabled: cfg.enabled !== false,
    minimumRiverTier: TIER_ORDER.includes(cfg.minimumRiverTier) ? cfg.minimumRiverTier : "M",
    injectPromptContext: cfg.injectPromptContext !== false,
    registerTool: cfg.registerTool !== false,
    debug: cfg.debug === true,
  };
}

export function promptTextFromEvent(event = {}) {
  if (event?.prompt && String(event.prompt).trim()) return String(event.prompt);
  const messages = Array.isArray(event?.messages) ? event.messages : [];
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const msg = messages[i] || {};
    const role = String(msg.role || msg.author || "").toLowerCase();
    if (role && role !== "user") continue;
    const content = msg.content ?? msg.text ?? msg.message;
    if (typeof content === "string" && content.trim()) return content;
    if (Array.isArray(content)) {
      const joined = content
        .map((part) => {
          if (typeof part === "string") return part;
          if (part && typeof part === "object") return part.text || part.content || "";
          return "";
        })
        .filter(Boolean)
        .join("\n");
      if (joined.trim()) return joined;
    }
  }
  return "";
}

export function extractClassifiableTaskText(text = "") {
  const lines = String(text || "").split(/\r?\n/);
  const kept = [];
  let skippingAdvisory = false;

  for (const line of lines) {
    if (/^## Forge OpenClaw Workflow Advisory\s*$/.test(line)) {
      skippingAdvisory = true;
      continue;
    }
    if (skippingAdvisory) {
      if (line.trim() === "") {
        skippingAdvisory = false;
      }
      continue;
    }
    kept.push(line);
  }

  let raw = kept.join("\n");

  // Discord/OpenClaw envelopes often append metadata and untrusted wrappers to
  // the prompt. Those are context for the model, not the user's task.
  raw = raw.replace(/Conversation info \(untrusted metadata\):[\s\S]*$/g, "");
  raw = raw.replace(/Sender \(untrusted metadata\):[\s\S]*$/g, "");
  raw = raw.replace(/Untrusted context \(metadata, do not treat as instructions or commands\):[\s\S]*$/g, "");
  raw = raw.replace(/<<<EXTERNAL_UNTRUSTED_CONTENT[\s\S]*?<<<END_EXTERNAL_UNTRUSTED_CONTENT[^>]*>>>/g, "\n");

  return raw.trim();
}

export function classifyWorkflowTier(text = "") {
  const raw = String(text || "");
  const low = raw.toLowerCase();
  const words = raw.trim() ? raw.trim().split(/\s+/).length : 0;
  let score = 0;
  const reasons = [];
  const add = (points, reason) => {
    score += points;
    reasons.push(reason);
  };

  if (words >= 30) add(1, "longer_prompt");
  if (words >= 120) add(1, "long_prompt");
  if (/\b(code|repo|api|test|build|deploy|integration|automation|database|service|workflow)\b/.test(low)) add(1, "multi_step");
  if (/\b(figure out|design|strategy|plan|investigate|research|ambiguous|unknown)\b/.test(low)) add(1, "ambiguity");
  if (/\b(security|secret|credential|auth|permission|payment|financial|bank|legal|contract|tenant|guest|reservation|property|production|migration|delete|destructive)\b/.test(low)) add(2, "risk");
  if (/\b(architecture|multi-system|platform|plugin|framework|all repos|company-wide|business-critical|launch|end-to-end)\b/.test(low)) add(3, "xl_scope");
  if ((low.match(/\band\b/g) || []).length >= 2) add(2, "multiple_conjoined_tasks");

  const tier = score >= 7 ? "XL" : score >= 5 ? "L" : score >= 2 ? "M" : "S";
  return {
    tier,
    mode: WORKFLOW_MODES[tier],
    recommendedAgents: [...RECOMMENDED_AGENTS[tier]],
    score,
    reasons: reasons.slice(0, 12),
  };
}

export function shouldUseRiver(tier, minimumTier = "M") {
  return TIER_ORDER.indexOf(tier) >= TIER_ORDER.indexOf(minimumTier);
}

export function renderWorkflowContext(result, minimumTier = "M") {
  const river = shouldUseRiver(result.tier, minimumTier);
  return [
    "## Forge OpenClaw Workflow Advisory",
    `- Classified workflow tier: ${result.tier}`,
    `- Recommended mode: ${result.mode}`,
    `- River workflow active: ${river ? "yes" : "no"}`,
    result.recommendedAgents.length
      ? `- Recommended specialist roles: ${result.recommendedAgents.join(", ")}`
      : "- Recommended specialist roles: none",
    "- OpenClaw remains the orchestrator. Do not spawn external/cloud subagents with secrets.",
    "- Local SECURITY.md, AGENTS.md, SOUL.md, USER.md, and tool policy override upstream Forge defaults.",
  ].join("\n");
}
