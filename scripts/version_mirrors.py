"""Single source of truth for every file that mirrors forge's version.

forge's version is stamped into several files that must always agree. Two tools
read this one list and nothing else, so the set of mirrors is defined exactly
once (CLAUDE.md doctrine hygiene: one home, not a second copy that rots):

- `scripts/bump-version.py` - the ONLY sanctioned writer. It rewrites every
  mirror below in one commit.
- `adapters/claude-code/hooks/tests/test_release_version.py` - the guard. It
  reads every mirror below and fails loudly on any drift.

`.claude-plugin/plugin.json` is CANONICAL: it is the first entry, and its version
is the truth every other mirror must equal. Each new adapter registers its own
manifest here when it lands (spec docs/spec/forge.md § 10 pt 4) - one line added
to `MIRRORS`, and both the writer and the guard pick it up with no other change.
"""

import re
from pathlib import Path

# scripts/ sits one level below the repo root.
REPO_ROOT = Path(__file__).resolve().parents[1]

# A dotted-semver, captured in exactly one group so read and write share it.
_SEMVER = r"(\d+\.\d+\.\d+)"


class Mirror:
    """One file that carries the version, plus the regex that finds it.

    The pattern must capture the semver in group 1 and match exactly once in the
    file - that single-match rule is the anchor's contract, enforced on both read
    and write so an ambiguous or stale pattern fails loud instead of silently
    editing the wrong line (or nothing).
    """

    def __init__(self, relpath: str, pattern: str, label: str):
        self.relpath = relpath
        self.path = REPO_ROOT / relpath
        self.regex = re.compile(pattern)
        self.label = label

    def _match(self) -> re.Match:
        text = self.path.read_text()
        matches = list(self.regex.finditer(text))
        if len(matches) != 1:
            raise ValueError(
                f"{self.relpath}: expected exactly one version match for "
                f"{self.label}, found {len(matches)} - the mirror pattern is "
                "stale or ambiguous"
            )
        return matches[0]

    def read(self) -> str:
        """The version currently stamped in this file."""
        return self._match().group(1)

    def write(self, new_version: str) -> str:
        """Replace only the captured version span, preserving the whole file
        byte-for-byte otherwise. Returns the version that was there before."""
        text = self.path.read_text()
        m = self._match()
        start, end = m.span(1)
        self.path.write_text(text[:start] + new_version + text[end:])
        return m.group(1)


# The mirrors, canonical first. Append one line per adapter as it lands.
MIRRORS = [
    Mirror(
        ".claude-plugin/plugin.json",
        r'"version":\s*"' + _SEMVER + r'"',
        "plugin.json version (canonical)",
    ),
    Mirror(
        ".claude-plugin/marketplace.json",
        r'"version":\s*"' + _SEMVER + r'"',
        "marketplace.json metadata.version",
    ),
    Mirror(
        "README.md",
        r"badge/version-" + _SEMVER + r"-",
        "README.md version badge",
    ),
    Mirror(
        "adapters/opencode/hooks/forge.js",
        r'FORGE_VERSION\s*=\s*"' + _SEMVER + r'"',
        "opencode adapter FORGE_VERSION stamp",
    ),
    Mirror(
        ".codex-plugin/plugin.json",
        r'"version":\s*"' + _SEMVER + r'"',
        "codex channel manifest version",
    ),
]

CANONICAL = MIRRORS[0]

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def canonical_version() -> str:
    """The version every other mirror must match."""
    return CANONICAL.read()


def verify():
    """Read every mirror and return the drifted ones as (mirror, found) pairs.

    An empty list means all mirrors agree with the canonical version. This is the
    read-audit both `--check` and the pytest guard run - one home for the check,
    so they can never disagree about what 'in sync' means.
    """
    canonical = canonical_version()
    drift = []
    for mirror in MIRRORS[1:]:
        found = mirror.read()
        if found != canonical:
            drift.append((mirror, found))
    return drift


def set_all(new_version: str) -> None:
    """Stamp `new_version` into every mirror. Raises before writing anything if
    the version is malformed; each mirror's single-match rule guards the rest."""
    if not SEMVER_RE.match(new_version):
        raise ValueError(f"not a semver string: {new_version!r}")
    for mirror in MIRRORS:
        mirror.write(new_version)
