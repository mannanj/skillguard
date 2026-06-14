#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""Materialization: write each server's *redacted*, scannable surface to disk so
the existing engines scan it like any skill, and (post-introspection) write the
model-facing text next to it. Only redacted text and NAMES ever reach disk."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from skillguard.mcp.model import McpServer
from skillguard.mcp.secrets import redact_url_secrets, redacted_config, redacted_launch_line
from skillguard.model import SkillInfo


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name) or "_unnamed"


def materialize_surface(mcp: McpServer, base_dir: Path) -> SkillInfo:
    """Write the server's redacted, scannable surface under
    ``base_dir/<safe-name>/surface/`` and return a SkillInfo (kind="mcp") the
    engine pipeline can scan like any skill. Inspectable after the fact: the
    files are exactly what was scanned."""
    sdir = base_dir / safe_name(mcp.name)
    surface = sdir / "surface"
    surface.mkdir(parents=True, exist_ok=True)

    files: list[Path] = []

    cfg_file = surface / "mcp-config.json"
    cfg_file.write_text(json.dumps(redacted_config(mcp), indent=2, sort_keys=True))
    files.append(cfg_file)

    if mcp.transport == "stdio" and mcp.launch_line:
        cmd_file = surface / "command.txt"
        cmd_file.write_text(redacted_launch_line(mcp) + "\n")
        files.append(cmd_file)

    if mcp.url:
        ep = surface / "endpoint.txt"
        header_names = "\n".join(f"header: {h}" for h in sorted(mcp.headers))
        ep.write_text(f"{redact_url_secrets(mcp.url)}\n{header_names}\n")
        files.append(ep)

    if mcp.env_names:
        env_file = surface / "env.txt"
        env_file.write_text("\n".join(mcp.env_names) + "\n")
        files.append(env_file)

    source_mtime = 0.0
    try:
        source_mtime = os.path.getmtime(mcp.source)
    except OSError:
        pass

    return SkillInfo(
        name=mcp.name,
        path=surface,
        scope=mcp.scope,
        files=files,
        kind="mcp",
        mtime_override=source_mtime,
        extra={"mcp": mcp},
    )


def write_introspection_surface(target: SkillInfo, intro: dict) -> list[Path]:
    """Materialize introspected model-facing text next to the static surface and
    register it on the target so the content engines scan it. Returns new files."""
    surface = target.path
    new_files: list[Path] = []

    if intro.get("instructions"):
        f = surface / "server-instructions.md"
        f.write_text(intro["instructions"])
        new_files.append(f)

    tools = intro.get("tools") or []
    if tools:
        lines = ["# MCP tool descriptions (model-facing surface)\n"]
        for t in tools:
            lines.append(f"## {t.get('name', '')}\n")
            lines.append((t.get("description") or "") + "\n")
            for p in t.get("params", []):
                lines.append(f"- param `{p.get('name', '')}`: {p.get('description', '')}")
            lines.append("")
        f = surface / "tools.md"
        f.write_text("\n".join(lines))
        new_files.append(f)

    target.files.extend(new_files)
    return new_files
