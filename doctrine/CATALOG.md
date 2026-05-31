# Stage Catalog

The catalog is the machine-readable index of workflow **stages**. Each stage is a
composable unit declared in its agent's frontmatter; `gen-catalog.py` compiles every
`agents/*.md` `stage:` block into `generated/catalog.json`, which the deterministic
router reads to assemble a route per task.

Foundation note: this is built alongside the current pipeline and does not yet drive
it. Wiring the router into the live workflow is migration step 3 (Swap).

## Two graphs over one stage

Every stage plays two roles:

- **data** (`input` / `output`) - the ORDER graph. A precedence DAG: a stage cannot
  run until every `input` artifact exists. `input` is **AND** (need all). This is the
  one rule never bent.
- **signals** (`subscribes` / `publishes`) - the MEMBERSHIP graph. Pub/sub: a stage
  joins the route when **any** signal it `subscribes` to is live. `subscribes` is
  **OR**. The route grows when one stage publishes a signal another subscribes to.

Sigils mark a value's type, and you author them in frontmatter: `@` required artifact,
`?` optional artifact, `#` signal. `gen-catalog.py` strips them - splitting `input` into
required/optional - and stores bare names, so the catalog and router never see a sigil.
Renders re-apply `@`/`#` for legibility. The tag is the value's type, constant across
stages; direction is positional.

## Frontmatter schema

Add a `stage:` block to an agent's YAML frontmatter. Values carry sigils, YAML-quoted
because `@`/`?`/`#` are reserved at the start of a scalar:

```yaml
---
name: security-reviewer
description: ...
model: opus
tools: ...
stage:
  routes: [build, spike]            # subset of build/spike/talk - MANDATORY
  data:
    input: ['@diff']                # @ required, ? optional (e.g. '?reuse-map')
    output: ['@findings']
  signals:
    subscribes: ['#auth-surface', '#secrets', '#perms-change']
    publishes: ['#findings:security', '#scope-shift']
  guard: sticky
---
```

- **Stage name** = the agent's `name:`.
- **`routes` is mandatory** - the subset of paths (`build`/`spike`/`talk`) the stage may run
  on. Multi-path is normal (`triage: [build, spike, talk]`, `reuse-scanner: [build, talk]`,
  `correctness-reviewer: [build, spike]`). The router drops a triggered stage whose `routes`
  exclude the live path; `gen-catalog` errors loudly if a stage omits `routes` or names a
  path outside `build`/`spike`/`talk`.
- **Sigils:** `@` = required artifact, `?` = optional artifact (inline in `input`, no
  separate field), `#` = signal. Quote them (`'@diff'`, `'?reuse-map'`, `'#code-written'`).
  An optional input orders its stage after the producer when that producer is in the route,
  and never causes a drop when absent.
- `signals.publishes` must include `#scope-shift` - every stage self-reports premise breaks.
- `guard: sticky` only on safety stages (once triggered, never auto-dropped). Omit otherwise.

## Signal naming

- lowercase-kebab topics: `auth-surface`, `code-written`, `plan-ready`.
- families take a `:qualifier`: `findings:security`, `missing-infra:email`, `risk:auth`,
  `code-changed:auth`. The router matches on the full topic.
- path topics: `build`, `spike`, `talk` (published by `triage`, exactly one per turn). A
  bug is `build` plus a `bug` signal, not a separate path.
- `scope-shift` is reserved and mandatory on every stage.

## Generation

`gen-catalog.py` runs as a `PostToolUse(Edit|Write)` hook, regenerating
`generated/catalog.json` whenever an `agents/*.md` file changes. Run it manually with
`python3 hooks/gen-catalog.py`.

## Non-route agents

Command-only agents carry no `stage:` block on purpose - `setup-agent` (the
`/alp-river:setup` command) is invoked directly, not composed into a route, so the
generator skips it. That absence is intentional, not a missing contract.
