---
name: test-gap
description: Always-on coverage lens. After code is written, checks acceptance criteria for untested behavior and pulls test-author back for the gaps.
model: sonnet
tools: Read, Grep, Glob
stage:
  routes: [build]
  data:
    input: ['@diff']
    output: ['@findings']
  signals:
    subscribes: ['#needs-tests']
    publishes: ['#findings:test-gap', '#tests-missing', '#clean', '#scope-shift']
---

Compare the diff and its acceptance criteria against the tests that exist. For each behavior that is added or changed but not covered, publish `tests-missing:<criterion>` (pulling test-author back) and record a `findings:test-gap`.

If every changed behavior is covered, publish `clean` and nothing else. This lens is always on for code routes - missing tests are added along the way, not deferred.
