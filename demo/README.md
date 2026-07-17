# demo — the three casts

The demo casts shown in the README and on the site. Everything here regenerates from
source; nothing is hand-recorded.

## How it works

- **Playbooks** (`playbooks/*.play`) are the single authored source — an autocast-style
  scene script per cast: lines, pauses, typing, spinners, and chapter markers. The DSL
  is documented at the top of [`cast.py`](cast.py).
- **`cast.py`** is the deterministic replay stub. `--out` emits an asciicast v3 `.cast`
  with computed timestamps — **byte-stable**: the same playbook always produces the same
  bytes, because no PTY or wall clock is involved. `--live` replays a playbook to the
  current terminal with real sleeps for eyeballing.
- **`casts/`** holds the generated `.cast` files (committed — the site's
  asciinema-player consumes them directly).
- **`build.sh`** regenerates every cast, then renders the README GIF from `hero.cast`
  when [`agg`](https://github.com/asciinema/agg) is on PATH (prebuilt binaries on its
  releases page; not needed for the casts themselves).

## The casts

| Cast | Length | Surface |
|---|---|---|
| `hero` | ~90 s | README GIF (`docs/assets/forge-hero.gif`) + site player; markers at each stage boundary |
| `crossfire` | ~40 s | site — the standalone review wave |
| `stage-*` (8) | ~10 s each | site — looping tiles in the system-map panel |

## Re-recording

Edit the playbook, run `./build.sh`, commit the changed `.play`, `.cast`, and GIF.
A clean regen produces no diff — if `git status` moves without a playbook or
`cast.py` change, something is wrong.
