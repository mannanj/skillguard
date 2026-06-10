"""The four version declarations must always agree.

The installed Claude Code plugin only refreshes on a version bump, so manifest
drift (as happened when 0.1.0 manifests shipped alongside 0.2.0 code) means
real fixes silently never reach live installs. CI fails here before that can
happen; the .githooks/pre-push guard enforces the bump itself at push time.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from skillguard.cli import __version__ as cli_version

ROOT = Path(__file__).resolve().parent.parent


def _pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "pyproject.toml has no version field"
    return match.group(1)


def _plugin_version() -> str:
    return json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]


def _marketplace_version() -> str:
    data = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    plugins = data["plugins"]
    assert len(plugins) == 1, "marketplace.json should list exactly the skillguard plugin"
    return plugins[0]["version"]


def test_all_version_declarations_agree():
    versions = {
        "pyproject.toml": _pyproject_version(),
        "skillguard/cli.py __version__": cli_version,
        ".claude-plugin/plugin.json": _plugin_version(),
        ".claude-plugin/marketplace.json": _marketplace_version(),
    }
    assert len(set(versions.values())) == 1, f"version drift: {versions}"


def test_version_is_semver_shaped():
    assert re.fullmatch(r"\d+\.\d+\.\d+", cli_version), cli_version
