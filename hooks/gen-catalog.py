#!/usr/bin/env python3
"""Compile stage contracts from agents/*.md frontmatter into generated/catalog.json.

Runs as a PostToolUse(Edit|Write) hook (regenerates only when an agents/*.md file
changed) and is also runnable manually. The catalog is the machine-readable index the
deterministic router consumes.

Authoring uses sigils, stripped at compile time (see doctrine/CATALOG.md):

  @artifact   required data input/output       ?artifact   optional data input
  #signal     pub/sub topic

Sigil-bearing scalars are YAML-quoted ('@x', '?x', '#x') because @/?/# are reserved at the
start of a YAML scalar. Storage is bare names; required-vs-optional is a structural split,
never a sigil. Every stage MUST declare a `routes` list (a subset of code/sketch/talk/system) -
the generator errors loudly if one is missing or names an unknown path.

Each stage also carries the verbatim fenced block under its `## Input` heading as
`input_template` (empty string when the agent has no `## Input` section).
"""

import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write("gen-catalog: PyYAML required (pip install pyyaml)\n")
    sys.exit(0)  # never block the tool call; surface and move on

ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = ROOT / "agents"
OUT = ROOT / "generated" / "catalog.json"
# The four routing paths a stage's `routes` may name.
PATHS = ("talk", "sketch", "code", "system")


def changed_path_from_hook_payload():
    """If invoked as a PostToolUse hook, return the edited file path; else None."""
    if sys.stdin.isatty():
        return None
    raw = sys.stdin.read().strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return (payload.get("tool_input") or {}).get("file_path")


def parse_frontmatter(text):
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return None
    try:
        return yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError:
        return None


def _list(d, key):
    v = (d or {}).get(key) or []
    return v if isinstance(v, list) else [v]


def _strip_signal(item):
    s = str(item).strip()
    return s[1:] if s.startswith("#") else s


def _normalize_lock(raw, stage_name="<unknown>"):
    items = raw if isinstance(raw, list) else [raw]
    out = []
    for e in items:
        if "while" not in e or "until" not in e:
            missing = [k for k in ("while", "until") if k not in e]
            raise ValueError(
                f"gen-catalog: stage '{stage_name}' has a lock entry missing required "
                f"key(s): {missing}. Entry: {e!r}"
            )
        out.append(
            {"while": _strip_signal(e["while"]), "until": _strip_signal(e["until"])}
        )
    return out


def _strip_artifact(item):
    """Drop a leading @/? sigil from a data artifact, leaving the bare type name."""
    s = str(item).strip()
    return s[1:] if s and s[0] in "@?" else s


def _split_inputs(items):
    """Sigil-aware input split: leading `?` = optional, `@` or bare = required.

    Returns (required, optional) as bare-name lists. Optional inputs order a stage after
    their producer only when that producer is in the route, and never drop it when absent.
    """
    required, optional = [], []
    for item in items:
        s = str(item).strip()
        if s.startswith("?"):
            optional.append(s[1:])
        elif s.startswith("@"):
            required.append(s[1:])
        else:
            required.append(s)
    return required, optional


def extract_input_template(text):
    """Return the verbatim inner text of the fenced block under the first `## Input` heading.

    First `## Input` wins. From the line after it, scan for an opening ``` fence and collect
    lines until the closing ``` fence, returning the inner text (no heading, no fence lines).
    The opening-fence search stops at the next `## ` heading, so a later `## Output` fence is
    never captured. No `## Input`, or no fence before the next `## `, returns "".
    """
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln == "## Input"), None)
    if start is None:
        return ""
    i = start + 1
    while i < len(lines) and not lines[i].startswith("```"):
        if lines[i].startswith("## "):
            return ""
        i += 1
    if i >= len(lines):
        return ""
    inner = []
    i += 1
    while i < len(lines) and not lines[i].startswith("```"):
        inner.append(lines[i])
        i += 1
    return "\n".join(inner) + "\n" if inner else ""


def normalize_stage(name, stage, input_template=""):
    data, signals = stage.get("data") or {}, stage.get("signals") or {}
    req_in, opt_in = _split_inputs(_list(data, "input"))
    entry = {
        "name": name,
        "routes": _list(stage, "routes"),
        "data": {
            "input": {"required": req_in, "optional": opt_in},
            "output": [_strip_artifact(a) for a in _list(data, "output")],
        },
        "signals": {
            "subscribes": [_strip_signal(s) for s in _list(signals, "subscribes")],
            "publishes": [_strip_signal(s) for s in _list(signals, "publishes")],
        },
    }
    entry["input_template"] = input_template
    if stage.get("guard"):
        entry["guard"] = stage["guard"]
    if stage.get("lock"):
        entry["lock"] = _normalize_lock(stage["lock"], name)
    if stage.get("milestone-scope"):
        entry["milestone-scope"] = stage["milestone-scope"]
    return entry


def build_catalog():
    stages, errors = {}, []
    for md in sorted(AGENTS_DIR.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if not fm or "stage" not in fm or "name" not in fm:
            continue
        name = fm["name"]
        routes = _list(fm["stage"], "routes")
        if not routes:
            errors.append(f"{name}: missing `routes`")
            continue
        unknown = [r for r in routes if r not in PATHS]
        if unknown:
            errors.append(
                f"{name}: unknown route(s) {unknown} (allowed: {list(PATHS)})"
            )
            continue
        stages[name] = normalize_stage(name, fm["stage"], extract_input_template(text))
    if errors:
        raise SystemExit("gen-catalog: ERROR - " + "; ".join(errors))
    return {"stages": stages}


def main():
    changed = changed_path_from_hook_payload()
    if changed is not None and "/agents/" not in changed.replace("\\", "/"):
        return  # hook fired on a non-agent edit; nothing to do
    catalog = build_catalog()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    sys.stderr.write(
        f"gen-catalog: {len(catalog['stages'])} stages -> {OUT.relative_to(ROOT)}\n"
    )


if __name__ == "__main__":
    main()
