#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""Opt-in live introspection — the ONLY module that executes an untrusted server.

For stdio servers ``introspect`` *launches* the server to pull its model-facing
text (the ``instructions`` string + every tool's name/description/param text) and
hand it back for prompt-injection scanning. Kept small and dependency-isolated.

This is unsandboxed execution, so it is hardened to reduce blast radius (true
OS-level sandboxing is a separate roadmap item — keep the printed warning honest):

* **Env minimization** — the child sees only ``PATH``/``HOME`` (+ ``SystemRoot``
  on Windows) and the server's *declared* ``env``, never the operator's full
  shell, so an untrusted server can't read every API key in ``os.environ``.
* **Process lifecycle** — the child is launched in its own session/process group
  and is always reaped in a ``finally``; on timeout the whole group is killed so
  forked grandchildren can't orphan.
* **SSRF guard** — HTTP introspection refuses loopback / RFC1918 / link-local /
  ``169.254.169.254`` (cloud metadata) and known exfil sinks unless the caller
  passes ``allow_local`` (the ``--allow-local`` flag)."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import signal
import socket
import subprocess
from typing import Any
from urllib.parse import urlparse

from skillguard.mcp.model import McpServer
from skillguard.mcp.rules import SUSPICIOUS_HOSTS


def introspect(mcp: McpServer, timeout: float = 20.0, allow_local: bool = False) -> dict:
    """Launch/connect to the server and pull its model-facing text (server
    ``instructions`` + every tool's name/description/param descriptions).

    WARNING: for stdio servers this EXECUTES the server. Callers gate it behind
    an explicit opt-in. Always returns a dict; failures populate ``error`` and
    leave ``instructions``/``tools`` empty so scanning degrades to static.

    ``allow_local`` lifts the HTTP SSRF guard (internal/metadata hosts) — only
    set it for a deliberately local/private endpoint you trust.
    """
    try:
        if mcp.transport == "stdio" and mcp.command:
            return _introspect_stdio(mcp, timeout)
        if mcp.transport in ("http", "sse") and mcp.url:
            return _introspect_http(mcp, timeout, allow_local=allow_local)
        return {
            "ok": False,
            "instructions": "",
            "tools": [],
            "error": f"no introspection for transport {mcp.transport!r}",
        }
    except Exception as e:  # never let introspection crash a scan
        return {"ok": False, "instructions": "", "tools": [], "error": str(e)}


def _jsonrpc(method: str, _id: int | None = None, **params: Any) -> str:
    msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if _id is not None:
        msg["id"] = _id
    if params:
        msg["params"] = params
    return json.dumps(msg)


_INIT_PARAMS = {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "skillguard", "version": "scan"},
}


# Vars a launcher legitimately needs to resolve binaries/interpreters. The
# untrusted child gets ONLY these plus the server's *declared* ``env`` — never
# the operator's full shell, which would hand every API key in ``os.environ`` to
# the very code we are about to execute.
_ENV_PASSTHROUGH = ("PATH", "HOME", "SystemRoot")


def _minimal_env(mcp: McpServer) -> dict[str, str]:
    """The deliberately small environment handed to the untrusted child."""
    env = {k: os.environ[k] for k in _ENV_PASSTHROUGH if k in os.environ}
    env.update({k: str(v) for k, v in mcp.env.items()})
    return env


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the child and, on POSIX, its whole process group — so a server that
    forks grandchildren can't leave them orphaned."""
    if os.name == "posix":
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass  # group already gone or unavailable; fall back to the child
    proc.kill()


def _reap(proc: subprocess.Popen) -> None:
    """Final, best-effort reap; never raises, so it is safe in a ``finally``."""
    if proc.poll() is None:
        _kill_tree(proc)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _introspect_stdio(mcp: McpServer, timeout: float) -> dict:
    requests = (
        "\n".join(
            [
                _jsonrpc("initialize", 1, **_INIT_PARAMS),
                _jsonrpc("notifications/initialized"),
                _jsonrpc("tools/list", 2),
            ]
        )
        + "\n"
    )

    proc = subprocess.Popen(
        [mcp.command, *mcp.args],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_minimal_env(mcp),
        # Own session/process group so a forking server can't orphan children.
        start_new_session=(os.name == "posix"),
    )
    out = ""
    try:
        try:
            out, _err = proc.communicate(input=requests, timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            # Only a *second* timeout is swallowed; any other error propagates to
            # introspect()'s handler and is recorded, never silently dropped.
            try:
                out, _err = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                out = ""
    finally:
        _reap(proc)
    return _parse_introspection(out)


def _blocked_host_reason(host: str) -> str | None:
    """Return why an HTTP introspection target is refused, or ``None`` to allow.

    Blocks SSRF-style targets: a known exfiltration sink, or any name that
    resolves to a loopback / private / link-local / reserved address — including
    the ``169.254.169.254`` cloud-metadata endpoint (which is link-local). DNS is
    resolved so a public name pointing at an internal IP is caught too."""
    if not host:
        return "no host in URL"
    host_l = host.lower()
    if any(host_l == h or host_l.endswith("." + h) for h in SUSPICIOUS_HOSTS):
        return f"{host!r} is a known exfiltration sink"
    try:
        addrs = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except socket.gaierror:
        addrs = {host}  # unresolvable — still test it as a possible literal IP
    for addr in addrs:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return f"{host!r} resolves to internal address {addr}"
    return None


def _introspect_http(mcp: McpServer, timeout: float, allow_local: bool = False) -> dict:
    import urllib.request

    if not allow_local:
        reason = _blocked_host_reason(urlparse(mcp.url).hostname or "")
        if reason:
            return {
                "ok": False,
                "instructions": "",
                "tools": [],
                "error": f"refused to connect: {reason} (pass --allow-local to override)",
            }

    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    # Pass through configured headers, resolving ${ENV} references locally.
    for hk, hv in mcp.headers.items():
        headers[hk] = _resolve_env_refs(hv)
    body = (_jsonrpc("initialize", 1, **_INIT_PARAMS) + "\n").encode()
    req = urllib.request.Request(mcp.url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
    # Best-effort: many remote servers require OAuth and will 401 before this.
    return _parse_introspection(raw)


def _resolve_env_refs(value: str) -> str:
    def sub(m: re.Match) -> str:
        return os.environ.get(m.group(1) or m.group(2) or "", m.group(0))

    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)", sub, str(value))


def _parse_introspection(stream: str) -> dict:
    """Pull initialize.instructions + tools/list from newline- or SSE-framed
    JSON-RPC output."""
    instructions, tools, ok = "", [], False
    for line in stream.splitlines():
        line = line.strip()
        if line.startswith("data:"):  # SSE framing
            line = line[5:].strip()
        if not line or not line.startswith("{"):
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        result = msg.get("result")
        if not isinstance(result, dict):
            continue
        if "serverInfo" in result or "instructions" in result or "protocolVersion" in result:
            ok = True
            if isinstance(result.get("instructions"), str):
                instructions = result["instructions"]
        if isinstance(result.get("tools"), list):
            ok = True
            for t in result["tools"]:
                if not isinstance(t, dict):
                    continue
                params = []
                schema = t.get("inputSchema") or {}
                props = schema.get("properties") if isinstance(schema, dict) else None
                if isinstance(props, dict):
                    for pname, pdef in props.items():
                        desc = pdef.get("description", "") if isinstance(pdef, dict) else ""
                        params.append({"name": pname, "description": desc})
                tools.append(
                    {
                        "name": t.get("name", ""),
                        "description": t.get("description", ""),
                        "params": params,
                    }
                )
    return {
        "ok": ok,
        "instructions": instructions,
        "tools": tools,
        "error": "" if ok else "no MCP response parsed",
    }
