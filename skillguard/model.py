#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""
Core scan data types, shared by the CLI engine pipeline and the MCP scanner.

These live in their own module so ``cli`` and ``mcp`` can both depend on them
without importing each other. ``cli`` re-exports ``Finding`` / ``SkillInfo`` so
existing ``from skillguard.cli import ...`` keeps working.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


@dataclass
class Finding:
    engine: str
    severity: str  # critical, high, medium, low, info
    category: str
    message: str
    file: str = ""
    line: int = 0
    context: str = ""
    triaged_fp: bool = False

    def sort_key(self) -> tuple:
        return (SEVERITY_ORDER.get(self.severity, 99), self.engine, self.category)


def max_severity_of(findings: Iterable[Finding]) -> str:
    """Worst (lowest sort_key) severity among findings, or 'clean' if none."""
    active = [f for f in findings if not f.triaged_fp]
    if not active:
        return "clean"
    return min(active, key=lambda f: f.sort_key()).severity


def worst_severity(severities: Iterable[str]) -> str:
    """Worst severity among a sequence of severity strings, 'clean' if all clean/empty."""
    worst = "clean"
    for s in severities:
        if SEVERITY_ORDER.get(s, 99) < SEVERITY_ORDER.get(worst, 99):
            worst = s
    return worst


def normalize_severity(sev: str) -> str:
    """Clamp an arbitrary severity string to the known severity vocabulary.

    Lower-cases the input and returns it when it is one of ``SEVERITY_ORDER``'s
    keys, otherwise falls back to ``"medium"``. This is the single home for the
    "unknown severity → medium" rule each engine used to inline. Engines that
    speak their own risk vocabulary (e.g. SkillAudit's ``clean``/``moderate``)
    pre-map those terms, then defer here for the final clamp.
    """
    s = (sev or "").lower()
    return s if s in SEVERITY_ORDER else "medium"


@dataclass
class SkillInfo:
    """A scannable target. Despite the name (kept for API stability), this
    represents either a *skill* (a directory of files) or an *MCP server* (a
    server config whose scannable surface has been materialized to ``files``).

    ``kind`` distinguishes the two. For MCP targets, ``path`` is the
    materialized surface directory, ``mtime_override`` carries the source config
    file's mtime (so the hook's TOCTOU guard re-blocks when the config changes),
    and ``extra['mcp']`` holds the originating server descriptor.
    """

    name: str
    path: Path
    scope: str  # skill: global|local ; mcp: global|project|plugin
    files: list[Path] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    kind: str = "skill"  # "skill" | "mcp"
    mtime_override: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def active_findings(self) -> list[Finding]:
        return [f for f in self.findings if not f.triaged_fp]

    @property
    def max_severity(self) -> str:
        return max_severity_of(self.findings)

    @property
    def mtime_epoch(self) -> float:
        """Source-of-truth mtime for the TOCTOU guard.

        MCP targets set ``mtime_override`` (the config file's mtime). Skill
        targets fall back to their ``SKILL.md`` mtime.
        """
        if self.mtime_override is not None:
            return self.mtime_override
        skill_md = self.path / "SKILL.md"
        if skill_md.exists():
            return skill_md.stat().st_mtime
        return 0.0


@runtime_checkable
class Engine(Protocol):
    """Structural contract every scan engine satisfies.

    An engine exposes:

    - ``name`` — stable identifier used in registry keys and finding records;
    - ``available`` — ``False`` when a backing tool/credential is missing, so the
      selector can skip it (declared read-only so an engine may back it with a
      plain attribute *or* a computed property, e.g. SnykEngine reads its token
      at call time);
    - ``inter_target_delay`` — seconds the dispatcher sleeps *between* targets for
      this engine (``0.0`` for everything except rate-limited remote APIs);
    - ``scan`` — maps one target to its findings.

    Engines are registered in ``skillguard.cli.ENGINE_REGISTRY`` and driven only
    through these members — the dispatcher never branches on a specific engine.
    ``runtime_checkable`` so tests can assert ``isinstance(engine, Engine)``.
    """

    name: str
    inter_target_delay: float

    @property
    def available(self) -> bool: ...

    def scan(self, target: SkillInfo, /) -> list[Finding]: ...
