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
OPENCODE_FORGE_JS = REPO_ROOT / "adapters" / "opencode" / "hooks" / "forge.js"
CODEX_PLUGIN_JSON = REPO_ROOT / ".codex-plugin" / "plugin.json"
GEMINI_EXTENSION_JSON = REPO_ROOT / "gemini-extension.json"


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


def test_opencode_plugin_version_stamp_matches_plugin_json():
    """adapters/opencode/hooks/forge.js is the fourth version mirror (spec § 10,
    #43 pt 4: "each new adapter registers its manifest path when it lands").
    Its FORGE_VERSION const is baked into the plugin artifact itself, so this
    gate reads it by regex - same pattern as the README badge check above -
    rather than importing the module (forge.js runs under opencode's Bun/ESM
    and has no reason to be import-safe from a pytest process)."""
    assert OPENCODE_FORGE_JS.exists(), (
        f"expected {OPENCODE_FORGE_JS} to exist so its FORGE_VERSION stamp "
        "can be checked against plugin.json (adapter-contract release gate)"
    )
    text = OPENCODE_FORGE_JS.read_text()
    m = re.search(r'FORGE_VERSION\s*=\s*"(\d+\.\d+\.\d+)"', text)
    assert m is not None, (
        f'expected a `FORGE_VERSION = "x.y.z"` stamp in {OPENCODE_FORGE_JS}'
    )
    assert m.group(1) == _plugin_version(), (
        f"expected adapters/opencode/hooks/forge.js FORGE_VERSION == "
        f"{_plugin_version()!r}, got {m.group(1)!r}"
    )


def test_codex_plugin_version_matches_plugin_json():
    """.codex-plugin/plugin.json is the fifth version mirror (spec § 10, #43
    pt 4: "each new adapter registers its manifest path when it lands") - the
    codex channel manifest at repo root, stamped with the one repo-wide
    version per contract § 7."""
    assert CODEX_PLUGIN_JSON.exists(), (
        f"expected {CODEX_PLUGIN_JSON} to exist so the codex channel manifest "
        "version can be checked against plugin.json (adapter-contract release gate)"
    )
    codex_version = json.loads(CODEX_PLUGIN_JSON.read_text()).get("version")
    assert codex_version == _plugin_version(), (
        ".codex-plugin/plugin.json and .claude-plugin/plugin.json versions "
        f"must be identical; codex={codex_version!r}, plugin={_plugin_version()!r}"
    )


def test_gemini_extension_version_matches_plugin_json():
    """gemini-extension.json is the sixth version mirror (spec § 10, #43 pt 4:
    "each new adapter registers its manifest path when it lands") - the gemini
    channel manifest at repo root, stamped with the one repo-wide version per
    contract § 7."""
    assert GEMINI_EXTENSION_JSON.exists(), (
        f"expected {GEMINI_EXTENSION_JSON} to exist so the gemini channel manifest "
        "version can be checked against plugin.json (adapter-contract release gate)"
    )
    gemini_version = json.loads(GEMINI_EXTENSION_JSON.read_text()).get("version")
    assert gemini_version == _plugin_version(), (
        "gemini-extension.json and .claude-plugin/plugin.json versions "
        f"must be identical; gemini={gemini_version!r}, plugin={_plugin_version()!r}"
    )
