from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from skillguard.shell_integration import write_shell_integration

pytestmark = pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh required")


def _fake_bin(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "skillguard").write_text("#!/bin/sh\necho 'SkillGuard: fake banner'\n")
    (bin_dir / "codex").write_text('#!/bin/sh\necho "codex $*"\n')
    (bin_dir / "claude").write_text('#!/bin/sh\necho "claude $*"\n')
    for p in bin_dir.iterdir():
        p.chmod(0o755)
    return bin_dir


def _run_zsh(tmp_path: Path, command: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["HOME"] = str(tmp_path)
    env["PATH"] = f"{tmp_path / 'bin'}:{env['PATH']}"
    env["SKILLGUARD_AGENT_SUMMARY_FORCE"] = "1"
    return subprocess.run(
        ["zsh", "-fc", f"source {tmp_path}/shell.sh; {command}"],
        capture_output=True,
        text=True,
        env=env,
    )


def test_shell_banner_shows_for_plain_agent_launch(tmp_path):
    _fake_bin(tmp_path)
    write_shell_integration(tmp_path / "shell.sh")

    r = _run_zsh(tmp_path, "codex")

    assert r.returncode == 0, r.stderr
    assert "SkillGuard: fake banner" in r.stdout
    assert "codex" in r.stdout


def test_shell_banner_is_suppressed_for_version_and_help(tmp_path):
    _fake_bin(tmp_path)
    write_shell_integration(tmp_path / "shell.sh")

    version = _run_zsh(tmp_path, "codex --version")
    help_out = _run_zsh(tmp_path, "claude --help")

    assert version.returncode == 0, version.stderr
    assert help_out.returncode == 0, help_out.stderr
    assert "SkillGuard: fake banner" not in version.stdout
    assert "SkillGuard: fake banner" not in help_out.stdout
    assert "codex --version" in version.stdout
    assert "claude --help" in help_out.stdout


def test_install_shell_integration_command_writes_shim_shell_and_zshrc(tmp_path):
    env = dict(os.environ)
    env["HOME"] = str(tmp_path)

    r = subprocess.run(
        [
            "python3",
            str(Path(__file__).resolve().parent.parent / "skillguard" / "cli.py"),
            "--install-shell-integration",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
    )

    assert r.returncode == 0, r.stderr
    shim = tmp_path / ".local" / "bin" / "skillguard"
    shell = tmp_path / ".claude" / "skillguard" / "shell.sh"
    command = tmp_path / ".claude" / "commands" / "skillguard.md"
    skill = tmp_path / ".claude" / "skills" / "skillguard" / "SKILL.md"
    zshrc = tmp_path / ".zshrc"
    assert shim.exists()
    assert shell.exists()
    assert command.exists()
    assert skill.exists()
    command_text = command.read_text()
    assert "allowed-tools:" in command_text
    assert str(shim) in command_text
    assert "--review" in command_text
    assert "Type allow" in command_text
    skill_text = skill.read_text()
    assert str(shim) in skill_text
    assert "--agent-summary" in skill_text
    assert "--review" in skill_text
    assert 'source "$HOME/.claude/skillguard/shell.sh"' in zshrc.read_text()
    assert "SkillGuard shell integration installed" in r.stdout


def test_install_shell_integration_writes_codex_plugin_command(tmp_path):
    env = dict(os.environ)
    env["HOME"] = str(tmp_path)

    r = subprocess.run(
        [
            "python3",
            str(Path(__file__).resolve().parent.parent / "skillguard" / "cli.py"),
            "--install-shell-integration",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
    )

    assert r.returncode == 0, r.stderr
    shim = tmp_path / ".local" / "bin" / "skillguard"
    codex_root = tmp_path / "plugins" / "skillguard"
    manifest = codex_root / ".codex-plugin" / "plugin.json"
    skill = codex_root / "skills" / "skillguard" / "SKILL.md"
    marketplace = tmp_path / ".agents" / "plugins" / "marketplace.json"

    assert manifest.exists()
    manifest_json = json.loads(manifest.read_text())
    assert manifest_json["name"] == "skillguard"
    assert manifest_json["version"] == "0.3.1"
    assert manifest_json["skills"] == "./skills/"
    assert manifest_json["interface"]["displayName"] == "SkillGuard"

    claude_skill = tmp_path / ".claude" / "skills" / "skillguard" / "SKILL.md"

    assert skill.exists()
    skill_text = skill.read_text()
    assert skill_text == claude_skill.read_text()
    assert "name: skillguard" in skill_text
    assert "Use when reviewing SkillGuard findings" in skill_text
    assert str(shim) in skill_text
    assert "--agent-summary" in skill_text
    assert "--review" in skill_text

    assert not (codex_root / "commands").exists()

    assert marketplace.exists()
    marketplace_json = json.loads(marketplace.read_text())
    assert marketplace_json["name"] == "personal"
    entry = next(p for p in marketplace_json["plugins"] if p["name"] == "skillguard")
    assert entry["source"] == {"source": "local", "path": "./plugins/skillguard"}
    assert entry["policy"] == {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}


def test_install_shell_integration_removes_stale_codex_command_wrapper(tmp_path):
    stale = tmp_path / "plugins" / "skillguard" / "commands" / "skillguard.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("old command")

    env = dict(os.environ)
    env["HOME"] = str(tmp_path)

    r = subprocess.run(
        [
            "python3",
            str(Path(__file__).resolve().parent.parent / "skillguard" / "cli.py"),
            "--install-shell-integration",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
    )

    assert r.returncode == 0, r.stderr
    assert not stale.exists()
