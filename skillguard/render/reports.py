#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""The four scan-report renderers (table / json / markdown / quiet).

Each takes a ``list[SkillInfo]`` and prints to stdout. The table, JSON, and
markdown renderers derive their engine/severity tallies from a single
``summarize()`` call instead of rebuilding them inline. ``cli`` re-exports all
four so ``from skillguard.cli import report_table`` keeps working.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime

from skillguard.model import SEVERITY_ORDER, SkillInfo
from skillguard.render.colors import bold, dim, reset, severity_color
from skillguard.render.summary import summarize


def _fmt_ts(iso: str) -> str:
    """Render a stored ISO timestamp as ``YYYY-MM-DD HH:MM`` for the history
    tables, degrading to a truncated raw string if it can't be parsed."""
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return str(iso or "")[:16]


def emit(data: dict, fmt: str) -> bool:
    """The shared ``--format json`` prologue for the history/activity/show
    commands: when ``fmt`` is ``json`` print ``data`` and report it handled
    (``True``); otherwise return ``False`` so the caller renders its text view."""
    if fmt == "json":
        print(json.dumps(data, indent=2))
        return True
    return False


def report_table(
    skills: list[SkillInfo], engines_used: list[str], scan_time: str, verbose: bool = False
) -> None:
    """Print a formatted table report to stdout."""
    s = summarize(skills, engines_used)

    print(f"\n{bold()}SkillGuard Scan Results{reset()} — {scan_time}")
    print("=" * 60)
    print(f"Engines: {', '.join(engines_used)}")
    if s.mcp_targets:
        print(f"Targets: {len(s.skill_targets)} skill(s), {len(s.mcp_targets)} MCP(s)")
    else:
        gc = sum(1 for t in s.skill_targets if t.scope == "global")
        lc = sum(1 for t in s.skill_targets if t.scope == "local")
        print(f"Scope:   global ({gc} skills), local ({lc} skills)")
    print()

    # Summary table
    engine_headers = [e[:8].upper() for e in engines_used]
    header = f"{'SEVERITY':<10}" + "".join(f"{h:>10}" for h in engine_headers) + f"{'TOTAL':>10}"
    print(f"{bold()}SUMMARY{reset()}")
    print(f"  {header}")
    print(f"  {'─' * len(header)}")
    for sev in ["critical", "high", "medium", "low"]:
        row_total = s.severity_totals[sev]
        color = severity_color(sev) if row_total > 0 else dim()
        cells = "".join(f"{s.engine_counts[e][sev]:>10}" for e in engines_used)
        print(f"  {color}{sev:<10}{cells}{row_total:>10}{reset()}")
    if s.triaged_total:
        print(
            f"  {dim()}({s.triaged_total} finding(s) suppressed as triaged false positives){reset()}"
        )
    print()

    # Findings by skill (high+ only in table mode)
    high_skills = [t for t in skills if t.max_severity in ("critical", "high")]
    if high_skills:
        print(f"{bold()}FINDINGS (HIGH+){reset()}")
        for skill in high_skills:
            high_findings = [f for f in skill.active_findings if f.severity in ("critical", "high")]
            for f in sorted(high_findings, key=lambda x: x.sort_key()):
                color = severity_color(f.severity)
                label = f"{skill.kind}/{skill.scope}" if skill.kind == "mcp" else skill.scope
                print(
                    f"  {color}{f.severity.upper():<9}{reset()} {skill.name} ({label}) — [{f.engine}] {f.message}"
                )
                if f.file:
                    print(f"           {dim()}{f.file}:{f.line}{reset()}")
                if f.context:
                    print(f"           {dim()}{f.context}{reset()}")
        print()

    # Medium findings (compact)
    med_findings_total = s.severity_totals["medium"]
    if med_findings_total > 0:
        print(f"{bold()}MEDIUM FINDINGS{reset()} ({med_findings_total} total)")
        for skill in skills:
            med_f = [f for f in skill.active_findings if f.severity == "medium"]
            if med_f:
                for f in sorted(med_f, key=lambda x: x.sort_key()):
                    print(
                        f"  {severity_color('medium')}MEDIUM{reset()}   {skill.name} — [{f.engine}] {f.message}"
                    )
                    if f.file:
                        print(f"           {dim()}{f.file}:{f.line}{reset()}")
                    if f.context:
                        print(f"           {dim()}{f.context}{reset()}")
        print()

    # Low/info advisories — supply-chain inventory and notes. Counted always,
    # listed only under -v so they don't drown the threat signal. For MCPs these
    # are the "what does this server run / what can it read" inventory.
    if verbose:
        advisories = [
            (t, f) for t in skills for f in t.active_findings if f.severity in ("low", "info")
        ]
        if advisories:
            print(f"{bold()}ADVISORIES (low/info){reset()}")
            for t, f in sorted(advisories, key=lambda sf: sf[1].sort_key()):
                label = f"{t.kind}/{t.scope}" if t.kind == "mcp" else t.scope
                print(
                    f"  {severity_color(f.severity)}{f.severity.upper():<8}{reset()} "
                    f"{t.name} ({label}) — [{f.engine}] {f.message}"
                )
            print()

    # Summary line
    noun = "target" if s.mcp_targets else "skill"
    if s.total_findings == 0:
        print(
            f"{severity_color('clean')}✓ All {len(skills)} {noun}s clean across all engines{reset()}"
        )
    else:
        print(f"✓ {s.clean_count}/{len(skills)} {noun}s clean")
        if any(t.max_severity in ("critical", "high") for t in skills):
            bad = sum(1 for t in skills if t.max_severity in ("critical", "high"))
            print(
                f"{severity_color('high')}⚠ {bad} {noun}(s) have HIGH+ findings — review recommended{reset()}"
            )
            print(
                f"{dim()}Next: skillguard --show <name> | "
                f"skillguard --mark-fp <name> after review{reset()}"
            )
    print()


def report_json(skills: list[SkillInfo], engines_used: list[str], scan_time: str) -> None:
    """Print JSON report to stdout.

    Skills and MCPs are reported in separate arrays (``skills`` is kept for
    back-compat and holds skill targets only; ``mcps`` is new), plus a combined
    ``targets`` array. ``by_scope`` covers skill scopes only.
    """
    s = summarize(skills, engines_used)

    def target_dict(t: SkillInfo) -> dict:
        return {
            "name": t.name,
            "kind": t.kind,
            "scope": t.scope,
            "path": str(t.path),
            "max_severity": t.max_severity,
            "triaged_fp_count": sum(1 for f in t.findings if f.triaged_fp),
            "findings": [asdict(f) for f in sorted(t.findings, key=lambda x: x.sort_key())],
        }

    by_scope: dict[str, dict] = {}
    for t in s.skill_targets:
        bucket = by_scope.setdefault(
            t.scope,
            {
                "total": 0,
                "findings_by_engine": {e: {sv: 0 for sv in SEVERITY_ORDER} for e in engines_used},
            },
        )
        bucket["total"] += 1
        for f in t.active_findings:
            fbe = bucket["findings_by_engine"]
            if f.engine in fbe and f.severity in fbe[f.engine]:
                fbe[f.engine][f.severity] += 1

    output = {
        "scan_time": scan_time,
        "summary": {
            "total_targets": len(skills),
            "total_skills": len(s.skill_targets),
            "total_mcps": len(s.mcp_targets),
            "skills_scanned": len(s.skill_targets),
            "engines_used": engines_used,
            "critical": s.severity_totals["critical"],
            "high": s.severity_totals["high"],
            "medium": s.severity_totals["medium"],
            "low": s.severity_totals["low"],
            "triaged_fp": s.triaged_total,
        },
        "by_scope": by_scope,
        "skills": [target_dict(t) for t in s.skill_targets],
        "mcps": [target_dict(t) for t in s.mcp_targets],
        "targets": [target_dict(t) for t in skills],
    }

    print(json.dumps(output, indent=2))


def report_markdown(
    skills: list[SkillInfo], engines_used: list[str], scan_time: str, verbose: bool = False
) -> None:
    """Print markdown report to stdout."""
    s = summarize(skills, engines_used)

    print("# SkillGuard Scan Report")
    print(f"\n**Date:** {scan_time}")
    print(f"**Engines:** {', '.join(engines_used)}")
    print(f"**Targets:** {len(s.skill_targets)} skill(s), {len(s.mcp_targets)} MCP(s)")
    print(f"**Findings:** {s.total_findings}")
    if s.triaged_total:
        print(f"**Triaged false positives:** {s.triaged_total}")
    print()

    # Summary table
    print("## Summary by Engine")
    print()
    header = "| Severity |" + "|".join(f" {e} " for e in engines_used) + "| Total |"
    sep = "|----------|" + "|".join("------" for _ in engines_used) + "|-------|"
    print(header)
    print(sep)

    for sev in ["critical", "high", "medium", "low"]:
        cells = [f" {s.engine_counts[e][sev]} " for e in engines_used]
        total = s.severity_totals[sev]
        print(f"| {sev} |" + "|".join(cells) + f"| {total} |")
    print()

    # Detailed findings
    flagged = [t for t in skills if t.active_findings]
    if flagged:
        print("## Findings by Target")
        print()
        for skill in flagged:
            sev = skill.max_severity.upper()
            label = f"{skill.kind}/{skill.scope}" if skill.kind == "mcp" else skill.scope
            print(f"### {skill.name} ({label}) — {sev}")
            print()
            for f in sorted(skill.active_findings, key=lambda x: x.sort_key()):
                loc = f" `{f.file}:{f.line}`" if f.file else ""
                print(f"- **[{f.engine}/{f.severity}]** {f.message}{loc}")
            print()
    else:
        print("## All targets clean")
        print()


def report_quiet(skills: list[SkillInfo]) -> None:
    """Minimal output for hook mode."""
    total = len(skills)
    flagged = sum(1 for s in skills if s.max_severity in ("critical", "high"))
    if flagged:
        print(f"⚠ SkillGuard: {flagged}/{total} target(s) have HIGH+ findings")
        for s in skills:
            if s.max_severity in ("critical", "high"):
                top = sorted(s.active_findings, key=lambda f: f.sort_key())[0]
                print(f"  - {s.name} ({s.kind}): {top.message}")
    else:
        print(f"SkillGuard: {total} target(s) scanned, all clean")
