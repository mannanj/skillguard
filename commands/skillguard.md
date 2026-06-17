---
description: Review SkillGuard findings and scan state from inside an agent session
argument-hint: "[review|summary|scan|history|activity|show <target>]"
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py":*)
---

# SkillGuard

User arguments: $ARGUMENTS

Use the SkillGuard CLI to inspect cached findings and guide triage. Prefer read-only commands first; mutate triage state only after the user explicitly asks.

Use this exact SkillGuard command:

```
"${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py"
```

## Routing

- No arguments, `review`, or `triage`: start the interactive review flow below.
- `summary` or `status`: run `"${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py" --agent-summary`.
- `scan`: run `"${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py" --target all --scope all --engines local`.
- `history`: run `"${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py" --history 20`.
- `activity`: run `"${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py" --activity 20`.
- `show <target>`: run `"${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py" --show <target>`.

If the user passes other SkillGuard CLI arguments, run them with this same command.

## Review Flow

1. Run `"${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py" --agent-summary`.
2. Show the first active item without changing state:

   ```bash
   printf 'q\n' | "${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py" --review
   ```

3. Ask the user what to do next. Offer exactly these actions:

   - `mark-fp`: reviewed benign; run `printf 'm\n' | "${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py" --review`
   - `ack`: allow despite risk. Before running it, ask the user to Type allow. Only after the user replies `allow`, run `printf 'a\nallow\n' | "${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py" --review`
   - `show`: show full target history; run `printf 's\nq\n' | "${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py" --review`
   - `next`: move to the next target without changing state. Run one blank line per target to skip, then `q`; for example, `printf '\nq\n' | "${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py" --review`
   - `quit`: stop the review

4. After `mark-fp` or confirmed `ack`, rerun `"${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py" --agent-summary` and continue if active findings remain.

Do not mark a finding false positive or acknowledge risk unless the user explicitly asks for that action.
