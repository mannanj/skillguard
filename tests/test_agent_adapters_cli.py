from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_install_agent_adapters_command_writes_project_adapter(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    env = dict(os.environ)
    env["HOME"] = str(tmp_path / "home")

    result = subprocess.run(
        [
            "python3",
            str(ROOT / "skillguard" / "cli.py"),
            "--install-agent-adapters",
            ".",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(project),
    )

    assert result.returncode == 0, result.stderr
    assert "SkillGuard agent adapters installed" in result.stdout
    assert "agents_md:" in result.stdout
    assert "13 agent surfaces" in (project / "AGENTS.md").read_text()
    assert (
        json.loads((project / ".gemini" / "settings.json").read_text())["contextFileName"]
        == "AGENTS.md"
    )
    assert (project / ".aider.conf.yml").read_text() == "read: AGENTS.md\n"
