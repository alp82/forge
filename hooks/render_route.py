"""Legibility renderers over a route result.

Variation A (`render_full`): the whole route at a gate, each stage tagged with the signal
that pulled it in. Variation B (`render_delta`): only what changed on a recompose, leading
with the why. The `@`/`#` sigils are applied here, at render time - storage stays bare.
"""


def render_full(result, catalog, route_type="build"):
    n = len(result["route"])
    lines = [f"{route_type} · {result['size']} · {n} stage{'' if n == 1 else 's'}"]
    for name in result["route"]:
        sig = result["triggered_by"].get(name)
        why = f" ← #{sig}" if sig else ""
        sticky = " [sticky]" if catalog["stages"].get(name, {}).get("guard") == "sticky" else ""
        lines.append(f"  • {name}{why}{sticky}")
    return "\n".join(lines)


def render_delta(prev_names, result):
    prev, new = set(prev_names), set(result["route"])
    added, removed = sorted(new - prev), sorted(prev - new)
    if not added and not removed:
        return "Route unchanged"
    parts = [f"+{n}" for n in added] + [f"-{n}" for n in removed]
    head = f"Route {' '.join(parts)}  (now {result['size']}/{len(result['route'])})"
    whys = [f"  +{n} ← #{result['triggered_by'][n]}"
            for n in added if result["triggered_by"].get(n)]
    return "\n".join([head] + whys)
