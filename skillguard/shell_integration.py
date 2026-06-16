from __future__ import annotations

from pathlib import Path


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
