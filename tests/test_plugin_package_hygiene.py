from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_plugin_source_does_not_point_at_dirty_repo_root():
    manifest = (ROOT / ".claude-plugin" / "marketplace.json").read_text()
    assert '"source": "./"' not in manifest


def test_plugin_ignore_or_package_builder_exists():
    assert (ROOT / ".claude-pluginignore").exists() or (
        ROOT / "scripts" / "build_plugin_package.py"
    ).exists()


def test_plugin_ships_interactive_skillguard_slash_command():
    command = ROOT / "commands" / "skillguard.md"
    text = command.read_text()

    assert "description:" in text
    assert "allowed-tools:" in text
    assert "--review" in text
    assert "mark-fp" in text
    assert "ack" in text
    assert "Type allow" in text
    assert "$ARGUMENTS" in text


def test_clean_package_includes_skillguard_slash_command():
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_plugin_package.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )

    assert r.returncode == 0, r.stderr
    packaged = ROOT / "dist" / "skillguard-plugin" / "commands" / "skillguard.md"
    assert packaged.exists()
