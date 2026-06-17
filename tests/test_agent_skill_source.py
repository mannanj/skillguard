from __future__ import annotations

from pathlib import Path

from skillguard.agent_skill import (
    agent_skill_source,
    claude_command_source,
    quoted_command,
)

ROOT = Path(__file__).resolve().parent.parent


def test_repo_skill_is_generated_from_shared_agent_skill_source():
    skill = ROOT / "skills" / "skillguard" / "SKILL.md"

    assert skill.read_text() == agent_skill_source("skillguard")


def test_plugin_command_is_generated_from_shared_agent_skill_source():
    command = ROOT / "commands" / "skillguard.md"
    plugin_cli = quoted_command("${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py")

    assert command.read_text() == claude_command_source(
        plugin_cli,
        allowed_tools_command="${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py",
    )
