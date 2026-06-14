"""End-to-end characterization tests for the *skill* scan path through ``main()``.

The MCP path already has an e2e harness (``test_cli_mcp.py``); the skill scan
path — discovery, the local engine, and the report renderers driven from
``main()`` — was unpinned. These tests run ``cli.py`` exactly as a user would:
as a subprocess with HOME pointed at a tmp dir, seeding skills by copying the
on-disk fixtures into ``$HOME/.claude/skills/<name>/``. They pin *current*
behavior (golden output safety net) ahead of the planned cli.py refactor; they
must not be loosened to accommodate a behavior change without a note.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI = REPO_ROOT / "skillguard" / "cli.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def run_cli(tmp_home: Path, *args: str) -> subprocess.CompletedProcess:
    """Run the CLI as a subprocess with HOME redirected (mirrors test_cli_mcp)."""
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


def seed_skill(tmp_home: Path, fixture_name: str, as_name: str) -> None:
    """Copy a fixture skill into the redirected global skills dir."""
    dst = tmp_home / ".claude" / "skills" / as_name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FIXTURES / fixture_name, dst)


def test_scan_skills_json_summary(tmp_path):
    seed_skill(tmp_path, "malicious-skill", "evil")
    seed_skill(tmp_path, "clean-skill", "good")

    r = run_cli(
        tmp_path,
        "--target",
        "skills",
        "--scope",
        "global",
        "--engines",
        "local",
        "--format",
        "json",
    )
    assert r.returncode == 0, r.stderr

    out = json.loads(r.stdout)
    assert out["summary"]["total_skills"] == 2
    by_name = {s["name"]: s for s in out["skills"]}
    assert by_name["evil"]["max_severity"] in ("critical", "high")
    assert by_name["good"]["max_severity"] == "clean"


def test_scan_skills_quiet_lines(tmp_path):
    seed_skill(tmp_path, "malicious-skill", "evil")
    seed_skill(tmp_path, "clean-skill", "good")

    r = run_cli(
        tmp_path, "--target", "skills", "--scope", "global", "--engines", "local", "--quiet"
    )
    assert r.returncode == 0, r.stderr
    assert "target(s) have HIGH+ findings" in r.stdout
    assert "evil" in r.stdout


def test_scan_skills_table_contains_finding(tmp_path):
    seed_skill(tmp_path, "malicious-skill", "evil")
    seed_skill(tmp_path, "clean-skill", "good")

    r = run_cli(tmp_path, "--target", "skills", "--scope", "global", "--engines", "local")
    assert r.returncode == 0, r.stderr
    assert "evil" in r.stdout
    assert ("HIGH" in r.stdout) or ("CRITICAL" in r.stdout)


def test_scan_no_skills_exits_1(tmp_path):
    # Empty HOME: no ~/.claude/skills dir at all.
    r = run_cli(tmp_path, "--target", "skills", "--scope", "global", "--engines", "local")
    assert r.returncode == 1
    assert "No skills" in r.stderr


def test_scan_findings_still_exit_0(tmp_path):
    # README exit-code contract: findings are reported, not an error.
    seed_skill(tmp_path, "malicious-skill", "evil")

    r = run_cli(tmp_path, "--target", "skills", "--scope", "global", "--engines", "local")
    assert r.returncode == 0, r.stderr
