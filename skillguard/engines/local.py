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
from skillguard.sanitize import fold_for_detection

# Categories whose patterns must ALSO see YAML frontmatter. For most categories a
# name/description that merely *names* a threat is metadata, not a directive, so
# the frontmatter is skipped; but for these two the frontmatter IS the attack
# surface: selection_manipulation framing and an invisible/bidi/ANSI char hidden
# in the description are the attack itself, not a mention of one.
_FRONTMATTER_SCANNED_CATEGORIES = frozenset({"selection_manipulation", "obfuscation"})


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
                # YAML frontmatter (name/description/--- delimiters) is metadata,
                # not instructions, so most categories skip it to avoid flagging a
                # description that merely *names* a threat. The exceptions live in
                # _FRONTMATTER_SCANNED_CATEGORIES (selection_manipulation +
                # obfuscation), whose framing/hidden chars ARE the attack surface.
                in_frontmatter = line_num <= 10 and (
                    line.startswith("---")
                    or line.startswith("name:")
                    or line.startswith("description:")
                )

                # Defeat Unicode obfuscation: fold invisibles/bidi away (and NFKC-
                # normalize) so a regex sees the canonical form (e.g. a zero-width
                # split of "curl" folds back to "curl"). fold_for_detection()
                # returns the line unchanged when it has no invisible/bidi char, so
                # benign emoji/accents/CJK/full-width text is never re-normalized.
                folded = fold_for_detection(line)

                for category, severity, pattern, description in LOCAL_PATTERNS:
                    if in_frontmatter and category not in _FRONTMATTER_SCANNED_CATEGORIES:
                        continue
                    if pattern.search(line) or (folded != line and pattern.search(folded)):
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
                        if category == "prompt_injection" and is_prompt_injection_education_line(
                            line
                        ):
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
