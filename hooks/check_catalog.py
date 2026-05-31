#!/usr/bin/env python3
"""Coherence check over generated/catalog.json - the second gate beside the router tests.

Verifies the four invariants a composed route relies on:

  1. every subscribed signal has a publisher (family-aware) or is an external seed
  2. every REQUIRED input has an in-catalog producer or is an external-seed artifact
  3. `scope-shift` is published by every stage (each self-reports premise breaks)
  4. `routes` is present, non-empty, and a subset of build/spike/talk on every stage

Runnable standalone (`python3 hooks/check_catalog.py`, exits 1 on any problem) and imported
by the router tests. External seeds are values that enter a route from outside any stage -
the orchestrator seed, user/gate decisions, or the /alp-river:adr command - listed below.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "generated" / "catalog.json"
PATHS = ("build", "spike", "talk")

# Signals that enter from outside any stage (orchestrator seed, user/gate decision, the
# /alp-river:adr command) - subscribing to one is not an orphan.
SEED_SIGNALS = {"request-received", "reshape", "run-visual", "design-decision"}
# Artifacts seeded the same way - `request` is THE seed; `decision-summary` rides in on the
# /alp-river:adr command (or a design gate that records a decision).
SEED_ARTIFACTS = {"request", "decision-summary"}


def _family_match(sub, published):
    """Satisfied by an exact topic, a qualified member of the family (sub `findings` <- pub
    `findings:security`), or the family base (sub `findings:x` <- pub `findings`)."""
    return any(p == sub or p.startswith(sub + ":") or sub.startswith(p + ":")
               for p in published)


def check(catalog):
    stages = catalog["stages"]
    published, produced = set(), set()
    for s in stages.values():
        published.update(s["signals"]["publishes"])
        produced.update(s["data"]["output"])
    problems = []
    for name, s in sorted(stages.items()):
        routes = s.get("routes") or []
        if not routes:
            problems.append(f"{name}: missing `routes`")
        elif any(rt not in PATHS for rt in routes):
            problems.append(f"{name}: routes {routes} not a subset of {list(PATHS)}")
        if "scope-shift" not in s["signals"]["publishes"]:
            problems.append(f"{name}: does not publish `scope-shift`")
        for sub in s["signals"]["subscribes"]:
            if sub not in SEED_SIGNALS and not _family_match(sub, published):
                problems.append(f"{name}: subscribes `{sub}` - no publisher or seed")
        for art in s["data"]["input"]["required"]:
            if art not in SEED_ARTIFACTS and art not in produced:
                problems.append(f"{name}: requires `{art}` - no producer or seed")
    return problems


def main():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    problems = check(catalog)
    if problems:
        sys.stderr.write("check-catalog: FAIL\n  " + "\n  ".join(problems) + "\n")
        sys.exit(1)
    sys.stderr.write(
        f"check-catalog: clean - {len(catalog['stages'])} stages, all invariants hold\n")


if __name__ == "__main__":
    main()
