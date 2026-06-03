"""Local engine detection tests.

Per CONTRIBUTING.md, every pattern category gets BOTH:
  - a malicious fixture that must be flagged with the right category + severity
  - a false-positive guard: the innocent look-alike must yield ZERO findings.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillguard.cli import LocalEngine, SkillInfo

# File extensions the scanner collects (mirrors discover_skills).
_SCAN_SUFFIXES = (".md", ".py", ".sh", ".js", ".ts", ".yaml", ".yml", ".json")


def _build_skill(skill_dir: Path) -> SkillInfo:
    """Construct a SkillInfo pointing at a fixture directory, the same way
    discover_skills collects files."""
    files = sorted(
        f for f in skill_dir.rglob("*") if f.is_file() and f.suffix in _SCAN_SUFFIXES
    )
    return SkillInfo(name=skill_dir.name, path=skill_dir, scope="local", files=files)


@pytest.fixture
def malicious_findings(malicious_skill_dir: Path):
    skill = _build_skill(malicious_skill_dir)
    return LocalEngine().scan(skill)


@pytest.fixture
def clean_findings(clean_skill_dir: Path):
    skill = _build_skill(clean_skill_dir)
    return LocalEngine().scan(skill)


# (category, expected_severity) for every category exercised by the fixture.
CATEGORY_SEVERITY = [
    ("reverse_shell", "critical"),
    ("data_exfil", "critical"),
    ("prompt_injection", "high"),
    ("env_exfil", "high"),
    ("credential_theft", "high"),
    ("shell_pipe", "high"),
    ("obfuscation", "high"),
]


@pytest.mark.parametrize("category,severity", CATEGORY_SEVERITY)
def test_malicious_category_flagged(malicious_findings, category, severity):
    """Each category must be detected with the documented severity."""
    matches = [f for f in malicious_findings if f.category == category]
    assert matches, f"expected at least one {category!r} finding, got none"
    for f in matches:
        assert f.severity == severity, (
            f"{category} reported severity {f.severity!r}, expected {severity!r}"
        )
        assert f.engine == "local"
        assert f.message  # non-empty human-readable description
        assert f.file  # which file it came from


def test_malicious_skill_is_not_clean(malicious_findings):
    assert len(malicious_findings) >= len(CATEGORY_SEVERITY)


def test_malicious_has_critical(malicious_findings):
    severities = {f.severity for f in malicious_findings}
    assert "critical" in severities


# ── False-positive guard ─────────────────────────────────────────────────────


@pytest.mark.parametrize("category,_severity", CATEGORY_SEVERITY)
def test_clean_skill_has_no_finding_for_category(clean_findings, category, _severity):
    offenders = [f for f in clean_findings if f.category == category]
    assert not offenders, (
        f"false positive: clean skill flagged for {category!r}: "
        f"{[(f.file, f.line, f.context) for f in offenders]}"
    )


def test_clean_skill_yields_zero_findings(clean_findings):
    """The strongest false-positive guard: a wholly innocent skill must be
    completely silent, even though its docs mention every threat by name."""
    assert clean_findings == [], (
        "clean skill produced findings: "
        f"{[(f.category, f.file, f.line, f.context) for f in clean_findings]}"
    )


def test_markdown_table_rows_suppressed(clean_skill_dir: Path):
    """Threat names inside |-delimited table rows must never fire."""
    findings = LocalEngine().scan(_build_skill(clean_skill_dir))
    table_line_hits = [f for f in findings if "|" in f.context]
    assert not table_line_hits
