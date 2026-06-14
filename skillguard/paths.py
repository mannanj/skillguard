#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""Filesystem paths for verdict caches, the triage store, and the history DB.

Every path is derived *per call* from ``cache_dir()`` so that tests which repoint
the cache — ``monkeypatch.setattr(cli, "CACHE_DIR", tmp)`` — transparently
redirect every helper here. ``cache_dir()`` reads ``cli.CACHE_DIR``, the single
monkeypatchable source of truth, and does so via a function-local import so this
module carries no import-time dependency on ``cli`` (``cli`` imports ``paths`` to
re-export these helpers; the read happens only at call time, once both modules
are fully loaded). Never freeze ``CACHE_DIR`` into a module global here.
"""

from __future__ import annotations

from pathlib import Path

from skillguard.mcp import safe_name

MCP_CACHE_SUBDIR = "mcps"  # MCP verdicts/surfaces live under <cache>/mcps/


def cache_dir() -> Path:
    """The active cache directory: ``cli.CACHE_DIR``, read at call time so the
    monkeypatch seam (and any runtime override) is always honored."""
    from skillguard import cli

    return cli.CACHE_DIR


def triage_path() -> Path:
    # Computed per-call (not module-level) so tests that repoint CACHE_DIR work.
    return cache_dir() / "_triage.json"


def db_path() -> Path:
    """History DB path, computed per-call so tests that repoint CACHE_DIR work."""
    return cache_dir() / "skillguard.db"


def cache_path_for(name: str, kind: str = "skill") -> Path:
    """Where a target's verdict cache lives. MCP verdicts live under a ``mcps/``
    subdir so they never collide with a same-named skill, and so the hook can
    tell the two apart."""
    if kind == "mcp":
        return cache_dir() / MCP_CACHE_SUBDIR / f"{safe_name(name)}.json"
    return cache_dir() / f"{name}.json"


def resolve_existing_cache(name: str) -> Path | None:
    """Locate a target's verdict cache, whether it's a skill (top-level) or an
    MCP (under ``mcps/``). Skill path wins on the rare name collision."""
    skill_p = cache_path_for(name, "skill")
    if skill_p.exists():
        return skill_p
    mcp_p = cache_path_for(name, "mcp")
    if mcp_p.exists():
        return mcp_p
    return None
