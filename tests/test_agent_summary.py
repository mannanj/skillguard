from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI = REPO_ROOT / "skillguard" / "cli.py"


def _run_cli(tmp_home: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["HOME"] = str(tmp_home)
    env.pop("SKILLGUARD_ACTIVITY_LOG", None)
    env.pop("SKILLGUARD_MCP_POLICY", None)
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_home),
    )


def _write_verdict(
    tmp_home: Path,
    name: str,
    *,
    kind: str,
    severity: str,
    count: int,
    scanned_at: str,
) -> None:
    base = tmp_home / ".claude" / "skillguard-cache"
    path = base / f"{name}.json"
    if kind == "mcp":
        path = base / "mcps" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    findings = [
        {
            "engine": "local",
            "severity": severity,
            "category": "cat",
            "message": f"{severity} issue",
            "file": "surface.txt",
            "line": 1,
            "context": "matched line",
            "triaged_fp": False,
        }
        for _ in range(count)
    ]
    path.write_text(
        json.dumps(
            {
                "skill_name": name,
                "target_name": name,
                "kind": kind,
                "scope": "global",
                "scanned_at": scanned_at,
                "skill_mtime_epoch": 0,
                "engines_used": ["local"],
                "skipped": False,
                "max_severity": severity,
                "finding_count": count,
                "triaged_fp_count": 0,
                "findings_summary": [],
                "findings": findings,
            }
        )
    )


def test_agent_summary_names_scope_recency_and_top_findings(tmp_path):
    _write_verdict(
        tmp_path,
        "cloudflare",
        kind="skill",
        severity="critical",
        count=3,
        scanned_at="2026-06-16T17:39:43+00:00",
    )
    _write_verdict(
        tmp_path,
        "headroom",
        kind="mcp",
        severity="high",
        count=2,
        scanned_at="2026-06-16T17:40:12+00:00",
    )
    _write_verdict(
        tmp_path,
        "clean-skill",
        kind="skill",
        severity="clean",
        count=0,
        scanned_at="2026-06-16T17:39:00+00:00",
    )

    r = _run_cli(tmp_path, "--agent-summary")

    assert r.returncode == 0, r.stderr
    assert "SkillGuard:" in r.stdout
    assert "2/3 high+" in r.stdout
    assert "2 skills + 1 MCP" in r.stdout
    assert "5 findings" in r.stdout
    assert "latest 2026-06-16 17:40 UTC" in r.stdout
    assert "skillguard --review" in r.stdout
    assert "cloudflare skill critical(3)" in r.stdout
    assert "headroom MCP high(2)" in r.stdout
