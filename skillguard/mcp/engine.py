#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""Structural analysis — the "mcp" engine.

``analyze_mcp_config`` surfaces MCP-specific risks the text engines can't see:
supply-chain execution, insecure transport, and inline plaintext secrets. The
former 117-line god-function is split into four single-concern predicates
(endpoint / launch / inline-secret / exposure) that each return findings in the
original emission order. Severities are calibrated so routine ``npx``/``uvx``
servers don't drown real red flags.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from urllib.parse import urlparse

from skillguard.mcp.launch import _docker_image, _runner_in, _runner_package
from skillguard.mcp.model import McpServer
from skillguard.mcp.rules import SUSPICIOUS_HOSTS
from skillguard.mcp.secrets import (
    _CRED_FLAG,
    _INLINE_KV_SECRET,
    _URL_QS_SECRET,
    _header_has_inline_secret,
    _is_safe_ref,
    looks_secretish,
)
from skillguard.model import Finding, SkillInfo

_CFG_REF = "mcp-config.json"


def _collector() -> tuple[list[Finding], Callable[..., None]]:
    """A findings list plus an ``add(severity, category, message, file=…)`` sink
    that appends an engine="mcp" Finding — the original god-function's idiom,
    now per-predicate so each detector reads as a flat list of rules."""
    out: list[Finding] = []

    def add(severity: str, category: str, message: str, file: str = _CFG_REF) -> None:
        out.append(
            Finding(engine="mcp", severity=severity, category=category, message=message, file=file)
        )

    return out, add


def _endpoint_findings(mcp: McpServer) -> list[Finding]:
    """Endpoint / transport risks (http, sse): exfil sinks, cleartext transport,
    raw-IP endpoints."""
    out, add = _collector()
    if not mcp.url:
        return out
    parsed = urlparse(mcp.url if "://" in mcp.url else f"//{mcp.url}")
    host = (parsed.hostname or "").lower()
    if any(host == h or host.endswith("." + h) or h in mcp.url.lower() for h in SUSPICIOUS_HOSTS):
        add(
            "critical",
            "mcp_suspicious_endpoint",
            f"MCP endpoint points at a known exfiltration host: {host or mcp.url}",
            "endpoint.txt",
        )
    if parsed.scheme == "http":
        add(
            "medium",
            "mcp_insecure_transport",
            f"MCP endpoint uses unencrypted http:// ({host}); traffic and any "
            f"auth header are sent in clear text.",
            "endpoint.txt",
        )
    if host and re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
        add(
            "low",
            "mcp_raw_ip_endpoint",
            f"MCP endpoint is a raw IP address ({host}), not a named host.",
            "endpoint.txt",
        )
    return out


def _launch_findings(mcp: McpServer) -> list[Finding]:
    """stdio launch-command risks: curl|sh, inline -e/-c exec, base64-decode,
    runner-fetched / unpinned packages, and container images."""
    out, add = _collector()
    launch = mcp.launch_line
    if not launch:
        return out
    low = launch.lower()

    if re.search(r"\b(curl|wget)\b[^\n|]*\|\s*(ba)?sh", low):
        add(
            "high",
            "mcp_remote_exec",
            "MCP launch command pipes a network download straight into a shell.",
            "command.txt",
        )
    if re.search(r"\b(node|deno|bun)\b[^\n]*\s-e\b", low) or re.search(
        r"\bpython[23]?\b[^\n]*\s-c\b", low
    ):
        add(
            "high",
            "mcp_inline_exec",
            "MCP launches inline code via an -e/-c flag; the code runs at every start.",
            "command.txt",
        )
    if re.search(r"base64\s+(--?d(ecode)?)\b", low):
        add(
            "high",
            "mcp_obfuscated_launch",
            "MCP launch command base64-decodes content before running it.",
            "command.txt",
        )

    runner = _runner_in(low)
    if runner:
        git_src = re.search(r"(git\+https?://\S+|github:\S+|--from\s+git\+\S+)", launch, re.I)
        if git_src:
            add(
                "medium",
                "mcp_remote_code_source",
                f"MCP runs code fetched from a git source via {runner}; the upstream "
                f"repo can change what executes at any time.",
                "command.txt",
            )
        else:
            pkg, ver = _runner_package(launch, runner)
            if pkg and (ver is None or ver == "latest"):
                add(
                    "low",
                    "mcp_unpinned_dependency",
                    f"MCP runs third-party package '{pkg}' unpinned (@{ver or 'none'}) via "
                    f"{runner}; a compromised or typosquatted upstream would execute at launch. "
                    f"Pin an exact version.",
                    "command.txt",
                )
            elif pkg:
                add(
                    "info",
                    "mcp_third_party_runtime",
                    f"MCP runs third-party package '{pkg}@{ver}' via {runner} (pinned).",
                    "command.txt",
                )
    if re.search(r"\bdocker\s+run\b", low):
        image = _docker_image(launch)
        add(
            "low",
            "mcp_container_runtime",
            f"MCP runs a container image{f' ({image})' if image else ''}; it pulls and "
            f"executes whatever that tag resolves to.",
            "command.txt",
        )
    return out


def _inline_secret_findings(mcp: McpServer) -> list[Finding]:
    """Inline plaintext secrets in env values, headers, launch args, or URL query
    parameters. NEVER echoes the secret value — only its location/name."""
    out, add = _collector()

    for ename, evalue in mcp.env.items():
        if looks_secretish(evalue):
            add(
                "high",
                "mcp_inline_secret",
                f"Env var '{ename}' has an inline literal value in the MCP config (looks like a "
                f"plaintext credential). Reference the environment with ${{{ename}}} instead.",
            )
    for hname, hvalue in mcp.headers.items():
        if _header_has_inline_secret(hname, hvalue):
            add(
                "high",
                "mcp_inline_secret",
                f"Header '{hname}' carries an inline literal credential in the MCP config. "
                f"Reference an env var (e.g. ${{TOKEN}}) instead of hard-coding it.",
                "endpoint.txt",
            )
    i = 0
    while i < len(mcp.args):
        s = str(mcp.args[i])
        kv = _INLINE_KV_SECRET.match(s)
        if looks_secretish(s):
            add(
                "high",
                "mcp_inline_secret",
                f"Launch argument #{i} looks like a plaintext credential. Pass it via an "
                f"environment variable reference instead of hard-coding it.",
                "command.txt",
            )
        elif kv and not _is_safe_ref(kv.group(2)):
            add(
                "high",
                "mcp_inline_secret",
                f"Launch flag '{kv.group(1).rstrip('=')}' carries an inline literal credential. "
                f"Reference an env var instead.",
                "command.txt",
            )
        elif _CRED_FLAG.match(s) and i + 1 < len(mcp.args):
            nxt = str(mcp.args[i + 1])
            if nxt and not _is_safe_ref(nxt) and not nxt.startswith("-"):
                add(
                    "high",
                    "mcp_inline_secret",
                    f"Launch flag '{s}' is followed by an inline literal credential. "
                    f"Reference an env var instead.",
                    "command.txt",
                )
                i += 2
                continue
        i += 1
    if mcp.url:
        for m in _URL_QS_SECRET.finditer(mcp.url):
            if not _is_safe_ref(m.group(3)):
                add(
                    "high",
                    "mcp_inline_secret",
                    f"MCP endpoint URL carries an inline credential in query parameter "
                    f"'{m.group(2)}'. Reference an env var instead.",
                    "endpoint.txt",
                )
                break
    return out


def _exposure_findings(mcp: McpServer) -> list[Finding]:
    """Informational: what this server can read, plus the unparsed-config
    fallback when there is nothing to scan statically."""
    out, add = _collector()
    if mcp.env_names:
        add(
            "info",
            "mcp_env_exposure",
            f"This MCP server is granted {len(mcp.env_names)} environment secret(s): "
            f"{', '.join(mcp.env_names)}. It can read these at runtime.",
        )
    if mcp.transport == "unknown" and not mcp.launch_line and not mcp.url:
        add(
            "info",
            "mcp_unparsed",
            "MCP server config has neither a command nor a url; nothing to scan statically.",
        )
    return out


def analyze_mcp_config(mcp: McpServer) -> list[Finding]:
    """MCP-specific structural findings the text engines can't see: supply-chain
    execution, insecure transport, and inline plaintext secrets. Severities are
    calibrated so routine ``npx``/``uvx`` servers don't drown real red flags —
    third-party runtimes are ``low``/``info`` awareness; ``curl|sh``, inline
    ``eval``, exfil endpoints, and plaintext secrets are ``high``/``critical``."""
    return [
        *_endpoint_findings(mcp),
        *_launch_findings(mcp),
        *_inline_secret_findings(mcp),
        *_exposure_findings(mcp),
    ]


class McpConfigEngine:
    """Engine-interface wrapper around ``analyze_mcp_config`` so structural MCP
    findings flow through the same pipeline, caching, and triage as every other
    engine. Returns nothing for skill targets, so it is harmless if always on."""

    name = "mcp"
    available = True
    inter_target_delay = 0.0

    def scan(self, target: SkillInfo) -> list[Finding]:
        mcp = target.extra.get("mcp") if getattr(target, "extra", None) else None
        if getattr(target, "kind", "skill") != "mcp" or mcp is None:
            return []
        return analyze_mcp_config(mcp)
