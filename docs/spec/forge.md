# forge — evolution spec

The single assembled record of every decision locked on the wayfinder map
[Evolve alp-river into a public, skill-first workflow toolkit](https://github.com/alp82/alp-river/issues/4).
Each section gists a decision and links the ticket that holds its full detail; where later
tickets amended earlier ones, this document states the **reconciled** result. The successor
(execution) map builds exactly what this document says — deviations discovered during the
build go back to the spec first.

Sources: tickets [#8](https://github.com/alp82/alp-river/issues/8) (capability set),
[#9](https://github.com/alp82/alp-river/issues/9) (architecture),
[#10](https://github.com/alp82/alp-river/issues/10) (name),
[#11](https://github.com/alp82/alp-river/issues/11) (companionship),
[#12](https://github.com/alp82/alp-river/issues/12) (workers),
[#13](https://github.com/alp82/alp-river/issues/13) (landing page),
[#15](https://github.com/alp82/alp-river/issues/15) (lens roster),
[#16](https://github.com/alp82/alp-river/issues/16) (migration),
[#17](https://github.com/alp82/alp-river/issues/17) (name due diligence),
[#18](https://github.com/alp82/alp-river/issues/18) (demo tooling),
plus the research corpus in `docs/research/`. The final coherence pass is
[#14](https://github.com/alp82/alp-river/issues/14)'s resolution.

## 1. Identity

**The name is forge** ([#10](https://github.com/alp82/alp-river/issues/10), confirmed with
spelling `forge` by [#17](https://github.com/alp82/alp-river/issues/17)).

- Repo: `alp82/alp-river` → `alp82/forge` (GitHub redirects old URLs).
- Plugin entry: `forge`. Marketplace name stays `alperortac`.
- Public command surface, bare names, no plugin prefix: **`/forge`** (entry verb, replaces
  `/go`), **`/crossfire`** (review wave, renamed from `/review` to avoid Claude Code's
  builtin), **`/setup-forge`**.
- Guardrails from due diligence: never ship a bare `forge` executable on PATH (ForgeCode,
  a 7.4k-star AI coding CLI, owns that invocation); don't budget on search findability —
  the Laravel Forge / SourceForge crowding is accepted as cosmetic since nothing collides
  in the `/forge` install surface.

## 2. Capability set

Decided by evidence roll call ([#8](https://github.com/alp82/alp-river/issues/8)):
evidence earns a slot, absence defaults to cut, rescue requires a forward-looking
public-toolkit case. All 42 prior capabilities accounted for.

**Paths.** Code is the only route. talk dissolves into plain conversation; sketch and
system are cut whole.

**Six stages kept** (amended post-2.0: test-author and test-review merged into the one
`tests` stage — two spawns, one stage, mirroring challenge's challenger + worker pair):

| Stage | Notes |
|---|---|
| triage | expanded into the detection quartet: unknowns → interview, unproven externals → prototype, missing knowledge → research, bug-framing → diagnose; plus sizing. Always-on detection is the intended USP. |
| planner | absorbs the Scout band's questions (reuse scan, health read, flag unknowns for a prototype detour) |
| challenger | kept untouched — strongest evidence in the corpus |
| implementer | kept |
| tests | one stage, two spawns: test-author (absorbs test-plan: derive cases + write red tests) then test-review as its gate — the false-green catch nobody else in the field has, kept an independent spawn |
| fixer | kept |

**Review wave + fixer** kept as a capability; the lens roster is § 4.

**Four primitives** — interview, prototype, research, diagnose — replace clarifier, the
six prototypers, prototype-identifier, sketch-build, researcher, and code-investigator.
They ship as **internal briefs**, not skills (§ 3;
amendment from [#11](https://github.com/alp82/alp-river/issues/11)).

**25 agents cut**, named in [#8](https://github.com/alp82/alp-river/issues/8)'s roll call.
Gating survives as prose stances (confirm-before-remote, confirm-before-destruction)
backed by the deterministic hooks — not as agents.

**Doctrine cut:** the 76-signal vocabulary, the 40-slot stage-contract grammar,
multi-plan, Shipping + Locks, all system-route doctrine. Surviving prose style: terse
status lines, the confirm stances, reviewer confidence tagging.

## 3. Architecture

Decided in [#9](https://github.com/alp82/alp-river/issues/9), amended by
[#11](https://github.com/alp82/alp-river/issues/11); the reconciled shape:

**Skills all the way down.** No `agents/*.md` definitions survive. Each stage's brief is a
plain markdown file; the orchestrator spawns generic harness subagents (`general-purpose`,
`Explore` for read-only work) with a one-line contract: *"Read `<path>` and follow it
against `<input paths>`."* Model choice rides the spawn call's `model` parameter, named in
prose. No paraphrase surface, no catalog to sync.

**Router: prose flow + convergence gate.** `skills/forge/SKILL.md` is the router — a
prose flow document: triage detours declared as conditions, then plan → challenge →
implement with tests → review wave → fix. `route.py` dies as a router. Its one
non-replaceable duty — knowing the session isn't done — survives as enforcement:
mark-code-change stamps edits, and a review-owed Stop gate blocks completion while code
changed but tests/review never ran.

**Two tiers, not three.** User-invoked skills (`disable-model-invocation: true`):
`/forge` and `/crossfire` public, `/audit` and `/reflect` repo-internal (this repo's own
`.claude/skills/`, outside the plugin payload). The model-invoked tier is **empty** —
[#11](https://github.com/alp82/alp-river/issues/11) demoted the four primitives to
internal briefs with zero namespace footprint. Stage briefs, primitive briefs, and lens
briefs are sibling files: zero names, zero context cost.

**Composition contract: file-carried artifacts, path-passing spawns.** Every stage output
a later stage consumes is a markdown file in a gitignored per-run working directory
(`.forge/<slug>/`): `plan.md`, `challenge.md`, `findings.md`, … Spawn prompts pass paths,
never re-pasted content; the conversation carries only gists and terse status lines. Runs
are compaction-proof: a fresh respawn needs only paths. Kickbacks are declared in the
briefs as explicit condition + successor by name.

**Layout** (locked in the [#14](https://github.com/alp82/alp-river/issues/14) coherence
pass — primitives and WORKER.md flat beside the stage briefs):

```
skills/
  forge/
    SKILL.md          ← router (prose flow)
    TRIAGE.md  PLANNER.md  CHALLENGER.md
    IMPLEMENTER.md  TEST-AUTHOR.md
    TEST-REVIEW.md  FIXER.md
    INTERVIEW.md  PROTOTYPE.md
    RESEARCH.md  DIAGNOSE.md
    WORKER.md         ← forwarder brief (§ 5); crossfire reaches it as ../forge/WORKER.md
  crossfire/
    SKILL.md          ← wave + ad-hoc review; forge's wave reaches lenses as ../crossfire/*.md
    CORRECTNESS.md  ACCEPTANCE.md  SIMPLICITY.md  SHAPE.md  CONVENTIONS.md
    UI.md  SECURITY.md  PERFORMANCE.md      ← conditional (§ 4)
  setup/
    SKILL.md          ← /setup-forge
hooks/                ← 6 survivors + hooks.json (§ 7)
.claude-plugin/       ← plugin.json, marketplace.json (distribution only)
```

**Word budgets as law:** each SKILL.md and brief fits one read — ~865-word target, 2,000
hard ceiling. `WORKFLOW.md` and `doctrine/` die as monoliths; content surviving the no-op
sentence test migrates into the skill files and nowhere else.

## 4. Crossfire lens roster

From per-lens analysis ([#15](https://github.com/alp82/alp-river/issues/15)): 11 lens
definitions → 8 briefs.

- **Standing (5):** correctness, acceptance (absorbs test-gap's coverage duty),
  simplicity, shape, conventions.
- **Conditional (3):** UI (the three ui-touched lenses — accessibility, ux,
  design-consistency — merged into one, runs when the diff touches UI), security,
  performance.
- The correctness × security overlap is deliberately kept — it is the only injection
  coverage on unflagged builds.

Reviewer confidence tagging rides with the wave. `/crossfire` doubles as the ad-hoc
file-review verb, reusing the same lens briefs.

## 5. Worker dispatch

Model-agnostic second opinions ([#12](https://github.com/alp82/alp-river/issues/12)):

1. **Judgment only.** Workers never write code; every worker run is read-only. Promoting
   a worker to a writing role later is additive, not a redesign.
2. **Generic seam.** A worker is any CLI that runs a prompt non-interactively.
   `WORKER.md` ships a static known-workers table — command templates, prompt-passing
   convention, runtime controls as flags never task text (`codex exec --sandbox read-only
   --json`, `--effort`/`--model`). Codex is the reference entry; gemini and opencode follow.
3. **Full auto-detect.** PATH probe in table order (codex → gemini → opencode); installing
   a CLI is the opt-in. One noted line per run ("worker: codex" / "no worker detected —
   single-model judgment"). Escape hatches: repo-pinned custom template; `worker: none` in
   `docs/agents/` stands detection down.
4. **Thin forwarder.** A generic subagent spawned in parallel with the same-model judge:
   read `WORKER.md`, run exactly the table's command in one Bash call, capture stdout
   verbatim. No-substitute rule: on failure write `WORKER FAILED: <exit code / stderr
   tail>` — never a generated stand-in. Neither verdict sees the other before both are
   written.
5. **Peer artifacts.** Output lands as `challenge-worker.md` / `findings-worker.md`
   beside the same-model artifacts; downstream consumers read one more file by path.
6. **Failure visible, non-blocking.** Dead worker → failure recorded, run proceeds on
   same-model judgment.
7. **Two call sites.** Challenger (second voice on the plan) and crossfire (one more lens
   over the diff). `challenge-only` enablement is a cheap later extension.
8. **Cross-vendor stop gate: out.** Forge's stop hooks stay deterministic and ~2 s;
   OpenAI's codex plugin composes alongside unmodified.

## 6. Companionship contract

Forge standalone and paired with wayfinder ([#11](https://github.com/alp82/alp-river/issues/11)):

- **Downward handoff:** the merge point is `/forge <ticket>`. Forge speaks generic
  tracker-ticket — when a request is or names a ticket, forge reads it as the request and
  posts the resolution back before closing. Wayfinder composes for free as "a thing that
  produces tickets."
- **Return path: context pointers, never content.** Resolution comment shape: verdict
  gist, pointer to the change's durable home (commit / PR), explicit deviations. Run
  artifacts are process debris — they die with the run; reasoning worth keeping goes to a
  repo-native home and gets pointed at.
- **Standalone floor:** the core loop needs no tracker; the ticket contract lies dormant
  without one. When a tracker exists, both toolkits read the same
  `docs/agents/issue-tracker.md`; `/setup-forge` writes it only if absent.
- **Upward handoff:** a multi-session request with open decisions gets the recommendation
  to chart a map with "a mapping skill such as /wayfinder" when available; otherwise the
  interview brief carves the largest one-session slice and names the remainder.

## 7. Distribution, hooks, and sync

**Plugin residue: 6 hooks + a setup skill.** The plugin format is a distribution channel,
nothing more.

- **Hooks:** verify-tests, verify-build, block-git-writes (measured earners),
  mark-code-change + the review-owed Stop gate (§ 3), and a minimal SessionStart injection
  — 3–4 lines: the entry rule ("code-modifying requests enter via /forge"), the flow-skill
  pointer, and the sync check below.
- **Cut:** user-context-injector, gen-catalog (dies with the agent-definition layer),
  route.py-as-router. **Evicted to personal settings:** auto-format, PermissionRequest
  notification.

**Skill install & sync** (locked in the [#14](https://github.com/alp82/alp-river/issues/14)
coherence pass — this amends [#10](https://github.com/alp82/alp-river/issues/10)/[#16](https://github.com/alp82/alp-river/issues/16)'s
plain copy): `/setup-forge` **symlinks** the bare skill names in `~/.claude/skills` to the
installed plugin's skill directories, so plugin updates propagate with zero re-run. Where
symlinks fail and a copy is made, the SessionStart hook compares the copy's stamped
version against the plugin version and prints a one-line "skills outdated — re-run
/setup-forge" nag. Bootstrap wrinkle, accepted and documented: `/setup-forge`'s first
invocation is necessarily plugin-prefixed; the bare names exist after it runs once.

**Setup scope:** per-repo config only — tracker conventions, `docs/agents/*.md` — plus
the skill install above. Per-repo facts, not doctrine.

## 8. Migration and versioning

The cutover ([#16](https://github.com/alp82/alp-river/issues/16)):

- **2.0.0, continuing the changelog.** No fresh 1.0; the entry names the lineage
  ("forge; previously alp-river").
- **Old surface removed outright** — the 4 commands and 41 agents go in the same commit
  that lands the skill-first shape. No deprecation release.
- **Rename mechanics:** repo renames in place (redirect keeps existing marketplace adds
  updating); marketplace name stays `alperortac`; the plugin entry becoming `forge` is the
  one hard identity break — installed plugins must be swapped.
- **Consumer migration, three steps** in the 2.0.0 changelog entry + a one-line README
  pointer (no MIGRATION.md unless steps outgrow a screenful):
  1. `/plugin uninstall alp-river`
  2. `/plugin install forge@alperortac`
  3. Run `/setup-forge`
- **Safety line:** tag the final alp-river commit before the rename.

## 9. Landing page and demos

Shape locked as merged variant E ([#13](https://github.com/alp82/alp-river/issues/13));
tooling from [#18](https://github.com/alp82/alp-river/issues/18).

- **Medium: both.** A full README carries the reference content (badges, tagline,
  install, stage table, three closers: Stop-gate hook, "it's just markdown", tracker
  support) and stands alone. A GitHub Pages site is the same spine with transcript acts
  and an interactive system map layered in. One source of copy, two renderings.
- **Story: reference-first, evidence-carried.** No manifesto voice. Claims appear as
  shown transcript moments (challenger killing a plan, test-review catching false green,
  the crossfire wave); the architecture is exposed as an interactive map.
- **Demos, three:** full run ~90 s (hero, README + site) · per-stage micro-casts ~10 s
  (map panel, site only) · crossfire wave ~40 s (crossfire act, site only).
- **Tooling:** asciinema (asciicast v3) is the single recording source. One `.cast`
  drives both surfaces — interactive asciinema-player on the site, `agg`-rendered GIF in
  the README. Map-panel micro-clips are their own short casts (player has `startAt`, no
  end bound). Re-recording is scripted via an autocast-style playbook; byte-stable regen
  requires a deterministic replay stub. Prototype source: branch `prototype/landing-page`.

## 10. Portability

Decisions from the harness-agnostic map
([#31](https://github.com/alp82/forge/issues/31)); each entry links the ticket holding
its full detail.

**The spawn floor** ([#36](https://github.com/alp82/forge/issues/36)):

1. **Isolated spawn is a hard requirement — no single-context fallback.** To run forge, a
   harness MUST spawn a fresh, isolated agent context per stage; the contract defines no
   degraded one-context mode, and a CLI that can't spawn is not a forge target. The
   independence *is* the product: a challenger sharing the planner's context isn't loyal
   opposition, an author sharing the reviewer's context defeats the test check. All four
   surveyed harnesses clear this floor.
2. **Parallel fan-out is optional, adapter-declared.** The guarantees rest on
   independence, not wall-clock parallelism — "neither seeing the other's verdict" holds
   when an adapter runs an independent pair serially into separate contexts, provided it
   never feeds the first agent's output to the second. Briefs say "spawn independently —
   in parallel where the adapter supports it." Keeps gemini (sequential-only) a valid
   proof; parallelism is a speed optimization, not a correctness line.
3. **Model-selectable spawn is required.** Every brief names a model per spawn, so the
   floor includes choosing the model at spawn time. Model *diversity* (the worker running
   a genuinely different model per harness) is a separate, still-open question.

## 11. Successor map charter

**Destination.** forge 2.0.0 is shipped and public: the skill-first shape built, the repo
renamed, the migration path live, and the landing page with its three casts published.
Every ticket executes a decision recorded in this spec.

**Notes.**
- Execution override: this map carries execution — tickets are build slices, not
  decisions. The way is already charted; this map walks it.
- Tickets are worked as plain sessions (or the current alp-river 1.4.1 pipeline) until
  the cutover ticket lands — forge cannot build itself before it exists.
- The spec is law: a build discovery that contradicts it amends `docs/spec/forge.md`
  first, then proceeds.
- Word budgets bind: ~865-word target, 2,000 hard ceiling per skill/brief file.

**Tickets** (blocking edges in parentheses):

1. **Build the forge skill** — router SKILL.md + 7 stage briefs, migrated from the
   current agent definitions under the word budget. *(frontier)*
2. **Write the primitive briefs** — INTERVIEW, PROTOTYPE, RESEARCH, DIAGNOSE. *(frontier)*
3. **Write WORKER.md** — forwarder brief, known-workers table, codex reference recipe +
   both prompt recipes. *(frontier)*
4. **Build the crossfire skill** — SKILL.md + 8 lens briefs. *(frontier)*
5. **Port the hooks** — 6 survivors + hooks.json; delete the rest; evictions noted in
   the changelog. *(frontier)*
6. **Build /setup-forge** — symlink install + version-check fallback + tracker-doc
   writer. *(blocked by 1, 4)*
7. **Kill the monoliths** — migrate surviving WORKFLOW.md/doctrine content into the
   skill files; delete `agents/`, `commands/`, `doctrine/`, `WORKFLOW.md`. *(blocked by
   1, 2, 4)*
8. **Cutover release** — tag final alp-river commit, rename repo, plugin entry → forge,
   2.0.0 changelog with migration steps. *(blocked by 1–7)*
9. **Write the README** — the reference spine, standing alone. *(blocked by 8)*
10. **Record the three casts** — deterministic replay stub + autocast playbook + hero
    cast, micro-casts, crossfire cast. *(blocked by 8)*
11. **Build the Pages site** — same spine, transcript acts, interactive map, embedded
    players. *(blocked by 9, 10)*
