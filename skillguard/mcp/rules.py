#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""Static detection data shared by the launch parser and the structural engine:
the package-runner set and the exfiltration-sink host list. Kept as plain data so
adding a runner or a sink host is a one-line edit with no logic change."""

from __future__ import annotations

# Hosts that are exfiltration sinks, not legitimate MCP endpoints.
SUSPICIOUS_HOSTS = (
    "webhook.site",
    "requestbin.com",
    "requestbin.net",
    "pipedream.net",
    "interact.sh",
    "burpcollaborator.net",
    "ngrok.io",
    "ngrok.com",
    "ngrok.app",
)

# Package runners that fetch and execute third-party code at launch.
_RUNNERS = ("npx", "pnpm", "bunx", "yarn", "uvx", "uv", "pipx", "dlx", "deno")
