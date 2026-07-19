#!/usr/bin/env python3
"""The only sanctioned way to change forge's version.

Every version string lives in more than one file (see scripts/version_mirrors.py).
Bumping them by hand drifted before - a mirror got missed and the release guard
went red for a whole minor series. This script rewrites every mirror in one shot
so a single commit lands them together, and scaffolds the matching CHANGELOG entry
for you to fill in. It never commits; you review the diff and commit yourself.

    python scripts/bump-version.py 2.4.0      # set an explicit version
    python scripts/bump-version.py --minor    # 2.3.1 -> 2.4.0
    python scripts/bump-version.py --patch     # 2.3.1 -> 2.3.2
    python scripts/bump-version.py --major     # 2.3.1 -> 3.0.0
    python scripts/bump-version.py --check      # audit only: are all mirrors in sync?
    python scripts/bump-version.py --minor --no-changelog   # skip the CHANGELOG stub

Run it from anywhere - paths resolve against the repo root, not the cwd.
"""

import argparse
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import version_mirrors as vm  # noqa: E402

CHANGELOG = vm.REPO_ROOT / "CHANGELOG.md"


def _bumped(current: str, level: str) -> str:
    major, minor, patch = (int(p) for p in current.split("."))
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def _run_check() -> int:
    """Report whether every mirror agrees with the canonical version."""
    canonical = vm.canonical_version()
    drift = vm.verify()
    if not drift:
        print(f"✓ all {len(vm.MIRRORS)} version mirrors agree at {canonical}")
        return 0
    print(f"✗ version drift against canonical {canonical}:", file=sys.stderr)
    for mirror, found in drift:
        print(f"    {mirror.relpath}: {found}  ({mirror.label})", file=sys.stderr)
    return 1


def _scaffold_changelog(new_version: str) -> None:
    """Insert a dated stub heading above the latest entry if one isn't there yet.
    The prose is yours to write - this only guarantees the guard-checked heading
    exists and points you at it."""
    text = CHANGELOG.read_text()
    heading = f"## {new_version}"
    if heading in text:
        return
    today = datetime.date.today().isoformat()
    stub = f"{heading} - {today}\n\n- _TODO: user-facing summary (see CONTRIBUTING.md § Changelog style)_\n\n"
    # Insert directly before the first existing release heading, so the new entry
    # sits at the top of the list but below the file's intro.
    anchor = text.find("\n## ")
    if anchor == -1:
        CHANGELOG.write_text(text.rstrip() + "\n\n" + stub)
    else:
        cut = anchor + 1  # keep the leading newline with the intro
        CHANGELOG.write_text(text[:cut] + stub + text[cut:])
    print(f"  scaffolded CHANGELOG.md {heading} - fill in the summary before committing")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("version", nargs="?", help="explicit target version, e.g. 2.4.0")
    group.add_argument("--major", action="store_const", const="major", dest="level")
    group.add_argument("--minor", action="store_const", const="minor", dest="level")
    group.add_argument("--patch", action="store_const", const="patch", dest="level")
    group.add_argument("--check", action="store_true", help="audit only, write nothing")
    parser.add_argument("--no-changelog", action="store_true", help="don't scaffold a CHANGELOG entry")
    args = parser.parse_args()

    if args.check:
        return _run_check()

    current = vm.canonical_version()
    target = args.version if args.version else _bumped(current, args.level)

    if not vm.SEMVER_RE.match(target):
        parser.error(f"not a semver string: {target!r}")
    if target == current:
        parser.error(f"target {target} equals the current version; nothing to bump")

    vm.set_all(target)
    print(f"bumped {current} -> {target} across {len(vm.MIRRORS)} mirrors:")
    for mirror in vm.MIRRORS:
        print(f"  {mirror.relpath}  ({mirror.label})")

    if not args.no_changelog:
        _scaffold_changelog(target)

    print(f"\nreview the diff, then commit all changes together (e.g. `git commit -am 'Release {target}'`)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
