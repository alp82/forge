#!/usr/bin/env python3
"""Deterministic replay stub + asciicast v3 generator for the forge demo casts.

A playbook (demo/playbooks/*.play) is the single authored source. Two modes:

  cast.py hero.play --out hero.cast    emit asciicast v3 with computed timestamps —
                                       byte-stable: same playbook, same bytes, no PTY
  cast.py hero.play --live             replay to the current terminal with real sleeps
                                       (eyeball mode; also recordable by real asciinema)

Playbook DSL — one command per line, `#` comments, text after the first `|`:

  @cols N / @rows N / @title T / @idle S    header fields
  m <pre> <label>        marker event (chapter boundary; invisible in playback)
  o <pre> |text          print line (appends \r\n); empty text = blank line
  r <pre> |text          raw print, no newline (prompts)
  t <pre> <perchar> |text   human typing, one event per char
  s <pre> <dur> |text    spinner on one line for <dur> seconds, self-erasing
  c <pre>                clear screen + cursor home
  w <dur>                extra pause folded into the next event's interval
  x <code>               exit event (last line)

<pre> is the pause in seconds before the command's first byte. Style tokens in text:
{b} bold, {d} dim, {u} underline, {/} reset, {red} {green} {yellow} {blue} {mag}
{cyan} {gray} {white}, {org} forge orange (truecolor).
"""

import argparse
import json
import sys
import time

STYLES = {
    "b": "\x1b[1m",
    "d": "\x1b[2m",
    "u": "\x1b[4m",
    "/": "\x1b[0m",
    "red": "\x1b[31m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "blue": "\x1b[34m",
    "mag": "\x1b[35m",
    "cyan": "\x1b[36m",
    "gray": "\x1b[90m",
    "white": "\x1b[97m",
    "org": "\x1b[38;2;217;119;87m",  # #D97757 — the forge accent
}

SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
SPINNER_TICK = 0.12
ERASE_LINE = "\r\x1b[2K"

# A dark theme pinned in the header so asciinema-player and agg render identically.
THEME = {
    "fg": "#c8ccd4",
    "bg": "#16181d",
    "palette": (
        "#16181d:#e05561:#8cc265:#d18f52:#4aa5f0:#c162de:#42b3c2:#c8ccd4:"
        "#5f6672:#ff616e:#a5e075:#f0a45d:#4dc4ff:#de73ff:#4cd1e0:#e6e6e6"
    ),
}


def styled(text):
    for token, code in STYLES.items():
        text = text.replace("{" + token + "}", code)
    return text


def parse(path):
    """Parse a playbook into (meta, events) where events are (interval, code, data)."""
    meta = {"cols": 100, "rows": 28, "title": None, "idle": None}
    events = []
    pending = 0.0  # extra wait from `w`, folded into the next event

    def emit(pre, code, data):
        nonlocal pending
        events.append((round(pre + pending, 3), code, data))
        pending = 0.0

    for lineno, rawline in enumerate(open(path, encoding="utf-8"), 1):
        line = rawline.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("@"):
            key, _, value = line[1:].partition(" ")
            meta[key] = value.strip()
            continue
        head, _, text = line.partition("|")
        fields = head.split()
        cmd = fields[0]
        text = styled(text)
        try:
            if cmd == "o":
                emit(float(fields[1]), "o", text + "\r\n")
            elif cmd == "r":
                emit(float(fields[1]), "o", text)
            elif cmd == "t":
                pre, per = float(fields[1]), float(fields[2])
                first = True
                for ch in text:
                    emit(pre if first else per, "o", ch)
                    first = False
            elif cmd == "s":
                pre, dur = float(fields[1]), float(fields[2])
                ticks = max(1, int(dur / SPINNER_TICK))
                for i in range(ticks):
                    frame = SPINNER_FRAMES[i % len(SPINNER_FRAMES)]
                    emit(pre if i == 0 else SPINNER_TICK, "o",
                         ERASE_LINE + STYLES["org"] + frame + STYLES["/"] + " " + text)
                emit(SPINNER_TICK, "o", ERASE_LINE)
            elif cmd == "m":
                emit(float(fields[1]), "m", " ".join(fields[2:]))
            elif cmd == "c":
                emit(float(fields[1]), "o", "\x1b[2J\x1b[H")
            elif cmd == "w":
                pending += float(fields[1])
            elif cmd == "x":
                emit(0.0, "x", fields[1])
            else:
                raise ValueError(f"unknown command {cmd!r}")
        except (IndexError, ValueError) as exc:
            sys.exit(f"{path}:{lineno}: {exc}")
    return meta, events


def header(meta):
    term = {"cols": int(meta["cols"]), "rows": int(meta["rows"]), "type": "xterm-256color",
            "theme": THEME}
    head = {"version": 3, "term": term}
    if meta["title"]:
        head["title"] = meta["title"]
    if meta["idle"]:
        head["idle_time_limit"] = float(meta["idle"])
    return head


def write_cast(meta, events, out):
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(header(meta), separators=(",", ":")) + "\n")
        for interval, code, data in events:
            fh.write(json.dumps([interval, code, data], separators=(",", ":"),
                                ensure_ascii=False) + "\n")


def play_live(events):
    for interval, code, data in events:
        time.sleep(interval)
        if code == "o":
            sys.stdout.write(data)
            sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("playbook")
    ap.add_argument("--out", help="write asciicast v3 to this path")
    ap.add_argument("--live", action="store_true", help="replay to this terminal")
    args = ap.parse_args()

    meta, events = parse(args.playbook)
    duration = round(sum(e[0] for e in events), 1)
    if args.live:
        play_live(events)
    if args.out:
        write_cast(meta, events, args.out)
        print(f"{args.out}: {len(events)} events, {duration}s", file=sys.stderr)
    elif not args.live:
        print(f"{args.playbook}: {len(events)} events, {duration}s", file=sys.stderr)


if __name__ == "__main__":
    main()
