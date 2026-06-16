from __future__ import annotations

import os
import sys
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


def installed_cli_command() -> str:
    return f"python3 {Path(sys.argv[0]).resolve()}"


def write_skillguard_shim(path: Path, command: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    target = command or installed_cli_command()
    path.write_text(f'#!/bin/sh\nexec {target} "$@"\n')
    path.chmod(0o755)


def user_slash_command_source(skillguard_path: Path) -> str:
    command = str(skillguard_path).replace('"', '\\"')
    return f"""---
description: Review SkillGuard findings and scan state
argument-hint: "[review|summary|scan|history|activity|show <target>]"
allowed-tools: Bash("{command}":*)
---

# SkillGuard

User arguments: $ARGUMENTS

Use this exact SkillGuard command:

```
"{command}"
```

## Routing

- No arguments, `review`, or `triage`: start the interactive review flow below.
- `summary` or `status`: run `"{command}" --agent-summary`.
- `scan`: run `"{command}" --target all --scope all --engines local`.
- `history`: run `"{command}" --history 20`.
- `activity`: run `"{command}" --activity 20`.
- `show <target>`: run `"{command}" --show <target>`.

If the user passes other SkillGuard CLI arguments, run them with this same command.

## Interactive Review Flow

1. Run `"{command}" --agent-summary`.
2. Display the first active review item without mutating state:

   ```
   printf 'q\\n' | "{command}" --review
   ```

3. Ask the user what to do next. Offer exactly these actions:

   - `mark-fp`: reviewed benign; run `printf 'm\\n' | "{command}" --review`
   - `ack`: allow despite risk. Before running it, ask the user to Type allow. Only after the user replies `allow`, run `printf 'a\\nallow\\n' | "{command}" --review`
   - `show`: show full target history; run `printf 's\\nq\\n' | "{command}" --review`
   - `next`: move to the next target without changing state. Run one blank line per target to skip, then `q`. For example, to show the second target, run `printf '\\nq\\n' | "{command}" --review`
   - `quit`: stop the review.

4. After `mark-fp` or confirmed `ack`, run the cached summary again and continue the flow if there are still active findings.

Keep the review conversational. Do not mark a finding false positive or acknowledge risk unless the user explicitly asks for that action.
"""


def write_user_slash_command(path: Path, skillguard_path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(user_slash_command_source(skillguard_path))


def ensure_zshrc_sources(zshrc: Path, shell_path: Path) -> bool:
    zshrc.parent.mkdir(parents=True, exist_ok=True)
    if not zshrc.exists():
        zshrc.write_text("")
    text = zshrc.read_text()
    marker = "# >>> skillguard >>>"
    if marker in text:
        return False
    source_line = 'source "$HOME/.claude/skillguard/shell.sh"'
    if shell_path != Path(os.environ.get("HOME", "~")).expanduser() / ".claude" / "skillguard" / "shell.sh":
        source_line = f'source "{shell_path}"'
    block = f"\n# >>> skillguard >>>\n{source_line}\n# <<< skillguard <<<\n"
    zshrc.write_text(text + block)
    return True


def install_shell_integration(home: Path | None = None, *, shell_only: bool = False) -> dict:
    root = home or Path(os.environ.get("HOME", "~")).expanduser()
    shell = root / ".claude" / "skillguard" / "shell.sh"
    write_shell_integration(shell)
    changed = {"shell": str(shell)}
    if not shell_only:
        shim = root / ".local" / "bin" / "skillguard"
        write_skillguard_shim(shim)
        command = root / ".claude" / "commands" / "skillguard.md"
        write_user_slash_command(command, shim)
        zshrc = root / ".zshrc"
        changed["shim"] = str(shim)
        changed["command"] = str(command)
        changed["zshrc"] = str(zshrc)
        changed["zshrc_updated"] = ensure_zshrc_sources(zshrc, shell)
    return changed
