# Project Intent

Keep this to roughly one page. The agents read it on every judgment-call spawn - density matters more than completeness.

## Purpose

Alp River is a Claude Code plugin that adds a complexity-aware staged pipeline to every coding request. It sizes each task automatically and runs only the stages that fit, so small changes pass quickly and larger ones get clarification, planning, adversarial challenge, multi-angle review, and self-heal before landing.

## Primary users

Primary: developers using Claude Code on their own projects who want a disciplined, multi-stage workflow without hand-rolling it every time. They install Alp River once via `/plugin install`, then describe what they want (in plain text or via `/alp-river:go`); the pipeline scales depth to the task and pauses at well-defined seams for confirmation.

Secondary: workflow tinkerers who want to swap personas, override grades in natural language, or read the pipeline source to learn the contract.

## Success criteria

- Small/mechanical tasks (S) finish in one pass via the main agent with no clarification, planning, or review overhead.
- Larger tasks (M/L/XL) automatically gain the stages that fit their complexity - Scout, clarification, planning, adversarial challenge, broad and specialist review, self-heal.
- User stays in the loop only at the seams that matter: intent confirmation (every tier), clarifier questions (M/L/XL when ambiguity remains), design picker (UI multi-shape), plan selection (XL), after-plan stop (L/XL), after-diagnose stop (bug-framing). No other interruptions.
- Tier classification is overridable in natural language (`treat this as L`, `skip clarify`, `go straight to plan`) without reaching for a flag.
- Bug-shaped requests (stack traces, symptoms) automatically take a diagnose path - investigator first, then a continue/stop picker - rather than jumping to implementation.

## Out of scope

- Not a build tool, test runner, or scaffolder - Alp River orchestrates LLM stages; project-side build/test/format is whatever the consumer project already has.
- Does not own code-generation logic. Subagents call Claude Code's own Edit/Write/Bash tools; the plugin shapes the staging and review around those calls, it does not replace them.
- Not a plugin marketplace browser or installer UI - Claude Code's `/plugin` commands handle install and updates.
- Not a multi-user/team-coordination tool - the pipeline is one developer per Claude Code session; team conventions belong in the consumer's `docs/`.
- Not a substitute for project-context docs themselves. The plugin reads INTENT/STACK/GLOSSARY/ADRs from each consumer project; it doesn't generate the project's intent for them (though `/alp-river:setup` helps bootstrap the files).
