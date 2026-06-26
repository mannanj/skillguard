from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

from skillguard.agent_skill import agent_skill_source, claude_command_source, quoted_command

SHELL_SOURCE = """# SkillGuard shell integration. Sourced by ~/.zshrc.
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac

_skillguard_agent_should_summarize() {
  [ "${SKILLGUARD_AGENT_SUMMARY:-1}" = "0" ] && return 1
  if [ "${SKILLGUARD_AGENT_SUMMARY_FORCE:-0}" != "1" ]; then
    [ -t 0 ] && [ -t 1 ] || return 1
  fi
  case "${1:-}" in
    --version|-V|version|--help|-h|help|plugin|plugins|mcp|auth)
      return 1
      ;;
  esac
  return 0
}

_skillguard_agent_summary() {
  _skillguard_agent_should_summarize "$@" || return 0
  if command -v skillguard >/dev/null 2>&1; then
    command skillguard --agent-summary 2>/dev/null || true
  elif [ -x "$HOME/.local/bin/skillguard" ]; then
    "$HOME/.local/bin/skillguard" --agent-summary 2>/dev/null || true
  fi
}

claude() {
  _skillguard_agent_summary "$@"
  command claude "$@"
}

codex() {
  _skillguard_agent_summary "$@"
  command codex "$@"
}
"""


def write_shell_integration(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SHELL_SOURCE)


def installed_cli_command() -> str:
    return f"python3 {Path(sys.argv[0]).resolve()}"


def write_skillguard_shim(path: Path, command: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    target = command or installed_cli_command()
    path.write_text(f'#!/bin/sh\nexec {target} "$@"\n')
    path.chmod(0o755)


def write_user_slash_command(path: Path, skillguard_path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    command = quoted_command(skillguard_path)
    path.write_text(claude_command_source(command, allowed_tools_command=skillguard_path))


def write_user_agent_skill(path: Path, skillguard_path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(agent_skill_source(quoted_command(skillguard_path)))


def _project_version() -> str:
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        text = pyproject.read_text()
    except OSError:
        return "0.3.1"
    in_project = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "[project]":
            in_project = True
            continue
        if in_project and stripped.startswith("["):
            break
        if in_project:
            match = re.fullmatch(r'version\s*=\s*"([^"]+)"', stripped)
            if match:
                return match.group(1)
    return "0.3.1"


def codex_plugin_manifest() -> dict:
    return {
        "name": "skillguard",
        "version": _project_version(),
        "description": (
            "Review SkillGuard cached findings and scan state from inside Codex sessions."
        ),
        "skills": "./skills/",
        "author": {"name": "Mannan Javid"},
        "homepage": "https://github.com/mannanj/skillguard",
        "repository": "https://github.com/mannanj/skillguard",
        "license": "AGPL-3.0-only OR LicenseRef-Commercial",
        "keywords": ["skillguard", "codex", "security", "skills", "mcp"],
        "interface": {
            "displayName": "SkillGuard",
            "shortDescription": "Review cached SkillGuard findings from Codex.",
            "longDescription": (
                "Adds a native Codex skill for SkillGuard cached risk summaries, "
                "read-only review navigation, and explicit false-positive or acknowledge actions."
            ),
            "developerName": "Mannan Javid",
            "category": "Developer Tools",
            "capabilities": ["Interactive"],
            "websiteURL": "https://github.com/mannanj/skillguard",
            "defaultPrompt": [
                "Review current SkillGuard findings",
                "Show the SkillGuard cached summary",
                "Inspect one SkillGuard target",
            ],
            "brandColor": "#C1121F",
        },
    }


def write_codex_skill(path: Path, skillguard_path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(agent_skill_source(quoted_command(skillguard_path)))


def write_codex_plugin(plugin_root: Path, skillguard_path: Path) -> None:
    stale_commands = plugin_root / "commands"
    if stale_commands.exists():
        shutil.rmtree(stale_commands)
    manifest = plugin_root / ".codex-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(codex_plugin_manifest(), indent=2) + "\n")
    write_codex_skill(plugin_root / "skills" / "skillguard" / "SKILL.md", skillguard_path)


def _skillguard_marketplace_entry() -> dict:
    return {
        "name": "skillguard",
        "source": {"source": "local", "path": "./plugins/skillguard"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": "Developer Tools",
    }


def write_codex_personal_marketplace(path: Path) -> None:
    if path.exists():
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            payload = {}
    else:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("name", "personal")
    interface = payload.get("interface")
    if not isinstance(interface, dict):
        payload["interface"] = {"displayName": "Personal"}
    else:
        interface.setdefault("displayName", "Personal")
    plugins = payload.get("plugins")
    if not isinstance(plugins, list):
        plugins = []
        payload["plugins"] = plugins

    entry = _skillguard_marketplace_entry()
    for index, plugin in enumerate(plugins):
        if isinstance(plugin, dict) and plugin.get("name") == "skillguard":
            plugins[index] = entry
            break
    else:
        plugins.append(entry)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def ensure_zshrc_sources(zshrc: Path, shell_path: Path) -> bool:
    zshrc.parent.mkdir(parents=True, exist_ok=True)
    if not zshrc.exists():
        zshrc.write_text("")
    text = zshrc.read_text()
    marker = "# >>> skillguard >>>"
    if marker in text:
        return False
    source_line = 'source "$HOME/.claude/skillguard/shell.sh"'
    if (
        shell_path
        != Path(os.environ.get("HOME", "~")).expanduser() / ".claude" / "skillguard" / "shell.sh"
    ):
        source_line = f'source "{shell_path}"'
    block = f"\n# >>> skillguard >>>\n{source_line}\n# <<< skillguard <<<\n"
    zshrc.write_text(text + block)
    return True


def install_shell_integration(home: Path | None = None, *, shell_only: bool = False) -> dict:
    root = home or Path(os.environ.get("HOME", "~")).expanduser()
    shell = root / ".claude" / "skillguard" / "shell.sh"
    write_shell_integration(shell)
    changed: dict[str, str | bool] = {"shell": str(shell)}
    if not shell_only:
        shim = root / ".local" / "bin" / "skillguard"
        write_skillguard_shim(shim)
        command = root / ".claude" / "commands" / "skillguard.md"
        write_user_slash_command(command, shim)
        skill = root / ".claude" / "skills" / "skillguard" / "SKILL.md"
        write_user_agent_skill(skill, shim)
        codex_plugin = root / "plugins" / "skillguard"
        write_codex_plugin(codex_plugin, shim)
        codex_marketplace = root / ".agents" / "plugins" / "marketplace.json"
        write_codex_personal_marketplace(codex_marketplace)
        zshrc = root / ".zshrc"
        changed["shim"] = str(shim)
        changed["command"] = str(command)
        changed["skill"] = str(skill)
        changed["codex_plugin"] = str(codex_plugin)
        changed["codex_marketplace"] = str(codex_marketplace)
        changed["zshrc"] = str(zshrc)
        changed["zshrc_updated"] = ensure_zshrc_sources(zshrc, shell)
    return changed
