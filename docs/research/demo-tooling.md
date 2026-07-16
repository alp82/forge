# Demo tooling: recording and embedding the three casts

Research for [issue #18](https://github.com/alp82/alp-river/issues/18), resolving the demo-tooling
question left open by the landing-page decision in [issue #13](https://github.com/alp82/alp-river/issues/13).

**Question.** Variant E locked three demos:

- **Hero cast** — full run, ~90s, embedded in **both** the GitHub README and the GitHub Pages site.
- **Per-stage micro-casts** — ~10s each, inside the site's interactive system-map panel (**site only**).
- **Crossfire-wave cast** — ~40s, inside the site's crossfire act (**site only**).

What records them, and what embeds them on each surface, such that the casts stay **re-recordable
via a script / in CI** when the toolkit changes?

Each claim below is tagged **[verified]** (stated in an official doc, spec, or source repo — URL given)
or **[judgment]** (my inference or a general-platform fact not sourced from the tool's own docs).

---

## 1. What actually plays on each surface

### GitHub README — no JavaScript, sanitized HTML

GitHub renders READMEs through a sanitizer; `<script>`, `<iframe>`, and hand-written `<video>` tags
pointing at repo files are stripped. What survives:

| Format | Plays in README? | Notes |
|---|---|---|
| **Animated GIF** | Yes | Standard image markdown `![](demo.gif)`; autoplays and loops, no JS. GitHub allows PNG/GIF/JPEG/SVG images, 10 MB limit. **[verified]** ([attaching-files docs](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/attaching-files)) |
| **Animated SVG** (SMIL/CSS embedded inline) | Yes, via `<img>` | This is exactly what `svg-term-cli` targets: "Replace GIF asciicast recordings where you can not use the asciinema player, e.g. `README.md` files on GitHub." The README embeds its own animated example as an `<img>`. **[verified]** ([svg-term-cli readme](https://github.com/marionebl/svg-term-cli)). Caveat: GitHub sanitizes SVG (strips scripts) and behavior with *relative* paths has historically been flaky — reference a committed/hosted file. **[judgment]** ([community discussion 151372](https://github.com/orgs/community/discussions/151372), [termtosvg #61](https://github.com/nbedos/termtosvg/issues/61)) |
| **MP4 / WebM via hand-written `<video>`** | No | GitHub strips `<video>` tags that reference repo files. **[judgment]** (well-known platform behavior; consistent with the sanitizer model above) |
| **MP4 / WebM via uploaded attachment** | Yes | Drag-drop into an issue/PR editor produces a `user-attachments`/`githubusercontent` URL that renders as a native player. Formats `.mp4/.mov/.webm`, H.264 recommended; 10 MB free / 100 MB paid. **[verified]** ([attaching-files docs](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/attaching-files)). But that URL is **not reproducible from CI** — it comes from a manual upload, so it defeats scripted regeneration. **[judgment]** |
| **Linked player image** | Yes | A static poster image that links out to the interactive player, e.g. `[![asciicast](https://asciinema.org/a/ID.svg)](https://asciinema.org/a/ID)`. asciinema documents this exact snippet "in places where `<script>` tags are not allowed, such as in a project's README." **[verified]** ([asciinema embedding docs](https://docs.asciinema.org/manual/server/embedding/)). Downside: it's a click-out, not an inline autoplay. |

**Takeaway for the README:** an inline **animated GIF** (from `agg` or VHS) is the only format that both
autoplays inline *and* regenerates cleanly from CI. Animated SVG is a crisper, smaller alternative that
also works, with a mild reliability caveat. An uploaded `<video>` looks best but breaks scripted regen.

### GitHub Pages site — full JavaScript

The site is static hosting with no sanitizer, so it can run the **asciinema-player** JS, serve
`<video>` MP4/WebM directly, or show the same GIF/SVG. `asciinema-player` supports `poster`,
`autoPlay`, `loop`, `startAt`, `idleTimeLimit`, `speed`, and `markers`, embedded via a script tag,
npm import, or `AsciinemaPlayer.create('demo.cast', el)`. **[verified]**
([asciinema-player repo](https://github.com/asciinema/asciinema-player)).

### Can one source drive both surfaces?

**Yes — one recording *source*, two *renderings*.** The clean architecture is a single
**asciicast `.cast`** file:

- **Site:** feed the `.cast` straight into `asciinema-player` (interactive, scrubbable, selectable text,
  tiny file). **[verified]** (player repo above)
- **README:** render that same `.cast` to a GIF with `agg` (or an animated SVG with `svg-term`), because
  the README can't run the player. **[verified]** (agg / svg-term below)

VHS inverts this: the `.tape` script is the single source and it renders GIF + MP4/WebM directly, but it
does **not** produce a `.cast`, so the site cannot use the interactive player from a VHS source
(the `.cast` output is unmerged PR [#706](https://github.com/charmbracelet/vhs/pull/706)). **[verified]**

---

## 2. Recorders

### asciicast v3 format (the source-of-truth format)

asciicast **v3** is the current format. **[verified]** ([v3 spec](https://docs.asciinema.org/manual/asciicast/v3/)).
Header carries `version: 3` and `term: {cols, rows}`; the event stream stores **raw terminal output**
(`"o"` events) verbatim, so ANSI 256-color/truecolor, cursor movement, spinners and redraws are all
preserved. It also has `"i"` (input), `"r"` (resize), `"x"` (exit status) and **`"m"` marker events with
optional labels for named chapters**. **[verified]** (same spec). Markers are the hook for slicing (§3).

### asciinema CLI — records and is CI-scriptable

`asciinema` (latest **v3.2.1**, 2026-06-16 — a Rust rewrite that makes asciicast v3 the default) records
a live PTY to `.cast`. **[verified]** ([releases](https://github.com/asciinema/asciinema/releases)). Its
own README lists **"headless mode, configurable terminal window size, and exit-status propagation for
scripted and CI-friendly recording and streaming."** **[verified]**
([asciinema repo README](https://github.com/asciinema/asciinema)).
`asciinema rec -c "./demo.sh"` records a single command/driver script non-interactively (recording ends
when it exits). **[verified]** ([quick-start](https://docs.asciinema.org/manual/cli/quick-start/)).

**Scripted / reproducible re-recording.** asciinema itself records a live session, so reproducibility
comes from a driver on top:

- **autocast** — a YAML playbook automates asciicast creation: command steps (bash/python, wait for
  prompt, hideable for setup/teardown), interactive steps (key sequences into TUIs), wait steps,
  **marker** and clear steps, configurable prompt/typing-speed/timeout. CI-friendly. **[verified]**
  ([autocast repo](https://github.com/k9withabone/autocast)). Caveat: single release dated July 2023 —
  a maintenance risk. **[verified]** (same)
- **asciinema_automation** — drives a recording from a command script with `#$`-comment directives for
  expected output and config, auto-waiting instead of hard-coded sleeps. **[verified]**
  ([asciinema_automation repo](https://github.com/PierreMarchand20/asciinema_automation))

### agg — `.cast` → animated GIF (README rendering)

`agg` converts a `.cast` to an optimized GIF (gifski encoder), preserving terminal colors, with
built-in themes, configurable font/size, FPS cap, playback speed, idle-time limiting, and — importantly
— **frame selection by time ranges, markers, percentages, and event indexes**. **[verified]**
([agg repo](https://github.com/asciinema/agg)). GIF file size for a 90s cast is not documented; GIF is
inherently heavier and lower-fidelity than video. **[judgment]**

### svg-term-cli — `.cast` → animated SVG (crisp README rendering)

Renders an asciicast to a razor-sharp animated SVG. Reads a cast id, stdin JSON (`--in`), or a recorded
command; options include **`--from` / `--to` / `--at` (millisecond time slicing)**, `--window`,
`--width/--height`, `--profile/--term` color themes, `--no-cursor`. Explicit purpose: embed where the
asciinema player can't run, "e.g. `README.md` files on GitHub." **[verified]**
([svg-term-cli readme](https://github.com/marionebl/svg-term-cli)). Caveats: the project is old
(MIT 2017, low recent activity) and its asciicast v3 support is unverified — may need a v2 cast.
**Embedding gotcha:** the CSS/SMIL animation is written *into* the SVG, and community reports say it
animates on GitHub only when referenced with an HTML **`<img src="...">` tag, not markdown `![]()`**
(which shows a static frame) — test the generated file in a real GitHub preview before shipping.
**[judgment]** ([termtosvg #61](https://github.com/nbedos/termtosvg/issues/61))

### charmbracelet/vhs — scripted recorder (strongest scriptability)

VHS is "terminal GIFs as code." A `.tape` text file scripts keystrokes and settings; VHS runs them
against a **real PTY** (`ttyd` + `ffmpeg`), so it captures a genuine program's output (256-color,
spinners, redraws), then renders. **[verified]** ([vhs repo](https://github.com/charmbracelet/vhs)).

- **`.tape` language:** `Type` (with per-step speed), `Enter/Tab/Ctrl+..`, `Sleep`, **`Wait /regex/`**
  (block until output appears — deterministic waits for variable-duration steps), `Hide`/`Show`
  (skip setup/teardown frames), `Set FontSize/Width/Height/Theme/Framerate/PlaybackSpeed/...`,
  multiple `Output` lines. **[verified]** (same)
- **Outputs:** `.gif`, `.mp4`, `.webm`, PNG frame dir, `.txt/.ascii` (golden test files). One tape can
  emit several formats in one run. **[verified]** (same). **No asciinema `.cast`** yet (unmerged PR
  [#706](https://github.com/charmbracelet/vhs/pull/706)). **[verified]**
- **CI:** first-party **charmbracelet/vhs-action** regenerates the GIF from the `.tape` on CI on every
  trigger (auto-commit or PR-comment the render). **[verified]**
  ([vhs-action](https://github.com/charmbracelet/vhs-action)). This is the strongest re-recording story
  of any tool here.
- Running `claude`: a tape just `Type "claude"` + `Enter` then types a prompt — VHS is program-agnostic.
  **[judgment]** (mechanism verified; applicability to `claude` inferred)

### Rejected recorders

- **sassman/t-rec-rs** — fast, high-quality GIFs, renders the real terminal, but records a **live,
  hand-performed** session ended with Ctrl+D. **No script/replay → not CI-reproducible.** **[verified]**
  ([t-rec-rs repo](https://github.com/sassman/t-rec-rs)). Fails the top requirement.
- **faressoft/terminalizer** — records a live session to YAML, renders GIF. Config- and frame-editable
  but **not keystroke-scripted**; "GIF compression is not implemented yet" (bad for a 90s cast); last
  release v0.12.0 (Aug 2024), effectively stale. **[verified]**
  ([terminalizer repo](https://github.com/faressoft/terminalizer),
  [npm](https://www.npmjs.com/package/terminalizer)). Fails on scriptability and size.

---

## 3. Micro-casts: slice one recording, or record separately?

Two viable approaches, both scriptable:

- **Slice one hero recording.** Author the ~90s hero `.cast` with **markers** at stage boundaries
  (asciinema `"m"` events / autocast marker steps), then render per-stage clips by range at render time:
  `agg --select 5..30` (also markers/percent/positions), and `svg-term --from/--to`. One source,
  N rendered clips, no intermediate `.cast` files. **[verified]** (agg / svg-term / v3-spec above).
  Limit: on the **site**, `asciinema-player` has `startAt` but **no `stopAt`/end bound** — it cannot
  autoplay-and-stop a single 10s slice — so an interactive micro-cast needs its own trimmed `.cast`.
  **[verified]** (player options). Trimming a standalone sub-`.cast` is tractable in v3 because event
  intervals are **relative**: keep the header + the wanted event lines and adjust the first interval
  (v2's absolute timestamps needed rebasing). **[judgment]** ([v3 spec](https://docs.asciinema.org/manual/asciicast/v3/))
- **Record each stage separately.** A short per-stage tape/playbook produces a tight, self-contained
  ~10s loop with no dependence on hero timing. Cleaner for the map panel's looping tiles; costs N little
  scripts instead of one. **[judgment]**

**Recommendation:** for the **README/GIF/SVG** artifacts, slice the one hero cast by marker (single
source, guaranteed visual consistency). For the **site's interactive** micro-casts in the map panel,
prefer **separate short recordings** (or separately-trimmed `.cast` files), because the player can't
range-bound between two markers and the map wants independent looping tiles. **[judgment]**

---

## 4. Viable stacks compared

| Stack | Recording source | README render | Site render | Scriptable / CI re-record | Verdict |
|---|---|---|---|---|---|
| **A. asciinema-centric** | `asciinema rec` (headless/CI) → `.cast` v3, driven by autocast/asciinema_automation | `agg` → GIF (or `svg-term` → SVG) | `asciinema-player` JS on the `.cast` (interactive, scrubbable, tiny) | headless CI mode + YAML/script playbook. Driver is third-party (autocast last release 2023) | **Recommended** — true single source, richest site, tiny assets, marker-based slicing |
| **B. VHS-centric** | `.tape` script → real PTY | GIF (from tape) | MP4/WebM `<video>` (from same tape) | **First-party** `vhs-action` on CI; `Wait /regex/` deterministic waits | **Strong alternative** — best scriptability; site loses the interactive player + selectable text; no `.cast` |
| **C. Hybrid VHS+asciinema** | VHS `.tape` for CI determinism **and** an asciinema `.cast` for the player | GIF from VHS | player from `.cast` | both, but two capture paths of a non-deterministic `claude` | Extra complexity for marginal gain; only if you need both first-party CI *and* the interactive player |
| **D. t-rec / terminalizer** | live hand-performed | GIF | GIF/video | **none** (t-rec) / weak (terminalizer) | **Rejected** — not re-recordable in CI |

---

## 5. Recommendation

**Record with asciinema (asciicast v3) as the single source; render per surface; drive it from a
scripted playbook in CI.**

1. **One hero `.cast`.** Record the ~90s run with `asciinema rec` in headless mode, laying **markers**
   at each stage boundary. Author it as an **autocast YAML playbook** (or asciinema_automation script)
   so it re-records from a script, not by hand. **[verified basis; the "which driver" choice is judgment]**
2. **Site = interactive player.** Embed the `.cast` with `asciinema-player` (`autoPlay`, `loop`,
   `poster`, `idleTimeLimit`). Selectable text, scrubbing, and a ~KB-scale file — the richest surface,
   which matches variant E's "expose the whole machine."
3. **README = animated GIF via `agg`.** Render the hero `.cast` to an optimized GIF. It autoplays inline,
   needs no JS, and regenerates from CI — the only README format that satisfies all three. Keep
   `svg-term` → animated SVG as an optional crisper/smaller variant (mind the v3-support caveat).
4. **Micro-casts.** README poster GIFs: slice the hero cast at render time with `agg --select`
   (or `svg-term --from/--to`). The map panel's interactive micro-casts: **separate short scripted
   recordings** (or hand-trimmed sub-`.cast` files), one per stage, because the player has `startAt`
   but no end bound.
5. **Crossfire-wave (~40s).** Its own short playbook → `.cast`; site plays it via the player. Same
   pipeline, shorter script.
6. **Re-recording strategy.** Commit the playbooks (`*.yaml`/`*.cast` scripts) to the repo and wire a CI
   job that runs the playbook → `.cast` → `agg`/`svg-term` renders, committing the refreshed `.cast` +
   GIF/SVG assets whenever the toolkit changes. **Reproducibility caveat:** a real `claude` session is
   non-deterministic (model output varies run to run), so a re-record won't be byte-identical. Two ways
   to handle it: (a) accept curated live variance — re-run the playbook and eyeball the result; or
   (b) for byte-stable CI output, drive a **deterministic replay stub** (a fake `claude` that prints a
   captured transcript with timed sleeps) instead of the live model. **[judgment]**

**When to pick VHS instead (Stack B):** if *first-party, zero-maintenance CI scriptability* outranks the
interactive site player. VHS's `.tape` + `vhs-action` is the most robust re-recording story here, and it
renders README-GIF and site-video from one tape — but the site then shows a plain video (no scrubbing,
no selectable text, larger files) and there is no `.cast` for the player until PR #706 lands. Given
variant E explicitly wants the architecture exposed interactively, Stack A's player earns its keep;
VHS is the pragmatic fallback if the asciinema driver's third-party maintenance risk is unacceptable.

---

## Sources

- Landing-page decision — [issue #13](https://github.com/alp82/alp-river/issues/13); this ticket — [issue #18](https://github.com/alp82/alp-river/issues/18)
- GitHub attaching files / supported formats — https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/attaching-files
- GitHub SVG-in-markdown sanitization — https://github.com/orgs/community/discussions/151372 · https://github.com/nbedos/termtosvg/issues/61
- asciicast v3 spec — https://docs.asciinema.org/manual/asciicast/v3/
- asciinema CLI / features — https://github.com/asciinema/asciinema · https://asciinema.org/
- asciinema embedding (README image link vs site player) — https://docs.asciinema.org/manual/server/embedding/
- asciinema-player — https://github.com/asciinema/asciinema-player
- agg (cast → GIF) — https://github.com/asciinema/agg
- svg-term-cli (cast → animated SVG) — https://github.com/marionebl/svg-term-cli
- autocast (YAML playbook) — https://github.com/k9withabone/autocast
- asciinema_automation — https://github.com/PierreMarchand20/asciinema_automation
- VHS — https://github.com/charmbracelet/vhs · vhs-action — https://github.com/charmbracelet/vhs-action · `.cast` PR — https://github.com/charmbracelet/vhs/pull/706 · discussion — https://github.com/charmbracelet/vhs/discussions/225
- t-rec-rs — https://github.com/sassman/t-rec-rs
- terminalizer — https://github.com/faressoft/terminalizer · https://www.npmjs.com/package/terminalizer
