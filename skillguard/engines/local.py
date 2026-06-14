#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""The local pattern-matching engine: zero-dependency regex scanning."""

from __future__ import annotations

from skillguard.discovery import rel_to
from skillguard.model import Finding, SkillInfo
from skillguard.patterns import LOCAL_PATTERNS


class LocalEngine:
    """Pattern-based local scanner. Zero dependencies."""

    name = "local"
    available = True
    inter_target_delay = 0.0

    def scan(self, skill: SkillInfo) -> list[Finding]:
        findings: list[Finding] = []
        for file_path in skill.files:
            try:
                content = file_path.read_text(errors="replace")
            except OSError:
                continue

            lines = content.split("\n")
            for line_num, line in enumerate(lines, 1):
                # Skip YAML frontmatter lines (metadata, not instructions)
                if line_num <= 10 and (
                    line.startswith("---")
                    or line.startswith("name:")
                    or line.startswith("description:")
                ):
                    continue

                for category, severity, pattern, description in LOCAL_PATTERNS:
                    if pattern.search(line):
                        # Context suppression: skip if line is in a code comment explaining the pattern
                        stripped = line.strip()
                        if stripped.startswith("#") and "detect" in stripped.lower():
                            continue
                        if stripped.startswith("//") and "detect" in stripped.lower():
                            continue
                        # Skip if the line is inside a markdown table header or description
                        if "|" in stripped and stripped.count("|") >= 3:
                            continue

                        rel_path = rel_to(file_path, skill.path)
                        findings.append(
                            Finding(
                                engine="local",
                                severity=severity,
                                category=category,
                                message=description,
                                file=rel_path,
                                line=line_num,
                                context=line.strip()[:120],
                            )
                        )
        return findings
