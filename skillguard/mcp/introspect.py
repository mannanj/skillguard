#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""Opt-in live introspection — the ONLY module that executes an untrusted server.

For stdio servers ``introspect`` *launches* the server to pull its model-facing
text (the ``instructions`` string + every tool's name/description/param text) and
hand it back for prompt-injection scanning. Kept small and dependency-isolated;
plan 008 hardens this (env minimization, SSRF guard, process lifecycle)."""

from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any

from skillguard.mcp.model import McpServer


def introspect(mcp: McpServer, timeout: float = 20.0) -> dict:
    """Launch/connect to the server and pull its model-facing text (server
    ``instructions`` + every tool's name/description/param descriptions).

    WARNING: for stdio servers this EXECUTES the server. Callers gate it behind
    an explicit opt-in. Always returns a dict; failures populate ``error`` and
    leave ``instructions``/``tools`` empty so scanning degrades to static.
    """
    try:
        if mcp.transport == "stdio" and mcp.command:
            return _introspect_stdio(mcp, timeout)
        if mcp.transport in ("http", "sse") and mcp.url:
            return _introspect_http(mcp, timeout)
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
        env={**os.environ, **{k: str(v) for k, v in mcp.env.items()}},
    )
    try:
        out, _err = proc.communicate(input=requests, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            out, _err = proc.communicate(timeout=5)
        except Exception:
            out = ""
    return _parse_introspection(out)


def _introspect_http(mcp: McpServer, timeout: float) -> dict:
    import urllib.request

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
