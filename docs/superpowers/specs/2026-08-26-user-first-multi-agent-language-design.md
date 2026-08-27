# User-First Multi-Agent Language Design

**Date:** 2026-08-26

**Status:** Approved for autonomous execution

## Objective

Make SkillGuard understandable before explaining how it is built. Remove
low-value implementation language from the README opening, describe the product
as protection for coding agents rather than a Claude-only tool, and move
platform-specific technical boundaries into the sections where readers expect
them.

The change must remain precise. SkillGuard supports scanning and review across
13 agent surfaces, but automatic runtime protection varies by host.

## Selected Approach

Use a user-first language hierarchy:

1. **Opening:** problem, protection, and outcome in plain language.
2. **What It Does:** user-visible actions and benefits.
3. **Quick Start and support:** accurate platform choices and capabilities.
4. **Architecture onward:** implementation detail for evaluators and
   contributors.

Rejected alternatives:

- An engineer-first opening would preserve the current jargon problem.
- A minimal marketing opening would be readable but too vague for a security
  product that needs clear trust boundaries.

## Opening Design

The first paragraph will say, in substance:

> SkillGuard protects coding agents from malicious skills and MCP servers. It
> checks them before use, explains what it finds, and blocks unsafe or
> unreviewed tools where the agent supports automatic enforcement.

The opening will not mention Python, SQLite, JSON, regexes, materialization,
PreToolUse, model-facing instructions, cache internals, or engine orchestration.
Those details remain available later.

The demo caption will explain the visible outcome rather than name the hook
boundary.

## Product-Language Design

`What It Does` will use outcome-led verbs:

- checks skills and MCP servers before use;
- catches hidden instructions, credential theft, data leaks, and dangerous
  commands;
- explains the evidence so a person can review it;
- blocks risky or unreviewed tools on supported runtime surfaces;
- remembers scans and review decisions;
- works through agent integrations, repository adapters, and the CLI.

Technical detection categories may appear as concrete examples, but the copy
must not explain file walkers, data structures, or persistence mechanisms in
the opening sections.

## Platform Positioning

The README will use `coding agents` or `agent tools` as the default product
language. Claude Code appears as one supported platform, not as the product
definition.

The capability table will state:

| Platform | Installed experience | Automatic protection |
|---|---|---|
| Claude Code | Native Agent Skill, CLI, review flow | Skills and MCP tools |
| Codex | Native Agent Skill, CLI, review flow | MCP tools after trusting the installed hook; skill loading is not exposed as a hook event |
| Cursor, Windsurf, Gemini CLI, GitHub Copilot coding agent, Jules, Aider, goose, opencode, Zed, Warp, Junie | Repository instructions plus CLI review | Depends on host hook support; no universal enforcement claim |

To make the Codex row true at publication time, the existing local installer
work that registers `~/.codex/hooks.json` will ship in the same release with its
tests and required synchronized version bump.

## Technical Detail Boundaries

Keep technical precision where it helps:

- `Architecture` may explain discovery, redaction, engines, cache/history, and
  host hooks.
- `Tech Stack` and `Repo Layout` remain technical references.
- `Configuration`, `Optional Detection Engines`, `Adding a Detection Engine`,
  `Development`, `Privacy`, and `License` retain necessary exact terms.

Rewrite explanatory prose in these sections when a shorter ordinary-language
sentence communicates the same fact. Do not remove commands, configuration
names, security limitations, privacy warnings, or license obligations.

## Release Scope

The release will include only the files needed to make the language and support
claims true:

- `README.md` language and capability table;
- Codex MCP-hook installer code and installer tests already present locally;
- production landing/docs copy that tells Codex users to trust the hook;
- synchronized `0.3.2` version declarations;
- changelog and security-boundary corrections required by that release.

Experimental Gandalf pages/assets, raw image responses, local skill packages,
Wrangler account cache data, and unrelated research/task files remain excluded.

## Validation

- Confirm the opening contains none of the banned implementation-first terms.
- Confirm every named platform appears in the adapter registry or native
  packaging.
- Confirm the Codex hook is idempotent and preserves unrelated hooks.
- Confirm all four release version declarations match.
- Run link checks, `git diff --check`, and the full test suite.
- Inspect the staged file list before committing.
- Push the release to GitHub, deploy a clean committed production bundle, and
  verify the public endpoints.

## Acceptance Criteria

- A reader can explain SkillGuard after reading only the opening and `What It
  Does`.
- Claude Code is no longer the product's default identity.
- Platform support is broad but does not imply equal runtime capabilities.
- Codex MCP protection is released before the README claims it.
- Technical reference material remains accurate and discoverable.
- No unrelated or generated local files are pushed or deployed.
