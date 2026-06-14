#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""
SkillGuard — Multi-engine security scanner for Claude Code skills.

Scans skills through up to 4 independent detection engines:
  - local:      50+ regex patterns (instant, no deps)
  - cisco:      YARA + YAML static rules, Python AST behavioral analysis
  - skillaudit: 401 patterns via REST API (skillaudit.vercel.app)
  - snyk:       LLM-powered semantic analysis via Snyk agent-scan CLI

Usage:
  skillguard                           # scan all, local engine
  skillguard --scope global            # global skills only
  skillguard --engines all             # all 4 engines
  skillguard --skill security          # single skill
  skillguard --format json             # JSON output
  skillguard --quiet                   # minimal output (for hooks)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

# Allow `python3 /path/to/skillguard/cli.py` to run standalone — the hook prints
# exactly that as its fallback scan command for plugin-only installs, where the
# package isn't pip-installed. Running a file puts only its own dir on sys.path,
# so add the repo root before importing sibling modules.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skillguard import config, store
from skillguard._util import atomic_write_json as _atomic_write_json
from skillguard._util import utcnow_iso
from skillguard.mcp import (
    McpConfigEngine,
    discover_mcps,
    introspect,
    materialize_surface,
    safe_name,
    write_introspection_surface,
)
from skillguard.model import (
    SEVERITY_ORDER,
    Engine,
    Finding,
    SkillInfo,
    max_severity_of,
    normalize_severity,
    worst_severity,
)

# ─── Constants ───────────────────────────────────────────────────────────────

__version__ = "0.3.0"

CACHE_DIR = config.default_cache_dir()
GLOBAL_SKILLS_DIR = Path.home() / ".claude" / "skills"
MCP_CACHE_SUBDIR = "mcps"  # MCP verdicts/surfaces live under CACHE_DIR/mcps/
SKILLAUDIT_BASE = os.environ.get("SKILLGUARD_SKILLAUDIT_BASE", "https://skillaudit.vercel.app")
# Delay between SkillAudit API calls (default respects the 30 req/min limit)
SKILLAUDIT_DELAY = float(os.environ.get("SKILLGUARD_SKILLAUDIT_DELAY", "2.1"))


# ─── Data Types ──────────────────────────────────────────────────────────────
# Finding, SkillInfo, and SEVERITY_ORDER now live in skillguard.model (so the
# MCP scanner can share them without a circular import). They are imported at
# the top of this module and re-exported here, so existing callers and tests
# that do `from skillguard.cli import Finding, SkillInfo` keep working.


# ─── Skill Discovery ────────────────────────────────────────────────────────


def discover_skills(
    scope: str, project_dir: Path, single_skill: str | None = None
) -> list[SkillInfo]:
    """Find all skills in global and/or local directories."""
    skills: list[SkillInfo] = []

    dirs_to_scan: list[tuple[Path, str]] = []
    if scope in ("global", "all"):
        dirs_to_scan.append((GLOBAL_SKILLS_DIR, "global"))
    if scope in ("local", "all"):
        local_skills = project_dir / ".claude" / "skills"
        if local_skills.is_dir():
            dirs_to_scan.append((local_skills, "local"))

    for base_dir, skill_scope in dirs_to_scan:
        if not base_dir.is_dir():
            continue
        for entry in sorted(base_dir.iterdir()):
            if not entry.is_dir() and not entry.is_symlink():
                continue
            # Skip disabled skills
            if entry.name.startswith("_disabled"):
                continue
            # Filter to single skill if requested
            if single_skill and entry.name != single_skill:
                continue

            # Resolve symlinks for scanning
            resolved = entry.resolve() if entry.is_symlink() else entry

            # Collect all files in the skill directory
            skill_files = []
            if resolved.is_dir():
                for f in resolved.rglob("*"):
                    if f.is_file() and f.suffix in (
                        ".md",
                        ".py",
                        ".sh",
                        ".js",
                        ".ts",
                        ".yaml",
                        ".yml",
                        ".json",
                    ):
                        skill_files.append(f)

            skills.append(
                SkillInfo(
                    name=entry.name,
                    path=resolved,
                    scope=skill_scope,
                    files=skill_files,
                )
            )

    return skills


# ─── Engine: Local Pattern Matching ─────────────────────────────────────────

# Each pattern: (category, severity, compiled_regex, description)
LOCAL_PATTERNS: list[tuple[str, str, re.Pattern, str]] = []


def _p(cat: str, sev: str, pattern: str, desc: str) -> None:
    """Register a detection pattern."""
    LOCAL_PATTERNS.append((cat, sev, re.compile(pattern, re.IGNORECASE), desc))


# --- Reverse shells & RCE (CRITICAL) ---
_p("reverse_shell", "critical", r"/dev/tcp/", "Reverse shell via /dev/tcp")
_p("reverse_shell", "critical", r"nc\s+(-e|-c)\s+", "Netcat reverse shell")
_p("reverse_shell", "critical", r"bash\s+-i\s+>&?\s*/dev/", "Bash interactive reverse shell")
_p(
    "reverse_shell",
    "critical",
    r"python[23]?\s+-c\s+['\"]import\s+socket",
    "Python socket reverse shell",
)
_p("reverse_shell", "critical", r"mkfifo\s+/tmp/", "Named pipe reverse shell")
_p("reverse_shell", "critical", r"socat\s+exec:", "Socat reverse shell")

# --- Data exfiltration (CRITICAL) ---
_p("data_exfil", "critical", r"webhook\.site", "Data exfiltration via webhook.site")
_p("data_exfil", "critical", r"requestbin\.(com|net)", "Data exfiltration via requestbin")
_p("data_exfil", "critical", r"burpcollaborator\.net", "Data exfiltration via Burp Collaborator")
_p("data_exfil", "critical", r"ngrok\.(io|com|app)", "Data exfiltration via ngrok tunnel")
_p("data_exfil", "critical", r"pipedream\.net", "Data exfiltration via Pipedream")
_p("data_exfil", "critical", r"interact\.sh", "Data exfiltration via interactsh")

# --- Prompt injection (HIGH) ---
_p(
    "prompt_injection",
    "high",
    r"ignore\s+(all\s+)?previous\s+instructions",
    "Prompt injection: ignore previous instructions",
)
_p(
    "prompt_injection",
    "high",
    r"forget\s+(all\s+)?(your|prior)\s+instructions",
    "Prompt injection: forget instructions",
)
_p(
    "prompt_injection",
    "high",
    r"you\s+are\s+now\s+(a|an)\s+",
    "Prompt injection: role reassignment",
)
_p(
    "prompt_injection",
    "high",
    r"disregard\s+(all\s+)?(prior|previous|above)",
    "Prompt injection: disregard prior",
)
_p("prompt_injection", "high", r"new\s+system\s+prompt", "Prompt injection: new system prompt")
_p(
    "prompt_injection",
    "high",
    r"override\s+(your\s+)?(instructions|rules|guidelines)",
    "Prompt injection: override rules",
)
_p("prompt_injection", "high", r"jailbreak", "Prompt injection: jailbreak reference")

# --- Environment variable exfiltration (HIGH) ---
_p("env_exfil", "high", r"cat\s+(/etc/passwd|/etc/shadow)", "Reading system password files")
_p("env_exfil", "high", r"printenv\s*\|", "Piping environment variables")
_p("env_exfil", "high", r"env\s*\|\s*(curl|wget|nc)", "Exfiltrating env vars via network")
_p("env_exfil", "high", r"\$\{?[A-Z_]*KEY[A-Z_]*\}?\s*[|>]", "Piping API keys")
_p("env_exfil", "high", r"\$\{?[A-Z_]*SECRET[A-Z_]*\}?\s*[|>]", "Piping secrets")
_p("env_exfil", "high", r"\$\{?[A-Z_]*TOKEN[A-Z_]*\}?\s*[|>]", "Piping tokens")

# --- Credential theft (HIGH) ---
_p(
    "credential_theft",
    "high",
    r"~/.ssh/(id_rsa|id_ed25519|config|known_hosts)",
    "Accessing SSH keys/config",
)
_p("credential_theft", "high", r"~/.aws/(credentials|config)", "Accessing AWS credentials")
_p("credential_theft", "high", r"~/.gcloud/", "Accessing GCloud credentials")
_p("credential_theft", "high", r"~/.kube/config", "Accessing Kubernetes config")
_p("credential_theft", "high", r"~/.npmrc", "Accessing npm auth token")
_p("credential_theft", "high", r"~/.netrc", "Accessing netrc credentials")
_p("credential_theft", "high", r"keychain|KeychainAccess", "Accessing system keychain")
_p("credential_theft", "high", r"seed\s*phrase", "References to seed phrases")
_p("credential_theft", "high", r"wallet\.dat|MetaMask", "Crypto wallet access")

# --- Shell pipe execution (HIGH) ---
_p("shell_pipe", "high", r"curl\s+[^\n]*\|\s*(ba)?sh", "curl piped to shell execution")
_p("shell_pipe", "high", r"wget\s+[^\n]*\|\s*(ba)?sh", "wget piped to shell execution")
_p("shell_pipe", "high", r"curl\s+[^\n]*\|\s*python", "curl piped to Python execution")

# --- Obfuscation (HIGH) ---
_p("obfuscation", "high", r"(?:base64\s+--?d|atob|b64decode)\s*[(\s]", "Base64 decoding execution")
_p(
    "obfuscation",
    "high",
    r"\\x[0-9a-f]{2}\\x[0-9a-f]{2}\\x[0-9a-f]{2}\\x[0-9a-f]{2}",
    "Hex-encoded strings (4+ bytes)",
)
_p("obfuscation", "high", r"[\u200b\u200c\u200d\ufeff]{3,}", "Zero-width character obfuscation")
_p(
    "obfuscation",
    "high",
    r"String\.fromCharCode\s*\(\s*\d+\s*(,\s*\d+\s*){3,}",
    "String.fromCharCode obfuscation",
)
_p(
    "obfuscation",
    "high",
    r"\\u00[0-9a-f]{2}\\u00[0-9a-f]{2}\\u00[0-9a-f]{2}",
    "Unicode escape obfuscation",
)

# --- Persistence (MEDIUM) ---
_p("persistence", "medium", r"crontab\s+-[el]", "Crontab manipulation")
_p("persistence", "medium", r"LaunchAgents|LaunchDaemons", "macOS launch agent/daemon persistence")
_p("persistence", "medium", r"systemctl\s+(enable|start|restart)", "Systemd service manipulation")
_p("persistence", "medium", r"~/.bashrc|~/.zshrc|~/.profile", "Shell profile modification")

# --- Suspicious network (MEDIUM) ---
_p("network", "medium", r"nc\s+-l", "Netcat listener")
_p("network", "medium", r"nmap\s+", "Port scanning with nmap")
_p("network", "medium", r"tcpdump\s+", "Packet capture")
_p("network", "medium", r"dns\s+exfil|dns\s+tunnel", "DNS exfiltration/tunneling reference")

# --- Dangerous operations (MEDIUM) ---
_p("dangerous_op", "medium", r"rm\s+-rf\s+/(?!tmp)", "Recursive deletion from root")
_p("dangerous_op", "medium", r"chmod\s+777\s+", "World-writable permissions")
_p("dangerous_op", "medium", r"dd\s+if=.*of=/dev/", "Disk overwrite with dd")
_p("dangerous_op", "medium", r":(){ :\|:& };:", "Fork bomb")

# --- Container escape (MEDIUM) ---
_p("container_escape", "medium", r"/var/run/docker\.sock", "Docker socket access")
_p("container_escape", "medium", r"nsenter\s+", "Namespace entry (container escape)")
_p("container_escape", "medium", r"LD_PRELOAD", "LD_PRELOAD injection")
_p("container_escape", "medium", r"/proc/self/", "Process self-inspection")

# --- Reconnaissance (LOW) ---
_p("recon", "low", r"whoami|id\s+-[anu]", "User reconnaissance")
_p("recon", "low", r"uname\s+-a", "System reconnaissance")
_p("recon", "low", r"ifconfig|ip\s+addr", "Network interface reconnaissance")
_p("recon", "low", r"hostname\s+-[fI]", "Hostname reconnaissance")


class LocalEngine:
    """Pattern-based local scanner. Zero dependencies."""

    name = "local"
    available = True
    inter_target_delay = 0.0

    def scan(self, skill: SkillInfo) -> list[Finding]:
        findings: list[Finding] = []
        for file_path in skill.files:
            try:
                content = file_path.read_text(errors="replace")
            except OSError:
                continue

            lines = content.split("\n")
            for line_num, line in enumerate(lines, 1):
                # Skip YAML frontmatter lines (metadata, not instructions)
                if line_num <= 10 and (
                    line.startswith("---")
                    or line.startswith("name:")
                    or line.startswith("description:")
                ):
                    continue

                for category, severity, pattern, description in LOCAL_PATTERNS:
                    if pattern.search(line):
                        # Context suppression: skip if line is in a code comment explaining the pattern
                        stripped = line.strip()
                        if stripped.startswith("#") and "detect" in stripped.lower():
                            continue
                        if stripped.startswith("//") and "detect" in stripped.lower():
                            continue
                        # Skip if the line is inside a markdown table header or description
                        if "|" in stripped and stripped.count("|") >= 3:
                            continue

                        rel_path = (
                            str(file_path.relative_to(skill.path))
                            if str(file_path).startswith(str(skill.path))
                            else file_path.name
                        )
                        findings.append(
                            Finding(
                                engine="local",
                                severity=severity,
                                category=category,
                                message=description,
                                file=rel_path,
                                line=line_num,
                                context=line.strip()[:120],
                            )
                        )
        return findings


# ─── Engine: Cisco Skill Scanner ────────────────────────────────────────────


class CiscoEngine:
    """Cisco AI Defense skill scanner via Python SDK."""

    name = "cisco"
    available = False
    inter_target_delay = 0.0
    unavailable_hint = (
        "Cisco engine: cisco-ai-skill-scanner not installed (uv pip install cisco-ai-skill-scanner)"
    )

    def __init__(self) -> None:
        try:
            from skill_scanner import SkillScanner

            self.available = True
            self._scanner_cls = SkillScanner
        except ImportError:
            pass

    def scan(self, skill: SkillInfo) -> list[Finding]:
        if not self.available:
            return []

        findings: list[Finding] = []
        try:
            scanner = self._scanner_cls()
            result = scanner.scan_skill(str(skill.path))

            for f in getattr(result, "findings", []):
                severity = normalize_severity(getattr(f, "severity", "medium"))
                findings.append(
                    Finding(
                        engine="cisco",
                        severity=severity,
                        category=getattr(f, "category", getattr(f, "rule_id", "unknown")),
                        message=getattr(f, "message", getattr(f, "description", str(f))),
                        file=getattr(f, "file", ""),
                        line=getattr(f, "line", 0),
                        context=getattr(f, "context", "")[:120],
                    )
                )
        except Exception as e:
            findings.append(
                Finding(
                    engine="cisco",
                    severity="info",
                    category="engine_error",
                    message=f"Cisco scanner error: {e}",
                )
            )
        return findings


# ─── Engine: SkillAudit REST API ────────────────────────────────────────────


class SkillAuditEngine:
    """SkillAudit.vercel.app REST API scanner."""

    name = "skillaudit"
    available = True
    # Throttle between targets to respect the API's 30 req/min limit. The
    # dispatcher reads this generically; no engine-name special-case.
    inter_target_delay = SKILLAUDIT_DELAY

    def scan(self, skill: SkillInfo) -> list[Finding]:
        findings: list[Finding] = []

        # Collect file contents for multi-file scan
        files_payload: list[dict] = []
        for file_path in skill.files[:30]:  # API limit: 30 files
            try:
                content = file_path.read_text(errors="replace")
                rel = (
                    str(file_path.relative_to(skill.path))
                    if str(file_path).startswith(str(skill.path))
                    else file_path.name
                )
                files_payload.append({"name": rel, "content": content})
            except OSError:
                continue

        if not files_payload:
            return []

        # Use /scan/files for multi-file analysis
        try:
            payload = json.dumps(
                {
                    "projectName": skill.name,
                    "files": files_payload,
                }
            ).encode()

            req = urllib.request.Request(
                f"{SKILLAUDIT_BASE}/scan/files",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())

            # Parse findings from response. /scan/files nests them under
            # files[].topFindings ({severity, name, rule, line}); accept a
            # top-level findings list too for older response shapes.
            raw_findings: list[dict] = list(data.get("findings", []))
            for file_entry in data.get("files", []):
                file_name = file_entry.get("file", "")
                for nested in file_entry.get("topFindings", []):
                    entry = dict(nested)
                    entry.setdefault("file", file_name)
                    raw_findings.append(entry)

            for f in raw_findings:
                # SkillAudit layers its own risk vocabulary ("clean", "moderate")
                # on top of the standard severities; translate those first, then
                # defer to the shared normalizer for the unknown → medium clamp.
                raw_sev = str(f.get("severity", f.get("level", "medium"))).lower()
                risk_map = {"clean": "info", "moderate": "medium"}
                severity = risk_map.get(raw_sev, normalize_severity(raw_sev))

                findings.append(
                    Finding(
                        engine="skillaudit",
                        severity=severity,
                        category=f.get("category", f.get("rule", f.get("ruleId", "unknown"))),
                        message=f.get("message", f.get("description", f.get("name", str(f)))),
                        file=f.get("file", ""),
                        line=f.get("line", 0),
                        context=f.get("context", f.get("evidence", ""))[:120],
                    )
                )

            # topFindings is capped per file: never let a truncated list
            # read as the complete report.
            total = data.get("totalFindings", 0)
            if isinstance(total, int) and total > len(raw_findings):
                findings.append(
                    Finding(
                        engine="skillaudit",
                        severity="info",
                        category="truncated",
                        message=(
                            f"SkillAudit reported {total} finding(s), "
                            f"{len(raw_findings)} returned in topFindings; "
                            "see the per-file SkillAudit report for the rest."
                        ),
                    )
                )

        except urllib.error.HTTPError as e:
            if e.code == 429:
                findings.append(
                    Finding(
                        engine="skillaudit",
                        severity="info",
                        category="rate_limited",
                        message="SkillAudit API rate limited (30 req/min). Try again later.",
                    )
                )
            else:
                findings.append(
                    Finding(
                        engine="skillaudit",
                        severity="info",
                        category="engine_error",
                        message=f"SkillAudit API error: HTTP {e.code}",
                    )
                )
        except Exception as e:
            findings.append(
                Finding(
                    engine="skillaudit",
                    severity="info",
                    category="engine_error",
                    message=f"SkillAudit error: {e}",
                )
            )

        return findings


# ─── Engine: Snyk Agent Scan ────────────────────────────────────────────────


class SnykEngine:
    """Snyk agent-scan CLI wrapper."""

    name = "snyk"
    inter_target_delay = 0.0
    unavailable_hint = "Snyk engine: SNYK_TOKEN not set"

    def __init__(self) -> None:
        self.token = os.environ.get("SNYK_TOKEN", "")

    @property
    def available(self) -> bool:
        return bool(self.token)

    def scan(self, skill: SkillInfo) -> list[Finding]:
        if not self.available:
            return []

        findings: list[Finding] = []
        try:
            result = subprocess.run(
                ["uvx", "snyk-agent-scan@latest", "--skills", str(skill.path), "--json"],
                capture_output=True,
                text=True,
                timeout=90,
                env={**os.environ, "SNYK_TOKEN": self.token},
            )

            if result.stdout.strip():
                data = json.loads(result.stdout)
                for issue in (
                    data if isinstance(data, list) else data.get("issues", data.get("findings", []))
                ):
                    if isinstance(issue, dict):
                        severity = normalize_severity(issue.get("severity", "medium"))
                        findings.append(
                            Finding(
                                engine="snyk",
                                severity=severity,
                                category=str(issue.get("code", issue.get("type", "unknown"))),
                                message=str(
                                    issue.get("message", issue.get("description", str(issue)))
                                ),
                                file=issue.get("file", ""),
                                line=issue.get("line", 0),
                            )
                        )

        except FileNotFoundError:
            findings.append(
                Finding(
                    engine="snyk",
                    severity="info",
                    category="engine_error",
                    message="uvx not found. Install uv: https://docs.astral.sh/uv/",
                )
            )
        except subprocess.TimeoutExpired:
            findings.append(
                Finding(
                    engine="snyk",
                    severity="info",
                    category="engine_error",
                    message="Snyk agent-scan timed out (90s limit)",
                )
            )
        except Exception as e:
            findings.append(
                Finding(
                    engine="snyk",
                    severity="info",
                    category="engine_error",
                    message=f"Snyk error: {e}",
                )
            )

        return findings


# ─── Engine registry ─────────────────────────────────────────────────────────
#
# The single source of truth for "what content engines exist". Adding an engine
# is one entry here (plus the engine class itself): `_build_engines`, the
# `--engines all` expansion, and `resolve_engine_names` all derive from this map,
# so there is no second list to keep in sync. `McpConfigEngine` is deliberately
# NOT registered — it is the structural MCP analyzer that `main()` appends only
# when MCP targets exist (a no-op on skills), never a user-selectable engine.

ENGINE_REGISTRY: dict[str, Callable[[], Engine]] = {
    "local": LocalEngine,
    "cisco": CiscoEngine,
    "skillaudit": SkillAuditEngine,
    "snyk": SnykEngine,
}


def resolve_engine_names(spec: str) -> list[str]:
    """Expand an ``--engines`` argument into a list of engine names.

    ``"all"`` expands to every registered engine in registry order; any other
    value is a comma-separated selection trimmed of surrounding whitespace.
    Unknown names are not rejected here — ``_build_engines`` validates them so the
    error names the offender.
    """
    if spec == "all":
        return list(ENGINE_REGISTRY)
    return [e.strip() for e in spec.split(",")]


# ─── Triage (false-positive suppression) ────────────────────────────────────


def triage_path() -> Path:
    # Computed per-call (not module-level) so tests that repoint CACHE_DIR work.
    return CACHE_DIR / "_triage.json"


def resolve_existing_cache(name: str) -> Path | None:
    """Locate a target's verdict cache, whether it's a skill (top-level) or an
    MCP (under ``mcps/``). Skill path wins on the rare name collision."""
    skill_p = cache_path_for(name, "skill")
    if skill_p.exists():
        return skill_p
    mcp_p = cache_path_for(name, "mcp")
    if mcp_p.exists():
        return mcp_p
    return None


def finding_fingerprint(skill_name: str, finding: Finding) -> str:
    # Line numbers are deliberately excluded: doc edits shift lines, and the
    # same pattern in the same file deserves the same verdict either way.
    return "|".join([skill_name, finding.engine, finding.category, finding.file, finding.message])


def load_triage() -> dict:
    try:
        data = json.loads(triage_path().read_text())
        if isinstance(data, dict) and isinstance(data.get("false_positives"), dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"version": 1, "false_positives": {}}


def save_triage(data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(triage_path(), data)


def apply_triage(skill: SkillInfo, triage: dict | None = None) -> None:
    """Flag findings previously marked false-positive so they stop counting."""
    fps = (triage if triage is not None else load_triage())["false_positives"]
    for f in skill.findings:
        if finding_fingerprint(skill.name, f) in fps:
            f.triaged_fp = True


def _rewrite_cache_verdict(cache_file: Path, cache: dict, findings: list[Finding]) -> None:
    """Recompute verdict fields from triaged findings, preserving scan metadata."""
    active = [f for f in findings if not f.triaged_fp]
    cache["max_severity"] = max_severity_of(active)
    cache["finding_count"] = len(active)
    cache["triaged_fp_count"] = len(findings) - len(active)
    cache["findings_summary"] = [
        f"[{f.engine}/{f.severity}] {f.message} in {f.file}:{f.line}"
        for f in sorted(active, key=lambda x: x.sort_key())[:10]
    ]
    cache["findings"] = [asdict(f) for f in sorted(findings, key=lambda x: x.sort_key())]
    _atomic_write_json(cache_file, cache)


def mark_fp_command(skill_name: str) -> None:
    """Mark all of a skill/MCP's current non-info findings as triaged false positives."""
    cache_file = resolve_existing_cache(skill_name)
    if cache_file is None:
        print(
            f"No scan on record for '{skill_name}'. Scan first: skillguard --skill {skill_name}"
            f"  (or --mcp {skill_name})",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        cache = json.loads(cache_file.read_text())
    except (OSError, json.JSONDecodeError):
        # A torn/unreadable cache must exit cleanly, not traceback — mirror the
        # hook's fail-closed guard (hook.py) and unmark_fp_command's read guard.
        print(
            f"Cache for '{skill_name}' is corrupted or unreadable. Re-scan first: skillguard --skill {skill_name}",
            file=sys.stderr,
        )
        sys.exit(1)
    raw = cache.get("findings")
    if raw is None:
        print(
            f"Cache for '{skill_name}' predates triage support. Re-scan first: skillguard --skill {skill_name}",
            file=sys.stderr,
        )
        sys.exit(1)

    findings = [Finding(**f) for f in raw]
    triage = load_triage()
    marked_at = utcnow_iso()
    marked = 0
    for f in findings:
        # info entries are advisories (engine errors, policy notes), not
        # security findings — suppressing them would hide real signal.
        if f.severity == "info" or f.triaged_fp:
            continue
        triage["false_positives"][finding_fingerprint(skill_name, f)] = {
            "skill": skill_name,
            "engine": f.engine,
            "severity": f.severity,
            "category": f.category,
            "file": f.file,
            "message": f.message,
            "marked_at": marked_at,
        }
        f.triaged_fp = True
        marked += 1

    if not marked:
        print(f"'{skill_name}' has no unmarked non-info findings.")
        return
    save_triage(triage)
    _rewrite_cache_verdict(cache_file, cache, findings)
    remaining = sum(1 for f in findings if not f.triaged_fp)
    print(
        f"Marked {marked} finding(s) in '{skill_name}' as false positives ({remaining} remain active)."
    )
    print(f"Marks persist across re-scans. Undo with: skillguard --unmark-fp {skill_name}")


def unmark_fp_command(skill_name: str) -> None:
    """Remove all false-positive marks for a skill and restore its cached verdict."""
    triage = load_triage()
    fps = triage["false_positives"]
    keys = [k for k, v in fps.items() if v.get("skill") == skill_name]
    if not keys:
        print(f"No false-positive marks recorded for '{skill_name}'.")
        return
    for k in keys:
        del fps[k]
    save_triage(triage)

    cache_file = resolve_existing_cache(skill_name)
    if cache_file is not None:
        try:
            cache = json.loads(cache_file.read_text())
            raw = cache.get("findings")
            if raw is not None:
                findings = [Finding(**{**f, "triaged_fp": False}) for f in raw]
                _rewrite_cache_verdict(cache_file, cache, findings)
        except (OSError, json.JSONDecodeError):
            pass
    print(f"Removed {len(keys)} false-positive mark(s) for '{skill_name}'.")


# ─── Cache ───────────────────────────────────────────────────────────────────


def cache_path_for(name: str, kind: str = "skill") -> Path:
    """Where a target's verdict cache lives. MCP verdicts live under a ``mcps/``
    subdir so they never collide with a same-named skill, and so the hook can
    tell the two apart."""
    if kind == "mcp":
        return CACHE_DIR / MCP_CACHE_SUBDIR / f"{safe_name(name)}.json"
    return CACHE_DIR / f"{name}.json"


def write_cache(skill: SkillInfo, engines_used: list[str], skipped: bool = False) -> dict:
    """Write scan results to cache for hook lookups. Returns the cache dict so
    callers can mirror it into the history DB without rebuilding it."""
    path = cache_path_for(skill.name, skill.kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    active = [] if skipped else skill.active_findings
    cache_data = {
        "skill_name": skill.name,
        "target_name": skill.name,
        "kind": skill.kind,
        "scope": skill.scope,
        "scanned_at": utcnow_iso(),
        "skill_mtime_epoch": skill.mtime_epoch,
        "engines_used": engines_used,
        "skipped": skipped,
        "max_severity": "skipped" if skipped else skill.max_severity,
        "finding_count": len(active),
        "triaged_fp_count": 0 if skipped else len(skill.findings) - len(active),
        "findings_summary": [
            f"[{f.engine}/{f.severity}] {f.message} in {f.file}:{f.line}"
            for f in sorted(active, key=lambda x: x.sort_key())[:10]
        ],
        "findings": []
        if skipped
        else [asdict(f) for f in sorted(skill.findings, key=lambda x: x.sort_key())],
    }
    # MCP verdicts carry the tokens the hook uses to map mcp__<server>__tool
    # calls back to this verdict.
    mcp = skill.extra.get("mcp") if skill.extra else None
    if mcp is not None:
        cache_data["match_tokens"] = mcp.match_tokens
    _atomic_write_json(path, cache_data)
    return cache_data


def write_skip_cache(skill_name: str, kind: str = "skill") -> None:
    """Write a 'skipped' cache entry so the hook stops blocking but shows reminders."""
    path = cache_path_for(skill_name, kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    cache_data = {
        "skill_name": skill_name,
        "target_name": skill_name,
        "kind": kind,
        "scanned_at": utcnow_iso(),
        "skill_mtime_epoch": 0,
        "engines_used": [],
        "skipped": True,
        "max_severity": "skipped",
        "finding_count": 0,
        "triaged_fp_count": 0,
        "findings_summary": [],
        "findings": [],
    }
    _atomic_write_json(path, cache_data)


# ─── History + Activity store integration ────────────────────────────────────


def db_path() -> Path:
    """History DB path, computed per-call so tests that repoint CACHE_DIR work."""
    return CACHE_DIR / "skillguard.db"


def log_activity(**kwargs) -> None:
    """Append to the activity audit log — unless the user has toggled it off.

    Gating here (not in store) keeps the toggle in one place and ensures it only
    affects the activity log: scan *history* is recorded separately and always.
    Best-effort: a logging failure never interrupts a scan.
    """
    if not config.activity_logging_enabled(CACHE_DIR):
        return
    kwargs.setdefault("source", "cli")
    try:
        conn = store.connect(db_path())
        try:
            store.log_activity(conn, **kwargs)
        finally:
            conn.close()
    except Exception:
        pass


def _dedupe_mcp_findings(findings: list[Finding]) -> list[Finding]:
    """Collapse identical (engine, category, message) findings on an MCP target.

    A server's launch command is materialized into more than one surface file
    (``command.txt`` and the ``mcp-config.json`` args), so a regex engine
    legitimately reports the same issue from each. For a config audit that is
    one issue, not several — keep the most specific location. Applied to MCP
    targets only; skills keep every distinct occurrence.
    """
    rank = {"command.txt": 0, "endpoint.txt": 0, "mcp-config.json": 1}
    best: dict[tuple, tuple[int, Finding]] = {}
    order: list[tuple] = []
    for f in findings:
        key = (f.engine, f.category, f.message)
        r = rank.get(f.file, 2)
        if key not in best:
            best[key] = (r, f)
            order.append(key)
        elif r < best[key][0]:
            best[key] = (r, f)
    return [best[k][1] for k in order]


# ─── Reporting ───────────────────────────────────────────────────────────────


def severity_color(sev: str) -> str:
    """ANSI color for severity level."""
    colors = {
        "critical": "\033[91m",
        "high": "\033[93m",
        "medium": "\033[33m",
        "low": "\033[36m",
        "info": "\033[37m",
        "clean": "\033[92m",
    }
    return colors.get(sev, "")


RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def report_table(
    skills: list[SkillInfo], engines_used: list[str], scan_time: str, verbose: bool = False
) -> None:
    """Print a formatted table report to stdout."""
    # Count findings by engine and severity (triaged FPs excluded)
    engine_counts: dict[str, dict[str, int]] = {
        e: {s: 0 for s in SEVERITY_ORDER} for e in engines_used
    }
    for skill in skills:
        for f in skill.active_findings:
            if f.engine in engine_counts and f.severity in engine_counts[f.engine]:
                engine_counts[f.engine][f.severity] += 1

    # Target breakdown by kind
    skill_targets = [s for s in skills if s.kind == "skill"]
    mcp_targets = [s for s in skills if s.kind == "mcp"]
    total_findings = sum(len(s.active_findings) for s in skills)
    triaged_total = sum(1 for s in skills for f in s.findings if f.triaged_fp)
    clean_count = sum(1 for s in skills if not s.active_findings)

    print(f"\n{BOLD}SkillGuard Scan Results{RESET} — {scan_time}")
    print("=" * 60)
    print(f"Engines: {', '.join(engines_used)}")
    if mcp_targets:
        print(f"Targets: {len(skill_targets)} skill(s), {len(mcp_targets)} MCP(s)")
    else:
        gc = sum(1 for s in skill_targets if s.scope == "global")
        lc = sum(1 for s in skill_targets if s.scope == "local")
        print(f"Scope:   global ({gc} skills), local ({lc} skills)")
    print()

    # Summary table
    engine_headers = [e[:8].upper() for e in engines_used]
    header = f"{'SEVERITY':<10}" + "".join(f"{h:>10}" for h in engine_headers) + f"{'TOTAL':>10}"
    print(f"{BOLD}SUMMARY{RESET}")
    print(f"  {header}")
    print(f"  {'─' * len(header)}")
    for sev in ["critical", "high", "medium", "low"]:
        row_total = sum(engine_counts[e][sev] for e in engines_used)
        color = severity_color(sev) if row_total > 0 else DIM
        cells = "".join(f"{engine_counts[e][sev]:>10}" for e in engines_used)
        print(f"  {color}{sev:<10}{cells}{row_total:>10}{RESET}")
    if triaged_total:
        print(f"  {DIM}({triaged_total} finding(s) suppressed as triaged false positives){RESET}")
    print()

    # Findings by skill (high+ only in table mode)
    high_skills = [s for s in skills if s.max_severity in ("critical", "high")]
    if high_skills:
        print(f"{BOLD}FINDINGS (HIGH+){RESET}")
        for skill in high_skills:
            high_findings = [f for f in skill.active_findings if f.severity in ("critical", "high")]
            for f in sorted(high_findings, key=lambda x: x.sort_key()):
                color = severity_color(f.severity)
                label = f"{skill.kind}/{skill.scope}" if skill.kind == "mcp" else skill.scope
                print(
                    f"  {color}{f.severity.upper():<9}{RESET} {skill.name} ({label}) — [{f.engine}] {f.message}"
                )
                if f.file:
                    print(f"           {DIM}{f.file}:{f.line}{RESET}")
        print()

    # Medium findings (compact)
    med_findings_total = sum(
        len([f for f in s.active_findings if f.severity == "medium"]) for s in skills
    )
    if med_findings_total > 0:
        print(f"{BOLD}MEDIUM FINDINGS{RESET} ({med_findings_total} total)")
        for skill in skills:
            med_f = [f for f in skill.active_findings if f.severity == "medium"]
            if med_f:
                for f in sorted(med_f, key=lambda x: x.sort_key()):
                    print(
                        f"  {severity_color('medium')}MEDIUM{RESET}   {skill.name} — [{f.engine}] {f.message}"
                    )
        print()

    # Low/info advisories — supply-chain inventory and notes. Counted always,
    # listed only under -v so they don't drown the threat signal. For MCPs these
    # are the "what does this server run / what can it read" inventory.
    if verbose:
        advisories = [
            (s, f) for s in skills for f in s.active_findings if f.severity in ("low", "info")
        ]
        if advisories:
            print(f"{BOLD}ADVISORIES (low/info){RESET}")
            for s, f in sorted(advisories, key=lambda sf: sf[1].sort_key()):
                label = f"{s.kind}/{s.scope}" if s.kind == "mcp" else s.scope
                print(
                    f"  {severity_color(f.severity)}{f.severity.upper():<8}{RESET} "
                    f"{s.name} ({label}) — [{f.engine}] {f.message}"
                )
            print()

    # Summary line
    noun = "target" if mcp_targets else "skill"
    if total_findings == 0:
        print(
            f"{severity_color('clean')}✓ All {len(skills)} {noun}s clean across all engines{RESET}"
        )
    else:
        print(f"✓ {clean_count}/{len(skills)} {noun}s clean")
        if any(s.max_severity in ("critical", "high") for s in skills):
            bad = sum(1 for s in skills if s.max_severity in ("critical", "high"))
            print(
                f"{severity_color('high')}⚠ {bad} {noun}(s) have HIGH+ findings — review recommended{RESET}"
            )
    print()


def report_json(skills: list[SkillInfo], engines_used: list[str], scan_time: str) -> None:
    """Print JSON report to stdout.

    Skills and MCPs are reported in separate arrays (``skills`` is kept for
    back-compat and holds skill targets only; ``mcps`` is new), plus a combined
    ``targets`` array. ``by_scope`` covers skill scopes only.
    """
    engine_counts: dict[str, dict[str, int]] = {
        e: {s: 0 for s in SEVERITY_ORDER} for e in engines_used
    }
    for skill in skills:
        for f in skill.active_findings:
            if f.engine in engine_counts and f.severity in engine_counts[f.engine]:
                engine_counts[f.engine][f.severity] += 1

    skill_targets = [s for s in skills if s.kind == "skill"]
    mcp_targets = [s for s in skills if s.kind == "mcp"]

    def target_dict(s: SkillInfo) -> dict:
        return {
            "name": s.name,
            "kind": s.kind,
            "scope": s.scope,
            "path": str(s.path),
            "max_severity": s.max_severity,
            "triaged_fp_count": sum(1 for f in s.findings if f.triaged_fp),
            "findings": [asdict(f) for f in sorted(s.findings, key=lambda x: x.sort_key())],
        }

    by_scope: dict[str, dict] = {}
    for s in skill_targets:
        bucket = by_scope.setdefault(
            s.scope,
            {
                "total": 0,
                "findings_by_engine": {e: {sv: 0 for sv in SEVERITY_ORDER} for e in engines_used},
            },
        )
        bucket["total"] += 1
        for f in s.active_findings:
            fbe = bucket["findings_by_engine"]
            if f.engine in fbe and f.severity in fbe[f.engine]:
                fbe[f.engine][f.severity] += 1

    output = {
        "scan_time": scan_time,
        "summary": {
            "total_targets": len(skills),
            "total_skills": len(skill_targets),
            "total_mcps": len(mcp_targets),
            "skills_scanned": len(skill_targets),
            "engines_used": engines_used,
            "critical": sum(engine_counts[e]["critical"] for e in engines_used),
            "high": sum(engine_counts[e]["high"] for e in engines_used),
            "medium": sum(engine_counts[e]["medium"] for e in engines_used),
            "low": sum(engine_counts[e]["low"] for e in engines_used),
            "triaged_fp": sum(1 for s in skills for f in s.findings if f.triaged_fp),
        },
        "by_scope": by_scope,
        "skills": [target_dict(s) for s in skill_targets],
        "mcps": [target_dict(s) for s in mcp_targets],
        "targets": [target_dict(s) for s in skills],
    }

    print(json.dumps(output, indent=2))


def report_markdown(
    skills: list[SkillInfo], engines_used: list[str], scan_time: str, verbose: bool = False
) -> None:
    """Print markdown report to stdout."""
    total_findings = sum(len(s.active_findings) for s in skills)
    triaged_total = sum(1 for s in skills for f in s.findings if f.triaged_fp)
    skill_targets = [s for s in skills if s.kind == "skill"]
    mcp_targets = [s for s in skills if s.kind == "mcp"]

    print("# SkillGuard Scan Report")
    print(f"\n**Date:** {scan_time}")
    print(f"**Engines:** {', '.join(engines_used)}")
    print(f"**Targets:** {len(skill_targets)} skill(s), {len(mcp_targets)} MCP(s)")
    print(f"**Findings:** {total_findings}")
    if triaged_total:
        print(f"**Triaged false positives:** {triaged_total}")
    print()

    # Summary table
    print("## Summary by Engine")
    print()
    header = "| Severity |" + "|".join(f" {e} " for e in engines_used) + "| Total |"
    sep = "|----------|" + "|".join("------" for _ in engines_used) + "|-------|"
    print(header)
    print(sep)

    for sev in ["critical", "high", "medium", "low"]:
        cells = []
        for e in engines_used:
            count = sum(
                1 for s in skills for f in s.active_findings if f.engine == e and f.severity == sev
            )
            cells.append(f" {count} ")
        total = sum(1 for s in skills for f in s.active_findings if f.severity == sev)
        print(f"| {sev} |" + "|".join(cells) + f"| {total} |")
    print()

    # Detailed findings
    flagged = [s for s in skills if s.active_findings]
    if flagged:
        print("## Findings by Target")
        print()
        for skill in flagged:
            sev = skill.max_severity.upper()
            label = f"{skill.kind}/{skill.scope}" if skill.kind == "mcp" else skill.scope
            print(f"### {skill.name} ({label}) — {sev}")
            print()
            for f in sorted(skill.active_findings, key=lambda x: x.sort_key()):
                loc = f" `{f.file}:{f.line}`" if f.file else ""
                print(f"- **[{f.engine}/{f.severity}]** {f.message}{loc}")
            print()
    else:
        print("## All targets clean")
        print()


def report_quiet(skills: list[SkillInfo]) -> None:
    """Minimal output for hook mode."""
    total = len(skills)
    flagged = sum(1 for s in skills if s.max_severity in ("critical", "high"))
    if flagged:
        print(f"⚠ SkillGuard: {flagged}/{total} target(s) have HIGH+ findings")
        for s in skills:
            if s.max_severity in ("critical", "high"):
                top = sorted(s.active_findings, key=lambda f: f.sort_key())[0]
                print(f"  - {s.name} ({s.kind}): {top.message}")
    else:
        print(f"SkillGuard: {total} target(s) scanned, all clean")


# ─── History / activity / show commands (read from the store) ────────────────


def _fmt_ts(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return str(iso or "")[:16]


def history_command(limit: int, fmt: str) -> None:
    """Show preserved scan history (every scan of every target, never overwritten)."""
    conn = store.connect(db_path())
    rows = store.recent_target_scans(conn, limit=limit)
    targets = store.list_targets(conn)
    st = store.stats(conn)
    conn.close()

    if fmt == "json":
        print(
            json.dumps(
                {
                    "stats": st,
                    "targets": [dict(t) for t in targets],
                    "recent_scans": [dict(r) for r in rows],
                },
                indent=2,
            )
        )
        return

    print(f"\n{BOLD}SkillGuard History{RESET}")
    print("=" * 64)
    print(
        f"Tracked: {st['skills_total']} skill(s), {st['mcps_total']} MCP(s) — "
        f"{st['target_scans_total']} scan(s) recorded, {st['findings_total']} finding(s) total"
    )
    if st["critical_targets"] or st["high_targets"]:
        print(
            f"{severity_color('high')}⚠ last verdict HIGH+: "
            f"{st['critical_targets']} critical, {st['high_targets']} high{RESET}"
        )
    print()
    if not rows:
        print(f"{DIM}No scans recorded yet. Run: skillguard --target all{RESET}\n")
        return
    print(f"{BOLD}{'WHEN':<17}{'KIND':<6}{'TARGET':<26}{'VERDICT':<10}{'FINDS':>6}  ENGINES{RESET}")
    print("─" * 78)
    for r in rows:
        sev = r["max_severity"] or "?"
        color = severity_color(sev)
        name = (r["name"] or "")[:25]
        print(
            f"{_fmt_ts(r['scanned_at']):<17}{r['kind'] or '?':<6}{name:<26}"
            f"{color}{sev:<10}{RESET}{r['finding_count']:>6}  {DIM}{r['engines'] or ''}{RESET}"
        )
    print()


def activity_command(limit: int, fmt: str) -> None:
    """Show the activity audit log: scans, overrides, and hook decisions."""
    conn = store.connect(db_path())
    rows = store.recent_activity(conn, limit=limit)
    conn.close()
    logging_on = config.activity_logging_enabled(CACHE_DIR)

    if fmt == "json":
        print(
            json.dumps(
                {
                    "activity_logging_enabled": logging_on,
                    "activities": [dict(r) for r in rows],
                },
                indent=2,
            )
        )
        return

    print(f"\n{BOLD}SkillGuard Activity{RESET}")
    print("=" * 64)
    if not rows:
        state = "ON" if logging_on else "OFF"
        print(f"{DIM}No activity recorded yet (logging is {state}).{RESET}")
    else:
        print(f"{BOLD}{'WHEN':<17}{'ACTOR':<7}{'ACTION':<13}{'TARGET':<22}{'OUTCOME'}{RESET}")
        print("─" * 72)
        for r in rows:
            sev = r["severity"]
            color = severity_color(sev) if sev else ""
            outcome = f"{color}{r['outcome'] or ''}{RESET}" if color else (r["outcome"] or "")
            tgt = (r["target_name"] or "")[:21]
            print(
                f"{_fmt_ts(r['ts']):<17}{(r['actor'] or '')[:6]:<7}"
                f"{(r['action'] or '')[:12]:<13}{tgt:<22}{outcome}"
            )
            if r["detail"]:
                print(f"{DIM}                 └ {r['detail']}{RESET}")
    # Make the toggle discoverable — this is a setting the user controls.
    print()
    if logging_on:
        print(
            f"{DIM}Activity logging is ON. Turn it off with: "
            f"skillguard --set-activity-logging off{RESET}"
        )
    else:
        print(
            f"{DIM}Activity logging is OFF (scan history is still recorded). "
            f"Turn it on with: skillguard --set-activity-logging on{RESET}"
        )
    print()


def show_command(name: str, fmt: str) -> None:
    """Show the full scan history for one target (skill or MCP), with findings."""
    conn = store.connect(db_path())
    rows = store.target_history(conn, kind="skill", name=name) + store.target_history(
        conn, kind="mcp", name=name
    )
    rows.sort(key=lambda r: r["id"], reverse=True)
    detail = {r["id"]: store.findings_for_scan(conn, r["id"]) for r in rows}
    conn.close()

    if fmt == "json":
        print(
            json.dumps(
                {
                    "target": name,
                    "scans": [
                        {**dict(r), "findings": [dict(f) for f in detail[r["id"]]]} for r in rows
                    ],
                },
                indent=2,
            )
        )
        return

    print(f"\n{BOLD}History for '{name}'{RESET}")
    print("=" * 64)
    if not rows:
        print(f"{DIM}No scans recorded for '{name}'.{RESET}\n")
        return
    for r in rows:
        sev = r["max_severity"] or "?"
        print(
            f"\n{_fmt_ts(r['scanned_at'])}  [{r['kind']}/{r['scope']}]  "
            f"{severity_color(sev)}{sev}{RESET}  "
            f"{DIM}({r['finding_count']} finding(s), engines: {r['engines']}){RESET}"
        )
        for f in detail[r["id"]]:
            if f["severity"] == "info" and not f["message"]:
                continue
            loc = f" {f['file']}:{f['line']}" if f["file"] else ""
            print(
                f"    {severity_color(f['severity'])}{f['severity']:<8}{RESET}"
                f"[{f['engine']}] {f['message']}{DIM}{loc}{RESET}"
            )
    print()


# ─── Main ────────────────────────────────────────────────────────────────────


def _build_engines(engine_names: list[str], quiet: bool) -> tuple[list[Engine], list[str]]:
    """Instantiate the requested engines, skipping any that are unavailable.

    Fully data-driven over ``ENGINE_REGISTRY``: each requested name is looked up,
    instantiated, and kept only if it reports ``available``. An unavailable engine
    is announced (unless quiet) via its own ``unavailable_hint``; an unknown name
    is a hard error (exit 1). Returns ``(engines, names-actually-used)``.
    """
    engines: list[Engine] = []
    used: list[str] = []
    for name in engine_names:
        factory = ENGINE_REGISTRY.get(name)
        if factory is None:
            print(f"Unknown engine: {name}", file=sys.stderr)
            sys.exit(1)
        engine = factory()
        if engine.available:
            engines.append(engine)
            used.append(name)
        elif not quiet:
            hint = getattr(engine, "unavailable_hint", "")
            print(f"{DIM}[skip] {hint}{RESET}", file=sys.stderr)
    return engines, used


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SkillGuard — Multi-engine security scanner for Claude Code skills and MCP servers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--scope",
        choices=["global", "local", "all"],
        default="all",
        help="Which scope to scan (default: all)",
    )
    parser.add_argument(
        "--target",
        choices=["skills", "mcps", "all"],
        default=None,
        help="What to scan: skills, mcps, or all (default: all unless --skill/--mcp narrows it)",
    )
    parser.add_argument(
        "--engines",
        default="local",
        help="Comma-separated engines: local,cisco,skillaudit,snyk,all (default: local)",
    )
    parser.add_argument("--skill", metavar="NAME", help="Scan a single skill by name")
    parser.add_argument("--mcp", metavar="NAME", help="Scan a single MCP server by name")
    parser.add_argument(
        "--mcp-introspect",
        dest="mcp_introspect",
        action="store_true",
        help="LAUNCH each MCP server to scan its tool descriptions/instructions for "
        "prompt injection (executes the server — only for servers you trust)",
    )
    parser.add_argument(
        "--no-plugins",
        dest="no_plugins",
        action="store_true",
        help="Exclude plugin-provided MCP servers from discovery",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json", "markdown"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--skip",
        metavar="NAME",
        help="Mark a skill as skipped (stops hook blocking, shows reminder instead)",
    )
    parser.add_argument(
        "--skip-mcp",
        metavar="NAME",
        dest="skip_mcp",
        help="Mark an MCP server as skipped (for the hook's enforce policy)",
    )
    parser.add_argument(
        "--mark-fp",
        metavar="NAME",
        dest="mark_fp",
        help="Mark all of a skill/MCP's current non-info findings as triaged false positives",
    )
    parser.add_argument(
        "--unmark-fp",
        metavar="NAME",
        dest="unmark_fp",
        help="Remove all false-positive marks for a skill/MCP",
    )
    parser.add_argument(
        "--history",
        nargs="?",
        type=int,
        const=25,
        default=None,
        metavar="N",
        help="Show the last N scans from the preserved history (default 25) and exit",
    )
    parser.add_argument(
        "--activity",
        nargs="?",
        type=int,
        const=30,
        default=None,
        metavar="N",
        help="Show the last N activity-log entries (default 30) and exit",
    )
    parser.add_argument(
        "--show",
        metavar="NAME",
        help="Show the full scan history for one target (skill or MCP) and exit",
    )
    parser.add_argument(
        "--set-activity-logging",
        dest="set_activity_logging",
        choices=["on", "off"],
        help="Turn the activity audit log on/off (persistent). Scan history is "
        "always kept regardless. Default: on",
    )
    parser.add_argument(
        "--set-mcp-policy",
        dest="set_mcp_policy",
        choices=list(config.VALID_MCP_POLICIES),
        help="Set how the hook treats MCP tool calls: off | warn | enforce (default warn)",
    )
    parser.add_argument("--quiet", action="store_true", help="Minimal output (for hooks/scripts)")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show all findings including low/info"
    )
    parser.add_argument("--version", action="version", version=f"skillguard {__version__}")
    args = parser.parse_args()

    # ── Read-only report commands (no scanning) ──────────────────────────────
    if args.history is not None:
        history_command(args.history, args.format)
        sys.exit(0)
    if args.activity is not None:
        activity_command(args.activity, args.format)
        sys.exit(0)
    if args.show:
        show_command(args.show, args.format)
        sys.exit(0)

    # ── Settings ─────────────────────────────────────────────────────────────
    if args.set_activity_logging:
        on = args.set_activity_logging == "on"
        config.set_activity_logging(on, CACHE_DIR)
        print(
            f"Activity logging is now {'ON' if on else 'OFF'}. "
            f"{'Scan history is recorded either way.' if not on else ''}".rstrip()
        )
        sys.exit(0)
    if args.set_mcp_policy:
        config.set_mcp_policy(args.set_mcp_policy, CACHE_DIR)
        print(f"MCP hook policy set to '{args.set_mcp_policy}'.")
        sys.exit(0)

    # ── Overrides (logged as activities) ─────────────────────────────────────
    if args.skip:
        write_skip_cache(args.skip, "skill")
        log_activity(
            actor="user",
            action="skip",
            target_kind="skill",
            target_name=args.skip,
            outcome="skipped",
            detail="hook will allow with a reminder",
        )
        print(f"Marked skill '{args.skip}' as skipped. Hook will show a reminder on each use.")
        print(f"To scan it properly: skillguard --skill {args.skip}")
        sys.exit(0)
    if args.skip_mcp:
        write_skip_cache(args.skip_mcp, "mcp")
        log_activity(
            actor="user",
            action="skip",
            target_kind="mcp",
            target_name=args.skip_mcp,
            outcome="skipped",
            detail="hook will allow with a reminder",
        )
        print(f"Marked MCP '{args.skip_mcp}' as skipped.")
        print(f"To scan it properly: skillguard --mcp {args.skip_mcp}")
        sys.exit(0)
    if args.mark_fp:
        mark_fp_command(args.mark_fp)
        log_activity(
            actor="user",
            action="mark_fp",
            target_name=args.mark_fp,
            outcome="ok",
            detail="findings marked false-positive",
        )
        sys.exit(0)
    if args.unmark_fp:
        unmark_fp_command(args.unmark_fp)
        log_activity(
            actor="user",
            action="unmark_fp",
            target_name=args.unmark_fp,
            outcome="ok",
            detail="false-positive marks removed",
        )
        sys.exit(0)

    project_dir = Path.cwd()

    # ── Decide what kinds to scan ────────────────────────────────────────────
    if args.target is None:
        if args.skill and not args.mcp:
            want_skills, want_mcps = True, False
        elif args.mcp and not args.skill:
            want_skills, want_mcps = False, True
        else:
            want_skills, want_mcps = True, True
    else:
        want_skills = args.target in ("skills", "all")
        want_mcps = args.target in ("mcps", "all")

    # ── Engines ──────────────────────────────────────────────────────────────
    engine_names = resolve_engine_names(args.engines)
    engines, engine_names_used = _build_engines(engine_names, args.quiet)

    # ── Discover + materialize targets ───────────────────────────────────────
    targets: list[SkillInfo] = []
    if want_skills:
        targets += discover_skills(args.scope, project_dir, single_skill=args.skill)
    mcp_targets: list[SkillInfo] = []
    if want_mcps:
        servers = discover_mcps(
            args.scope, project_dir, single=args.mcp, include_plugins=not args.no_plugins
        )
        mcp_base = CACHE_DIR / MCP_CACHE_SUBDIR
        for srv in servers:
            mcp_targets.append(materialize_surface(srv, mcp_base))
        targets += mcp_targets

    # The MCP structural engine always runs for MCP targets (it is the core MCP
    # analysis); it is a no-op for skills, so adding it is harmless.
    if mcp_targets:
        engines.append(McpConfigEngine())
        engine_names_used.append("mcp")

    if not engines:
        print("No engines available. At minimum, use --engines local", file=sys.stderr)
        sys.exit(1)
    if not targets:
        if args.skill:
            what = f"skill named '{args.skill}'"
        elif args.mcp:
            what = f"MCP server named '{args.mcp}'"
        elif want_mcps and not want_skills:
            what = "MCP servers"
        elif want_skills and not want_mcps:
            what = "skills"
        else:
            what = "targets"
        print(f"No {what} found in {args.scope} scope", file=sys.stderr)
        sys.exit(1)

    # ── Opt-in live introspection (executes servers) ─────────────────────────
    if args.mcp_introspect and mcp_targets:
        if not args.quiet:
            print(
                f"{DIM}⚠ --mcp-introspect LAUNCHES each MCP server to read its tool "
                f"descriptions/instructions. Only do this for servers you trust.{RESET}",
                file=sys.stderr,
            )
        for t in mcp_targets:
            srv = t.extra["mcp"]
            intro = introspect(srv)
            if intro.get("ok"):
                write_introspection_surface(t, intro)
            elif not args.quiet:
                # A deliberately-requested introspection that fails must be
                # visible — not buried in the activity log, which the toggle can
                # silence. stderr so it never corrupts json/markdown on stdout.
                print(
                    f"⚠ introspection of {srv.name} failed: {intro.get('error')}", file=sys.stderr
                )
            log_activity(
                actor="user",
                action="introspect",
                target_kind="mcp",
                target_name=srv.name,
                outcome="ok" if intro.get("ok") else "error",
                detail=(intro.get("error") or f"{len(intro.get('tools', []))} tool(s) read"),
            )

    # ── Scan ─────────────────────────────────────────────────────────────────
    scan_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    total = len(targets)
    triage = load_triage()

    target_kind_label = "all" if want_skills and want_mcps else "mcps" if want_mcps else "skills"

    # History is best-effort but OBSERVABLE. A single try/finally owns the
    # connection for the whole scan, so the handle is always closed — even if
    # opening half-succeeds (connect OK, start_scan_run fails) or scanning raises
    # mid-loop (no leak either way). DB failures are collected and surfaced once
    # to stderr instead of silently swallowed, so a user never believes a scan was
    # recorded when it wasn't. Recording stays independent of the activity-log
    # toggle. When plan 006 extracts the scan loop, this owner moves as one unit.
    conn = run_id = None
    history_error = None  # first DB error encountered; surfaced once after the loop
    try:
        try:
            conn = store.connect(db_path())
            run_id = store.start_scan_run(
                conn,
                engines=engine_names_used,
                scope=args.scope,
                target_kind=target_kind_label,
                source="cli",
                command_line=" ".join(sys.argv),
            )
        except Exception as e:
            history_error, run_id = (
                e,
                None,
            )  # history unavailable; conn (if opened) closed in finally

        for i, target in enumerate(targets):
            if not args.quiet and args.format == "table":
                print(
                    f"\r  Scanning {i + 1}/{total}: {target.name:<40}",
                    end="",
                    file=sys.stderr,
                    flush=True,
                )

            for engine in engines:
                target.findings.extend(engine.scan(target))
                # Throttle between targets for any engine that asks for it (e.g.
                # SkillAudit's rate limit) — by attribute, never by engine name.
                if i < total - 1 and engine.inter_target_delay:
                    time.sleep(engine.inter_target_delay)

            if target.kind == "mcp":
                target.findings = _dedupe_mcp_findings(target.findings)
            apply_triage(target, triage)
            cache = write_cache(target, engine_names_used)

            # History is ALWAYS preserved (independent of the activity-log toggle).
            if conn is not None and run_id is not None:
                try:
                    store.record_scan(
                        conn,
                        run_id=run_id,
                        kind=target.kind,
                        name=target.name,
                        scope=target.scope,
                        scanned_at=cache["scanned_at"],
                        engines=engine_names_used,
                        max_severity=cache["max_severity"],
                        finding_count=cache["finding_count"],
                        triaged_fp_count=cache["triaged_fp_count"],
                        mtime_epoch=cache["skill_mtime_epoch"],
                        skipped=False,
                        findings=cache["findings"],
                        raw_json=cache,
                    )
                except Exception as e:
                    history_error = history_error or e

        if not args.quiet and args.format == "table":
            print("\r" + " " * 60 + "\r", end="", file=sys.stderr, flush=True)

        total_findings = sum(len(t.active_findings) for t in targets)
        worst = worst_severity(t.max_severity for t in targets)
        if conn is not None and run_id is not None:
            try:
                store.finish_scan_run(conn, run_id, num_targets=total, num_findings=total_findings)
            except Exception as e:
                history_error = history_error or e
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    if history_error is not None and not args.quiet:
        print(f"[history] could not record scan: {history_error}", file=sys.stderr)

    # One activity entry summarizing the run (gated by the toggle).
    log_activity(
        actor="user",
        action="scan",
        target_kind=target_kind_label if total > 1 else (targets[0].kind if targets else None),
        target_name=(targets[0].name if total == 1 else None),
        outcome="findings" if total_findings else "clean",
        severity=worst if worst != "clean" else None,
        detail=f"{total} target(s) scanned, {total_findings} active finding(s)",
        metadata={"engines": engine_names_used, "scope": args.scope, "kind": target_kind_label},
    )

    # ── Report ───────────────────────────────────────────────────────────────
    if args.quiet:
        report_quiet(targets)
    elif args.format == "json":
        report_json(targets, engine_names_used, scan_time)
    elif args.format == "markdown":
        report_markdown(targets, engine_names_used, scan_time, verbose=args.verbose)
    else:
        report_table(targets, engine_names_used, scan_time, verbose=args.verbose)


if __name__ == "__main__":
    main()
