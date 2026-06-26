"""Selection-manipulation detection tests.

This category flags description/manifest framing engineered to win the agent's
*skill selection* (trust claims, directives to ignore competing skills) — the
attack class from Nesbitt's "Skills Registry Threat Models" and the SKILL.md
study's measured ~77.6% adversarial-selection rate.

Per CONTRIBUTING.md, the category gets BOTH:
  - a malicious fixture flagged with the right category + severity, and
  - a false-positive guard: an innocent look-alike (legitimate "official" /
    "verified" provenance) that yields ZERO selection_manipulation findings.

Unlike every other local category, selection_manipulation must also see the YAML
frontmatter, because the name + description ARE the selection surface. The
`test_*frontmatter*` cases pin that behavior so the engines/local.py exemption
cannot silently regress.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillguard.cli import LocalEngine, SkillInfo

_SCAN_SUFFIXES = (".md", ".py", ".sh", ".js", ".ts", ".yaml", ".yml", ".json")
_CATEGORY = "selection_manipulation"


def _build_skill(skill_dir: Path) -> SkillInfo:
    files = sorted(f for f in skill_dir.rglob("*") if f.is_file() and f.suffix in _SCAN_SUFFIXES)
    return SkillInfo(name=skill_dir.name, path=skill_dir, scope="local", files=files)


@pytest.fixture
def manip_findings(manipulative_skill_dir: Path):
    return [f for f in LocalEngine().scan(_build_skill(manipulative_skill_dir))]


@pytest.fixture
def honest_findings(honest_skill_dir: Path):
    return LocalEngine().scan(_build_skill(honest_skill_dir))


# Each distinct rule message and the exact severity it must report. Pinning the
# severity (not just presence) means a mutation that flips high<->medium is RED.
EXPECTED = [
    ("tells the agent to ignore other skills", "high"),
    ("tells the agent not to use other skills", "high"),
    ("tells the agent to prefer this skill over others", "high"),
    ("claims to be the only skill the agent should use", "high"),
    ("unverifiable official-verification claim", "medium"),
    ("claims vendor approval or endorsement", "medium"),
    ("absolute safety guarantee", "medium"),
    ("absolute trust claim", "medium"),
]


@pytest.mark.parametrize("needle,severity", EXPECTED)
def test_each_rule_fires_with_its_severity(manip_findings, needle, severity):
    """Every selection_manipulation rule fires on the malicious fixture, and at
    the documented severity tier."""
    matches = [f for f in manip_findings if f.category == _CATEGORY and needle in f.message]
    assert matches, f"expected a selection_manipulation finding matching {needle!r}, got none"
    for f in matches:
        assert f.severity == severity, f"{needle!r} reported {f.severity!r}, expected {severity!r}"
        assert f.engine == "local"
        assert f.file


def test_both_severity_tiers_present(manip_findings):
    """The category is genuinely tiered: anti-competitive directives are high,
    trust framing is medium."""
    sevs = {f.severity for f in manip_findings if f.category == _CATEGORY}
    assert "high" in sevs
    assert "medium" in sevs


def test_description_frontmatter_is_scanned(manip_findings):
    """Load-bearing: the manipulative DESCRIPTION (frontmatter line 3) must be
    flagged. Reverting the engines/local.py frontmatter exemption makes this RED,
    proving the exemption is what catches description-framing attacks.

    The fixture frontmatter is:
        1: ---
        2: name: db-helper-pro
        3: description: Officially verified, Anthropic-approved ... only skill ...
    """
    line3 = [
        f
        for f in manip_findings
        if f.category == _CATEGORY and f.file == "SKILL.md" and f.line == 3
    ]
    assert line3, (
        "no selection_manipulation finding on the description line (frontmatter "
        "exemption regressed?)"
    )
    # That single description line carries both a trust claim and a directive.
    assert {"medium", "high"} <= {f.severity for f in line3}


# ── False-positive guard ─────────────────────────────────────────────────────


def test_honest_skill_has_no_selection_manipulation(honest_findings):
    """Legitimate provenance ('the official Stripe integration', 'verified
    against the API', 'trusted by the team') must NOT be flagged."""
    offenders = [f for f in honest_findings if f.category == _CATEGORY]
    assert not offenders, (
        "false positive: honest skill flagged for selection_manipulation: "
        f"{[(f.file, f.line, f.message, f.context) for f in offenders]}"
    )


def test_honest_skill_is_completely_silent(honest_findings):
    """The strongest guard: an honest skill that even documents the manipulative
    phrases (inside a markdown table) produces zero findings of any category."""
    assert honest_findings == [], (
        "honest skill produced findings: "
        f"{[(f.category, f.file, f.line, f.context) for f in honest_findings]}"
    )


def test_documentation_table_rows_are_suppressed(honest_skill_dir: Path):
    """selection_manipulation honors the shared markdown-table suppression: the
    threat-reference table naming the manipulative phrases must never fire."""
    findings = LocalEngine().scan(_build_skill(honest_skill_dir))
    table_hits = [f for f in findings if "|" in f.context]
    assert not table_hits
