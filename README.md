# SkillGuard

[![CI](https://github.com/mannanj/skillguard/actions/workflows/ci.yml/badge.svg)](https://github.com/mannanj/skillguard/actions/workflows/ci.yml)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

SkillGuard protects coding agents from malicious skills and MCP servers—the add-ons and tool connections that extend what agents can do. It checks them before use, shows you what it found, and blocks unsafe or unreviewed tools when your agent supports automatic protection.

**[skillguard.sh](https://skillguard.sh)**

## Demo

<img src="demo/demo.gif" alt="SkillGuard catching and blocking a malicious skill" width="700">

SkillGuard catches a malicious skill, explains the risk, and stops it before it can run.

## What It Does

SkillGuard gives you one security workflow for the skills and MCP servers used by coding agents:

- **Checks before use** — scans skills and MCP servers before they become part of an agent workflow
- **Catches dangerous behavior** — finds hidden instructions, credential theft, data leaks, unsafe downloads, and destructive commands
- **Explains the evidence** — shows the file, location, severity, and reason behind each finding
- **Stops unreviewed tools** — blocks risky, changed, or unscanned tools on supported runtime surfaces
- **Remembers your decisions** — keeps scan history, acknowledgements, and false-positive reviews together
- **Works across agent workflows** — provides native Claude Code and Codex integrations, a CLI, and repository adapters for 13 agent surfaces

Findings help you make a security decision. They do not guarantee that a tool is safe or malicious.

## Architecture

```text
Skills on disk                       MCP configuration
      |                                      |
      +-------------- discovery ------------+
                         |
             Static scan materialization
             - skill source files
             - redacted MCP launch surface
                         |
        +----------------+----------------+
        |                |                |
   local patterns   MCP structure   optional engines
                                    Cisco / SkillAudit / Snyk
        +----------------+----------------+
                         |
              normalized findings
                         |
          verdict cache + SQLite history
                         |
        +----------------+----------------+
        |                                 |
Automatic host protection         Agent Skill / CLI review
allow / warn / block              summary / show / triage
```

**Discovery** — SkillGuard finds global, project, and plugin skills plus configured MCP servers. Repository adapters bring the same scan-and-review workflow into supported coding-agent projects.

**MCP materialization** — Static scans never launch a server. SkillGuard builds a redacted scan surface from its command, arguments, endpoint, environment-variable names, and header names. Secret values are used in memory only to identify unsafe inline credentials and are not written to findings, cache files, or history.

**Automatic protection** — Claude Code can gate skills and MCP tools. Codex can gate MCP tool calls after you trust the installed hook; Codex does not currently expose skill loading as a hook event. Other integrations use SkillGuard's scan and review workflow unless their host provides an equivalent hook.

**History and review** — JSON cache entries make hook decisions fast. SQLite preserves scan history and, when enabled, activity records. A review disposition is cleared when a new scan changes the evidence it covered.

See [SECURITY.md](SECURITY.md) for the complete threat model and documented boundaries.

## Tech Stack

| Layer | Choice |
|---|---|
| Core runtime | Python 3.10+ standard library |
| Package/build metadata | `pyproject.toml` + Hatchling |
| Local detection | Compiled regular expressions and deterministic structural checks |
| Persistence | SQLite history plus JSON verdict and triage files |
| Runtime integration | Automatic skill/MCP checks in Claude Code and MCP checks in Codex |
| Agent interfaces | Native Claude Code and Codex Agent Skills, CLI, and 13 repository adapters |
| Optional scanners | Cisco AI Skill Scanner, SkillAudit, Snyk agent-scan |
| Landing site | Static HTML/CSS/JavaScript on Cloudflare Workers |
| License | AGPL-3.0-only or a separate commercial license |

The scanner's required dependency list is intentionally empty. Optional engines sit behind availability checks and degrade to a reported skip when their dependency, token, or network access is unavailable.

## Repo Layout

```text
skillguard/
├── skillguard/
│   ├── cli.py                 # CLI entry point and compatibility exports
│   ├── args.py                # Command-line interface definition
│   ├── discovery.py           # Skill discovery
│   ├── scan.py                # Scan lifecycle and engine orchestration
│   ├── patterns.py            # Local threat patterns and categories
│   ├── hook.py                # Automatic host protection for supported tool calls
│   ├── cache.py               # Verdict cache reads and atomic writes
│   ├── store.py               # SQLite scan history and activity store
│   ├── triage.py              # Acknowledgement and false-positive state
│   ├── agent_skill.py         # Shared Claude/Codex Agent Skill workflow
│   ├── agent_adapters.py      # Repository adapters for supported agents
│   ├── engines/               # Local, Cisco, SkillAudit, and Snyk engines
│   ├── mcp/                   # MCP discovery, redaction, rules, and introspection
│   └── render/                # Table, JSON, Markdown, and summary output
├── skills/skillguard/         # Native Agent Skill package
├── hooks/hooks.json           # Claude plugin hook registration
├── commands/skillguard.md     # Legacy Claude command wrapper
├── examples/                  # Manual hook configuration example
├── scripts/                   # Plugin packaging and project utilities
├── tests/                     # Unit, integration, security, and fixture tests
├── demo/                      # Terminal demo source and rendered GIF
├── landing/                   # Static skillguard.sh site and deployment config
├── install.sh                 # Local/Codex installer
├── SECURITY.md                # Threat model and private reporting policy
└── CONTRIBUTING.md            # Development and release workflow
```

## Quick Start

Choose the native integration for your coding agent.

For Claude Code:

```text
/plugin marketplace add mannanj/skillguard
/plugin install skillguard@skillguard
/reload-plugins
```

For Codex and terminal use:

```bash
curl -fsSL https://skillguard.sh/install | sh
codex plugin add skillguard@personal
```

Then run the first scan:

```bash
skillguard --target all --engines local
```

In Claude Code, run `/skillguard:skillguard` or ask the agent to use SkillGuard. In Codex, restart after installation, open `/hooks`, trust the SkillGuard MCP hook, then choose SkillGuard from `/skills` or type `$skillguard`. Terminal users can run `skillguard` directly.

> **First run:** The local engine is offline and has no required third-party dependencies. Network access, API tokens, and heavier packages are needed only when you select an optional engine.

## Run the Runtime Guard

Automatic protection depends on what the host exposes. Claude Code checks skill and MCP tool calls. Codex checks MCP tool calls after you trust the installed SkillGuard hook; Codex skill loading is not currently available as a hook event.

On supported runtime surfaces, SkillGuard compares each tool call with the latest scan before allowing it to continue.

| Target state | Skill behavior | MCP behavior under `enforce` |
|---|---|---|
| Never scanned | Block | Block |
| Cache missing or corrupted | Block | Block |
| Changed since scan | Block and request re-scan | Block when source freshness is available |
| Scanned clean | Allow | Allow |
| Critical/high findings | Block until acknowledged | Block until acknowledged |
| Explicitly skipped | Allow with reminder | Allow with reminder |
| Findings marked false positive | Allow if no untriaged blocking evidence remains | Same review model |

Change the MCP runtime posture explicitly:

```bash
skillguard --set-mcp-policy enforce  # block unknown and high-risk MCP servers
skillguard --set-mcp-policy warn     # allow calls and record one-time warnings
skillguard --set-mcp-policy off      # ignore MCP tool calls
```

The configured default is `enforce`. An environment variable can override it for one process:

```bash
export SKILLGUARD_MCP_POLICY=warn
```

Repository adapters use the same scan, history, and review commands. They provide workflow guidance rather than automatic protection unless their host exposes an equivalent hook.

## Protect Your Agent Environment

Start with a complete local inventory:

```bash
skillguard --target all --engines local
```

Then work through the evidence rather than accepting an aggregate count:

```bash
skillguard --agent-summary   # terse cached-risk overview
skillguard --review          # interactive target-by-target review
skillguard --show NAME       # one target's full scan timeline
skillguard --history         # recent scan history
skillguard --activity        # scans, overrides, and hook decisions
```

For a reviewed finding, choose an explicit disposition:

```bash
skillguard --ack NAME        # accept current skill risk; cleared on re-scan
skillguard --ack-mcp NAME    # accept current MCP risk; cleared on re-scan
skillguard --mark-fp NAME    # suppress matching current non-info findings
skillguard --unmark-fp NAME  # restore those findings
skillguard --skip NAME       # bypass skill gating with a visible reminder
skillguard --skip-mcp NAME   # bypass MCP enforcement with a reminder
```

Re-scan after installing, updating, or editing agent extensions. A prior verdict is evidence about the scanned content, not about a future version.

## Interfaces

| Platform | SkillGuard experience | Automatic protection |
|---|---|---|
| **Claude Code** | Native Agent Skill, CLI, and review flow | Skills and MCP tools |
| **Codex** | Native Agent Skill, CLI, and review flow | MCP tools after trusting the installed hook; skill loading is not exposed as a hook event |
| **Cursor, Windsurf, Gemini CLI, GitHub Copilot coding agent, Jules, Aider, goose, opencode, Zed, Warp, and Junie** | Repository instructions and CLI review | Depends on host hook support; SkillGuard makes no universal enforcement claim |
| **Terminal and automation** | CLI plus table, JSON, Markdown, and quiet output | Explicit commands rather than host-triggered enforcement |

Install repository guidance for the supported adapter-based agents with `skillguard --install-agent-adapters .`.

## Scan Targets

Scan all discovered skills and MCP servers:

```bash
skillguard --target all
```

Narrow the scan by kind or name:

```bash
skillguard --target skills
skillguard --target mcps
skillguard --skill prompt-engineering
skillguard --mcp github
```

MCP discovery reads the configured global, project, and plugin sources. Static scanning materializes a redacted representation and never starts the server.

For a server you already trust enough to execute, opt into live tool-description and instruction scanning:

```bash
skillguard --target mcps --mcp-introspect --engines local,skillaudit
```

Live introspection launches or connects to the server. Loopback, private, and link-local HTTP targets are refused unless you add `--allow-local`; that flag relaxes the SSRF guard and should be used deliberately.

## Installation and Distribution

| Channel | Install | Result |
|---|---|---|
| **Claude Code plugin** | `/plugin marketplace add mannanj/skillguard`, then `/plugin install skillguard@skillguard` | Agent Skill plus automatic Claude runtime hooks |
| **Codex plugin and local CLI** | `curl -fsSL https://skillguard.sh/install \| sh`, then `codex plugin add skillguard@personal` | Native Codex Agent Skill, CLI, review flow, and MCP runtime hook |
| **Editable Python install** | Clone the repository, then `pip install -e .` | `skillguard` and `skillguard-hook` entry points |
| **Repository adapters** | `skillguard --install-agent-adapters .` | Agent instructions/configuration for 13 supported surfaces |
| **Manual Claude hook** | Add [examples/settings-hook-snippet.json](examples/settings-hook-snippet.json) to `~/.claude/settings.json` | Explicit control over the local hook registration |

For editable development:

```bash
git clone https://github.com/mannanj/skillguard.git
cd skillguard
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

The repository root contains development files and is not the clean Claude plugin payload. Plugin development should build the package with:

```bash
python3 scripts/build_plugin_package.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for version synchronization, pre-push checks, and release-channel details.

## Configuration

| Variable or setting | Default | Purpose |
|---|---|---|
| `SKILLGUARD_MCP_POLICY` | `enforce` | MCP hook policy: `off`, `warn`, or `enforce` |
| `SKILLGUARD_ACTIVITY_LOG` | `on` | Enable or disable activity records; scan history is always preserved |
| `SKILLGUARD_AGENT_SUMMARY` | `1` | Set to `0` to suppress the coding-agent launch summary |
| `SKILLGUARD_SKILLAUDIT_BASE` | `https://skillaudit.vercel.app` | Override the SkillAudit service endpoint |
| `SKILLGUARD_SKILLAUDIT_DELAY` | `2.1` | Delay between SkillAudit calls to respect its request limit |
| `SNYK_TOKEN` | — | Enable authenticated Snyk agent-scan use |

Persistent settings live at `~/.claude/skillguard-cache/_settings.json`. Environment variables override persisted values for one invocation. Scan verdicts and triage files share the `~/.claude/skillguard-cache/` root, and history/activity records live in `skillguard.db` beneath that directory.

Set persistent values through the CLI:

```bash
skillguard --set-mcp-policy enforce
skillguard --set-activity-logging off
```

Turning activity logging off stops new activity entries only. It never disables scan history.

## Optional Detection Engines

| Engine | What it adds | Requirement |
|---|---|---|
| **local** | Deterministic offline patterns for prompt injection, exfiltration, credential access, shell execution, obfuscation, persistence, and related behavior | Nothing |
| **mcp** | Structural MCP checks for unsafe launch chains, plaintext credentials, suspicious endpoints, insecure transport, and unpinned runtimes | Applied automatically to MCP targets |
| **cisco** | [Cisco AI Skill Scanner](https://github.com/cisco-ai-defense/skill-scanner) rules and structural analysis | `pip install "skillguard[cisco]"` |
| **skillaudit** | [SkillAudit](https://skillaudit.vercel.app) remote pattern and cross-file analysis | Network access |
| **snyk** | [Snyk agent-scan](https://github.com/snyk/agent-scan) semantic analysis | `SNYK_TOKEN`, `uv`, and network access |

Select a mix explicitly:

```bash
skillguard --engines all
skillguard --engines local,cisco
skillguard --engines local,skillaudit
```

If an optional engine is unavailable, SkillGuard reports the skip and continues with the engines it can run. Selecting remote engines may send scan material to their service or provider; review their terms and your data requirements first.

## Adding a Detection Engine

1. Add an engine module under `skillguard/engines/` with a stable `name` and a `scan(target)` method that returns normalized `Finding` objects.
2. Register its factory in `ENGINE_REGISTRY` in `skillguard/engines/__init__.py`.
3. Keep imports and dependency checks lazy so an unavailable optional engine reports a skip instead of breaking the CLI.
4. Add any dependency under `[project.optional-dependencies]` in `pyproject.toml`; do not add it to the zero-dependency core.
5. Add a realistic malicious fixture and a nearby innocent look-alike to protect against false positives.
6. Add engine dispatch, parsing, availability, and output tests under `tests/`.
7. Add an entry under `Unreleased` in [CHANGELOG.md](CHANGELOG.md) and run the complete verification suite.

The local engine follows the same evidence discipline: a new pattern is not complete without a malicious example and a false-positive guard.

## Development

```bash
git clone https://github.com/mannanj/skillguard.git
cd skillguard
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

pytest -q
ruff check .
mypy skillguard
python3 scripts/build_plugin_package.py
```

The test fixtures include deliberately malicious samples. Do not execute fixture scripts; the scanner and tests read them as data.

Enable the repository's release guard when developing locally:

```bash
git config core.hooksPath .githooks
```

Runtime plugin changes require synchronized version declarations before push. Documentation-only changes do not require a version bump.

## Detection and Test System

The test suite covers the scanner as a security boundary rather than only checking happy-path CLI output:

- malicious, honest, and manipulative skill fixtures
- true-positive and false-positive pattern pairs
- Unicode obfuscation and output-spoofing defenses
- cache corruption, staleness, acknowledgement, and triage behavior
- MCP discovery, redaction, secret non-persistence, introspection, and policy enforcement
- Claude Code and Codex integration packaging and installer synchronization
- Agent Skill generation, repository adapters, and review text
- landing-page, branding, version-sync, and plugin-package hygiene

The clean repository snapshot used for this README passed 313 tests. CI runs the project checks for every pushed change; the exact count will grow as new detections and regression cases are added.

Security-sensitive invariants are tested directly: static MCP scanning must not launch servers, secret values must not reach persistent records, corrupt caches must not silently allow skill use, and new detection patterns must include false-positive protection.

## Privacy

SkillGuard is local-first. The local engine, MCP structural engine, verdict cache, triage files, and SQLite history run on and remain on your machine.

MCP environment and header values are read in memory only to identify inline credentials. Persistent scan material records their names, not their values. Credential-bearing launch flags and URL query parameters are also redacted according to the boundaries documented in [SECURITY.md](SECURITY.md).

Two operations cross the default static boundary:

- Selecting a remote engine such as SkillAudit or Snyk can send scan material to that provider.
- Passing `--mcp-introspect` launches or contacts a server and retrieves its live instructions and tool descriptions.

Both are explicit choices. The default local scan is offline, and static MCP scanning never starts a server.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The highest-value contribution is usually a narrowly scoped detection with both malicious evidence and an innocent false-positive guard.

Every contribution should include:

- working implementation with no stubs
- tests for new behavior and important failure modes
- no new required dependency unless the core design is deliberately reconsidered
- an `Unreleased` changelog entry for user-visible behavior
- passing `pytest`, Ruff, mypy, packaging, and version-synchronization checks as applicable

Report detection bypasses, cache poisoning, secret persistence, path traversal, or scanner code execution privately through a [GitHub security advisory](https://github.com/mannanj/skillguard/security/advisories/new).

## License

Copyright (C) 2026 Mannan Javid. SkillGuard is dual-licensed:

- **[AGPL-3.0-only](LICENSE)** — free to run, study, modify, and use commercially under the AGPL. Works based on SkillGuard, including network services built from it, must satisfy the AGPL source and attribution obligations and retain [NOTICE](NOTICE).
- **[Commercial license](LICENSE-COMMERCIAL.md)** — available for building on SkillGuard without the AGPL obligations. Contact `hello@mannan.is`.

Running the unmodified scanner personally or at work does not require the commercial license. The commercial option applies when you need different terms for building on or distributing SkillGuard.
