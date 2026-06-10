"""Triage (false-positive suppression) tests.

Covers: fingerprint identity, apply_triage flagging, cache verdicts that
exclude triaged findings, the --mark-fp / --unmark-fp commands, persistence
of marks across a re-scan, and the hook's triaged-FP status line.

All tests redirect skillguard.cli.CACHE_DIR into tmp_path so the real
~/.claude/skillguard-cache is never touched.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import skillguard.cli as cli
from skillguard.cli import (
    Finding,
    LocalEngine,
    SkillInfo,
    apply_triage,
    finding_fingerprint,
    load_triage,
    mark_fp_command,
    save_triage,
    unmark_fp_command,
    write_cache,
)


@pytest.fixture
def cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "skillguard-cache"
    monkeypatch.setattr(cli, "CACHE_DIR", d)
    return d


def _skill(tmp_path: Path, *findings: Finding) -> SkillInfo:
    skill_dir = tmp_path / "victim"
    skill_dir.mkdir(exist_ok=True)
    (skill_dir / "SKILL.md").write_text("---\nname: victim\n---\n# hi\n")
    return SkillInfo(name="victim", path=skill_dir, scope="global", findings=list(findings))


def _finding(sev: str = "high", file: str = "SKILL.md", line: int = 5, msg: str = "Bad thing") -> Finding:
    return Finding(engine="local", severity=sev, category="cat", message=msg, file=file, line=line)


# ── fingerprint ───────────────────────────────────────────────────────────────


def test_fingerprint_ignores_line_number():
    a = _finding(line=5)
    b = _finding(line=99)
    assert finding_fingerprint("victim", a) == finding_fingerprint("victim", b)


def test_fingerprint_distinguishes_skill_file_and_message():
    base = _finding()
    assert finding_fingerprint("victim", base) != finding_fingerprint("other", base)
    assert finding_fingerprint("victim", base) != finding_fingerprint("victim", _finding(file="other.md"))
    assert finding_fingerprint("victim", base) != finding_fingerprint("victim", _finding(msg="Other thing"))


# ── apply_triage + active counting ───────────────────────────────────────────


def test_apply_triage_flags_only_marked_findings(cache_dir, tmp_path):
    marked, unmarked = _finding(msg="Marked"), _finding(msg="Unmarked")
    skill = _skill(tmp_path, marked, unmarked)
    save_triage({"version": 1, "false_positives": {
        finding_fingerprint("victim", marked): {"skill": "victim"},
    }})

    apply_triage(skill)

    assert marked.triaged_fp is True
    assert unmarked.triaged_fp is False
    assert skill.active_findings == [unmarked]


def test_max_severity_ignores_triaged_findings(tmp_path):
    crit = _finding(sev="critical", msg="FP crit")
    crit.triaged_fp = True
    skill = _skill(tmp_path, crit, _finding(sev="low", msg="Real low"))
    assert skill.max_severity == "low"

    skill.findings[1].triaged_fp = True
    assert skill.max_severity == "clean"


def test_write_cache_excludes_triaged_from_verdict(cache_dir, tmp_path):
    fp = _finding(sev="critical", msg="FP crit")
    fp.triaged_fp = True
    skill = _skill(tmp_path, fp, _finding(sev="medium", msg="Real med"))
    write_cache(skill, ["local"])

    data = json.loads((cache_dir / "victim.json").read_text())
    assert data["max_severity"] == "medium"
    assert data["finding_count"] == 1
    assert data["triaged_fp_count"] == 1
    assert len(data["findings"]) == 2  # full fidelity kept
    assert all("FP crit" not in line for line in data["findings_summary"])


# ── --mark-fp / --unmark-fp ──────────────────────────────────────────────────


def test_mark_fp_rewrites_cache_to_clean_and_persists_marks(cache_dir, tmp_path, capsys):
    skill = _skill(tmp_path, _finding(sev="critical"), _finding(sev="low", msg="Other"))
    write_cache(skill, ["local"])

    mark_fp_command("victim")

    data = json.loads((cache_dir / "victim.json").read_text())
    assert data["max_severity"] == "clean"
    assert data["finding_count"] == 0
    assert data["triaged_fp_count"] == 2
    assert len(load_triage()["false_positives"]) == 2
    assert "Marked 2 finding(s)" in capsys.readouterr().out


def test_mark_fp_never_suppresses_info_advisories(cache_dir, tmp_path):
    skill = _skill(
        tmp_path,
        _finding(sev="high"),
        Finding(engine="cisco", severity="info", category="policy_violation", message="No license field"),
    )
    write_cache(skill, ["local", "cisco"])

    mark_fp_command("victim")

    data = json.loads((cache_dir / "victim.json").read_text())
    assert data["triaged_fp_count"] == 1
    assert data["finding_count"] == 1  # the info advisory stays active
    assert data["max_severity"] == "info"


def test_mark_fp_requires_existing_scan(cache_dir):
    with pytest.raises(SystemExit) as exc:
        mark_fp_command("never-scanned")
    assert exc.value.code == 1


def test_mark_fp_requires_structured_findings(cache_dir):
    # Pre-triage cache format: no "findings" key
    cache_dir.mkdir(parents=True)
    (cache_dir / "old.json").write_text(json.dumps({
        "skill_name": "old", "max_severity": "high", "finding_count": 1,
        "findings_summary": ["[local/high] Bad thing in SKILL.md:5"],
    }))
    with pytest.raises(SystemExit) as exc:
        mark_fp_command("old")
    assert exc.value.code == 1


def test_unmark_fp_restores_verdict(cache_dir, tmp_path, capsys):
    skill = _skill(tmp_path, _finding(sev="critical"))
    write_cache(skill, ["local"])
    mark_fp_command("victim")

    unmark_fp_command("victim")

    data = json.loads((cache_dir / "victim.json").read_text())
    assert data["max_severity"] == "critical"
    assert data["finding_count"] == 1
    assert data["triaged_fp_count"] == 0
    assert load_triage()["false_positives"] == {}


def test_unmark_fp_only_removes_named_skill(cache_dir, tmp_path):
    save_triage({"version": 1, "false_positives": {
        "victim|local|cat|SKILL.md|Bad thing": {"skill": "victim"},
        "other|local|cat|SKILL.md|Bad thing": {"skill": "other"},
    }})
    unmark_fp_command("victim")
    assert list(load_triage()["false_positives"].values()) == [{"skill": "other"}]


# ── persistence across a re-scan ─────────────────────────────────────────────


def test_marks_survive_rescan(cache_dir, tmp_path, monkeypatch):
    # A skill whose SKILL.md trips the local "whoami" recon pattern.
    skill_dir = tmp_path / "skills" / "victim"
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("---\nname: victim\n---\n\nRun `whoami` to check your user.\n")

    def scan() -> SkillInfo:
        s = SkillInfo(name="victim", path=skill_dir, scope="global", files=[skill_md])
        s.findings.extend(LocalEngine().scan(s))
        apply_triage(s)
        write_cache(s, ["local"])
        return s

    first = scan()
    assert first.max_severity == "low"
    mark_fp_command("victim")

    rescanned = scan()
    assert rescanned.max_severity == "clean"
    data = json.loads((cache_dir / "victim.json").read_text())
    assert data["finding_count"] == 0
    assert data["triaged_fp_count"] == 1


def test_corrupt_triage_store_treated_as_empty(cache_dir, tmp_path):
    cache_dir.mkdir(parents=True)
    (cache_dir / "_triage.json").write_text("{not json")
    assert load_triage() == {"version": 1, "false_positives": {}}


# ── hook status line ─────────────────────────────────────────────────────────


def test_hook_shows_triaged_fp_note(hook_path, tmp_path):
    cache_dir = tmp_path / ".claude" / "skillguard-cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / "victim.json").write_text(json.dumps({
        "skill_name": "victim",
        "scanned_at": "2026-06-10T12:00:00+00:00",
        "skill_mtime_epoch": 0,
        "engines_used": ["local"],
        "skipped": False,
        "max_severity": "clean",
        "finding_count": 0,
        "triaged_fp_count": 3,
        "findings_summary": [],
        "findings": [],
    }))

    env = dict(os.environ)
    env["HOME"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps({"tool_input": {"skill": "victim"}}),
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0
    assert "clean (3 triaged FP)" in result.stdout
