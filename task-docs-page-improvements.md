# Task: Docs Page Improvements

**Status:** open
**Created:** 2026-06-17

## Goal

Turn the current docs page from a minimal command table into a useful first-stop
reference for installing, running, configuring, and troubleshooting Gandalf.

## Current State

The docs page at `landing/public/docs/index.html` is intentionally small. It
has a header, a short command reference table, and links back home/source. It
does not yet explain installation paths, runtime behavior, MCP enforcement,
review workflows, cache behavior, or common failures.

## Direction

- Keep the docs page quiet, fast, and consistent with the landing page visual
  system.
- Add practical sections instead of marketing copy.
- Preserve the existing static deployment model: no build step and no client
  framework.
- Make the page scannable for users who are trying to install, run a scan, or
  understand why Gandalf blocked something.

## Proposed Sections

- Quick install
- First scan
- Claude Code plugin usage
- Codex/plugin usage
- Command reference
- MCP checks and enforcement modes
- Review, acknowledgement, and false-positive flow
- Cache and rescan behavior
- Local versus optional cloud engines
- Troubleshooting
- Security and privacy notes

## Files

- Docs page: `landing/public/docs/index.html`
- Landing page links: `landing/public/index.html`
- Command/source truth: `README.md`, `SECURITY.md`, `CHANGELOG.md`
- Tests: `tests/test_landing_page.py`

## Acceptance Criteria

- The docs page explains the primary install and first-scan path without sending
  users back to the README for basics.
- Command examples match the CLI behavior and existing tests.
- The page includes clear sections for MCP checks, review flow, and
  troubleshooting.
- Navigation back to the landing page and GitHub source remains available.
- The visual treatment matches the landing page without adding heavy assets or a
  build step.
- Existing landing/docs tests pass, with updated assertions for any intentional
  docs copy changes.
