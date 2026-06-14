#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""Discovery: find every MCP server Claude Code would load — the global
``~/.claude.json`` (top-level + per-project), ``~/.claude/mcp.json``, the
project-local ``.mcp.json``, and plugin-declared servers — and normalize each
config mapping into an ``McpServer``."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from skillguard.mcp.model import McpServer


def global_config_path() -> Path:
    return Path.home() / ".claude.json"


def secondary_config_path() -> Path:
    return Path.home() / ".claude" / "mcp.json"


def plugins_root() -> Path:
    return Path.home() / ".claude" / "plugins"


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _server_from_config(
    name: str, cfg: Any, source: Path, scope: str, plugin: str | None = None
) -> McpServer:
    cfg = cfg if isinstance(cfg, dict) else {}
    ttype = str(cfg.get("type") or cfg.get("transport") or "").lower()
    command = str(cfg.get("command") or "")
    url = str(cfg.get("url") or "")

    if ttype == "sse":
        transport = "sse"
    elif ttype in ("http", "streamable-http", "streamablehttp", "https"):
        transport = "http"
    elif ttype == "stdio":
        transport = "stdio"
    elif command:
        transport = "stdio"
    elif url:
        transport = "sse" if "sse" in url.lower() else "http"
    else:
        transport = "unknown"

    args = cfg.get("args") or []
    if not isinstance(args, list):
        args = [str(args)]
    env = cfg.get("env") if isinstance(cfg.get("env"), dict) else {}
    headers = cfg.get("headers") if isinstance(cfg.get("headers"), dict) else {}

    return McpServer(
        name=name,
        source=str(source),
        scope=scope,
        transport=transport,
        command=command,
        args=[str(a) for a in args],
        env=dict(env),
        url=url,
        headers=dict(headers),
        plugin=plugin,
        raw=dict(cfg),
    )


def _servers_from_mapping(
    mapping: Any, source: Path, scope: str, plugin: str | None = None
) -> list[McpServer]:
    if not isinstance(mapping, dict):
        return []
    return [_server_from_config(name, cfg, source, scope, plugin) for name, cfg in mapping.items()]


def discover_mcps(
    scope: str = "all",
    project_dir: Path | None = None,
    single: str | None = None,
    include_plugins: bool = True,
) -> list[McpServer]:
    """Find every MCP server Claude Code would load, deduplicated by (scope,name).

    ``scope`` mirrors the skill scanner: ``global`` (user-level configs),
    ``local``/``project`` (this project's servers), or ``all``.
    """
    # Monkeypatch seam: tests patch the path accessors on the ``skillguard.mcp``
    # package facade (e.g. ``isolate`` redirects them at a tmp_path), so resolve
    # them through the facade at call time rather than binding the local
    # submodule functions — mirrors ``paths.cache_dir`` reading ``cli.CACHE_DIR``.
    from skillguard import mcp as _facade

    global_config_path = _facade.global_config_path
    secondary_config_path = _facade.secondary_config_path

    project_dir = Path(project_dir) if project_dir else Path.cwd()
    want_global = scope in ("global", "all")
    want_project = scope in ("local", "project", "all")
    servers: list[McpServer] = []

    # 1. ~/.claude.json — top-level (global) + per-project mcpServers
    gc = _read_json(global_config_path())
    if gc is not None:
        if want_global:
            servers += _servers_from_mapping(gc.get("mcpServers"), global_config_path(), "global")
        if want_project:
            raw_projects = gc.get("projects")
            projects = raw_projects if isinstance(raw_projects, dict) else {}
            for key in {str(project_dir), str(project_dir.resolve())}:
                proj = projects.get(key)
                if isinstance(proj, dict):
                    servers += _servers_from_mapping(
                        proj.get("mcpServers"), global_config_path(), "project"
                    )

    # 2. ~/.claude/mcp.json (global)
    if want_global:
        sc = _read_json(secondary_config_path())
        if sc is not None:
            servers += _servers_from_mapping(
                sc.get("mcpServers"), secondary_config_path(), "global"
            )

    # 3. project-local .mcp.json
    if want_project:
        proj_mcp = project_dir / ".mcp.json"
        pj = _read_json(proj_mcp)
        if pj is not None:
            servers += _servers_from_mapping(pj.get("mcpServers"), proj_mcp, "project")

    # 4. plugin-provided servers
    if include_plugins and want_global:
        servers += _discover_plugin_mcps()

    # Deduplicate by (scope, name); later definitions win.
    deduped: dict[tuple[str, str], McpServer] = {}
    for s in servers:
        deduped[(s.scope, s.name)] = s
    result = list(deduped.values())

    if single:
        result = [s for s in result if s.name == single]
    result.sort(key=lambda s: (s.scope, s.name))
    return result


# Directories never worth walking for MCP configs — pruning them keeps
# discovery fast on real plugin trees (which can contain huge node_modules).
_PRUNE_DIRS = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "dist",
    "build",
    "__pycache__",
    ".cache",
    ".next",
    "target",
}


def _discover_plugin_mcps(root: Path | None = None, cap: int = 4000) -> list[McpServer]:
    """Find plugin-declared MCP servers in ``.mcp.json`` / ``plugin.json`` files.

    Uses a pruned, bounded walk (not ``rglob``) so a plugin tree with vendored
    dependencies can't make discovery crawl. ``cap`` bounds files inspected.
    """
    if root is None:
        # Same monkeypatch seam as discover_mcps — honor a patched plugins_root.
        from skillguard import mcp as _facade

        root = _facade.plugins_root()
    if not root.is_dir():
        return []
    servers: list[McpServer] = []
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _PRUNE_DIRS]
        for fn in filenames:
            if fn != "plugin.json" and not fn.endswith(".mcp.json"):
                continue
            if seen >= cap:
                return servers
            seen += 1
            cfg_path = Path(dirpath) / fn
            data = _read_json(cfg_path)
            if data is None:
                continue
            if fn == "plugin.json":
                mapping = data.get("mcpServers")
            else:
                mapping = data.get("mcpServers", data)
            if not isinstance(mapping, dict):
                continue
            plugin = _plugin_name_for(cfg_path, root)
            servers += _servers_from_mapping(mapping, cfg_path, "plugin", plugin)
    return servers


def _plugin_name_for(cfg_path: Path, root: Path) -> str:
    """Best-effort plugin identifier from a config path under the plugins root."""
    try:
        rel = cfg_path.resolve().relative_to(root.resolve())
        parts = rel.parts
        # e.g. cache/<plugin>/.mcp.json  or  marketplaces/<mp>/<plugin>/.mcp.json
        if len(parts) >= 2:
            return parts[-2]
        return parts[0]
    except (ValueError, OSError):
        return cfg_path.parent.name
