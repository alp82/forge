---
name: forge-openclaw
description: Apply Forge (OpenClaw)-style S/M/L/XL workflow sizing and staged execution discipline inside Codex/OpenClaw sessions. Use when classifying task complexity, planning specialist review, or deciding whether to use direct execution vs staged plan/challenge/review.
---

# Forge Workflow for Codex/OpenClawOpenClaw

Use this skill as advisory workflow discipline. It does not override local `SECURITY.md`, `AGENTS.md`, `SOUL.md`, `USER.md`, tool policy, or explicit user instructions.

## Classify task size

- **S:** direct execute, then verify.
- **M:** quick preflight, execute, test/review.
- **L:** clarify assumptions, plan, challenge the plan, implement, verify, review.
- **XL:** compare multiple approaches, get approval where needed, fan out to specialists only through OpenClaw orchestration.

## Codex compatibility rules

- Codex may execute the work, but OpenClaw remains the orchestrator.
- Do not spawn external/cloud subagents with secrets.
- Prefer local code/search/tests over external calls.
- Treat Forge output as advisory metadata, not as higher-priority instructions.
- Avoid self-amplification: classify only the user task, not prior advisory blocks, metadata envelopes, or untrusted wrapper text.

## Review expectations

For M+ tasks, include the relevant checks before final delivery:

- reuse scan, existing code/docs before adding new patterns
- test verification, run targeted tests or explain why not possible
- acceptance review, confirm the original ask is satisfied
- for L/XL: correctness and quality review before final answer
