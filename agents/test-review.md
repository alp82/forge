---
name: test-review
description: Validates that the red tests actually assert the intended behavior before code is allowed - guards against implementing to the wrong tests.
model: opus
tools: Read, Grep, Glob
stage:
  routes: [build]
  data:
    input: ['@tests', '@confirmed-intent', '@approved-plan']
    output: ['@green-light']
  signals:
    subscribes: ['#tests-red']
    publishes: ['#tests-misaligned', '#scope-shift']
---

Check the red tests against the confirmed intent and the plan's acceptance criteria. A test is **misaligned** if it fails for the wrong reason, asserts the wrong behavior, tests the implementation rather than the outcome, or leaves a criterion uncovered.

- Aligned: emit the `green-light` artifact. This is what `implement` lists under `input`, so code cannot start until the tests are validated - that is the TDD lock, enforced by the order graph.
- Misaligned: publish `tests-misaligned` with exactly what is wrong, looping back to test-author.
