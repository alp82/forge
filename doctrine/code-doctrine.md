## Code Doctrine

Bias every plan, implementation, and review toward simple, local, pure-where-possible code with explicit dependencies and strong types.

**Lean toward**
- Simplicity over cleverness. The shortest readable solution wins.
- Locality - code that changes together lives together; logic stays close to the data and call site it serves.
- Pure functions and explicit data flow. Push side effects to the edges; keep the core a transformation from inputs to outputs.
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
