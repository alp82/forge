"""Version / changelog checks for the 1.4.2 hook-port release.

Per CLAUDE.md's versioning rule, a workflow-surface change under agents/,
commands/, hooks/, or WORKFLOW.md earns a version bump, mirrored in both
plugin.json and marketplace.json, plus a CHANGELOG.md entry. This file is the
single release-version gate - it tracks the current release (it moved 1.3.6 ->
1.3.7 -> 1.3.8 -> 1.3.9 -> 1.3.10 -> 1.3.11 -> 1.3.12 -> 1.3.13 -> 1.3.14 ->
1.3.15 -> 1.3.16 -> 1.4.0 -> 1.4.1, now 1.4.1 -> 1.4.2 - a patch bump).

TC-VER-04 (soft prose-style check on the changelog entry) is intentionally
NOT authored here - it is human judgment, not a test, per the test plan.
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_JSON = REPO_ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE_JSON = REPO_ROOT / ".claude-plugin" / "marketplace.json"
CHANGELOG_MD = REPO_ROOT / "CHANGELOG.md"
README_MD = REPO_ROOT / "README.md"

EXPECTED_VERSION = "1.4.2"


def test_plugin_json_version_is_1_4_2():
    data = json.loads(PLUGIN_JSON.read_text())
    assert data.get("version") == EXPECTED_VERSION, (
        f"expected .claude-plugin/plugin.json version == {EXPECTED_VERSION!r}, "
        f"got {data.get('version')!r}"
    )


def test_marketplace_json_version_matches_plugin_json():
    marketplace = json.loads(MARKETPLACE_JSON.read_text())
    marketplace_version = marketplace.get("metadata", {}).get("version")
    assert marketplace_version == EXPECTED_VERSION, (
        f"expected .claude-plugin/marketplace.json metadata.version == "
        f"{EXPECTED_VERSION!r}, got {marketplace_version!r}"
    )
    plugin_version = json.loads(PLUGIN_JSON.read_text()).get("version")
    assert marketplace_version == plugin_version, (
        "marketplace.json and plugin.json versions must be identical; "
        f"marketplace={marketplace_version!r}, plugin={plugin_version!r}"
    )


def test_changelog_has_1_4_2_entry():
    text = CHANGELOG_MD.read_text()
    assert (
        f"## {EXPECTED_VERSION}" in text
    ), f"expected a '## {EXPECTED_VERSION}' entry heading in CHANGELOG.md"


def test_readme_version_badge_matches_plugin_json():
    """The README.md version badge is the third version mirror CLAUDE.md requires
    bumped in lockstep. Anchor on the shieldcn.dev badge URL shape (version-<semver>-)
    so the assertion survives line moves, and pin it to the same EXPECTED_VERSION."""
    text = README_MD.read_text()
    m = re.search(r"shieldcn\.dev/badge/version-(\d+\.\d+\.\d+)-", text)
    assert (
        m is not None
    ), "expected a shieldcn.dev version badge (version-<semver>-) in README.md"
    assert (
        m.group(1) == EXPECTED_VERSION
    ), f"expected README.md version badge == {EXPECTED_VERSION!r}, got {m.group(1)!r}"


def test_changelog_and_readme_bullets_match_for_current_version():
    """CHANGELOG.md and README.md's 'Latest updates' block are meant to carry the
    same bullets for the current release. Nothing else compares the bullet TEXT
    (only headings/version numbers are pinned elsewhere), so a future release
    could edit one and not the other and stay green. Read the version from
    plugin.json rather than hardcoding it, so this test keeps working release
    over release."""
    version = json.loads(PLUGIN_JSON.read_text()).get("version")

    changelog_text = CHANGELOG_MD.read_text()
    changelog_match = re.search(
        rf"## {re.escape(version)}[^\n]*\n(.*?)(?:\n## |\Z)",
        changelog_text,
        re.DOTALL,
    )
    assert (
        changelog_match is not None
    ), f"expected a '## {version}' entry in CHANGELOG.md"
    changelog_bullets = re.findall(r"^- (.+)$", changelog_match.group(1), re.MULTILINE)
    assert changelog_bullets, f"expected bullets under the '## {version}' entry"

    readme_text = README_MD.read_text()
    readme_match = re.search(
        r"## 📰 Latest updates\n(.*?)\n---", readme_text, re.DOTALL
    )
    assert readme_match is not None, "expected a '## 📰 Latest updates' section"

    for bullet in changelog_bullets:
        assert bullet in readme_match.group(1), (
            f"CHANGELOG.md bullet for {version} not found verbatim in README.md "
            f"'Latest updates' block: {bullet!r}"
        )


def test_readme_latest_updates_window_is_142_141_140():
    """The README '## 📰 Latest updates' section keeps a window of exactly three
    entries. This pins WHICH three remain after the 1.4.2 release: 1.4.2 enters
    at the top, 1.4.1 and 1.4.0 stay, 1.3.16 drops."""
    text = README_MD.read_text()
    m = re.search(r"## 📰 Latest updates\n(.*?)\n---", text, re.DOTALL)
    assert m is not None, "expected a '## 📰 Latest updates' section in README.md"
    versions = re.findall(r"\*\*(\d+\.\d+\.\d+)\*\*", m.group(1))
    assert versions == ["1.4.2", "1.4.1", "1.4.0"], (
        "README Latest updates window must be exactly "
        f"['1.4.2', '1.4.1', '1.4.0'] top-down; got {versions!r}"
    )
