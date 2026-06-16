# Task: Add Codex agent slash-command support for SkillGuard

**Status:** open
**Created:** 2026-06-16

## Goal

Make SkillGuard invokable from inside Codex agent sessions with a command like
`/skillguard`, matching the Claude-agent review experience while Claude Code
quota is blocked.

## Current State

- Claude plugin support landed in `b45a5ea Add SkillGuard agent slash command`.
- Claude plugin namespace command exists at `commands/skillguard.md`
  (`/skillguard:skillguard`).
- `skillguard --install-shell-integration` writes a user-level Claude command at
  `~/.claude/commands/skillguard.md`, enabling bare `/skillguard` for Claude.
- A full Claude run of `/skillguard` is blocked by weekly quota until
  2026-06-18 06:00 America/New_York, but after install it no longer returns
  `Unknown command`.
- Codex CLI is available:
  - `codex --version` -> `codex-cli 0.140.0`
  - `codex plugin --help` shows plugin add/list/marketplace/remove commands.
  - `/Users/manblack/.codex/.tmp/plugins/README.md` says Codex plugins use
    `.codex-plugin/plugin.json` and may include `commands/`.

## Requirements

1. Discover the Codex plugin/command format from local examples or official docs
   if local examples are insufficient.
2. Add a SkillGuard Codex command surface that can be invoked as `/skillguard`
   or the closest Codex-native equivalent.
3. Reuse the same SkillGuard CLI paths and review semantics:
   - `summary` -> `skillguard --agent-summary`
   - default/review -> cached review flow
   - `scan` -> `skillguard --target all --scope all --engines local`
   - `history` -> `skillguard --history 20`
   - `activity` -> `skillguard --activity 20`
   - `show <target>` -> `skillguard --show <target>`
4. Preserve the explicit review safety model:
   - `mark-fp` only when the user asks for it.
   - `ack` must require the user to type `allow`.
   - `next`, `show`, and `quit` must be non-mutating.
5. Add automated tests for:
   - Codex command file/manifests are included in the clean package or installed
     by setup.
   - Generated command content references the stable SkillGuard shim.
   - Command text includes `mark-fp`, `ack`, `Type allow`, `next`, `show`, and
     `quit`.
6. Test in a real Codex agent flow.

## Suggested Validation Commands

```bash
codex plugin --help
codex plugin list
codex exec "/skillguard summary"
codex exec "/skillguard"
printf 'q\n' | /Users/manblack/.local/bin/skillguard --review
printf '\nq\n' | /Users/manblack/.local/bin/skillguard --review
printf 'a\n\nq\n' | /Users/manblack/.local/bin/skillguard --review
```

If Codex requires a plugin marketplace entry before `codex exec` can discover
commands, document and automate that setup in a reversible local install path.

## Acceptance Criteria

- Codex can discover and invoke SkillGuard from an in-agent command flow.
- The first Codex run prints the cached SkillGuard summary or first review item.
- `next`, `show`, and ack-cancel are tested without mutating real triage state.
- Tests pass with `.venv/bin/python -m pytest`.
- `python3 scripts/build_plugin_package.py` still produces a clean plugin
  package with no dev artifacts.
- README or a short docs note explains the Claude vs Codex command surfaces
  without claiming broader agent support than has been implemented.
