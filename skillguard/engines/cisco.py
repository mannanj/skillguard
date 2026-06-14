#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""The Cisco AI Defense skill-scanner engine (optional ``cisco-ai-skill-scanner``)."""

from __future__ import annotations

from skillguard.model import Finding, SkillInfo, normalize_severity


class CiscoEngine:
    """Cisco AI Defense skill scanner via Python SDK."""

    name = "cisco"
    available = False
    inter_target_delay = 0.0
    unavailable_hint = (
        "Cisco engine: cisco-ai-skill-scanner not installed (uv pip install cisco-ai-skill-scanner)"
    )

    def __init__(self) -> None:
        try:
            from skill_scanner import SkillScanner

            self.available = True
            self._scanner_cls = SkillScanner
        except ImportError:
            pass

    def scan(self, skill: SkillInfo) -> list[Finding]:
        if not self.available:
            return []

        findings: list[Finding] = []
        try:
            scanner = self._scanner_cls()
            result = scanner.scan_skill(str(skill.path))

            for f in getattr(result, "findings", []):
                severity = normalize_severity(getattr(f, "severity", "medium"))
                findings.append(
                    Finding(
                        engine="cisco",
                        severity=severity,
                        category=getattr(f, "category", getattr(f, "rule_id", "unknown")),
                        message=getattr(f, "message", getattr(f, "description", str(f))),
                        file=getattr(f, "file", ""),
                        line=getattr(f, "line", 0),
                        context=getattr(f, "context", "")[:120],
                    )
                )
        except Exception as e:
            findings.append(
                Finding(
                    engine="cisco",
                    severity="info",
                    category="engine_error",
                    message=f"Cisco scanner error: {e}",
                )
            )
        return findings
