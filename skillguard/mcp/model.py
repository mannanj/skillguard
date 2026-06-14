#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""The ``McpServer`` descriptor — the in-memory representation of one discovered
MCP server config. Holds the original (possibly secret) ``env``/``headers``/``raw``
values; see the package docstring's secret discipline for what may leave."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class McpServer:
    """A discovered MCP server config. ``env``/``headers``/``raw`` hold the
    original (possibly secret) values and stay in memory only — see the package
    docstring's secret discipline. Use ``env_names`` / redacted accessors when
    emitting anything that persists."""

    name: str
    source: str  # config file this came from
    scope: str  # global | project | plugin
    transport: str  # stdio | http | sse | unknown
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)  # in-memory only
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)  # in-memory only
    plugin: str | None = None
    raw: dict = field(default_factory=dict)  # in-memory only

    @property
    def env_names(self) -> list[str]:
        return sorted(self.env.keys())

    @property
    def launch_line(self) -> str:
        return " ".join([self.command, *[str(a) for a in self.args]]).strip()

    @property
    def match_tokens(self) -> list[str]:
        """Candidate identifiers Claude Code might use as the ``mcp__<token>__``
        tool-name prefix for this server, for the hook to map calls back here.
        Imperfect by design (Claude's exact sanitization isn't reproduced); the
        hook longest-prefix-matches and defaults to a non-blocking policy."""
        names = {self.name, self.name.replace("-", "_"), self.name.replace("_", "-")}
        if self.plugin:
            for n in list(names):
                names.add(f"plugin_{self.plugin}_{n}")
                names.add(f"plugin_{self.plugin.replace('-', '_')}_{n}")
        return sorted(t for t in names if t)
