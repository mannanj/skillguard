---
description: Review SkillGuard findings and scan state from inside an agent session
argument-hint: "[review|summary|scan|history|activity|show <target>]"
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py":*)
---

# SkillGuard

User arguments: $ARGUMENTS

Use the SkillGuard CLI bundled with this plugin:

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

If the user passes other SkillGuard CLI arguments, run them with the same plugin-local CLI path.

## Interactive Review Flow

1. Run the cached summary:

   ```
   "${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py" --agent-summary
   ```

2. Display the first active review item without mutating state:

   ```
   printf 'q\n' | "${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py" --review
   ```

3. Ask the user what to do next. Offer exactly these actions:

   - `mark-fp`: reviewed benign; run `printf 'm\n' | "${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py" --review`
   - `ack`: allow despite risk. Before running it, ask the user to Type allow. Only after the user replies `allow`, run `printf 'a\nallow\n' | "${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py" --review`
   - `show`: show full target history; run `printf 's\nq\n' | "${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py" --review`
   - `next`: move to the next target without changing state. Run one blank line per target to skip, then `q`. For example, to show the second target, run `printf '\nq\n' | "${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py" --review`
   - `quit`: stop the review.

4. After `mark-fp` or confirmed `ack`, run the cached summary again and continue the flow if there are still active findings.

Keep the review conversational. Do not mark a finding false positive or acknowledge risk unless the user explicitly asks for that action.
