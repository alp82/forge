avoid full sentences if they dont carry meaning:
* symbols and state transitions
* simple defined language
* no fillers, no verbosity
* don't narrate yourself (e.g. "Let me scope the diff, then run a proportionate review.")

avoid: "This build carries #needs-tests, so the implementer stays locked behind the TDD gate until the red tests are written and validated."
better example: "#needs-test ▶ start writing tests"

avoid: "Both gates now clear — TDD (tests-ready) and plan (plan-approved). The implementer unlocks.
        Both locks released → ▶ code-implementer (builds the frontmatter + doctrine + docs, regenerates the catalog, turns the 12 red tests green)."
better example: "#plan-approved + #test-ready ▶ starting code implementation"

avoid: "This Stop-hook firing is a transient mid-implementation snapshot — the drift failure (test_catalog_no_drift_from_committed: "regenerate after...") shows the implementer has started editing frontmatter but hasn't regenerated catalog.json yet. It's still running in the background; the working tree is simply caught mid-write, which is the safe, expected state for a backgrounded side-effecting stage."
better example: "stop hook ignored (implementation ongoing)"

not bad already: "#code-written + @diff now live → the End Review wave composes."
better example: "#code-written + @diff ▶ start reviews"

---

test failed stop hooks shouldnt run before implementation
* if we have some extra logic to deal with ignoring that - it needs to be removed

---

opus fallback if fable is not available
* review fable effort levels

---

question asking is bad
* pros and cons
* simple language
* visuals
* extra resources + context if needed

---

call codex from claude

---

improve
    https://github.com/shadcn/improve
    https://www.reddit.com/r/ClaudeCode/comments/1u37glf/if_you_do_one_thing_with_fable_5_access_do_this/

---

agnostic plugin
    https://www.ap-sdk.dev/docs/porting/claude

---

linting & testing
    https://x.com/fortysevenfx/status/2065671297980420313
    https://v1.evalite.dev

---

mdx: visual plan & recap
    https://github.com/BuilderIO/skills/tree/main/skills/visual-plan
    https://github.com/BuilderIO/skills/tree/main/skills/visual-recap

---

river smaller footprint. goal: identify context overload and use less.
subagents to the rescue.
main orchestrator as lean as possible without quality decrease

---

SOUL.md continuation

---

image generation

---

video generation

---

remove git hook

---

reviewer-calibration harness: run a reviewer N times over a fixture set of diffs, report finding-rate + variance, to check a criteria change cut noise without dropping real findings (measure variance on ambiguous cases, never N=1).

---

experiment/judge optimization loop: define a metric (scalar or LLM-judge rubric), generate N prompt/code variants, score over fixtures, keep the winner; for tuning alp-river's own agent prompts against labeled fixtures.

---
