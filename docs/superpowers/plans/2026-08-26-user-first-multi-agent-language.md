# User-First Multi-Agent Language Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give SkillGuard a plain-language, platform-neutral README and release the Codex MCP runtime hook needed to support its published capability claims.

**Architecture:** Rewrite only reader-facing explanations while preserving the OpenExecutive-derived section structure and technical reference material. Ship the already-developed Codex installer hook as a synchronized `0.3.2` patch release, update the two production pages that explain Codex setup, and keep unrelated local landing experiments outside every commit and deployment.

**Tech Stack:** GitHub-Flavored Markdown, Python 3.10+, shell installer, JSON plugin manifests, static HTML, pytest, Git, Wrangler.

---

## File Structure

- Modify: `README.md` — user-first opening, outcome-led product explanation, and platform capability matrix.
- Modify: `install.sh` — register SkillGuard's MCP PreToolUse hook in Codex's user hooks file.
- Modify: `tests/test_install_sync.py` — verify Codex hook creation, idempotence, backup, and preservation of unrelated hooks.
- Modify: `landing/public/index.html` — accurate Codex setup sentence.
- Modify: `landing/public/docs/index.html` — separate Claude and Codex installation guidance and Codex hook boundary.
- Modify: `pyproject.toml` — package version `0.3.2`.
- Modify: `skillguard/cli.py` — CLI version `0.3.2`.
- Modify: `.claude-plugin/plugin.json` — plugin version `0.3.2`.
- Modify: `.claude-plugin/marketplace.json` — marketplace version `0.3.2`.
- Modify: `CHANGELOG.md` — document the Codex MCP hook and multi-agent positioning release.
- Modify: `SECURITY.md` — correct the current MCP default and document the Codex/Claude runtime boundary.

### Task 1: Release Codex MCP runtime protection

**Files:**
- Modify: `install.sh`
- Modify: `tests/test_install_sync.py`
- Modify: `pyproject.toml`
- Modify: `skillguard/cli.py`
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `CHANGELOG.md`
- Modify: `SECURITY.md`

- [ ] **Step 1: Verify the Codex installer tests cover the intended contract**

Keep the existing local tests that assert all of the following:

```python
hooks_config = json.loads(codex_hooks.read_text())
codex_pre = hooks_config["hooks"]["PreToolUse"]
assert len(codex_pre) == 1
assert codex_pre[0]["matcher"] == "^mcp__.*"
assert codex_pre[0]["hooks"][0]["command"].endswith(
    "/.claude/skillguard/hook.py"
)
assert codex_pre[0]["hooks"][0]["timeout"] == 30
```

The idempotence test must run the installer twice, preserve an existing
`^shell$` hook, retain an existing top-level description, create a backup, and
leave exactly one SkillGuard MCP entry.

- [ ] **Step 2: Verify the existing Codex installer implementation**

The implementation in `install.sh` must:

```python
pre.append({
    "matcher": "^mcp__.*",
    "hooks": [{
        "type": "command",
        "command": hook_cmd,
        "timeout": 30,
        "statusMessage": "Checking MCP call with SkillGuard",
    }],
})
```

It must write `~/.codex/hooks.json` atomically, back up an existing file, remove
only prior SkillGuard `hook.py` entries, and preserve every unrelated hook.

- [ ] **Step 3: Run the focused installer tests**

Run:

```bash
.venv/bin/pytest tests/test_install_sync.py -q
```

Expected: all installer synchronization and Codex hook tests pass.

- [ ] **Step 4: Bump all release declarations to 0.3.2**

Update the exact values:

```text
pyproject.toml:                    version = "0.3.2"
skillguard/cli.py:                 __version__ = "0.3.2"
.claude-plugin/plugin.json:        "version": "0.3.2"
.claude-plugin/marketplace.json:   "version": "0.3.2"
```

Run:

```bash
.venv/bin/pytest tests/test_version_sync.py -q
```

Expected: version synchronization passes.

- [ ] **Step 5: Document the release and security boundary**

Add a `0.3.2` changelog entry dated `2026-08-26` stating that the local installer
now registers a Codex MCP PreToolUse hook and preserves unrelated hooks. Update
`SECURITY.md` to say the configured MCP default is `enforce`, Claude can gate
skills and MCP tools, and Codex can gate MCP tools but does not expose skill
loading as a hook event.

### Task 2: Rewrite the public language

**Files:**
- Modify: `README.md`
- Modify: `landing/public/index.html`
- Modify: `landing/public/docs/index.html`

- [ ] **Step 1: Replace the README opening with user-first language**

Use this opening:

```markdown
SkillGuard protects coding agents from malicious skills and MCP servers. It checks them before use, shows you what it found, and blocks unsafe or unreviewed tools when your agent supports automatic protection.
```

Replace the demo caption with:

```markdown
SkillGuard catches a malicious skill, explains the risk, and stops it before it can run.
```

The opening and demo caption must not contain `local-first`, `runtime gate`,
`model-facing`, `detection engines`, `SQLite`, `JSON`, `PreToolUse`, or `cache`.

- [ ] **Step 2: Make What It Does outcome-led**

Use concise bullets that communicate these outcomes:

```markdown
- **Checks before use** — scans skills and MCP servers before they become part of an agent workflow
- **Catches dangerous behavior** — finds hidden instructions, credential theft, data leaks, unsafe downloads, and destructive commands
- **Explains the evidence** — shows the file, location, severity, and reason behind each finding
- **Stops unreviewed tools** — blocks risky, changed, or unscanned tools on supported runtime surfaces
- **Remembers your decisions** — keeps scan history, acknowledgements, and false-positive reviews together
- **Works across agent workflows** — provides native Claude Code and Codex integrations, a CLI, and repository adapters for 13 agent surfaces
```

Follow with one short accuracy statement: findings support a human security
decision and do not guarantee that a tool is safe or malicious.

- [ ] **Step 3: Make architecture prose platform-neutral where possible**

Change the diagram's final branches to `Automatic host protection` and
`Agent Skill / CLI review`. Explain host-specific behavior in one paragraph:

```markdown
**Automatic protection** — Claude Code can gate skills and MCP tools. Codex can gate MCP tool calls after you trust the installed hook; Codex does not currently expose skill loading as a hook event. Other integrations use SkillGuard's scan and review workflow unless their host provides an equivalent hook.
```

Retain detailed discovery, redaction, history, configuration, and development
information after the reader-facing sections.

- [ ] **Step 4: Replace the Interfaces table with a capability matrix**

Use the platform rows from the approved design:

```markdown
| Platform | SkillGuard experience | Automatic protection |
|---|---|---|
| **Claude Code** | Native Agent Skill, CLI, and review flow | Skills and MCP tools |
| **Codex** | Native Agent Skill, CLI, and review flow | MCP tools after trusting the installed hook; skill loading is not exposed as a hook event |
| **Cursor, Windsurf, Gemini CLI, GitHub Copilot coding agent, Jules, Aider, goose, opencode, Zed, Warp, and Junie** | Repository instructions and CLI review | Depends on host hook support; SkillGuard makes no universal enforcement claim |
| **Terminal and automation** | CLI plus table, JSON, Markdown, and quiet output | Explicit commands rather than host-triggered enforcement |
```

- [ ] **Step 5: Update setup and support prose**

Present Claude Code and Codex as parallel native integrations in Quick Start and
Installation. In the runtime section, explain the capability difference once
instead of repeatedly defining the product through Claude Code.

Update the production pages to instruct Codex users to restart Codex, open
`/hooks`, trust the SkillGuard MCP hook, and use `$skillguard` for review. State
that Codex gates MCP calls while skill-loading hooks are unavailable.

### Task 3: Verify, publish, and deploy

**Files:**
- Verify all files listed above.

- [ ] **Step 1: Run language and support checks**

Run:

```bash
sed -n '1,35p' README.md
rg -n 'Claude Code|Codex|PreToolUse|automatic protection|13 agent surfaces' README.md
```

Expected: the opening is plain and platform-neutral; platform-specific terms
appear only where they clarify installation, architecture, or capability.

- [ ] **Step 2: Run formatting and full tests**

Run:

```bash
git diff --check
.venv/bin/pytest -q
```

Expected: no whitespace errors and all tests pass.

- [ ] **Step 3: Inspect and stage only release files**

The staged file list must contain only:

```text
.claude-plugin/marketplace.json
.claude-plugin/plugin.json
CHANGELOG.md
README.md
SECURITY.md
install.sh
landing/public/docs/index.html
landing/public/index.html
pyproject.toml
skillguard/cli.py
tests/test_install_sync.py
```

Experimental Gandalf files, `.agents/`, `skills-lock.json`, Wrangler cache data,
and unrelated task/research documents must remain unstaged.

- [ ] **Step 4: Commit and push**

Commit with:

```bash
git commit -m "Release multi-agent SkillGuard language and Codex MCP gating"
git push origin main
```

Expected: the pre-push release guard accepts the synchronized version bump and
GitHub `main` advances without a force push.

- [ ] **Step 5: Deploy committed production assets**

Create a clean detached worktree from the pushed commit, run:

```bash
wrangler deploy --dry-run
wrangler deploy --strict --keep-vars --message "Deploy SkillGuard 0.3.2"
```

Expected: the clean bundle contains no raw generation artifacts, Cloudflare
activates the new Worker version, and `skillguard.sh`, `www.skillguard.sh`,
`/install`, `gandalf.sh`, and the workers.dev URL return their expected status.
