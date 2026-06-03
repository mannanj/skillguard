# Changelog

All notable changes to SkillGuard are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Planned
- Allowlist/baseline file (gitleaks-style) for accepted findings
- Plugin-namespaced skill resolution for the TOCTOU mtime guard
- PyPI release (`uvx skillguard`)

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
