#!/usr/bin/env bash
# Regenerate every demo cast from its playbook (byte-stable), then the README GIF
# from hero.cast when `agg` is on PATH. Run from anywhere.
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p casts
for play in playbooks/*.play; do
  name="$(basename "$play" .play)"
  python3 cast.py "$play" --out "casts/$name.cast"
done

if command -v agg >/dev/null 2>&1; then
  agg casts/hero.cast ../docs/assets/forge-hero.gif --font-size 16 --fps-cap 24
else
  echo "agg not on PATH — skipped docs/assets/forge-hero.gif (see demo/README.md)" >&2
fi
