#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""The local pattern-matching engine: zero-dependency regex scanning."""

from __future__ import annotations

from skillguard.discovery import rel_to
from skillguard.model import Finding, SkillInfo
from skillguard.patterns import (
    LOCAL_PATTERNS,
    is_cloudflared_service_management,
    is_explicit_non_finding_line,
    is_markdown_table_row,
    is_package_cache_cleanup,
    is_placeholder_webhook_site,
    is_prompt_injection_education_line,
    is_vendor_install_pipe,
)


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
                        if is_markdown_table_row(stripped):
                            continue
                        if is_explicit_non_finding_line(stripped):
                            continue
                        if category == "data_exfil" and is_placeholder_webhook_site(line):
                            continue
                        if category == "prompt_injection" and is_prompt_injection_education_line(line):
                            continue
                        if category == "shell_pipe" and is_vendor_install_pipe(line):
                            continue
                        if category == "persistence" and is_cloudflared_service_management(line):
                            continue
                        if category == "dangerous_op" and is_package_cache_cleanup(line):
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
                                context=_context_excerpt(line),
                            )
                        )
        return findings


def _context_excerpt(line: str, limit: int = 120) -> str:
    """Trim matched source lines without hiding that trimming happened."""
    stripped = line.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[: max(0, limit - 3)].rstrip() + "..."
