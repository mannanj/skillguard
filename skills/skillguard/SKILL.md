---
name: skillguard
description: Use when reviewing SkillGuard findings, cached risk summaries, scan history, MCP/skill scan state, or false-positive/acknowledgement triage from an agent session.
---

# SkillGuard

Use the SkillGuard CLI to inspect cached findings and guide triage. Prefer read-only commands first; mutate triage state only after the user explicitly asks.

Use this exact SkillGuard command:

```
skillguard
```

## Routing

- No arguments, `review`, or `triage`: start the interactive review flow below.
- `summary` or `status`: run `skillguard --agent-summary`.
- `scan`: run `skillguard --target all --scope all --engines local`.
- `history`: run `skillguard --history 20`.
- `activity`: run `skillguard --activity 20`.
- `show <target>`: run `skillguard --show <target>`.

If the user asks for another SkillGuard CLI view, run it with this same command.

## Review Flow

1. Run `skillguard --agent-summary`.
2. Show the first active item without changing state:

   ```bash
   printf 'q\n' | skillguard --review
   ```

3. Ask the user what to do next. Offer exactly these actions:

   - `mark-fp`: reviewed benign; run `printf 'm\n' | skillguard --review`
   - `ack`: allow despite risk. Before running it, ask the user to Type allow. Only after the user replies `allow`, run `printf 'a\nallow\n' | skillguard --review`
   - `show`: show full target history; run `printf 's\nq\n' | skillguard --review`
   - `next`: move to the next target without changing state. Run one blank line per target to skip, then `q`; for example, `printf '\nq\n' | skillguard --review`
   - `quit`: stop the review

4. After `mark-fp` or confirmed `ack`, rerun `skillguard --agent-summary` and continue if active findings remain.

Do not mark a finding false positive or acknowledge risk unless the user explicitly asks for that action.
