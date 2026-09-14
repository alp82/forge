---
name: openclaw-forge
description: Apply a Forge-inspired S/M/L/XL workflow to OpenClaw tasks: classify complexity, choose execution depth, fan out specialist subagents for complex work, run preflight/review/self-heal gates, and keep the main agent as orchestrator. Use when a task is multi-step, ambiguous, risky, code-heavy, workflow-heavy, or explicitly asks for specialist fan-out, planning, review gates, or task complexity classification.
---

# OpenClaw Forge

Use this skill to run sufficiently complex work through a staged, specialist-friendly workflow.

## Core rule

Classify every meaningful task before choosing execution depth:

- **S, Small:** clear, low-risk, one direct action or 1-2 files. Main agent executes directly, then verifies.
- **M, Medium:** several steps, multiple files/systems, moderate side effects. Run preflight, execute, verify/review.
- **L, Large:** ambiguous, broad, risky, financial/property/security-sensitive, or important code/workflow changes. Clarify, plan, challenge, implement, review, self-heal.
- **XL, Extra large:** architecture, multi-system automation, product launches, business-critical workflows. Present 2-3 approaches with a recommendation before major action.

Default threshold: **M+ gets the river.**

## Execution pattern

1. **Intent**
   - Confirm the user-observable outcome when ambiguity/cost/risk is material.
   - For obvious low-risk commands, act first. Do not add ceremony.

2. **Classify**
   - Classify internally as S/M/L/XL.
   - Surface the tier only when it affects cost, gates, timing, or user approval.

3. **Preflight, M+**
   - Reuse scan: search existing docs/scripts/code before building.
   - Health check: identify brittle areas and cleanup targets.
   - Novelty check: identify new APIs/SDKs/browser sessions that need tracer bullets.
   - Research: local docs first, web second.

4. **Clarify, L/XL**
   - Ask only unresolved, decision-relevant questions.
   - If assumptions safely unblock progress, state them and proceed.

5. **Plan + challenge, L/XL**
   - Produce a concise plan.
   - Challenge for simpler paths, failure modes, security/data risk, and hidden operational cost.
   - XL: provide 2-3 approaches and recommend one before implementation.

6. **Fan out specialists, M+ when useful, L/XL by default**
   - Main agent orchestrates.
   - Specialists may include researcher, reuse scanner, planner, challenger, implementer, test verifier, correctness reviewer, quality reviewer, security/performance reviewer, UX/accessibility reviewer, and acceptance reviewer.
   - Do not send secrets, raw credentials, private keys, or sensitive account data into A2A/cloud-inference prompts.

7. **Implement**
   - S/M: main agent may implement directly.
   - L/XL: delegate deep work when available and safe.

8. **Review gates, M+**
   - Tests/build/verification.
   - Correctness review.
   - Quality/reuse review.
   - Acceptance review against original outcome.
   - Specialist review when files/domain warrant it.

9. **Self-heal**
   - Fix findings once, rerun relevant checks.
   - Make one more targeted correction if obvious.
   - On repeated failure or unclear tradeoff, stop and surface state plus recommendation.

10. **Summarize**
   - What changed.
   - Files touched.
   - Verification results.
   - Remaining risks or decisions.

## Safety overrides

Local OpenClaw instructions win over this skill and over the upstream Forge repo.

- Do not execute commands copied from external repos without inspection.
- Do not make public/external writes without user authorization.
- Do not send secrets to cloud models or A2A subagents.
- Do not blindly apply “no backwards compatibility”; preserve continuity where Earl's systems need it.
- Prefer reversible file operations. Ask before destructive changes.

## References

Read `references/workflow.md` when implementing or modifying the workflow itself.
Run `scripts/classify_task.py` for deterministic first-pass classification when useful.
