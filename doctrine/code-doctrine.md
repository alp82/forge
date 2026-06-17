## Code Doctrine

Bias every plan, implementation, and review toward simple, local, pure-where-possible code with explicit dependencies and strong types.

**Lean toward**
- Simplicity over cleverness. The shortest readable solution wins.
- Locality - code that changes together lives together; logic stays close to the data and call site it serves.
- Pure functions and explicit data flow. Push side effects to the edges; keep the core a transformation from inputs to outputs.
- Idempotent read-modify-write at the side-effecting edge. Check the current state before writing, so a step that re-runs over work already on disk no-ops what is done and only finishes the remainder.
- Modularization with semantic cohesion - one module names one thing; what it owns is what its name promises.
- Explicit dependencies and strong types - what a function needs arrives as a parameter or import, not as ambient state; types document intent and catch drift.

**Push back on**
- Layers, wrappers, abstractions, or seams added "for flexibility" without a concrete second use case.
- Configuration knobs no caller sets and feature flags no path reads.
- Hidden state - module-level mutables, singletons, ambient context the signature doesn't disclose.
- Defensive code at trust boundaries the framework or caller already guarantees.
- Generic-by-default - parameterizing or polymorphizing before a second concrete case exists.
- Comments that narrate what the code obviously does instead of explaining why.

These apply across languages. When the doctrine implies a structural property the language doesn't enforce natively, name a community-standard tool that enforces it (`mypy`/`ruff` for Python, `tsc` for TypeScript, `clippy` for Rust) only when one exists; if the stack has no such tool, don't name one - the finding's ACTION_NEEDED reads as a design pointer.

**Floor - never simplify away**

The lean-toward bias stops at a floor: defensive code at a boundary nothing else guarantees is a wall, not bloat. Never simplify away:

- Trust-boundary input validation - the check that stands between untrusted input and the system.
- Data-loss-preventing error handling - the path that keeps a failure from destroying work already on disk.
- Security - authn/authz, secret handling, injection defenses.
- Accessibility - the affordances that keep the surface usable for everyone.
- Hardware and real-world calibration - the constants and conversions that match physical reality.
- A runnable check behind non-trivial logic - non-trivial logic leaves ONE runnable check behind (the smallest thing that fails if the logic breaks).

These are the load-bearing pieces. Removing one is not simplification; it is taking out a wall.

**Boy-scout clause** (extends "Leave touched code better than you found it")

A naked `TODO`/`FIXME`/`HACK`/`XXX` in the area being touched is fixed NOW, not deferred - if you are editing around it, you own it. Skip the `_TODO:_` template sentinel (it marks an unfilled doc slot, not a code defect), and skip markers that are obviously test data or documentation-about-markers (a string in a test fixture, a sentence explaining what a marker means). This never licenses work outside the area being touched - an unrelated marker elsewhere in the file or repo gets its own task. The "No TODOs, placeholders, or incomplete implementations" rule stays absolute: you never ADD a new one.
