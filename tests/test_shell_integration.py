from __future__ import annotations

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
    (bin_dir / "codex").write_text("#!/bin/sh\necho \"codex $*\"\n")
    (bin_dir / "claude").write_text("#!/bin/sh\necho \"claude $*\"\n")
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
