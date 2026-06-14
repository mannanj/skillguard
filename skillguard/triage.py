#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""Triage: persistent false-positive suppression.

A finding is fingerprinted by ``(target, engine, category, file, message)`` —
deliberately excluding the line number so doc edits don't unmark it. Marks live
in ``<cache>/_triage.json`` and are re-applied on every scan via ``apply_triage``;
``mark_fp_command`` / ``unmark_fp_command`` add/remove them and rewrite the
affected verdict cache (through the shared ``cache.verdict_fields`` authority).
``cli`` re-exports these for ``from skillguard.cli import ...`` back-compat.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from skillguard._util import atomic_write_json as _atomic_write_json
from skillguard._util import utcnow_iso
from skillguard.cache import verdict_fields
from skillguard.model import Finding, SkillInfo
from skillguard.paths import cache_dir, resolve_existing_cache, triage_path


def finding_fingerprint(skill_name: str, finding: Finding) -> str:
    # Line numbers are deliberately excluded: doc edits shift lines, and the
    # same pattern in the same file deserves the same verdict either way.
    return "|".join([skill_name, finding.engine, finding.category, finding.file, finding.message])


def load_triage() -> dict:
    try:
        data = json.loads(triage_path().read_text())
        if isinstance(data, dict) and isinstance(data.get("false_positives"), dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"version": 1, "false_positives": {}}


def save_triage(data: dict) -> None:
    cache_dir().mkdir(parents=True, exist_ok=True)
    _atomic_write_json(triage_path(), data)


def apply_triage(skill: SkillInfo, triage: dict | None = None) -> None:
    """Flag findings previously marked false-positive so they stop counting."""
    fps = (triage if triage is not None else load_triage())["false_positives"]
    for f in skill.findings:
        if finding_fingerprint(skill.name, f) in fps:
            f.triaged_fp = True


def _rewrite_cache_verdict(cache_file: Path, cache: dict, findings: list[Finding]) -> None:
    """Recompute verdict fields from triaged findings, preserving scan metadata.

    Updates only the findings-derived fields (via the shared ``verdict_fields``
    authority) in place, leaving the cache's metadata + key order untouched so
    the on-disk JSON stays byte-compatible with the hook contract."""
    cache.update(verdict_fields(findings))
    _atomic_write_json(cache_file, cache)


def mark_fp_command(skill_name: str) -> None:
    """Mark all of a skill/MCP's current non-info findings as triaged false positives."""
    cache_file = resolve_existing_cache(skill_name)
    if cache_file is None:
        print(
            f"No scan on record for '{skill_name}'. Scan first: skillguard --skill {skill_name}"
            f"  (or --mcp {skill_name})",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        cache = json.loads(cache_file.read_text())
    except (OSError, json.JSONDecodeError):
        # A torn/unreadable cache must exit cleanly, not traceback — mirror the
        # hook's fail-closed guard (hook.py) and unmark_fp_command's read guard.
        print(
            f"Cache for '{skill_name}' is corrupted or unreadable. Re-scan first: skillguard --skill {skill_name}",
            file=sys.stderr,
        )
        sys.exit(1)
    raw = cache.get("findings")
    if raw is None:
        print(
            f"Cache for '{skill_name}' predates triage support. Re-scan first: skillguard --skill {skill_name}",
            file=sys.stderr,
        )
        sys.exit(1)

    findings = [Finding(**f) for f in raw]
    triage = load_triage()
    marked_at = utcnow_iso()
    marked = 0
    for f in findings:
        # info entries are advisories (engine errors, policy notes), not
        # security findings — suppressing them would hide real signal.
        if f.severity == "info" or f.triaged_fp:
            continue
        triage["false_positives"][finding_fingerprint(skill_name, f)] = {
            "skill": skill_name,
            "engine": f.engine,
            "severity": f.severity,
            "category": f.category,
            "file": f.file,
            "message": f.message,
            "marked_at": marked_at,
        }
        f.triaged_fp = True
        marked += 1

    if not marked:
        print(f"'{skill_name}' has no unmarked non-info findings.")
        return
    save_triage(triage)
    _rewrite_cache_verdict(cache_file, cache, findings)
    remaining = sum(1 for f in findings if not f.triaged_fp)
    print(
        f"Marked {marked} finding(s) in '{skill_name}' as false positives ({remaining} remain active)."
    )
    print(f"Marks persist across re-scans. Undo with: skillguard --unmark-fp {skill_name}")


def unmark_fp_command(skill_name: str) -> None:
    """Remove all false-positive marks for a skill and restore its cached verdict."""
    triage = load_triage()
    fps = triage["false_positives"]
    keys = [k for k, v in fps.items() if v.get("skill") == skill_name]
    if not keys:
        print(f"No false-positive marks recorded for '{skill_name}'.")
        return
    for k in keys:
        del fps[k]
    save_triage(triage)

    cache_file = resolve_existing_cache(skill_name)
    if cache_file is not None:
        try:
            cache = json.loads(cache_file.read_text())
            raw = cache.get("findings")
            if raw is not None:
                findings = [Finding(**{**f, "triaged_fp": False}) for f in raw]
                _rewrite_cache_verdict(cache_file, cache, findings)
        except (OSError, json.JSONDecodeError):
            pass
    print(f"Removed {len(keys)} false-positive mark(s) for '{skill_name}'.")
