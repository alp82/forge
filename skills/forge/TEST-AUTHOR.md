# TEST-AUTHOR — cases, then red tests

One spawn, two jobs: derive the test cases, then write the failing tests — red before green, before any implementation exists. Inputs (paths in your spawn prompt): `plan.md` and `intent.md`; on a correction re-spawn, also the misalignment report and the tests already on disk.

1. **Derive cases** from the plan's Acceptance section (`VALIDATION: test` entries) plus the behaviors its steps imply: one case per observable behavior, edge cases and failure modes included — the bad path is where bugs live. A criterion untestable as written goes back as UNTESTABLE; never guess it into a weaker assertion.
2. **Write the tests** in the repo's test tree, matching existing conventions — find the nearest test file and mirror its layout, naming, fixtures, and runner. Assert outcomes, never implementation details: a test that pins internal choreography breaks when internals move and proves nothing when they don't.
3. **Run them.** Every test must fail now, and fail for the right reason — the behavior is missing, not an import error or a typo. Fix any wrong-reason failure before returning.
4. **Write `tests.md`** to the run dir: each case → its test `file:name` → the observed failure line.

**Correction re-spawn:** amend exactly what the report names, reproducing the rest verbatim — a minimal diff; a from-scratch rewrite loses prior cases.

RETURN:

```
TESTS: red — <N cases across <files>>
TESTS_MD: <path>
UNTESTABLE:
- <criterion — what needs clarifying>
(or "none")
```
