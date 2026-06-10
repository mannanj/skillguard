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
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ─── Constants ───────────────────────────────────────────────────────────────

__version__ = "0.2.1"

CACHE_DIR = Path.home() / ".claude" / "skillguard-cache"
GLOBAL_SKILLS_DIR = Path.home() / ".claude" / "skills"
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
SKILLAUDIT_BASE = os.environ.get("SKILLGUARD_SKILLAUDIT_BASE", "https://skillaudit.vercel.app")
# Delay between SkillAudit API calls (default respects the 30 req/min limit)
SKILLAUDIT_DELAY = float(os.environ.get("SKILLGUARD_SKILLAUDIT_DELAY", "2.1"))


# ─── Data Types ──────────────────────────────────────────────────────────────

@dataclass
class Finding:
    engine: str
    severity: str  # critical, high, medium, low, info
    category: str
    message: str
    file: str = ""
    line: int = 0
    context: str = ""
    triaged_fp: bool = False

    def sort_key(self) -> tuple:
        return (SEVERITY_ORDER.get(self.severity, 99), self.engine, self.category)


@dataclass
class SkillInfo:
    name: str
    path: Path
    scope: str  # "global" or "local"
    files: list[Path] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def active_findings(self) -> list[Finding]:
        return [f for f in self.findings if not f.triaged_fp]

    @property
    def max_severity(self) -> str:
        active = self.active_findings
        if not active:
            return "clean"
        return min(active, key=lambda f: f.sort_key()).severity

    @property
    def mtime_epoch(self) -> float:
        skill_md = self.path / "SKILL.md"
        if skill_md.exists():
            return skill_md.stat().st_mtime
        return 0.0


# ─── Skill Discovery ────────────────────────────────────────────────────────

def discover_skills(scope: str, project_dir: Path, single_skill: Optional[str] = None) -> list[SkillInfo]:
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
                    if f.is_file() and f.suffix in (".md", ".py", ".sh", ".js", ".ts", ".yaml", ".yml", ".json"):
                        skill_files.append(f)

            skills.append(SkillInfo(
                name=entry.name,
                path=resolved,
                scope=skill_scope,
                files=skill_files,
            ))

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
_p("reverse_shell", "critical", r"python[23]?\s+-c\s+['\"]import\s+socket", "Python socket reverse shell")
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
_p("prompt_injection", "high", r"ignore\s+(all\s+)?previous\s+instructions", "Prompt injection: ignore previous instructions")
_p("prompt_injection", "high", r"forget\s+(all\s+)?(your|prior)\s+instructions", "Prompt injection: forget instructions")
_p("prompt_injection", "high", r"you\s+are\s+now\s+(a|an)\s+", "Prompt injection: role reassignment")
_p("prompt_injection", "high", r"disregard\s+(all\s+)?(prior|previous|above)", "Prompt injection: disregard prior")
_p("prompt_injection", "high", r"new\s+system\s+prompt", "Prompt injection: new system prompt")
_p("prompt_injection", "high", r"override\s+(your\s+)?(instructions|rules|guidelines)", "Prompt injection: override rules")
_p("prompt_injection", "high", r"jailbreak", "Prompt injection: jailbreak reference")

# --- Environment variable exfiltration (HIGH) ---
_p("env_exfil", "high", r"cat\s+(/etc/passwd|/etc/shadow)", "Reading system password files")
_p("env_exfil", "high", r"printenv\s*\|", "Piping environment variables")
_p("env_exfil", "high", r"env\s*\|\s*(curl|wget|nc)", "Exfiltrating env vars via network")
_p("env_exfil", "high", r"\$\{?[A-Z_]*KEY[A-Z_]*\}?\s*[|>]", "Piping API keys")
_p("env_exfil", "high", r"\$\{?[A-Z_]*SECRET[A-Z_]*\}?\s*[|>]", "Piping secrets")
_p("env_exfil", "high", r"\$\{?[A-Z_]*TOKEN[A-Z_]*\}?\s*[|>]", "Piping tokens")

# --- Credential theft (HIGH) ---
_p("credential_theft", "high", r"~/.ssh/(id_rsa|id_ed25519|config|known_hosts)", "Accessing SSH keys/config")
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
_p("obfuscation", "high", r"\\x[0-9a-f]{2}\\x[0-9a-f]{2}\\x[0-9a-f]{2}\\x[0-9a-f]{2}", "Hex-encoded strings (4+ bytes)")
_p("obfuscation", "high", r"[\u200b\u200c\u200d\ufeff]{3,}", "Zero-width character obfuscation")
_p("obfuscation", "high", r"String\.fromCharCode\s*\(\s*\d+\s*(,\s*\d+\s*){3,}", "String.fromCharCode obfuscation")
_p("obfuscation", "high", r"\\u00[0-9a-f]{2}\\u00[0-9a-f]{2}\\u00[0-9a-f]{2}", "Unicode escape obfuscation")

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
                if line_num <= 10 and (line.startswith("---") or line.startswith("name:") or line.startswith("description:")):
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

                        rel_path = str(file_path.relative_to(skill.path)) if str(file_path).startswith(str(skill.path)) else file_path.name
                        findings.append(Finding(
                            engine="local",
                            severity=severity,
                            category=category,
                            message=description,
                            file=rel_path,
                            line=line_num,
                            context=line.strip()[:120],
                        ))
        return findings


# ─── Engine: Cisco Skill Scanner ────────────────────────────────────────────

class CiscoEngine:
    """Cisco AI Defense skill scanner via Python SDK."""

    name = "cisco"
    available = False

    def __init__(self) -> None:
        try:
            from skill_scanner import SkillScanner  # type: ignore
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
                severity = getattr(f, "severity", "medium").lower()
                if severity not in SEVERITY_ORDER:
                    severity = "medium"
                findings.append(Finding(
                    engine="cisco",
                    severity=severity,
                    category=getattr(f, "category", getattr(f, "rule_id", "unknown")),
                    message=getattr(f, "message", getattr(f, "description", str(f))),
                    file=getattr(f, "file", ""),
                    line=getattr(f, "line", 0),
                    context=getattr(f, "context", "")[:120],
                ))
        except Exception as e:
            findings.append(Finding(
                engine="cisco",
                severity="info",
                category="engine_error",
                message=f"Cisco scanner error: {e}",
            ))
        return findings


# ─── Engine: SkillAudit REST API ────────────────────────────────────────────

class SkillAuditEngine:
    """SkillAudit.vercel.app REST API scanner."""

    name = "skillaudit"

    def scan(self, skill: SkillInfo) -> list[Finding]:
        findings: list[Finding] = []

        # Collect file contents for multi-file scan
        files_payload: list[dict] = []
        for file_path in skill.files[:30]:  # API limit: 30 files
            try:
                content = file_path.read_text(errors="replace")
                rel = str(file_path.relative_to(skill.path)) if str(file_path).startswith(str(skill.path)) else file_path.name
                files_payload.append({"name": rel, "content": content})
            except OSError:
                continue

        if not files_payload:
            return []

        # Use /scan/files for multi-file analysis
        try:
            payload = json.dumps({
                "projectName": skill.name,
                "files": files_payload,
            }).encode()

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
                severity = str(f.get("severity", f.get("level", "medium"))).lower()
                if severity not in SEVERITY_ORDER:
                    # Map SkillAudit risk levels
                    risk_map = {"clean": "info", "moderate": "medium"}
                    severity = risk_map.get(severity, "medium")

                findings.append(Finding(
                    engine="skillaudit",
                    severity=severity,
                    category=f.get("category", f.get("rule", f.get("ruleId", "unknown"))),
                    message=f.get("message", f.get("description", f.get("name", str(f)))),
                    file=f.get("file", ""),
                    line=f.get("line", 0),
                    context=f.get("context", f.get("evidence", ""))[:120],
                ))

            # topFindings is capped per file: never let a truncated list
            # read as the complete report.
            total = data.get("totalFindings", 0)
            if isinstance(total, int) and total > len(raw_findings):
                findings.append(Finding(
                    engine="skillaudit",
                    severity="info",
                    category="truncated",
                    message=(
                        f"SkillAudit reported {total} finding(s), "
                        f"{len(raw_findings)} returned in topFindings; "
                        "see the per-file SkillAudit report for the rest."
                    ),
                ))

        except urllib.error.HTTPError as e:
            if e.code == 429:
                findings.append(Finding(
                    engine="skillaudit",
                    severity="info",
                    category="rate_limited",
                    message="SkillAudit API rate limited (30 req/min). Try again later.",
                ))
            else:
                findings.append(Finding(
                    engine="skillaudit",
                    severity="info",
                    category="engine_error",
                    message=f"SkillAudit API error: HTTP {e.code}",
                ))
        except Exception as e:
            findings.append(Finding(
                engine="skillaudit",
                severity="info",
                category="engine_error",
                message=f"SkillAudit error: {e}",
            ))

        return findings


# ─── Engine: Snyk Agent Scan ────────────────────────────────────────────────

class SnykEngine:
    """Snyk agent-scan CLI wrapper."""

    name = "snyk"

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
                for issue in data if isinstance(data, list) else data.get("issues", data.get("findings", [])):
                    if isinstance(issue, dict):
                        severity = issue.get("severity", "medium").lower()
                        if severity not in SEVERITY_ORDER:
                            severity = "medium"
                        findings.append(Finding(
                            engine="snyk",
                            severity=severity,
                            category=issue.get("code", issue.get("type", "unknown")),
                            message=issue.get("message", issue.get("description", str(issue))),
                            file=issue.get("file", ""),
                            line=issue.get("line", 0),
                        ))

        except FileNotFoundError:
            findings.append(Finding(
                engine="snyk",
                severity="info",
                category="engine_error",
                message="uvx not found. Install uv: https://docs.astral.sh/uv/",
            ))
        except subprocess.TimeoutExpired:
            findings.append(Finding(
                engine="snyk",
                severity="info",
                category="engine_error",
                message="Snyk agent-scan timed out (90s limit)",
            ))
        except Exception as e:
            findings.append(Finding(
                engine="snyk",
                severity="info",
                category="engine_error",
                message=f"Snyk error: {e}",
            ))

        return findings


# ─── Triage (false-positive suppression) ────────────────────────────────────

def triage_path() -> Path:
    # Computed per-call (not module-level) so tests that repoint CACHE_DIR work.
    return CACHE_DIR / "_triage.json"


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


def apply_triage(skill: SkillInfo, triage: Optional[dict] = None) -> None:
    """Flag findings previously marked false-positive so they stop counting."""
    fps = (triage if triage is not None else load_triage())["false_positives"]
    for f in skill.findings:
        if finding_fingerprint(skill.name, f) in fps:
            f.triaged_fp = True


def _rewrite_cache_verdict(cache_file: Path, cache: dict, findings: list[Finding]) -> None:
    """Recompute verdict fields from triaged findings, preserving scan metadata."""
    active = [f for f in findings if not f.triaged_fp]
    cache["max_severity"] = min(active, key=lambda f: f.sort_key()).severity if active else "clean"
    cache["finding_count"] = len(active)
    cache["triaged_fp_count"] = len(findings) - len(active)
    cache["findings_summary"] = [
        f"[{f.engine}/{f.severity}] {f.message} in {f.file}:{f.line}"
        for f in sorted(active, key=lambda x: x.sort_key())[:10]
    ]
    cache["findings"] = [asdict(f) for f in sorted(findings, key=lambda x: x.sort_key())]
    _atomic_write_json(cache_file, cache)


def mark_fp_command(skill_name: str) -> None:
    """Mark all of a skill's current non-info findings as triaged false positives."""
    cache_file = CACHE_DIR / f"{skill_name}.json"
    if not cache_file.exists():
        print(f"No scan on record for '{skill_name}'. Scan first: skillguard --skill {skill_name}", file=sys.stderr)
        sys.exit(1)
    cache = json.loads(cache_file.read_text())
    raw = cache.get("findings")
    if raw is None:
        print(f"Cache for '{skill_name}' predates triage support. Re-scan first: skillguard --skill {skill_name}", file=sys.stderr)
        sys.exit(1)

    findings = [Finding(**f) for f in raw]
    triage = load_triage()
    marked_at = datetime.now(timezone.utc).isoformat()
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
    print(f"Marked {marked} finding(s) in '{skill_name}' as false positives ({remaining} remain active).")
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

    cache_file = CACHE_DIR / f"{skill_name}.json"
    if cache_file.exists():
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

def write_cache(skill: SkillInfo, engines_used: list[str], skipped: bool = False) -> None:
    """Write scan results to cache for hook lookups."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    active = [] if skipped else skill.active_findings
    cache_data = {
        "skill_name": skill.name,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
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
        "findings": [] if skipped else [asdict(f) for f in sorted(skill.findings, key=lambda x: x.sort_key())],
    }
    _atomic_write_json(CACHE_DIR / f"{skill.name}.json", cache_data)


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON via temp-file-then-rename so concurrent scans never leave a torn cache."""
    tmp = path.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def write_skip_cache(skill_name: str) -> None:
    """Write a 'skipped' cache entry so the hook stops blocking but shows reminders."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_data = {
        "skill_name": skill_name,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "skill_mtime_epoch": 0,
        "engines_used": [],
        "skipped": True,
        "max_severity": "skipped",
        "finding_count": 0,
        "triaged_fp_count": 0,
        "findings_summary": [],
        "findings": [],
    }
    _atomic_write_json(CACHE_DIR / f"{skill_name}.json", cache_data)


# ─── Reporting ───────────────────────────────────────────────────────────────

def severity_color(sev: str) -> str:
    """ANSI color for severity level."""
    colors = {"critical": "\033[91m", "high": "\033[93m", "medium": "\033[33m", "low": "\033[36m", "info": "\033[37m", "clean": "\033[92m"}
    return colors.get(sev, "")

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def report_table(skills: list[SkillInfo], engines_used: list[str], scan_time: str) -> None:
    """Print a formatted table report to stdout."""
    # Count findings by engine and severity (triaged FPs excluded)
    engine_counts: dict[str, dict[str, int]] = {e: {s: 0 for s in SEVERITY_ORDER} for e in engines_used}
    for skill in skills:
        for f in skill.active_findings:
            if f.engine in engine_counts and f.severity in engine_counts[f.engine]:
                engine_counts[f.engine][f.severity] += 1

    # Scope breakdown
    global_count = sum(1 for s in skills if s.scope == "global")
    local_count = sum(1 for s in skills if s.scope == "local")
    total_findings = sum(len(s.active_findings) for s in skills)
    triaged_total = sum(1 for s in skills for f in s.findings if f.triaged_fp)
    clean_count = sum(1 for s in skills if not s.active_findings)

    print(f"\n{BOLD}SkillGuard Scan Results{RESET} — {scan_time}")
    print("=" * 60)
    print(f"Engines: {', '.join(engines_used)}")
    print(f"Scope:   global ({global_count} skills), local ({local_count} skills)")
    print()

    # Summary table
    engine_headers = [e[:8].upper() for e in engines_used]
    header = f"{'SEVERITY':<10}" + "".join(f"{h:>10}" for h in engine_headers) + f"{'TOTAL':>10}"
    print(f"{BOLD}SUMMARY{RESET}")
    print(f"  {header}")
    print(f"  {'─' * len(header)}")
    for sev in ["critical", "high", "medium", "low"]:
        row_total = sum(engine_counts[e][sev] for e in engines_used)
        if row_total == 0 and sev in ("low",):
            # Always show low even if 0
            pass
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
                print(f"  {color}{f.severity.upper():<9}{RESET} {skill.name} ({skill.scope}) — [{f.engine}] {f.message}")
                if f.file:
                    print(f"           {DIM}{f.file}:{f.line}{RESET}")
        print()

    # Medium findings (compact)
    med_skills = [s for s in skills if s.max_severity == "medium" and s.max_severity not in ("critical", "high")]
    med_findings_total = sum(len([f for f in s.active_findings if f.severity == "medium"]) for s in skills)
    if med_findings_total > 0:
        print(f"{BOLD}MEDIUM FINDINGS{RESET} ({med_findings_total} total)")
        for skill in skills:
            med_f = [f for f in skill.active_findings if f.severity == "medium"]
            if med_f:
                for f in sorted(med_f, key=lambda x: x.sort_key()):
                    print(f"  {severity_color('medium')}MEDIUM{RESET}   {skill.name} — [{f.engine}] {f.message}")
        print()

    # Summary line
    if total_findings == 0:
        print(f"{severity_color('clean')}✓ All {len(skills)} skills clean across all engines{RESET}")
    else:
        print(f"✓ {clean_count}/{len(skills)} skills clean")
        if any(s.max_severity in ("critical", "high") for s in skills):
            bad = sum(1 for s in skills if s.max_severity in ("critical", "high"))
            print(f"{severity_color('high')}⚠ {bad} skill(s) have HIGH+ findings — review recommended{RESET}")
    print()


def report_json(skills: list[SkillInfo], engines_used: list[str], scan_time: str) -> None:
    """Print JSON report to stdout."""
    # Build structured output
    engine_counts: dict[str, dict[str, int]] = {e: {s: 0 for s in SEVERITY_ORDER} for e in engines_used}
    for skill in skills:
        for f in skill.active_findings:
            if f.engine in engine_counts and f.severity in engine_counts[f.engine]:
                engine_counts[f.engine][f.severity] += 1

    global_skills = [s for s in skills if s.scope == "global"]
    local_skills = [s for s in skills if s.scope == "local"]

    output = {
        "scan_time": scan_time,
        "summary": {
            "total_skills": len(skills),
            "skills_scanned": len(skills),
            "engines_used": engines_used,
            "critical": sum(engine_counts[e]["critical"] for e in engines_used),
            "high": sum(engine_counts[e]["high"] for e in engines_used),
            "medium": sum(engine_counts[e]["medium"] for e in engines_used),
            "low": sum(engine_counts[e]["low"] for e in engines_used),
            "triaged_fp": sum(1 for s in skills for f in s.findings if f.triaged_fp),
        },
        "by_scope": {
            "global": {
                "total": len(global_skills),
                "findings_by_engine": {e: {s: 0 for s in SEVERITY_ORDER} for e in engines_used},
            },
            "local": {
                "total": len(local_skills),
                "findings_by_engine": {e: {s: 0 for s in SEVERITY_ORDER} for e in engines_used},
            },
        },
        "skills": [],
    }

    for skill in skills:
        for f in skill.active_findings:
            scope_data = output["by_scope"][skill.scope]["findings_by_engine"]
            if f.engine in scope_data and f.severity in scope_data[f.engine]:
                scope_data[f.engine][f.severity] += 1

        skill_data = {
            "name": skill.name,
            "scope": skill.scope,
            "path": str(skill.path),
            "max_severity": skill.max_severity,
            "triaged_fp_count": sum(1 for f in skill.findings if f.triaged_fp),
            "findings": [asdict(f) for f in sorted(skill.findings, key=lambda x: x.sort_key())],
        }
        output["skills"].append(skill_data)

    print(json.dumps(output, indent=2))


def report_markdown(skills: list[SkillInfo], engines_used: list[str], scan_time: str) -> None:
    """Print markdown report to stdout."""
    total_findings = sum(len(s.active_findings) for s in skills)
    triaged_total = sum(1 for s in skills for f in s.findings if f.triaged_fp)
    global_count = sum(1 for s in skills if s.scope == "global")
    local_count = sum(1 for s in skills if s.scope == "local")

    print(f"# SkillGuard Scan Report")
    print(f"\n**Date:** {scan_time}")
    print(f"**Engines:** {', '.join(engines_used)}")
    print(f"**Skills:** {len(skills)} total ({global_count} global, {local_count} local)")
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
            count = sum(1 for s in skills for f in s.active_findings if f.engine == e and f.severity == sev)
            cells.append(f" {count} ")
        total = sum(1 for s in skills for f in s.active_findings if f.severity == sev)
        print(f"| {sev} |" + "|".join(cells) + f"| {total} |")
    print()

    # Detailed findings
    flagged = [s for s in skills if s.active_findings]
    if flagged:
        print("## Findings by Skill")
        print()
        for skill in flagged:
            sev = skill.max_severity.upper()
            print(f"### {skill.name} ({skill.scope}) — {sev}")
            print()
            for f in sorted(skill.active_findings, key=lambda x: x.sort_key()):
                loc = f" `{f.file}:{f.line}`" if f.file else ""
                print(f"- **[{f.engine}/{f.severity}]** {f.message}{loc}")
            print()
    else:
        print("## All skills clean")
        print()


def report_quiet(skills: list[SkillInfo]) -> None:
    """Minimal output for hook mode."""
    total = len(skills)
    flagged = sum(1 for s in skills if s.max_severity in ("critical", "high"))
    if flagged:
        print(f"⚠ SkillGuard: {flagged}/{total} skill(s) have HIGH+ findings")
        for s in skills:
            if s.max_severity in ("critical", "high"):
                top = sorted(s.active_findings, key=lambda f: f.sort_key())[0]
                print(f"  - {s.name}: {top.message}")
    else:
        print(f"SkillGuard: {total} skills scanned, all clean")


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SkillGuard — Multi-engine security scanner for Claude Code skills",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--scope", choices=["global", "local", "all"], default="all",
                        help="Which skills to scan (default: all)")
    parser.add_argument("--engines", default="local",
                        help="Comma-separated engines: local,cisco,skillaudit,snyk,all (default: local)")
    parser.add_argument("--skill", metavar="NAME",
                        help="Scan a single skill by name")
    parser.add_argument("--format", choices=["table", "json", "markdown"], default="table",
                        help="Output format (default: table)")
    parser.add_argument("--skip", metavar="NAME",
                        help="Mark a skill as skipped (stops hook blocking, shows reminder instead)")
    parser.add_argument("--mark-fp", metavar="NAME", dest="mark_fp",
                        help="Mark all of a skill's current non-info findings as triaged false positives (persists across re-scans)")
    parser.add_argument("--unmark-fp", metavar="NAME", dest="unmark_fp",
                        help="Remove all false-positive marks for a skill")
    parser.add_argument("--quiet", action="store_true",
                        help="Minimal output (for hooks/scripts)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show all findings including low/info")
    parser.add_argument("--version", action="version", version=f"skillguard {__version__}")
    args = parser.parse_args()

    # Handle --skip immediately (no scanning needed)
    if args.skip:
        write_skip_cache(args.skip)
        print(f"Marked '{args.skip}' as skipped. Hook will show a reminder on each use.")
        print(f"To scan it properly: skillguard --skill {args.skip}")
        sys.exit(0)

    if args.mark_fp:
        mark_fp_command(args.mark_fp)
        sys.exit(0)

    if args.unmark_fp:
        unmark_fp_command(args.unmark_fp)
        sys.exit(0)

    # Resolve project directory (cwd or git root)
    project_dir = Path.cwd()

    # Parse engine selection
    if args.engines == "all":
        engine_names = ["local", "cisco", "skillaudit", "snyk"]
    else:
        engine_names = [e.strip() for e in args.engines.split(",")]

    # Initialize engines
    engines: list = []
    engine_names_used: list[str] = []

    for name in engine_names:
        if name == "local":
            engines.append(LocalEngine())
            engine_names_used.append("local")
        elif name == "cisco":
            eng = CiscoEngine()
            if eng.available:
                engines.append(eng)
                engine_names_used.append("cisco")
            else:
                if not args.quiet:
                    print(f"{DIM}[skip] Cisco engine: cisco-ai-skill-scanner not installed (uv pip install cisco-ai-skill-scanner){RESET}", file=sys.stderr)
        elif name == "skillaudit":
            engines.append(SkillAuditEngine())
            engine_names_used.append("skillaudit")
        elif name == "snyk":
            eng = SnykEngine()
            if eng.available:
                engines.append(eng)
                engine_names_used.append("snyk")
            else:
                if not args.quiet:
                    print(f"{DIM}[skip] Snyk engine: SNYK_TOKEN not set{RESET}", file=sys.stderr)
        else:
            print(f"Unknown engine: {name}", file=sys.stderr)
            sys.exit(1)

    if not engines:
        print("No engines available. At minimum, use --engines local", file=sys.stderr)
        sys.exit(1)

    # Discover skills
    skills = discover_skills(args.scope, project_dir, single_skill=args.skill)

    if not skills:
        if args.skill:
            print(f"Skill '{args.skill}' not found in {args.scope} scope", file=sys.stderr)
        else:
            print(f"No skills found in {args.scope} scope", file=sys.stderr)
        sys.exit(1)

    # Scan
    scan_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    total = len(skills)
    triage = load_triage()

    for i, skill in enumerate(skills):
        if not args.quiet and args.format == "table":
            print(f"\r  Scanning {i+1}/{total}: {skill.name:<40}", end="", file=sys.stderr, flush=True)

        for engine in engines:
            findings = engine.scan(skill)
            skill.findings.extend(findings)

            # Rate limiting for API engines
            if engine.name == "skillaudit" and i < total - 1:
                time.sleep(SKILLAUDIT_DELAY)

        apply_triage(skill, triage)
        write_cache(skill, engine_names_used)

    if not args.quiet and args.format == "table":
        print("\r" + " " * 60 + "\r", end="", file=sys.stderr, flush=True)

    # Report
    if args.quiet:
        report_quiet(skills)
    elif args.format == "json":
        report_json(skills, engine_names_used, scan_time)
    elif args.format == "markdown":
        report_markdown(skills, engine_names_used, scan_time)
    else:
        report_table(skills, engine_names_used, scan_time)


if __name__ == "__main__":
    main()
