"""Version / changelog release gate.

Per CLAUDE.md's versioning rule, a workflow-surface change under skills/ or
adapters/ earns a version bump, mirrored in three places that must always agree:
`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`
(`metadata.version`), and the README version badge - plus a matching
CHANGELOG.md entry.

The gate reads the canonical version from plugin.json and asserts the other
mirrors match it, rather than hardcoding a release number here. A hardcoded
number rots: it silently went stale across the 2.0.0 rename, red for every
2.x release until noticed. Reading plugin.json makes the invariant - "the
three mirrors and the changelog agree" - the thing under test, release over
release, with nothing to bump by hand.

TC-VER-04 (soft prose-style check on the changelog entry) is intentionally
NOT authored here - it is human judgment, not a test, per the test plan.
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
PLUGIN_JSON = REPO_ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE_JSON = REPO_ROOT / ".claude-plugin" / "marketplace.json"
CHANGELOG_MD = REPO_ROOT / "CHANGELOG.md"
README_MD = REPO_ROOT / "README.md"


def _plugin_version():
    return json.loads(PLUGIN_JSON.read_text()).get("version")


def test_plugin_json_version_is_semver():
    version = _plugin_version()
    assert version is not None and re.fullmatch(r"\d+\.\d+\.\d+", version), (
        f"expected .claude-plugin/plugin.json version to be a semver string, "
        f"got {version!r}"
    )


def test_marketplace_json_version_matches_plugin_json():
    marketplace_version = (
        json.loads(MARKETPLACE_JSON.read_text()).get("metadata", {}).get("version")
    )
    plugin_version = _plugin_version()
    assert marketplace_version == plugin_version, (
        "marketplace.json and plugin.json versions must be identical; "
        f"marketplace={marketplace_version!r}, plugin={plugin_version!r}"
    )


def test_changelog_has_current_version_entry():
    version = _plugin_version()
    text = CHANGELOG_MD.read_text()
    assert (
        f"## {version}" in text
    ), f"expected a '## {version}' entry heading in CHANGELOG.md"


def test_readme_version_badge_matches_plugin_json():
    """The README.md version badge is the third version mirror CLAUDE.md requires
    bumped in lockstep. Anchor on the shieldcn.dev badge URL shape (version-<semver>-)
    so the assertion survives line moves, and pin it to the canonical plugin version."""
    text = README_MD.read_text()
    m = re.search(r"shieldcn\.dev/badge/version-(\d+\.\d+\.\d+)-", text)
    assert (
        m is not None
    ), "expected a shieldcn.dev version badge (version-<semver>-) in README.md"
    assert m.group(1) == _plugin_version(), (
        f"expected README.md version badge == {_plugin_version()!r}, "
        f"got {m.group(1)!r}"
    )
