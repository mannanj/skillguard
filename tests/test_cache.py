"""Cache-writing tests for write_cache / write_skip_cache / _atomic_write_json.

All tests redirect skillguard.cli.CACHE_DIR into tmp_path so the real
~/.claude/skillguard-cache is never touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import skillguard.cli as cli
from skillguard.cli import (
    Finding,
    SkillInfo,
    write_cache,
    write_skip_cache,
    _atomic_write_json,
)


@pytest.fixture
def cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "skillguard-cache"
    monkeypatch.setattr(cli, "CACHE_DIR", d)
    return d


def _skill_with_findings(tmp_path: Path, *severities: str) -> SkillInfo:
    skill_dir = tmp_path / "victim"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: victim\n---\n# hi\n")
    findings = [
        Finding(engine="local", severity=sev, category="cat", message=f"msg {sev}")
        for sev in severities
    ]
    return SkillInfo(name="victim", path=skill_dir, scope="global", findings=findings)


# ── write_cache ───────────────────────────────────────────────────────────────


def test_write_cache_produces_valid_json_with_expected_keys(cache_dir, tmp_path):
    skill = _skill_with_findings(tmp_path, "high")
    write_cache(skill, ["local"])

    cache_file = cache_dir / "victim.json"
    assert cache_file.exists()
    data = json.loads(cache_file.read_text())  # raises if not valid JSON

    expected_keys = {
        "skill_name",
        "scanned_at",
        "skill_mtime_epoch",
        "engines_used",
        "skipped",
        "max_severity",
        "finding_count",
        "findings_summary",
    }
    assert expected_keys <= set(data)
    assert data["skill_name"] == "victim"
    assert data["engines_used"] == ["local"]
    assert data["skipped"] is False
    assert data["finding_count"] == 1


def test_write_cache_reflects_max_severity(cache_dir, tmp_path):
    # Mixed severities — the most severe (critical) must win.
    skill = _skill_with_findings(tmp_path, "low", "critical", "medium", "high")
    write_cache(skill, ["local"])

    data = json.loads((cache_dir / "victim.json").read_text())
    assert data["max_severity"] == "critical"
    assert data["finding_count"] == 4


def test_write_cache_clean_when_no_findings(cache_dir, tmp_path):
    skill = _skill_with_findings(tmp_path)  # no findings
    write_cache(skill, ["local"])

    data = json.loads((cache_dir / "victim.json").read_text())
    assert data["max_severity"] == "clean"
    assert data["finding_count"] == 0
    assert data["findings_summary"] == []


def test_write_cache_records_skill_mtime(cache_dir, tmp_path):
    skill = _skill_with_findings(tmp_path, "high")
    write_cache(skill, ["local"])
    data = json.loads((cache_dir / "victim.json").read_text())
    # SKILL.md exists, so mtime must be a positive epoch.
    assert data["skill_mtime_epoch"] > 0


# ── write_skip_cache ──────────────────────────────────────────────────────────


def test_write_skip_cache(cache_dir):
    write_skip_cache("someskill")
    cache_file = cache_dir / "someskill.json"
    assert cache_file.exists()
    data = json.loads(cache_file.read_text())

    assert data["skill_name"] == "someskill"
    assert data["skipped"] is True
    assert data["max_severity"] == "skipped"
    assert data["finding_count"] == 0
    assert data["engines_used"] == []


# ── _atomic_write_json ────────────────────────────────────────────────────────


def test_atomic_write_leaves_no_tmp_files(cache_dir, tmp_path):
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / "atomic.json"
    _atomic_write_json(target, {"a": 1, "b": [2, 3]})

    assert target.exists()
    assert json.loads(target.read_text()) == {"a": 1, "b": [2, 3]}

    # No leftover *.tmp.* sidecar files anywhere in the cache dir.
    leftovers = [p for p in cache_dir.iterdir() if ".tmp." in p.name]
    assert leftovers == [], f"atomic write left temp files: {leftovers}"


def test_atomic_write_overwrites_existing(cache_dir):
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / "over.json"
    _atomic_write_json(target, {"v": 1})
    _atomic_write_json(target, {"v": 2})
    assert json.loads(target.read_text()) == {"v": 2}
    assert [p for p in cache_dir.iterdir() if ".tmp." in p.name] == []


def test_write_cache_creates_cache_dir_if_missing(cache_dir, tmp_path):
    assert not cache_dir.exists()
    skill = _skill_with_findings(tmp_path, "medium")
    write_cache(skill, ["local"])
    assert cache_dir.is_dir()
