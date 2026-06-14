#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""Launch-string parsing: identify the package runner in a launch command and
extract the package/version or container image it would fetch and execute."""

from __future__ import annotations

import os

from skillguard.mcp.rules import _RUNNERS


def _runner_in(low_launch: str) -> str | None:
    toks = low_launch.split()
    for i, t in enumerate(toks):
        base = os.path.basename(t)
        if base in _RUNNERS:
            # `uv tool run` / `uv run` / `pnpm dlx` / `yarn dlx` count as runners
            if base in ("uv", "pnpm", "yarn", "deno"):
                nxt = toks[i + 1] if i + 1 < len(toks) else ""
                if base == "uv" and nxt in ("tool", "run"):
                    return "uv"
                if base in ("pnpm", "yarn") and nxt == "dlx":
                    return base
                if base == "deno" and nxt in ("run",):
                    return "deno"
                continue
            return base
    return None


def _runner_package(launch: str, runner: str) -> tuple[str | None, str | None]:
    """Extract (package, version) from a runner invocation. Skips flags and the
    runner subcommand. Returns version None when unpinned."""
    toks = launch.split()
    # advance past the runner token and known sub-tokens / flags
    i = 0
    while i < len(toks) and os.path.basename(toks[i]).lower() != runner:
        i += 1
    i += 1
    skip_words = {"dlx", "run", "tool", "--from", "exec"}
    pkg = None
    while i < len(toks):
        t = toks[i]
        if t in skip_words:
            i += 1
            # --from takes the package as its argument
            continue
        if t.startswith("-"):
            i += 1
            continue
        pkg = t
        break
    if not pkg:
        return None, None
    # strip scoped-package leading @, then split version
    if pkg.startswith("@"):
        at = pkg.find("@", 1)
        if at == -1:
            return pkg, None
        return pkg[:at], pkg[at + 1 :]
    if "@" in pkg:
        name, ver = pkg.rsplit("@", 1)
        return name, ver
    return pkg, None


def _docker_image(launch: str) -> str:
    toks = launch.split()
    for i, t in enumerate(toks):
        if t == "run":
            for cand in toks[i + 1 :]:
                if cand.startswith("-"):
                    continue
                if cand in ("-e", "--env", "-v", "--volume", "-i", "--rm", "-t"):
                    continue
                return cand
    return ""
