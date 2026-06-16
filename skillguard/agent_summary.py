from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from skillguard.paths import cache_dir

HIGH_PLUS = {"critical", "high"}
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4, "clean": 5}


def verdict_files() -> list[Path]:
    base = cache_dir()
    if not base.exists():
        return []
    files = [p for p in base.glob("*.json") if not p.name.startswith("_")]
    mcp_dir = base / "mcps"
    if mcp_dir.exists():
        files.extend(p for p in mcp_dir.glob("*.json") if not p.name.startswith("_"))
    return sorted(files)


def load_cached_verdicts() -> list[dict]:
    verdicts: list[dict] = []
    for path in verdict_files():
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            data.setdefault("_cache_path", str(path))
            verdicts.append(data)
    return verdicts


def active_verdicts(verdicts: Iterable[dict]) -> list[dict]:
    return [
        v
        for v in verdicts
        if not v.get("skipped") and int(v.get("finding_count") or 0) > 0
    ]


def high_plus_verdicts(verdicts: Iterable[dict]) -> list[dict]:
    return sorted(
        [v for v in active_verdicts(verdicts) if v.get("max_severity") in HIGH_PLUS],
        key=lambda v: (
            SEVERITY_RANK.get(str(v.get("max_severity")), 99),
            str(v.get("target_name") or v.get("skill_name") or ""),
        ),
    )


def target_name(verdict: dict) -> str:
    return str(verdict.get("target_name") or verdict.get("skill_name") or "<unknown>")


def finding_count(verdict: dict) -> int:
    return int(verdict.get("finding_count") or 0)


def kind_label(kind: str, count: int) -> str:
    if kind == "mcp":
        return f"{count} MCP" if count == 1 else f"{count} MCPs"
    return f"{count} skill" if count == 1 else f"{count} skills"


def scope_label(verdicts: list[dict]) -> str:
    counts = Counter(str(v.get("kind") or "skill") for v in verdicts)
    parts: list[str] = []
    if counts.get("skill"):
        parts.append(kind_label("skill", counts["skill"]))
    if counts.get("mcp"):
        parts.append(kind_label("mcp", counts["mcp"]))
    return " + ".join(parts) if parts else "0 targets"


def latest_scan_label(verdicts: list[dict]) -> str:
    parsed: list[datetime] = []
    for verdict in verdicts:
        raw = str(verdict.get("scanned_at") or "")
        try:
            parsed.append(datetime.fromisoformat(raw.replace("Z", "+00:00")))
        except ValueError:
            continue
    if not parsed:
        return "latest unknown"
    latest = max(parsed).astimezone(timezone.utc)
    return f"latest {latest:%Y-%m-%d %H:%M UTC}"


def render_agent_summary(verdicts: list[dict]) -> str:
    if not verdicts:
        return "SkillGuard: no cached scan - run: skillguard --target all --engines local"

    active = active_verdicts(verdicts)
    high = high_plus_verdicts(verdicts)
    if not active:
        return (
            f"SkillGuard: 0/{len(verdicts)} high+ - {scope_label(verdicts)} - "
            f"clean - {latest_scan_label(verdicts)}"
        )

    total_findings = sum(finding_count(v) for v in active)
    first = (
        f"SkillGuard: {len(high)}/{len(verdicts)} high+ - "
        f"{scope_label(verdicts)} - {total_findings} finding"
        f"{'s' if total_findings != 1 else ''} - "
        f"{latest_scan_label(verdicts)} - skillguard --review"
    )
    if not high:
        return first
    names = [
        f"{target_name(v)} {'MCP' if v.get('kind') == 'mcp' else 'skill'} "
        f"{v.get('max_severity')}({finding_count(v)})"
        for v in high[:3]
    ]
    suffix = f" +{len(high) - len(names)} more" if len(high) > len(names) else ""
    return f"{first}\n  {'; '.join(names)}{suffix}"
