# Task: Claude-first command scope with future-agent badges

**Status:** open
**Created:** 2026-06-16

## Decision

Keep SkillGuard's active skill-scanning command surface Claude-first for now.
Do not ship half-enabled Codex or generic "all agents" scanning until discovery,
cache keys, hook semantics, and tests cover those roots deliberately.

Where the product needs to hint at future coverage, use compact status badges:

| Agent | Badge | Meaning |
|---|---|---|
| Claude | `enabled` | Current supported skill scan/hook path |
| Codex | `soon` | Planned, not active |

No paragraph explaining the roadmap in command output. Every word has to earn its
place.

## Why

Today's real protected path is Claude Code skills:

- `~/.claude/skills`
- project-local `.claude/skills`
- symlinked skills reachable from those directories

Other local skill roots exist (`~/.codex/skills`, `~/.agents/skills`,
`Documents/agent-scripts/skills`), but SkillGuard does not model them as first-class
agent scopes yet. Scanning them through temporary symlink corpora is useful for
research, not a product contract.

## Follow-up Work

1. Add an explicit agent/provider model before adding more roots.
2. Keep the default command scoped to Claude until another provider has equivalent
   tests and cache behavior.
3. If command help, docs, or landing copy mention agent coverage, use badge-style
   copy only:
   - `Claude enabled`
   - `Codex soon`
4. Add tests that prove unsupported provider roots are not silently implied by
   `--scope all`.
5. When Codex support becomes real, add fixtures for Codex system/user skill roots,
   duplicate-name behavior, cache naming, and reporting.

## Acceptance Criteria

- `skillguard --target skills --scope all` continues to mean supported Claude skill
  roots only.
- Help/docs do not promise generic "all agents" scanning.
- Any future-facing provider language is badge-sized and unambiguous.
- A future Codex implementation cannot land without discovery, cache, report, and
  regression tests.
