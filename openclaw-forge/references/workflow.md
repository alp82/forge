# OpenClaw Forge Workflow Reference

This is an OpenClaw adaptation of OpenClaw Forge's staged agent refinement pattern.

## Tier heuristics

### S
- One direct operation.
- Low ambiguity.
- Low risk.
- Easy rollback.
- No specialist review needed.

### M
- Multiple steps or files.
- Some uncertainty, but no major product/business decision.
- Verification matters.
- A short preflight prevents rework.

### L
- Ambiguous requirements.
- High-value code or ops workflow.
- Financial, security, property, customer, or external-system impact.
- Needs plan/challenge and specialist review.

### XL
- Architectural or multi-system.
- Requires sequencing across agents/services/repos.
- Wrong direction is expensive.
- Needs approach selection before implementation.

## Suggested specialist roles

- `classifier`: assign S/M/L/XL and explain gates.
- `researcher`: local docs plus web where needed.
- `reuse-scanner`: find existing scripts/workflows/code.
- `health-checker`: identify fragility and cleanup targets.
- `planner`: write implementation plan.
- `plan-challenger`: adversarially review plan.
- `implementer`: execute approved plan.
- `test-verifier`: run tests/checks.
- `correctness-reviewer`: catch broken logic and edge cases.
- `quality-reviewer`: catch bloat, duplication, bad abstractions.
- `security-reviewer`: auth, permissions, secrets, injection, data exposure.
- `performance-reviewer`: databases, hot paths, expensive loops.
- `acceptance-reviewer`: compare result to user-observable outcome.

## OpenClaw integration targets

1. Skill: teaches the operating pattern.
2. Sage Router: emits workflow tier metadata alongside routing intent.
3. Plugin: enforces classification, fan-out, workflow state, and review gates.

## Backward-edge budget

For L/XL, allow at most two backward edges before surfacing state:

- challenge rejects plan -> replan or reinterview;
- implementation reveals constraint -> patch plan/replan;
- clarify materially shifts scope -> reclassify.

Clarification loops inside a step are not backward edges.

## Output contract

For M+ final summaries, include:

- built/changed;
- files touched;
- checks run and results;
- review gates passed/failed;
- remaining risks or decisions.
