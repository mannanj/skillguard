from __future__ import annotations

import json
from pathlib import Path

from skillguard.agent_adapters import (
    SUPPORTED_AGENT_ADAPTERS,
    agent_adapter_source,
    supported_agent_count,
    write_project_agent_adapters,
)


def test_supported_agent_adapter_count_is_explicitly_thirteen() -> None:
    names = [adapter.name for adapter in SUPPORTED_AGENT_ADAPTERS]

    assert supported_agent_count() == 13
    assert len(names) == 13
    assert len(set(names)) == 13
    assert "Claude Code" in names
    assert "Codex" in names
    assert "Cursor" in names
    assert "Windsurf" in names
    assert "Gemini CLI" in names
    assert "GitHub Copilot coding agent" in names


def test_agent_adapter_source_names_supported_agents_and_cli() -> None:
    source = agent_adapter_source("/tmp/bin/skillguard")

    assert "13 agent surfaces" in source
    assert "/tmp/bin/skillguard --agent-summary" in source
    assert "/tmp/bin/skillguard --review" in source
    assert "Claude Code" in source
    assert "Codex" in source
    assert "Gemini CLI" in source
    assert "GitHub Copilot coding agent" in source
    assert "Do not mark a finding false positive" in source
    assert "2 agents" not in source


def test_write_project_agent_adapters_creates_repo_files(tmp_path: Path) -> None:
    changed = write_project_agent_adapters(tmp_path, "/tmp/bin/skillguard")

    agents = tmp_path / "AGENTS.md"
    gemini = tmp_path / ".gemini" / "settings.json"
    aider = tmp_path / ".aider.conf.yml"

    assert changed["agents_md"] == str(agents)
    assert changed["gemini_settings"] == str(gemini)
    assert changed["aider_config"] == str(aider)
    assert "13 agent surfaces" in agents.read_text()
    assert "/tmp/bin/skillguard --agent-summary" in agents.read_text()
    assert json.loads(gemini.read_text())["contextFileName"] == "AGENTS.md"
    assert aider.read_text() == "read: AGENTS.md\n"


def test_write_project_agent_adapters_is_idempotent_and_preserves_settings(
    tmp_path: Path,
) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# Project\n\nKeep this.\n")
    gemini = tmp_path / ".gemini" / "settings.json"
    gemini.parent.mkdir()
    gemini.write_text(json.dumps({"theme": "GitHub", "contextFileName": "GEMINI.md"}))
    aider = tmp_path / ".aider.conf.yml"
    aider.write_text("model: sonnet\n")

    write_project_agent_adapters(tmp_path, "skillguard")
    write_project_agent_adapters(tmp_path, "skillguard")

    agents_text = agents.read_text()
    assert agents_text.count("<!-- skillguard-agent-adapter:start -->") == 1
    assert agents_text.startswith("# Project\n\nKeep this.")

    settings = json.loads(gemini.read_text())
    assert settings["theme"] == "GitHub"
    assert settings["contextFileName"] == ["GEMINI.md", "AGENTS.md"]

    aider_text = aider.read_text()
    assert "model: sonnet" in aider_text
    assert aider_text.count("read: AGENTS.md") == 1
