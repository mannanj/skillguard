# Changelog

All notable changes to SkillGuard are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added
- **False-positive triage**: `skillguard --mark-fp NAME` suppresses all of a skill's current non-info findings; `--unmark-fp NAME` undoes it. Marks persist across re-scans in `~/.claude/skillguard-cache/_triage.json`, keyed by engine + category + file + message (line numbers ignored, so doc edits don't invalidate marks — but new findings always count). The hook status line shows `clean (N triaged FP)`, and table/JSON/markdown reports exclude triaged findings from verdicts while keeping them in the JSON for full fidelity
- Cache entries now store structured `findings` (full finding objects) and `triaged_fp_count` alongside the existing summary fields

### Planned
- Plugin-namespaced skill resolution for the TOCTOU mtime guard

## [0.2.0] — 2026-06-05

First PyPI release — `pip install skillguard` / `uvx skillguard`.

### Changed
- **License: relicensed from Apache-2.0 to dual AGPL-3.0-only + commercial** (2026-06-05). Sole-author relicense; no external contributors at the time of change. Forks and derivative works must remain open source under the AGPL and retain the `NOTICE` attribution to SkillGuard and the original repository; commercial use without AGPL obligations requires a commercial license (`LICENSE-COMMERCIAL.md`). Versions up to and including 0.1.0 remain available under Apache-2.0.

## [0.1.0] — 2026-06-03

First public release.

### Added
- Multi-engine scanner CLI (`skillguard`): zero-dependency local engine (50+ patterns, 13 threat categories), plus optional Cisco AI Skill Scanner, SkillAudit API, and Snyk agent-scan engines
- PreToolUse hook that blocks unscanned skills at the moment of use
- Claude Code plugin packaging — hook auto-registers on `/plugin install`
- Table, JSON, markdown, and quiet output formats
- Scan cache at `~/.claude/skillguard-cache/`

### Security
- Hook **fails closed**: corrupted or unreadable cache entries block instead of silently allowing
- TOCTOU guard: a skill modified after its last scan is blocked until re-scanned (global skills)
- Atomic cache writes (temp-file-then-rename) eliminate torn caches from concurrent scans
