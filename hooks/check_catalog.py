#!/usr/bin/env python3
"""Coherence check over generated/catalog.json - the second gate beside the router tests.

Verifies the invariants a composed route relies on:

  1. every subscribed signal has a publisher (family-aware) or is an external seed
  2. every REQUIRED input has an in-catalog producer or is an external-seed artifact
  3. `scope-shift` is published by every stage (each self-reports premise breaks)
  4. `routes` is present, non-empty, and a subset of code/sketch/talk/system on every stage
  5. every `lock` while/until signal has a publisher (family-aware) or is an external seed
  6. every stage with a required input carries a non-empty `input_template` (except `triage`)
  7. every reviewer (publishes `clean` or a `findings:*` lens) carries a `SIGNALS_PUBLISHED:`
     line INSIDE its `output_template` whose tokens agree with its frontmatter signals: `#clean`
     iff it publishes `clean`, `#findings` present when it publishes any `findings:*`, and a
     `#findings:<lens>` token's lens is one the stage actually publishes (family-aware)

Runnable standalone (`python3 hooks/check_catalog.py`, exits 1 on any problem) and imported
by the router tests. External seeds are values that enter a route from outside any stage -
the orchestrator seed or user/gate decisions - listed below.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "generated" / "catalog.json"
# The four routing paths a stage's `routes` may name.
PATHS = ("talk", "sketch", "code", "system")

# Signals that enter from outside any stage (orchestrator seed, user/gate decision) -
# subscribing to one is not an orphan.
SEED_SIGNALS = {
    "request-received",
    "reshape",
    # Multi-plan adjudication trigger - enters the route from outside any stage; the
    # orchestrator seeds it (atomic co-publish, see doctrine/multi-plan.md). Same basis as
    # request-received/reshape: orchestrator-sourced, no in-catalog publisher.
    "critiques-ready",
    # Ship-tail trigger - orchestrator-emitted at convergence on a ship request (reliably
    # emitted, not the unsatisfiable #milestones-complete case), so the ship-gate subscribe
    # and the executor's `while:ship-ready` resolve. (`ship-approved` resolves via the
    # ship-gate publisher; `ship-requested` via triage - neither needs a seed.)
    "ship-ready",
}
# Artifacts seeded the same way - `request` is THE seed; `competing-plans` and
# `plan-critiques` are orchestrator-sourced on a multi-plan run - values that enter a route
# from outside any stage; the orchestrator seeds these (see doctrine/multi-plan.md).
SEED_ARTIFACTS = {
    "request",
    "competing-plans",
    "plan-critiques",
}
# Stages exempt from the template-presence invariant - `triage` consumes the raw request
# directly and has no `## Input` template.
TEMPLATE_EXEMPT = {"triage"}
# Token a reviewer's `output_template` must carry, on its own line, so the orchestrator reads
# convergence from an explicit signal rather than inferring it from VERDICT prose.
SIGNALS_PUBLISHED_TOKEN = "SIGNALS_PUBLISHED:"


def _family_match(sub, published):
    """Satisfied by an exact topic, a qualified member of the family (sub `findings` <- pub
    `findings:security`), or the family base (sub `findings:x` <- pub `findings`)."""
    return any(
        p == sub or p.startswith(sub + ":") or sub.startswith(p + ":")
        for p in published
    )


def _check_reviewer_signals(name, s, pubs):
    """Invariant 7: a reviewer's SIGNALS_PUBLISHED line agrees with its frontmatter signals.

    Returns a list of problem strings (empty when the reviewer's line is well-formed). Checks,
    in both directions where applicable:
      - the `SIGNALS_PUBLISHED:` line exists inside `output_template` (the captured fence);
      - `#clean` <-> publishing `clean` (each implies the other; matched as a whole token,
        so `#cleanup` neither satisfies nor falsely triggers `#clean`);
      - a `#findings` or `#findings:<lens>` token present whenever the stage publishes any
        `findings:*` family member;
      - EVERY `#findings:<lens>` token's lens is one of the stage's published `findings:*`
        lenses (family-aware) - catches any token naming a lens the frontmatter does not publish.
    """
    problems = []
    signal_line = next(
        (
            ln
            for ln in s.get("output_template", "").splitlines()
            if ln.strip().startswith(SIGNALS_PUBLISHED_TOKEN)
        ),
        None,
    )
    if signal_line is None:
        problems.append(
            f"{name}: reviewer missing `{SIGNALS_PUBLISHED_TOKEN}` line inside output_template"
        )
        return problems
    publishes_findings = _family_match("findings", pubs)
    tokens = _signal_line_tokens(signal_line)
    if "clean" in pubs and "#clean" not in tokens:
        problems.append(
            f"{name}: publishes `clean` but {SIGNALS_PUBLISHED_TOKEN} line lacks `#clean`"
        )
    if publishes_findings and not any(
        tok == "#findings" or tok.startswith("#findings:") for tok in tokens
    ):
        problems.append(
            f"{name}: publishes `findings:*` but {SIGNALS_PUBLISHED_TOKEN} line lacks `#findings`"
        )
    if "#clean" in tokens and "clean" not in pubs:
        problems.append(
            f"{name}: {SIGNALS_PUBLISHED_TOKEN} line names `#clean` but frontmatter does not publish `clean`"
        )
    # Lens-match: every `#findings:<lens>` token must name a published findings lens. Parse
    # each token's lens and require `findings:<lens>` to be a member of the stage's findings
    # family.
    for token_lens in _findings_token_lenses(signal_line):
        if not _family_match("findings:" + token_lens, pubs):
            problems.append(
                f"{name}: {SIGNALS_PUBLISHED_TOKEN} line names `#findings:{token_lens}` "
                f"but frontmatter does not publish that findings lens"
            )
    return problems


def _signal_line_tokens(signal_line):
    """Return the line's whitespace-delimited tokens with bracket/punctuation decoration
    stripped (brackets replaced by spaces, trailing `,`/`.`/`;`/`)`/`|` stripped), so a
    decorated token like `[#clean]` or `#clean,` still matches as a whole token."""
    tokens = []
    for raw in signal_line.replace("[", " ").replace("]", " ").split():
        tok = raw.strip(",.;)|")
        if tok:
            tokens.append(tok)
    return tokens


def _findings_token_lenses(signal_line):
    """Return every `<lens>` named by a `#findings:<lens>` token in the line (possibly empty).

    A bare `#findings` names no lens and contributes nothing."""
    lenses = []
    for tok in _signal_line_tokens(signal_line):
        if tok.startswith("#findings:"):
            lens = tok[len("#findings:") :]
            if lens:
                lenses.append(lens)
    return lenses


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
        ms = s.get("milestone-scope")
        if ms is not None and ms not in {"local", "both"}:
            problems.append(f"{name}: milestone-scope '{ms}' not in {{local, both}}")
        for sub in s["signals"]["subscribes"]:
            if sub not in SEED_SIGNALS and not _family_match(sub, published):
                problems.append(f"{name}: subscribes `{sub}` - no publisher or seed")
        for art in s["data"]["input"]["required"]:
            if art not in SEED_ARTIFACTS and art not in produced:
                problems.append(f"{name}: requires `{art}` - no producer or seed")
        if (
            s["data"]["input"]["required"]
            and name not in TEMPLATE_EXEMPT
            and not s.get("input_template", "").strip()
        ):
            problems.append(f"{name}: has required input but empty input_template")
        pubs = s["signals"]["publishes"]
        # A reviewer emits a bare `findings` data output AND reports via clean/findings:* - the
        # Reviewer Contract shape. Stages that publish a findings:* signal but emit a different
        # artifact (researcher, plan-challenger, system-verifier) are not reviewers.
        is_reviewer = "findings" in s["data"]["output"] and (
            "clean" in pubs or _family_match("findings", pubs)
        )
        if is_reviewer:
            problems.extend(_check_reviewer_signals(name, s, pubs))
        for lk in s.get("lock", []):
            for sig in (lk["while"], lk["until"]):
                if sig not in SEED_SIGNALS and not _family_match(sig, published):
                    problems.append(
                        f"{name}: lock signal '{sig}' has no publisher or seed"
                    )
    return problems


def main():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    problems = check(catalog)
    if problems:
        sys.stderr.write("check-catalog: FAIL\n  " + "\n  ".join(problems) + "\n")
        sys.exit(1)
    sys.stderr.write(
        f"check-catalog: clean - {len(catalog['stages'])} stages, all invariants hold\n"
    )


if __name__ == "__main__":
    main()
