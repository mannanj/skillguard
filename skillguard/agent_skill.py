from __future__ import annotations

from pathlib import Path

SKILL_DESCRIPTION = (
    "Use when reviewing SkillGuard findings, cached risk summaries, scan history, "
    "MCP/skill scan state, or false-positive/acknowledgement triage from an agent session."
)

ARGUMENT_HINT = "[review|summary|scan|history|activity|show <target>]"


def quoted_command(command: str | Path) -> str:
    escaped = str(command).replace('"', '\\"')
    return f'"{escaped}"'


def _workflow_source(command: str, *, include_arguments: bool = False) -> str:
    arguments = "\nUser arguments: $ARGUMENTS\n" if include_arguments else ""
    other_args = (
        "\nIf the user passes other SkillGuard CLI arguments, run them with this same command.\n"
        if include_arguments
        else "\nIf the user asks for another SkillGuard CLI view, run it with this same command.\n"
    )
    return f"""# SkillGuard
{arguments}
Use the SkillGuard CLI to inspect cached findings and guide triage. Prefer read-only commands first; mutate triage state only after the user explicitly asks.

Use this exact SkillGuard command:

```
{command}
```

## Routing

- No arguments, `review`, or `triage`: start the interactive review flow below.
- `summary` or `status`: run `{command} --agent-summary`.
- `scan`: run `{command} --target all --scope all --engines local`.
- `history`: run `{command} --history 20`.
- `activity`: run `{command} --activity 20`.
- `show <target>`: run `{command} --show <target>`.
{other_args}
## Review Flow

1. Run `{command} --agent-summary`.
2. Show the first active item without changing state:

   ```bash
   printf 'q\\n' | {command} --review
   ```

3. Ask the user what to do next. Offer exactly these actions:

   - `mark-fp`: reviewed benign; run `printf 'm\\n' | {command} --review`
   - `ack`: allow despite risk. Before running it, ask the user to Type allow. Only after the user replies `allow`, run `printf 'a\\nallow\\n' | {command} --review`
   - `show`: show full target history; run `printf 's\\nq\\n' | {command} --review`
   - `next`: move to the next target without changing state. Run one blank line per target to skip, then `q`; for example, `printf '\\nq\\n' | {command} --review`
   - `quit`: stop the review

4. After `mark-fp` or confirmed `ack`, rerun `{command} --agent-summary` and continue if active findings remain.

Do not mark a finding false positive or acknowledge risk unless the user explicitly asks for that action.
"""


def agent_skill_source(command: str | Path = "skillguard") -> str:
    return f"""---
name: skillguard
description: {SKILL_DESCRIPTION}
---

{_workflow_source(str(command))}"""


def claude_command_source(
    command: str | Path,
    *,
    allowed_tools_command: str | Path | None = None,
) -> str:
    allowed = str(allowed_tools_command or command).strip('"').replace('"', '\\"')
    return f"""---
description: Review SkillGuard findings and scan state from inside an agent session
argument-hint: "{ARGUMENT_HINT}"
allowed-tools: Bash("{allowed}":*)
---

{_workflow_source(str(command), include_arguments=True)}"""
