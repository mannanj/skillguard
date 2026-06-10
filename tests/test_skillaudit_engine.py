"""SkillAudit engine response-parsing tests.

Regression coverage for the /scan/files API schema change: findings moved
from a top-level ``findings`` list to ``files[].topFindings``. The old
parser read only the top-level key, so every scan — including known-malicious
skills — came back "clean". These tests mock ``urllib.request.urlopen`` and
never touch the network.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pytest

from skillguard.cli import SkillAuditEngine, SkillInfo


class _FakeResponse:
    """Minimal stand-in for the http.client response used as a context manager."""

    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc) -> bool:
        return False


@pytest.fixture
def skill(tmp_path: Path) -> SkillInfo:
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("# helper\nFormats text nicely.\n")
    return SkillInfo(name="probe", path=tmp_path, scope="local", files=[skill_md])


def _scan_with(monkeypatch: pytest.MonkeyPatch, skill: SkillInfo, payload: dict):
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda req, timeout=30: _FakeResponse(payload)
    )
    return SkillAuditEngine().scan(skill)


# Mirrors the live /scan/files response shape (verified 2026-06-10).
NESTED_RESPONSE = {
    "project": "probe",
    "overallRisk": "critical",
    "totalFindings": 2,
    "totalCritical": 1,
    "files": [
        {
            "file": "SKILL.md",
            "riskLevel": "critical",
            "findings": 2,
            "topFindings": [
                {"severity": "critical", "name": "Reverse shell", "rule": "REVERSE_SHELL", "line": 2},
                {"severity": "high", "name": "Credential exfiltration", "rule": "CRED_ENV_READ", "line": 3},
            ],
        }
    ],
}


def test_nested_topfindings_are_parsed(monkeypatch, skill):
    findings = _scan_with(monkeypatch, skill, NESTED_RESPONSE)

    assert len(findings) == 2, "files[].topFindings must be surfaced"
    by_rule = {f.category: f for f in findings}
    assert by_rule["REVERSE_SHELL"].severity == "critical"
    assert by_rule["REVERSE_SHELL"].message == "Reverse shell"
    assert by_rule["REVERSE_SHELL"].file == "SKILL.md"
    assert by_rule["REVERSE_SHELL"].line == 2
    assert by_rule["CRED_ENV_READ"].severity == "high"


def test_malicious_response_is_not_reported_clean(monkeypatch, skill):
    """The original bug: a critical-risk response yielded zero findings."""
    findings = _scan_with(monkeypatch, skill, NESTED_RESPONSE)
    assert findings, "a critical SkillAudit response must never parse as clean"
    assert any(f.severity == "critical" for f in findings)


def test_truncated_topfindings_get_an_info_note(monkeypatch, skill):
    payload = json.loads(json.dumps(NESTED_RESPONSE))
    payload["totalFindings"] = 11  # API counted more than topFindings returned

    findings = _scan_with(monkeypatch, skill, payload)

    notes = [f for f in findings if f.category == "truncated"]
    assert len(notes) == 1
    assert notes[0].severity == "info"
    assert "11" in notes[0].message


def test_legacy_top_level_findings_still_parse(monkeypatch, skill):
    payload = {
        "findings": [
            {"severity": "high", "category": "data_exfil", "message": "posts env to remote", "file": "run.sh", "line": 7}
        ]
    }

    findings = _scan_with(monkeypatch, skill, payload)

    assert len(findings) == 1
    assert findings[0].category == "data_exfil"
    assert findings[0].severity == "high"


def test_skillaudit_risk_levels_map_to_severities(monkeypatch, skill):
    payload = {
        "totalFindings": 2,
        "files": [
            {
                "file": "SKILL.md",
                "topFindings": [
                    {"severity": "moderate", "name": "Network call", "rule": "NETWORK", "line": 1},
                    {"severity": "clean", "name": "Note", "rule": "NOTE", "line": 1},
                ],
            }
        ],
    }

    findings = _scan_with(monkeypatch, skill, payload)

    assert {f.severity for f in findings} == {"medium", "info"}


def test_clean_response_yields_no_findings(monkeypatch, skill):
    payload = {"totalFindings": 0, "files": [{"file": "SKILL.md", "topFindings": []}]}
    assert _scan_with(monkeypatch, skill, payload) == []
