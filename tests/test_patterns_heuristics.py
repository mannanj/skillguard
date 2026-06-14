#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""The shared markdown-table suppression heuristic, hoisted from LocalEngine.

These pin the exact rule so the LocalEngine suppression and any future engine
adapter (e.g. a Cisco post-filter) that reuses ``is_markdown_table_row`` stay in
lockstep — the whole point of hoisting it into the shared ruleset module.
"""

from __future__ import annotations

from skillguard.patterns import is_markdown_table_row


def test_table_rows_and_separators_are_detected():
    assert is_markdown_table_row("| name | severity | note |")
    assert is_markdown_table_row("|------|----------|------|")
    assert is_markdown_table_row("reverse_shell | critical | /dev/tcp | blocked")


def test_prose_and_thin_pipes_are_not_tables():
    assert not is_markdown_table_row("just a sentence")
    assert not is_markdown_table_row("a | b")  # one pipe
    assert not is_markdown_table_row("cmd1 | cmd2 | x")  # two pipes, below threshold


def test_whitespace_does_not_change_the_verdict():
    raw = "  | a | b | c |  "
    assert is_markdown_table_row(raw) == is_markdown_table_row(raw.strip())
