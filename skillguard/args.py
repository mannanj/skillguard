#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""The SkillGuard command-line argument parser (definitions only).

Kept separate from ``cli`` so the entry module stays a thin facade. ``--version``
is added by ``cli.main`` so the version string remains owned by ``cli``.
"""

from __future__ import annotations

import argparse

from skillguard import config


def build_parser() -> argparse.ArgumentParser:
    """Construct the full CLI parser (every flag except ``--version``)."""
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
        "--allow-local",
        dest="allow_local",
        action="store_true",
        help="With --mcp-introspect, permit HTTP introspection of loopback/private/"
        "link-local hosts (refused by default as an SSRF guard)",
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
        "--ack",
        metavar="NAME",
        help="Acknowledge a scanned skill's critical/high findings so the hook ALLOWS "
        "it (records that you accepted the risk; automatically cleared on re-scan)",
    )
    parser.add_argument(
        "--ack-mcp",
        metavar="NAME",
        dest="ack_mcp",
        help="Acknowledge a scanned MCP server's critical/high findings so the "
        "enforce-policy hook ALLOWS it (cleared on re-scan)",
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
        "--agent-summary",
        action="store_true",
        help="Show a terse cached-risk summary for agent launch wrappers and exit",
    )
    parser.add_argument(
        "--review",
        action="store_true",
        help="Interactively review cached findings one target at a time and exit",
    )
    parser.add_argument(
        "--install-shell-integration",
        action="store_true",
        help=(
            "Install ~/.local/bin/skillguard plus codex/claude launch summary "
            "shell integration and exit"
        ),
    )
    parser.add_argument(
        "--install-agent-adapters",
        nargs="?",
        const=".",
        default=None,
        metavar="DIR",
        help=(
            "Write repo-level AGENTS.md, Gemini, and Aider adapter files for "
            "SkillGuard's 13 supported agent surfaces"
        ),
    )
    parser.add_argument(
        "--shell-only",
        action="store_true",
        help=argparse.SUPPRESS,
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
        help="Set how the hook treats MCP tool calls: off | warn | enforce (default enforce)",
    )
    parser.add_argument("--quiet", action="store_true", help="Minimal output (for hooks/scripts)")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show all findings including low/info"
    )
    return parser
