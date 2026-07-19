"""Version / changelog release gate - the read side of the version-mirror guard.

Per CLAUDE.md's versioning rule, a workflow-surface change under skills/ or
adapters/ earns a version bump, mirrored across several files that must always
agree. The full set of mirrors is defined exactly once, in scripts/version_mirrors.py;
the same registry backs scripts/bump-version.py, the only sanctioned writer. This
gate imports that registry and asserts the invariant it describes - "every mirror
equals the canonical plugin.json version, and the changelog carries an entry" -
rather than restating the mirror list here where it would drift from the writer.

A hardcoded release number rots: it silently went stale across the 2.0.0 rename,
red for every 2.x release until noticed. Reading the canonical version from the
registry keeps the invariant, not a number, under test release over release.

TC-VER-04 (soft prose-style check on the changelog entry) is intentionally NOT
authored here - it is human judgment, not a test, per the test plan.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import version_mirrors as vm  # noqa: E402

CHANGELOG_MD = REPO_ROOT / "CHANGELOG.md"

# Non-canonical mirrors, id'd by path so a failure names the drifted file.
_OTHER_MIRRORS = vm.MIRRORS[1:]


def test_canonical_version_is_semver():
    version = vm.canonical_version()
    assert version is not None and vm.SEMVER_RE.match(version), (
        f"expected {vm.CANONICAL.relpath} version to be a semver string, "
        f"got {version!r}"
    )


@pytest.mark.parametrize("mirror", _OTHER_MIRRORS, ids=[m.relpath for m in _OTHER_MIRRORS])
def test_mirror_matches_canonical(mirror):
    """Every registered mirror carries the same version as canonical plugin.json.
    Registering a new adapter's manifest in version_mirrors.py extends this check
    automatically - no edit here."""
    found = mirror.read()
    canonical = vm.canonical_version()
    assert found == canonical, (
        f"{mirror.relpath} ({mirror.label}) version must equal the canonical "
        f"{vm.CANONICAL.relpath} version; mirror={found!r}, canonical={canonical!r}"
    )


def test_verify_reports_no_drift():
    """The registry's own audit - the exact check `bump-version.py --check` and
    the guard share - reports every mirror in sync."""
    drift = vm.verify()
    assert not drift, "version drift: " + ", ".join(
        f"{m.relpath}={found!r}" for m, found in drift
    )


def test_changelog_has_current_version_entry():
    version = vm.canonical_version()
    text = CHANGELOG_MD.read_text()
    assert (
        f"## {version}" in text
    ), f"expected a '## {version}' entry heading in CHANGELOG.md"
