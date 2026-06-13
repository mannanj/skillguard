# Changelog

All notable changes to SkillGuard are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Planned
- Plugin-namespaced skill resolution for the TOCTOU mtime guard
- Exact MCP tool-name prefix reconstruction for plugin-namespaced servers (hook enforce-mode matching is best-effort today)

## [0.3.0] — 2026-06-13

Scans MCP servers as well as skills, and remembers everything it does.

### Added
- **MCP server scanning** (`--target mcps`, `--mcp NAME`; `--target all` is the default and scans both). SkillGuard discovers every MCP server Claude Code would load — `~/.claude.json` (global + per-project), `~/.claude/mcp.json`, and plugin `.mcp.json` files — and scans each one. A server's scannable surface (a **redacted** config, the launch command, the endpoint URL + header names, and env-var names) is materialized to `~/.claude/skillguard-cache/mcps/<name>/surface/` so every existing engine scans it unchanged, and a new structural **`mcp` engine** adds MCP-specific findings: `curl|sh` / inline `eval` / base64 launch (high), git-source and unpinned-`npx`/`uvx`/`docker` runtimes (medium/low), insecure `http://` and raw-IP endpoints (medium/low), known exfiltration endpoints (critical), and **inline plaintext secrets** in `env`/`headers` (high — flagged by *name*, never by value)
- **Opt-in live introspection** (`--mcp-introspect`): launches a server, performs the MCP handshake, and scans its tool descriptions and server instructions for prompt injection — the model-facing surface a static config scan can't see. Off by default because it **executes the server**; only use it for servers you trust
- **Durable history + activity store** (SQLite, stdlib-only, at `~/.claude/skillguard-cache/skillguard.db`). Every scan of every target (skill or MCP) is appended and **never overwritten**, so the full history is preserved: `skillguard --history`, `skillguard --show NAME` (one target's timeline with findings), and `--format json` for all of it. A separate **activity log** records what SkillGuard does and how you interact with it — scans, `--skip`/`--mark-fp` overrides, and every PreToolUse hook decision (allow/warn/block) with its outcome: `skillguard --activity`
- **Activity-logging toggle** (default **on**): `skillguard --set-activity-logging off` (or env `SKILLGUARD_ACTIVITY_LOG=off`) stops the activity log. Scan history is always recorded regardless — the toggle only affects the activity audit log
- **MCP tool gating in the hook**, governed by `mcp_policy` (`skillguard --set-mcp-policy …` or env `SKILLGUARD_MCP_POLICY`): `off` ignores MCP tools, **`warn`** (default) never blocks but nudges once per unscanned server and logs every call, `enforce` blocks unscanned servers and critical/high verdicts (symmetric with skills). `--skip-mcp NAME` allows a server under `enforce`
- `-v/--verbose` now lists low/info advisories (the MCP supply-chain inventory: what a server runs, what env it can read), and JSON reports split `skills` / `mcps` / `targets`

### Security
- **Secrets never persist.** Env and header *values* are read in memory only, to decide whether an inline literal credential is present; they are never written to a materialized surface, a finding message, the cache, or the history DB. Only variable/header names ever leave the scanner — verified against real configs on every run
- Static scanning **never launches a server**; introspection (which does) is strictly opt-in and clearly labeled
- The hook's package integration is import-guarded: if SkillGuard isn't importable, the hook still performs its core blocking duty with a default `warn` policy and no logging — it never crashes a tool call. Activity logging from the hook is best-effort and can never block or fail a tool call
- MCP verdicts carry a config-file mtime for the TOCTOU guard, so editing a server's config requires a re-scan

### Fixed
- **curl-installer parity with the plugin.** The remote `install.sh` path now fetches every package module (`config.py`/`model.py`/`store.py`/`mcp.py`), not just `cli.py`/`hook.py`/`__init__.py` — without them the new scanner can't import. The installer also registers **both** PreToolUse matchers (`Skill` *and* `mcp__.*`), matching the plugin's `hooks.json`, so curl-installed setups gate MCP tools too; re-running the installer self-heals an older single-`Skill` registration. A new `tests/test_install_sync.py` fails CI if `install.sh` ever drifts from the package modules or the plugin's matcher set

## [0.2.1] — 2026-06-10

Intended first PyPI release (publish pending, tracked in task.md).

### Fixed
- **SkillAudit engine parsed zero findings** after the `/scan/files` API moved results from a top-level `findings` list to `files[].topFindings` — every scan via this engine reported clean, including known-malicious skills. The parser now reads the nested shape (legacy top-level lists still parse), and when the API's `totalFindings` exceeds what `topFindings` returns, an info-level note flags the truncation instead of silently under-reporting

### Added
- **False-positive triage**: `skillguard --mark-fp NAME` suppresses all of a skill's current non-info findings; `--unmark-fp NAME` undoes it. Marks persist across re-scans in `~/.claude/skillguard-cache/_triage.json`, keyed by engine + category + file + message (line numbers ignored, so doc edits don't invalidate marks — but new findings always count). The hook status line shows `clean (N triaged FP)`, and table/JSON/markdown reports exclude triaged findings from verdicts while keeping them in the JSON for full fidelity
- Cache entries now store structured `findings` (full finding objects) and `triaged_fp_count` alongside the existing summary fields
- **Plugin auto-sync for development** (`.githooks/pre-push`, enable with `git config core.hooksPath .githooks`): pushing runtime changes to main without a version bump is refused — installed plugins only refresh on a bump — and after a push lands, the locally-installed plugin is refreshed automatically (`claude plugin update`). `tests/test_version_sync.py` keeps pyproject, `__version__`, and both plugin manifests in lockstep

## [0.2.0] — 2026-06-05

Relicensing release (never published to PyPI; first PyPI publish planned as 0.2.1).

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
