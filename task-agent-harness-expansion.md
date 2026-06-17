# Task: Expand SkillGuard beyond Claude Code + MCP

**Status:** future
**Created:** 2026-06-16

## Goal

Make SkillGuard work across agent harnesses beyond today's Claude Code skills
and MCP servers, without turning the current landing page into roadmap copy.

## Current Landing Scope

The landing page should speak to what is true today:

- Claude Code skills and MCP servers are supported today.
- SkillGuard scans skill files, bundled scripts, MCP configs, launch commands,
  endpoint metadata, and env/header names while redacting secret values.
- The hook blocks unscanned or changed skills before Claude runs them.
- MCP tool calls are governed by `mcp_policy`; the current default is `enforce`,
  which blocks unscanned or critical/high MCP verdicts.
- Installation can be presented with a generic command first, but the product
  claim should not promise Codex, Gemini, or other harness support yet.

## Future Requirements

1. Define a harness-neutral target model for agent extensions:
   - Claude Code skills (already supported)
   - MCP servers (already supported)
   - Codex instructions/plugins, if a stable extension surface exists
   - Gemini CLI instructions/extensions, if a stable extension surface exists
   - Other agent harnesses only after their discovery, scan, and runtime
     enforcement points are verified
2. Split product copy into current truth and supported badges:
   - Badges should reflect implemented support, not future intent.
   - The hero can stay broad only after the scanner and enforcement path are
     broad.
3. Add discovery adapters per harness.
4. Add runtime enforcement adapters per harness where the harness exposes a
   reliable pre-execution hook.
5. Keep secret redaction and cache/history guarantees identical across harnesses.
6. Add fixtures and tests for every new adapter before updating marketing copy.

## Out Of Scope For Current Landing Revamp

- No "works with all agents" headline.
- No Codex/Gemini install carousel entries unless those commands are real.
- No promise that Codex, Gemini, or other harnesses are blocked at runtime unless
  their policy and hook behavior are implemented and verified in tests.

## Completion Criteria

- At least two non-Claude-Code harnesses have implemented discovery adapters.
- Runtime enforcement behavior is documented per harness: block, warn, or
  scan-only.
- Tests cover discovery, redaction, cache writes, and enforcement decisions for
  each adapter.
- The landing page is updated only after those tests pass.
