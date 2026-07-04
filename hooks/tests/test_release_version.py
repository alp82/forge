"""Version / changelog checks for the 1.3.7 trivial-path (direct-impl) release.

Per CLAUDE.md's versioning rule, a workflow-surface change under agents/,
commands/, hooks/, or WORKFLOW.md earns a patch bump, mirrored in both
plugin.json and marketplace.json, plus a CHANGELOG.md entry. This file is the
single release-version gate - it tracks the current release (it moved 1.3.5 ->
1.3.6, now 1.3.6 -> 1.3.7).

TC-VER-04 (soft prose-style check on the changelog entry) is intentionally
NOT authored here - it is human judgment, not a test, per the test plan.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_JSON = REPO_ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE_JSON = REPO_ROOT / ".claude-plugin" / "marketplace.json"
CHANGELOG_MD = REPO_ROOT / "CHANGELOG.md"

EXPECTED_VERSION = "1.3.7"


def test_plugin_json_version_is_1_3_7():
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


def test_changelog_has_1_3_7_entry():
    text = CHANGELOG_MD.read_text()
    assert (
        f"## {EXPECTED_VERSION}" in text
    ), f"expected a '## {EXPECTED_VERSION}' entry heading in CHANGELOG.md"
