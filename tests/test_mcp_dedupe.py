"""Unit characterization tests for ``_dedupe_mcp_findings``.

A server's launch command is materialized into several surface files, so a
regex engine reports the same (engine, category, message) from each. For an MCP
config audit that is one issue: dedupe keeps the most specific location
(``command.txt``/``endpoint.txt`` rank 0 < ``mcp-config.json`` rank 1 < other
rank 2), preserving first-seen order. Distinct messages are all kept.
"""

from __future__ import annotations

from skillguard.cli import _dedupe_mcp_findings
from skillguard.model import Finding


def _f(message, file, category="shell_pipe", engine="local"):
    return Finding(engine=engine, severity="high", category=category, message=message, file=file)


def test_dedupe_keeps_most_specific_location():
    # Same (engine, category, message); the more specific command.txt must win
    # over mcp-config.json regardless of input order.
    findings = [
        _f("curl | sh detected", "mcp-config.json"),
        _f("curl | sh detected", "command.txt"),
    ]
    result = _dedupe_mcp_findings(findings)
    assert len(result) == 1
    assert result[0].file == "command.txt"


def test_dedupe_keeps_distinct_messages():
    findings = [
        _f("first issue", "command.txt"),
        _f("second issue", "command.txt"),
    ]
    result = _dedupe_mcp_findings(findings)
    assert len(result) == 2
    assert [r.message for r in result] == ["first issue", "second issue"]
