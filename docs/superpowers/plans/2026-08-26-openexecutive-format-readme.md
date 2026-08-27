# OpenExecutive-Format SkillGuard README Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite SkillGuard's README in the exact structural format of the OpenExecutive README, verify every project claim, and publish the isolated documentation change to GitHub.

**Architecture:** Replace the current product-led README order with a section-for-section SkillGuard translation of the OpenExecutive information architecture. Keep all implementation in `README.md`, use repository code and tests as factual authority, and isolate the commit from the existing dirty landing-site work.

**Tech Stack:** GitHub-Flavored Markdown, Mermaid/ASCII diagrams, repository CLI and tests, Git.

---

## File Structure

- Modify: `README.md` — the complete public GitHub project overview, setup guide, architecture reference, and contributor entry point.
- Reference: `docs/superpowers/specs/2026-08-26-openexecutive-format-readme-design.md` — approved section mapping and accuracy rules.
- Reference: `pyproject.toml` — package metadata, Python compatibility, dependencies, and license declaration.
- Reference: `skillguard/args.py` and `skillguard/config.py` — supported flags and current defaults.
- Reference: `install.sh`, `hooks/hooks.json`, and `tests/test_install_sync.py` — Claude/Codex installation and hook behavior.
- Reference: `SECURITY.md` and `CONTRIBUTING.md` — security, privacy, disclosure, contribution, and release boundaries.

### Task 1: Rewrite the README in the approved reference structure

**Files:**
- Modify: `README.md`
- Reference: `docs/superpowers/specs/2026-08-26-openexecutive-format-readme-design.md`

- [ ] **Step 1: Replace the centered HTML opening with the reference-style opening**

Use this exact top-level order and preserve the existing working CI, license,
Python, website, and demo links:

```markdown
# SkillGuard

[![CI](https://github.com/mannanj/skillguard/actions/workflows/ci.yml/badge.svg)](https://github.com/mannanj/skillguard/actions/workflows/ci.yml)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

SkillGuard scans agent skills and MCP servers for malicious behavior before your coding agent runs them, then gates unscanned or changed targets at runtime.

## Demo

![SkillGuard blocking a malicious skill](demo/demo.gif)

SkillGuard blocks a malicious skill at the Claude Code PreToolUse boundary.

## What It Does
```

The paragraph must distinguish scanning from prevention: SkillGuard finds
suspicious evidence, records verdicts, and gates unscanned or changed targets;
it does not guarantee that scanned code is harmless.

- [ ] **Step 2: Add the product, architecture, stack, and layout sections**

Write these headings in this exact order:

```markdown
## What It Does
## Architecture
## Tech Stack
## Repo Layout
```

`What It Does` must cover skills, MCP servers, local and optional engines,
history/activity, and triage. `Architecture` must show discovery, redacted MCP
materialization, engine fan-out, SQLite/cache persistence, and runtime hooks.
`Tech Stack` must state that the core is Python 3.10+ stdlib-only while Cisco,
Snyk, and SkillAudit are optional/network-backed. `Repo Layout` must list only
paths that exist in the repository.

- [ ] **Step 3: Add installation and operating sections**

Write these headings in this exact order:

```markdown
## Quick Start
## Run the Runtime Guard
## Protect Your Agent Environment
## Interfaces
## Scan Targets
## Installation and Distribution
```

Use the verified Claude plugin commands, Codex curl/plugin commands, and
`skillguard --target all --engines local`. State plainly that Claude gates skill
invocations and MCP tools while Codex's installed PreToolUse hook gates MCP
tools; do not claim that Codex exposes skill loading to hooks.

- [ ] **Step 4: Add configuration and extension sections**

Write these headings in this exact order:

```markdown
## Configuration
## Optional Detection Engines
## Adding a Detection Engine
## Development
## Detection and Test System
```

Document `mcp_policy` with the implementation's current default of `enforce`,
activity logging with the default `on`, cache/settings paths, `SNYK_TOKEN`, and
SkillAudit controls. Explain live MCP introspection as opt-in execution of a
trusted server. Provide concrete engine-extension and development steps that
point to the engine registry, fixtures, and full test command.

- [ ] **Step 5: Add closing trust and governance sections**

Write these headings in this exact order:

```markdown
## Privacy
## Contributing
## License
```

Privacy must cover local SQLite/cache persistence, redaction of MCP secret
values, network disclosure to selected remote engines, and live-introspection
risk. License text must retain both AGPL-3.0-only and the commercial license,
including NOTICE attribution and the distinction between running unmodified
SkillGuard and building on it.

### Task 2: Verify the rewritten documentation

**Files:**
- Verify: `README.md`
- Reference: `skillguard/args.py`
- Reference: `skillguard/config.py`
- Reference: `install.sh`

- [ ] **Step 1: Compare documented top-level sections with the approved order**

Run:

```bash
rg -n '^## ' README.md
```

Expected: headings appear in the same translated sequence documented in Task 1,
with no leftover top-level sections from the old information architecture.

- [ ] **Step 2: Verify every relative Markdown target exists**

Run:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from urllib.parse import unquote
import re

root = Path.cwd()
text = (root / "README.md").read_text(encoding="utf-8")
missing = []
for raw in re.findall(r"!?\[[^]]*\]\(([^)]+)\)", text):
    target = raw.split("#", 1)[0]
    if not target or "://" in target or target.startswith(("mailto:", "#")):
        continue
    path = root / unquote(target)
    if not path.exists():
        missing.append(target)
if missing:
    raise SystemExit("missing README links: " + ", ".join(missing))
print("all relative README links exist")
PY
```

Expected: exit code 0 and `all relative README links exist`.

- [ ] **Step 3: Verify commands and defaults against the implementation**

Run:

```bash
.venv/bin/python -m skillguard.cli --help
rg -n 'mcp_policy|activity_logging' skillguard/config.py
rg -n 'PreToolUse|mcp__|codex plugin add|marketplace add' install.sh hooks tests/test_install_sync.py
```

Expected: all README commands are present, MCP policy defaults to `enforce`,
activity logging defaults to on, and the Claude/Codex distinctions match the
installer and tests.

- [ ] **Step 4: Run formatting and repository tests**

Run:

```bash
git diff --check -- README.md
.venv/bin/pytest -q
```

Expected: no whitespace errors and all tests pass.

### Task 3: Commit and publish the isolated README change

**Files:**
- Commit: `README.md`

- [ ] **Step 1: Inspect the README diff**

Run:

```bash
git diff -- README.md
```

Expected: only the approved README rewrite, with no generated assets or
unrelated landing-site edits.

- [ ] **Step 2: Stage only the README**

Run:

```bash
git add -- README.md
git diff --cached --name-only
```

Expected: output contains exactly `README.md`.

- [ ] **Step 3: Commit the documentation change**

Run:

```bash
git commit -m "Revamp README in OpenExecutive format"
```

Expected: one documentation commit containing only `README.md`.

- [ ] **Step 4: Push GitHub main**

Run:

```bash
git push origin main
```

Expected: `origin/main` advances to the README commit without force-pushing.

- [ ] **Step 5: Verify the remote commit**

Run:

```bash
git ls-remote origin refs/heads/main
git rev-parse HEAD
```

Expected: both commands report the same commit SHA.
