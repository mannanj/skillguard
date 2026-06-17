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
CODEX_USER_SKILLS_DIR = Path.home() / ".agents" / "skills"
CODEX_SYSTEM_SKILLS_DIR = Path.home() / ".codex" / "skills" / ".system"
CODEX_ADMIN_SKILLS_DIR = Path("/Library/Application Support/OpenAI/Codex/skills")
CODEX_PLUGIN_CACHE_DIR = Path.home() / ".codex" / "plugins" / "cache"

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
    seen: set[Path] = set()

    dirs_to_scan: list[tuple[Path, str]] = []
    if scope in ("global", "all"):
        dirs_to_scan.append((GLOBAL_SKILLS_DIR, "global"))
        dirs_to_scan.append((CODEX_USER_SKILLS_DIR, "global"))
        dirs_to_scan.append((CODEX_SYSTEM_SKILLS_DIR, "global"))
        dirs_to_scan.append((CODEX_ADMIN_SKILLS_DIR, "global"))
    if scope in ("local", "all"):
        dirs_to_scan.extend((path, "local") for path in _local_skill_dirs(project_dir))

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
            resolved_key = resolved.resolve()
            if resolved_key in seen:
                continue
            seen.add(resolved_key)

            # Collect all files in the skill directory
            skill_files = _scannable_files(resolved)

            skills.append(
                SkillInfo(
                    name=entry.name,
                    path=resolved,
                    scope=skill_scope,
                    files=skill_files,
                )
            )

    if scope in ("global", "all"):
        skills.extend(_discover_codex_plugin_skills(single_skill, seen))

    return skills


def _scannable_files(skill_dir: Path) -> list[Path]:
    if not skill_dir.is_dir():
        return []
    return sorted(f for f in skill_dir.rglob("*") if f.is_file() and f.suffix in SCANNABLE_SUFFIXES)


def _local_skill_dirs(project_dir: Path) -> list[Path]:
    dirs: list[Path] = []
    for root in _project_roots(project_dir):
        dirs.append(root / ".claude" / "skills")
        dirs.append(root / ".agents" / "skills")
    return dirs


def _project_roots(project_dir: Path) -> list[Path]:
    roots = [project_dir]
    for parent in (project_dir, *project_dir.parents):
        if (parent / ".git").exists():
            if parent not in roots:
                roots.append(parent)
            break
    return roots


def _discover_codex_plugin_skills(single_skill: str | None, seen: set[Path]) -> list[SkillInfo]:
    if not CODEX_PLUGIN_CACHE_DIR.is_dir():
        return []

    skills: list[SkillInfo] = []
    for skill_file in sorted(CODEX_PLUGIN_CACHE_DIR.glob("*/*/*/skills/*/SKILL.md")):
        skill_dir = skill_file.parent
        plugin_dir = skill_dir.parent.parent.parent
        plugin_name = plugin_dir.name
        name = f"{skill_dir.name}@{plugin_name}"
        if single_skill and single_skill not in (skill_dir.name, plugin_name, name):
            continue
        resolved = skill_dir.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        skills.append(
            SkillInfo(
                name=name,
                path=skill_dir,
                scope="plugin",
                files=_scannable_files(skill_dir),
            )
        )
    return skills
