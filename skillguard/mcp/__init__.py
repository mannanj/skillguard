#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""
MCP (Model Context Protocol) server discovery and scanning.

Claude Code loads MCP servers — third-party processes and remote endpoints that
inject tool descriptions and "instructions" straight into the model's context —
from several config files. Those servers are an unaudited supply chain with the
same trust problem as skills, plus a prompt-injection surface skills don't have:
their tool descriptions and server instructions are model-facing text.

This package:
  * **discovers** every configured server (``~/.claude.json`` global + per
    project, ``~/.claude/mcp.json``, and plugin ``.mcp.json`` files) — see
    ``discovery``;
  * **materializes** each server's scannable surface — a *redacted* config plus
    the launch command / endpoint / env-var NAMES — to inspectable files so the
    existing engines (local regex, Cisco, SkillAudit, Snyk) scan it unchanged —
    see ``materialize`` (redaction authority is ``secrets``);
  * **analyzes** the config structurally for MCP-specific risks (remote/unpinned
    code execution, insecure transport, inline plaintext secrets) via
    ``McpConfigEngine`` — see ``engine`` (launch parsing in ``launch``, detection
    data in ``rules``);
  * optionally **introspects** a server (opt-in — this *launches* it) to pull its
    tool descriptions and instructions and scan them for prompt injection — see
    ``introspect`` (the only module that executes untrusted code).

Secret discipline: any value that could be a secret — an env value, a header
value, a credential-bearing launch argument, or a credential-bearing URL query
parameter — is read in memory only, to decide whether an inline literal secret
is present. It is NEVER written to a materialized file, a finding message, the
cache, or the history DB. Only NAMES (variable, header, flag, query-param) ever
leave this package. ``secrets`` is the single authority for that discipline.

This ``__init__`` is a thin facade: it re-exports the names the rest of the
codebase and the test suite import from ``skillguard.mcp`` so the package
conversion is invisible to importers. New code should import from the focused
submodule; these re-exports preserve the historical flat-module API.
"""

from __future__ import annotations

from skillguard.mcp.discovery import discover_mcps

# Re-exported via the redundant-alias idiom (``x as x``) so ruff treats them as
# intentional re-exports, not unused imports: the three path accessors are the
# monkeypatch seam the ``isolate`` test fixture patches on this package, and
# ``_runner_package`` is reached for by attribute in ``test_mcp_engine``.
from skillguard.mcp.discovery import global_config_path as global_config_path
from skillguard.mcp.discovery import plugins_root as plugins_root
from skillguard.mcp.discovery import secondary_config_path as secondary_config_path
from skillguard.mcp.engine import McpConfigEngine, analyze_mcp_config
from skillguard.mcp.introspect import introspect
from skillguard.mcp.launch import _runner_package as _runner_package
from skillguard.mcp.materialize import (
    materialize_surface,
    safe_name,
    write_introspection_surface,
)
from skillguard.mcp.model import McpServer
from skillguard.mcp.secrets import redacted_config

__all__ = [
    # model
    "McpServer",
    # discovery
    "discover_mcps",
    # redaction / secret detection (single authority lives in ``secrets``)
    "redacted_config",
    # materialization
    "safe_name",
    "materialize_surface",
    "write_introspection_surface",
    # structural analysis
    "analyze_mcp_config",
    "McpConfigEngine",
    # introspection (executes untrusted code — see ``introspect``)
    "introspect",
]
