from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AgentAdapter:
    key: str
    name: str
    surface: str


SUPPORTED_AGENT_ADAPTERS: tuple[AgentAdapter, ...] = (
    AgentAdapter("claude", "Claude Code", "native SKILL.md/plugin"),
    AgentAdapter("codex", "Codex", "native SKILL.md/plugin + AGENTS.md"),
    AgentAdapter("cursor", "Cursor", "AGENTS.md"),
    AgentAdapter("windsurf", "Windsurf", "AGENTS.md"),
    AgentAdapter("gemini", "Gemini CLI", "AGENTS.md via .gemini/settings.json"),
    AgentAdapter("copilot", "GitHub Copilot coding agent", "agent skills/custom instructions"),
    AgentAdapter("jules", "Jules", "AGENTS.md"),
    AgentAdapter("aider", "Aider", "AGENTS.md via .aider.conf.yml"),
    AgentAdapter("goose", "goose", "AGENTS.md"),
    AgentAdapter("opencode", "opencode", "AGENTS.md"),
    AgentAdapter("zed", "Zed", "AGENTS.md"),
    AgentAdapter("warp", "Warp", "AGENTS.md"),
    AgentAdapter("junie", "Junie", "AGENTS.md"),
)

START_MARKER = "<!-- skillguard-agent-adapter:start -->"
END_MARKER = "<!-- skillguard-agent-adapter:end -->"


def supported_agent_count() -> int:
    return len(SUPPORTED_AGENT_ADAPTERS)


def agent_adapter_source(command: str | Path = "skillguard") -> str:
    cmd = str(command)
    agents = "\n".join(
        f"- {adapter.name}: {adapter.surface}" for adapter in SUPPORTED_AGENT_ADAPTERS
    )
    return f"""{START_MARKER}
## SkillGuard

SkillGuard supports {supported_agent_count()} agent surfaces through this shared adapter plus its native SKILL.md/plugin packages.

Use SkillGuard when reviewing cached findings, scan history, MCP/skill scan state, or false-positive/acknowledgement triage from an agent session.

Run these commands:

- Summary: `{cmd} --agent-summary`
- Review: `{cmd} --review`
- Scan: `{cmd} --target all --scope all --engines local`
- History: `{cmd} --history 20`
- Activity: `{cmd} --activity 20`
- Show one target: `{cmd} --show <target>`

Review rules:

- Prefer read-only commands first.
- Do not mark a finding false positive unless the user explicitly asks.
- Do not acknowledge risk unless the user explicitly asks and then types `allow`.

Supported agent surfaces:

{agents}
{END_MARKER}
"""


def write_project_agent_adapters(project_dir: Path, command: str | Path = "skillguard") -> dict:
    project_dir.mkdir(parents=True, exist_ok=True)
    agents = project_dir / "AGENTS.md"
    gemini = project_dir / ".gemini" / "settings.json"
    aider = project_dir / ".aider.conf.yml"

    _write_agents_md(agents, agent_adapter_source(command))
    _write_gemini_settings(gemini)
    _write_aider_config(aider)

    return {
        "agents_md": str(agents),
        "gemini_settings": str(gemini),
        "aider_config": str(aider),
    }


def _write_agents_md(path: Path, block: str) -> None:
    if path.exists():
        text = path.read_text()
    else:
        text = "# AGENTS.md\n"

    if START_MARKER in text and END_MARKER in text:
        before, rest = text.split(START_MARKER, 1)
        _, after = rest.split(END_MARKER, 1)
        path.write_text(before.rstrip() + "\n\n" + block.rstrip() + "\n" + after)
        return

    sep = "\n\n" if text.strip() else ""
    path.write_text(text.rstrip() + sep + block)


def _write_gemini_settings(path: Path) -> None:
    if path.exists():
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError:
            payload = {}
    else:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    current = payload.get("contextFileName")
    if current is None:
        payload["contextFileName"] = "AGENTS.md"
    elif isinstance(current, str):
        if current != "AGENTS.md":
            payload["contextFileName"] = [current, "AGENTS.md"]
    elif isinstance(current, list):
        values = [str(item) for item in current]
        if "AGENTS.md" not in values:
            values.append("AGENTS.md")
        payload["contextFileName"] = values
    else:
        payload["contextFileName"] = "AGENTS.md"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _write_aider_config(path: Path) -> None:
    line = "read: AGENTS.md"
    if path.exists():
        text = path.read_text()
        if line in {item.strip() for item in text.splitlines()}:
            return
        if text and not text.endswith("\n"):
            text += "\n"
        path.write_text(text + line + "\n")
        return
    path.write_text(line + "\n")
