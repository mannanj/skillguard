from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_plugin_source_does_not_point_at_dirty_repo_root():
    manifest = (ROOT / ".claude-plugin" / "marketplace.json").read_text()
    assert '"source": "./"' not in manifest


def test_plugin_ignore_or_package_builder_exists():
    assert (ROOT / ".claude-pluginignore").exists() or (
        ROOT / "scripts" / "build_plugin_package.py"
    ).exists()
