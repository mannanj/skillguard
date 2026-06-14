#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""Skill discovery: enumerate skill directories into ``SkillInfo`` targets.

``cli`` re-exports ``discover_skills`` (tests/the entrypoint monkeypatch it as
``cli.discover_skills``). MCP discovery lives in ``skillguard.mcp``.
"""

from __future__ import annotations

from pathlib import Path

from skillguard.model import SkillInfo

GLOBAL_SKILLS_DIR = Path.home() / ".claude" / "skills"

# File types a skill can ship that are worth scanning.
SCANNABLE_SUFFIXES = (".md", ".py", ".sh", ".js", ".ts", ".yaml", ".yml", ".json")


def rel_to(file_path: Path, base: Path) -> str:
    """Path of ``file_path`` relative to its target ``base``, for display in a
    finding. Falls back to the bare filename when the file resolves outside
    ``base`` (e.g. a symlinked-in file), so a finding always names *something*.
    """
    return (
        str(file_path.relative_to(base)) if str(file_path).startswith(str(base)) else file_path.name
    )


def discover_skills(
    scope: str, project_dir: Path, single_skill: str | None = None
) -> list[SkillInfo]:
    """Find all skills in global and/or local directories."""
    skills: list[SkillInfo] = []

    dirs_to_scan: list[tuple[Path, str]] = []
    if scope in ("global", "all"):
        dirs_to_scan.append((GLOBAL_SKILLS_DIR, "global"))
    if scope in ("local", "all"):
        local_skills = project_dir / ".claude" / "skills"
        if local_skills.is_dir():
            dirs_to_scan.append((local_skills, "local"))

    for base_dir, skill_scope in dirs_to_scan:
        if not base_dir.is_dir():
            continue
        for entry in sorted(base_dir.iterdir()):
            if not entry.is_dir() and not entry.is_symlink():
                continue
            # Skip disabled skills
            if entry.name.startswith("_disabled"):
                continue
            # Filter to single skill if requested
            if single_skill and entry.name != single_skill:
                continue

            # Resolve symlinks for scanning
            resolved = entry.resolve() if entry.is_symlink() else entry

            # Collect all files in the skill directory
            skill_files = []
            if resolved.is_dir():
                for f in resolved.rglob("*"):
                    if f.is_file() and f.suffix in SCANNABLE_SUFFIXES:
                        skill_files.append(f)

            skills.append(
                SkillInfo(
                    name=entry.name,
                    path=resolved,
                    scope=skill_scope,
                    files=skill_files,
                )
            )

    return skills
