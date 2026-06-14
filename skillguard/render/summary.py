#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""The scan-summary aggregate: engine/severity tallies computed once.

Before this, the table, JSON, and markdown renderers each rebuilt the same
``engine_counts`` table inline (three copies that could drift). ``summarize`` is
now the single authority; every renderer consumes a ``ScanSummary``.
"""

from __future__ import annotations

from dataclasses import dataclass

from skillguard.model import SEVERITY_ORDER, SkillInfo


@dataclass(frozen=True)
class ScanSummary:
    """Aggregated counts over a scanned target set, shared by every renderer."""

    engines_used: list[str]
    skill_targets: list[SkillInfo]
    mcp_targets: list[SkillInfo]
    engine_counts: dict[str, dict[str, int]]  # engine -> severity -> active count
    severity_totals: dict[str, int]  # severity -> active count across engines
    total_findings: int  # total active (non-triaged) findings
    triaged_total: int  # findings suppressed as triaged false positives
    clean_count: int  # targets with no active findings


def summarize(targets: list[SkillInfo], engines_used: list[str]) -> ScanSummary:
    """Tally active findings by engine and severity across ``targets``.

    A finding contributes to ``engine_counts`` only when its engine is in
    ``engines_used`` and its severity is a known level — the same guard every
    renderer applied inline. ``severity_totals[sev]`` sums that row across
    engines; since every finding's engine is one of ``engines_used``, this equals
    a plain per-severity count of active findings.
    """
    engine_counts: dict[str, dict[str, int]] = {
        e: {s: 0 for s in SEVERITY_ORDER} for e in engines_used
    }
    for t in targets:
        for f in t.active_findings:
            if f.engine in engine_counts and f.severity in engine_counts[f.engine]:
                engine_counts[f.engine][f.severity] += 1

    severity_totals = {
        sev: sum(engine_counts[e][sev] for e in engines_used) for sev in SEVERITY_ORDER
    }

    return ScanSummary(
        engines_used=engines_used,
        skill_targets=[t for t in targets if t.kind == "skill"],
        mcp_targets=[t for t in targets if t.kind == "mcp"],
        engine_counts=engine_counts,
        severity_totals=severity_totals,
        total_findings=sum(len(t.active_findings) for t in targets),
        triaged_total=sum(1 for t in targets for f in t.findings if f.triaged_fp),
        clean_count=sum(1 for t in targets if not t.active_findings),
    )
