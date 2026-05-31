#!/usr/bin/env python3
"""Deterministic router: assembles a route from the catalog + currently live signals.

Pure function of (catalog, live_signals, available_artifacts, already_run). Steps:

1. **trigger** - membership is OR over `subscribes`: any live topic a stage subscribes to
   triggers it (family-prefix aware: `findings` matches `findings:correctness`).
2. **route filter** - drop a triggered stage whose `routes` exclude the live path
   (build/spike/talk, read from the live signals). No path live yet (pre-triage) = no-op.
3. **drop unsatisfiable** - a stage whose REQUIRED inputs can't be produced is dropped.
   Optional (`?`) inputs never cause a drop.
4. **topo-sort** the survivors by the `input`/`output` precedence DAG. A required OR an
   optional input both order a stage after its producer *when that producer is in the
   route*; an optional input absent from the route just creates no edge.

Size is the stage count. No optimistic expansion through declared `publishes` - the route
grows across recomposes as stages actually emit signals. See doctrine/CATALOG.md.
"""
import json
from pathlib import Path

_SIZES = [(1, "XS"), (3, "S"), (6, "M"), (10, "L"), (15, "XL")]
PATHS = ("build", "spike", "talk")


def load_catalog(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def size_label(n):
    if n <= 0:
        return "empty"
    for hi, label in _SIZES:
        if n <= hi:
            return label
    return "XXL"


def _required(s):
    return s["data"]["input"]["required"]


def _inputs(s):
    """Required + optional - both create an ordering edge when their producer is in-route."""
    return s["data"]["input"]["required"] + s["data"]["input"]["optional"]


def _toposort(stages, names):
    names = set(names)
    producers = {}
    for n in names:
        for art in stages[n]["data"]["output"]:
            producers.setdefault(art, set()).add(n)
    edges = {n: set() for n in names}
    indeg = {n: 0 for n in names}
    for n in names:
        preds = set()
        for art in _inputs(stages[n]):
            preds |= producers.get(art, set())       # producer in-route -> ordering edge
        preds.discard(n)
        for p in preds:
            if n not in edges[p]:
                edges[p].add(n)
                indeg[n] += 1
    queue = sorted(n for n in names if indeg[n] == 0)
    order = []
    while queue:
        n = queue.pop(0)
        order.append(n)
        for m in sorted(edges[n]):
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
                queue.sort()
    if len(order) < len(names):                      # cycle guard (data graph is acyclic)
        order += sorted(names - set(order))
    return order


def _matches(sub, live):
    """A subscription matches a live topic exactly, or as a family base: subscribing
    `findings` matches `findings:correctness`; `missing-infra` matches `missing-infra:email`."""
    return any(topic == sub or topic.startswith(sub + ":") for topic in live)


def _trigger(stages, live, already_run):
    triggered = {}
    for name, s in stages.items():
        if name in already_run:
            continue
        match = next((sig for sig in s["signals"]["subscribes"] if _matches(sig, live)), None)
        if match is not None:
            triggered[name] = match
    return triggered


def _on_live_path(stages, triggered, live):
    """Drop a triggered stage whose `routes` exclude the live path. With no path signal
    live yet (the pre-triage seed), there is nothing to filter against - keep everything."""
    live_paths = {p for p in PATHS if p in live}
    if not live_paths:
        return dict(triggered)
    return {n: sig for n, sig in triggered.items()
            if set(stages[n]["routes"]) & live_paths}


def _drop_unsatisfiable(stages, triggered, available):
    kept = dict(triggered)
    while True:
        produced = set()
        for n in kept:
            produced.update(stages[n]["data"]["output"])
        unsat = [n for n in kept
                 if any(art not in available and art not in produced
                        for art in _required(stages[n]))]
        if not unsat:
            return kept
        for n in unsat:
            del kept[n]


def compute_route(catalog, live_signals, available=frozenset(), already_run=frozenset()):
    stages = catalog["stages"]
    live, available = set(live_signals), set(available)
    triggered = _trigger(stages, live, set(already_run))
    on_path = _on_live_path(stages, triggered, live)
    kept = _drop_unsatisfiable(stages, on_path, available)
    order = _toposort(stages, kept)
    dropped = {}
    for n in triggered:
        if n not in on_path:
            dropped[n] = "off-path"
        elif n not in kept:
            dropped[n] = "unsatisfiable-input"
    return {
        "route": order,
        "size": size_label(len(order)),
        "triggered_by": {n: triggered[n] for n in order},
        "dropped": dropped,
    }


def merge_sticky(catalog, prev_names, result):
    """Asymmetric safety: a sticky stage triggered earlier stays in the route even if its
    signal has since gone quiet. Never auto-dropped."""
    stages = catalog["stages"]
    keep = [n for n in prev_names
            if stages.get(n, {}).get("guard") == "sticky" and n not in result["route"]]
    if not keep:
        return result
    order = _toposort(stages, set(result["route"]) | set(keep))
    merged = dict(result)
    merged["route"] = order
    merged["size"] = size_label(len(order))
    merged["sticky_kept"] = keep
    return merged


def _main():
    import sys
    req = json.loads(sys.stdin.read() or "{}")
    catalog_path = req.get("catalog") or (
        Path(__file__).resolve().parent.parent / "generated" / "catalog.json")
    res = compute_route(
        load_catalog(catalog_path),
        req.get("live", []),
        req.get("available", []),
        req.get("already_run", []),
    )
    print(json.dumps(res, indent=2, sort_keys=True))


if __name__ == "__main__":
    _main()
