"""Cached agent-launch summary and one-at-a-time review tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI = REPO_ROOT / "skillguard" / "cli.py"


def _run_cli(
    tmp_home: Path, *args: str, input_text: str | None = None
) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["HOME"] = str(tmp_home)
    env.pop("SKILLGUARD_ACTIVITY_LOG", None)
    env.pop("SKILLGUARD_MCP_POLICY", None)
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        input=input_text,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_home),
    )


def _cache_dir(tmp_home: Path) -> Path:
    d = tmp_home / ".claude" / "skillguard-cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_verdict(
    tmp_home: Path,
    name: str,
    *,
    severity: str = "high",
    count: int = 1,
    kind: str = "skill",
) -> None:
    findings = [
        {
            "engine": "local",
            "severity": severity,
            "category": "cat",
            "message": f"{severity} issue",
            "file": "SKILL.md",
            "line": 7,
            "context": "matched line",
            "triaged_fp": False,
        }
        for _ in range(count)
    ]
    (_cache_dir(tmp_home) / f"{name}.json").write_text(
        json.dumps(
            {
                "skill_name": name,
                "target_name": name,
                "kind": kind,
                "scope": "global",
                "scanned_at": "2026-06-16T12:00:00+00:00",
                "skill_mtime_epoch": 0,
                "engines_used": ["local"],
                "skipped": False,
                "max_severity": severity,
                "finding_count": count,
                "triaged_fp_count": 0,
                "findings_summary": [f"[local/{severity}] {severity} issue in SKILL.md:7"],
                "findings": findings,
            }
        )
    )


def test_agent_summary_points_to_interactive_review(tmp_path):
    _write_verdict(tmp_path, "cloudflare", severity="critical", count=3)
    _write_verdict(tmp_path, "prompt-engineering-skill", severity="high", count=1)
    _write_verdict(tmp_path, "clean", severity="clean", count=0)

    r = _run_cli(tmp_path, "--agent-summary")

    assert r.returncode == 0, r.stderr
    assert "SkillGuard:" in r.stdout
    assert "2/3 high+" in r.stdout
    assert "3 skills" in r.stdout
    assert "4 findings" in r.stdout
    assert "latest 2026-06-16 12:00 UTC" in r.stdout
    assert "skillguard --review" in r.stdout
    assert "cloudflare skill critical(3)" in r.stdout


def test_agent_summary_handles_empty_cache(tmp_path):
    r = _run_cli(tmp_path, "--agent-summary")

    assert r.returncode == 0
    assert "no cached scan" in r.stdout
    assert "skillguard --target all" in r.stdout


def test_review_quit_shows_one_target_at_a_time(tmp_path):
    _write_verdict(tmp_path, "cloudflare", severity="critical", count=2)

    r = _run_cli(tmp_path, "--review", input_text="q\n")

    assert r.returncode == 0, r.stderr
    assert "[1/1] cloudflare" in r.stdout
    assert "critical issue" in r.stdout
    assert "mark-fp" in r.stdout


def test_review_can_mark_target_false_positive(tmp_path):
    _write_verdict(tmp_path, "prompt-engineering-skill", severity="high", count=1)

    r = _run_cli(tmp_path, "--review", input_text="m\n")

    assert r.returncode == 0, r.stderr
    assert "Marked 1 finding(s)" in r.stdout
    verdict = json.loads((_cache_dir(tmp_path) / "prompt-engineering-skill.json").read_text())
    assert verdict["max_severity"] == "clean"
    assert verdict["finding_count"] == 0
    assert verdict["triaged_fp_count"] == 1
    triage = json.loads((_cache_dir(tmp_path) / "_triage.json").read_text())
    assert len(triage["false_positives"]) == 1

    activity = _run_cli(tmp_path, "--activity", "10")
    assert activity.returncode == 0, activity.stderr
    assert "mark_fp" in activity.stdout
    assert "prompt-engineering" in activity.stdout
