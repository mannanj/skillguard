#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""The verdict cache: the on-disk JSON the hook reads before allowing a target.

``build_verdict`` is the single authority for the verdict schema; ``write_cache``,
``write_skip_cache``, and triage's re-triage (``triage._rewrite_cache_verdict``)
all derive from it via ``verdict_fields``. The on-disk field set AND order are a
hook contract — ``hook.py`` reads ``scanned_at`` / ``skipped`` / ``max_severity``
/ ``finding_count`` / ``triaged_fp_count`` / ``match_tokens`` / ``target_name`` —
so keep it byte-compatible.
"""

from __future__ import annotations

from dataclasses import asdict

from skillguard._util import atomic_write_json as _atomic_write_json
from skillguard._util import utcnow_iso
from skillguard.model import Finding, SkillInfo, max_severity_of
from skillguard.paths import cache_path_for


def summarize_findings(findings: list[Finding], limit: int = 10) -> list[str]:
    """The compact ``findings_summary`` lines: the worst ``limit`` findings as
    ``[engine/severity] message in file:line``."""
    return [
        f"[{f.engine}/{f.severity}] {f.message} in {f.file}:{f.line}"
        for f in sorted(findings, key=lambda x: x.sort_key())[:limit]
    ]


def verdict_fields(findings: list[Finding], *, skipped: bool = False) -> dict:
    """The findings-derived verdict fields, shared by ``build_verdict`` and
    re-triage. ``max_severity_of`` already ignores triaged findings, so passing
    all findings yields the same severity as filtering to the active ones first.
    """
    active = [] if skipped else [f for f in findings if not f.triaged_fp]
    return {
        "max_severity": "skipped" if skipped else max_severity_of(findings),
        "finding_count": len(active),
        "triaged_fp_count": 0 if skipped else len(findings) - len(active),
        "findings_summary": summarize_findings(active),
        "findings": []
        if skipped
        else [asdict(f) for f in sorted(findings, key=lambda x: x.sort_key())],
    }


def build_verdict(
    name: str,
    kind: str,
    *,
    scope: str | None,
    scanned_at: str,
    mtime_epoch: float,
    engines_used: list[str],
    skipped: bool,
    findings: list[Finding],
    match_tokens: list[str] | None = None,
) -> dict:
    """Assemble the canonical verdict dict in its on-disk field order.

    ``scope`` and ``match_tokens`` are omitted when ``None`` so the skip-cache
    shape (no scope) and skill-vs-MCP shape (match_tokens only for MCPs) stay
    byte-compatible with what the hook already reads.
    """
    verdict: dict = {"skill_name": name, "target_name": name, "kind": kind}
    if scope is not None:
        verdict["scope"] = scope
    verdict["scanned_at"] = scanned_at
    verdict["skill_mtime_epoch"] = mtime_epoch
    verdict["engines_used"] = engines_used
    verdict["skipped"] = skipped
    verdict.update(verdict_fields(findings, skipped=skipped))
    if match_tokens is not None:
        verdict["match_tokens"] = match_tokens
    return verdict


def write_cache(skill: SkillInfo, engines_used: list[str], skipped: bool = False) -> dict:
    """Write scan results to cache for hook lookups. Returns the cache dict so
    callers can mirror it into the history DB without rebuilding it."""
    path = cache_path_for(skill.name, skill.kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    # MCP verdicts carry the tokens the hook uses to map mcp__<server>__tool
    # calls back to this verdict; skills have no such tokens.
    mcp = skill.extra.get("mcp") if skill.extra else None
    verdict = build_verdict(
        skill.name,
        skill.kind,
        scope=skill.scope,
        scanned_at=utcnow_iso(),
        mtime_epoch=skill.mtime_epoch,
        engines_used=engines_used,
        skipped=skipped,
        findings=skill.findings,
        match_tokens=mcp.match_tokens if mcp is not None else None,
    )
    _atomic_write_json(path, verdict)
    return verdict


def write_skip_cache(skill_name: str, kind: str = "skill") -> None:
    """Write a 'skipped' cache entry so the hook stops blocking but shows reminders."""
    path = cache_path_for(skill_name, kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    verdict = build_verdict(
        skill_name,
        kind,
        scope=None,
        scanned_at=utcnow_iso(),
        mtime_epoch=0,
        engines_used=[],
        skipped=True,
        findings=[],
    )
    _atomic_write_json(path, verdict)
