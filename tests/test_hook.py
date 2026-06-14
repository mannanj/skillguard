"""End-to-end tests for the PreToolUse hook (skillguard/hook.py).

The hook is exercised exactly as Claude Code runs it: as a subprocess that
reads a JSON event on stdin and signals via exit code (0 = allow, 2 = block).

Isolation: the hook computes CACHE_DIR / GLOBAL_SKILLS_DIR from Path.home() at
import time, so we run every subprocess with a fresh HOME pointing at tmp_path.
The real ~/.claude is never read or written.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _run_hook(hook_path: Path, tmp_home: Path, stdin_text: str) -> subprocess.CompletedProcess:
    """Invoke the hook as a subprocess with HOME overridden to tmp_home."""
    env = dict(os.environ)
    env["HOME"] = str(tmp_home)
    return subprocess.run(
        [sys.executable, str(hook_path)],
        input=stdin_text,
        capture_output=True,
        text=True,
        env=env,
    )


def _event(skill_name: str) -> str:
    return json.dumps({"tool_input": {"skill": skill_name}})


def _cache_dir(tmp_home: Path) -> Path:
    d = tmp_home / ".claude" / "skillguard-cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_cache_entry(tmp_home: Path, name: str, data: dict) -> Path:
    cache_dir = _cache_dir(tmp_home)
    p = cache_dir / f"{name}.json"
    p.write_text(json.dumps(data))
    return p


def _clean_cache(name: str, mtime: float = 0.0) -> dict:
    return {
        "skill_name": name,
        "scanned_at": "2026-06-03T12:00:00+00:00",
        "skill_mtime_epoch": mtime,
        "engines_used": ["local"],
        "skipped": False,
        "max_severity": "clean",
        "finding_count": 0,
        "findings_summary": [],
    }


# ── (a) never scanned → exit 2 ────────────────────────────────────────────────


def test_never_scanned_blocks(hook_path, tmp_path):
    _cache_dir(tmp_path)  # cache dir exists but no entry for this skill
    result = _run_hook(hook_path, tmp_path, _event("ghost-skill"))
    assert result.returncode == 2
    assert "never been scanned" in result.stderr


# ── (b) corrupted cache JSON → exit 2 (fail closed) ───────────────────────────


def test_corrupted_cache_fails_closed(hook_path, tmp_path):
    cache_dir = _cache_dir(tmp_path)
    (cache_dir / "broken.json").write_text("{ this is not valid json ::::")
    result = _run_hook(hook_path, tmp_path, _event("broken"))
    assert result.returncode == 2
    assert "corrupted" in result.stderr.lower()


# ── (c) clean cache → exit 0 with "clean" in stdout ───────────────────────────


def test_clean_cache_allows(hook_path, tmp_path):
    _write_cache_entry(tmp_path, "tidy", _clean_cache("tidy"))
    result = _run_hook(hook_path, tmp_path, _event("tidy"))
    assert result.returncode == 0
    assert "clean" in result.stdout.lower()
    assert "tidy" in result.stdout


# ── (d) skipped cache → exit 0 with reminder ──────────────────────────────────


def test_skipped_cache_allows_with_reminder(hook_path, tmp_path):
    _write_cache_entry(
        tmp_path,
        "lazyskill",
        {
            "skill_name": "lazyskill",
            "scanned_at": "2026-06-03T12:00:00+00:00",
            "skill_mtime_epoch": 0,
            "engines_used": [],
            "skipped": True,
            "max_severity": "skipped",
            "finding_count": 0,
            "findings_summary": [],
        },
    )
    result = _run_hook(hook_path, tmp_path, _event("lazyskill"))
    assert result.returncode == 0
    assert "SKIPPED" in result.stdout
    assert "lazyskill" in result.stdout


# ── (e) cache older than current SKILL.md → exit 2 with "MODIFIED" ────────────


def test_modified_after_scan_blocks(hook_path, tmp_path):
    # Cache says the skill was scanned at epoch 100.0.
    name = "drifted"
    _write_cache_entry(tmp_path, name, _clean_cache(name, mtime=100.0))

    # A real SKILL.md exists in the global skills dir with a current (newer)
    # mtime, simulating an edit after the scan.
    skill_dir = tmp_path / ".claude" / "skills" / name
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("---\nname: drifted\n---\n# changed after scan\n")
    # Real file mtime is ~now (>> 101), so the TOCTOU guard must fire. Belt and
    # suspenders: set it explicitly far in the future.
    future = time.time() + 10_000
    os.utime(skill_md, (future, future))

    result = _run_hook(hook_path, tmp_path, _event(name))
    assert result.returncode == 2
    assert "MODIFIED" in result.stderr


def test_unmodified_after_scan_allows(hook_path, tmp_path):
    """Mirror of the TOCTOU guard: if the on-disk SKILL.md is OLDER than the
    cached scan, the hook must allow (no false MODIFIED block)."""
    name = "stable"
    skill_dir = tmp_path / ".claude" / "skills" / name
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("---\nname: stable\n---\n# unchanged\n")
    old = time.time() - 10_000
    os.utime(skill_md, (old, old))
    # Cache scanned well after the file's mtime.
    _write_cache_entry(tmp_path, name, _clean_cache(name, mtime=time.time()))

    result = _run_hook(hook_path, tmp_path, _event(name))
    assert result.returncode == 0
    assert "clean" in result.stdout.lower()


# ── (f) namespaced "plugin:name" falls back to short-name cache ───────────────


def test_namespaced_skill_falls_back_to_short_name(hook_path, tmp_path):
    # Cache file written under the short name only.
    _write_cache_entry(tmp_path, "formatter", _clean_cache("formatter"))
    result = _run_hook(hook_path, tmp_path, _event("myplugin:formatter"))
    assert result.returncode == 0
    assert "clean" in result.stdout.lower()
    # The full namespaced name is echoed in the status line.
    assert "myplugin:formatter" in result.stdout


# ── (g) empty / invalid stdin → exit 0 ────────────────────────────────────────


def test_empty_stdin_allows(hook_path, tmp_path):
    _cache_dir(tmp_path)
    result = _run_hook(hook_path, tmp_path, "")
    assert result.returncode == 0


def test_invalid_json_stdin_allows(hook_path, tmp_path):
    _cache_dir(tmp_path)
    result = _run_hook(hook_path, tmp_path, "}{ not json at all")
    assert result.returncode == 0


# ── (h) no skill key → exit 0 ─────────────────────────────────────────────────


def test_no_skill_key_allows(hook_path, tmp_path):
    _cache_dir(tmp_path)
    result = _run_hook(hook_path, tmp_path, json.dumps({"tool_input": {}}))
    assert result.returncode == 0


def test_empty_skill_value_allows(hook_path, tmp_path):
    _cache_dir(tmp_path)
    result = _run_hook(hook_path, tmp_path, json.dumps({"tool_input": {"skill": ""}}))
    assert result.returncode == 0


# ══ MCP tool gating ═══════════════════════════════════════════════════════════
#
# The hook also fires on mcp__<server>__<tool> calls, governed by mcp_policy
# (off | warn | enforce). Policy is supplied here via the SKILLGUARD_MCP_POLICY
# env var, which config.mcp_policy honors over the persisted setting.


def _mcp_dir(tmp_home: Path) -> Path:
    d = tmp_home / ".claude" / "skillguard-cache" / "mcps"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_mcp_verdict(
    tmp_home, name, *, max_severity="clean", finding_count=0, skipped=False, match_tokens=None
) -> Path:
    d = _mcp_dir(tmp_home)
    data = {
        "skill_name": name,
        "target_name": name,
        "kind": "mcp",
        "scope": "global",
        "scanned_at": "2026-06-11T12:00:00+00:00",
        "skill_mtime_epoch": 0,
        "engines_used": ["local", "mcp"],
        "skipped": skipped,
        "max_severity": "skipped" if skipped else max_severity,
        "finding_count": finding_count,
        "triaged_fp_count": 0,
        "findings_summary": [],
        "findings": [],
        "match_tokens": match_tokens or [name],
    }
    p = d / f"{name}.json"
    p.write_text(json.dumps(data))
    return p


def _mcp_event(tool_name: str) -> str:
    return json.dumps({"tool_name": tool_name, "tool_input": {}})


def _run_hook_mcp(hook_path, tmp_home, stdin_text, policy=None):
    env = dict(os.environ)
    env["HOME"] = str(tmp_home)
    env.pop("SKILLGUARD_ACTIVITY_LOG", None)
    if policy:
        env["SKILLGUARD_MCP_POLICY"] = policy
    else:
        env.pop("SKILLGUARD_MCP_POLICY", None)
    return subprocess.run(
        [sys.executable, str(hook_path)],
        input=stdin_text,
        capture_output=True,
        text=True,
        env=env,
    )


def test_mcp_unscanned_warn_allows_with_nudge(hook_path, tmp_path):
    _mcp_dir(tmp_path)  # no verdict for this server
    r = _run_hook_mcp(hook_path, tmp_path, _mcp_event("mcp__ghost__do"), policy="warn")
    assert r.returncode == 0
    assert "unscanned" in r.stdout.lower()


def test_mcp_unscanned_warn_nudges_only_once(hook_path, tmp_path):
    _mcp_dir(tmp_path)
    first = _run_hook_mcp(hook_path, tmp_path, _mcp_event("mcp__ghost__do"), policy="warn")
    second = _run_hook_mcp(hook_path, tmp_path, _mcp_event("mcp__ghost__do"), policy="warn")
    assert "unscanned" in first.stdout.lower()
    assert second.stdout.strip() == ""  # gentle: silent on the second call
    assert second.returncode == 0


def test_mcp_unscanned_enforce_blocks(hook_path, tmp_path):
    _mcp_dir(tmp_path)
    r = _run_hook_mcp(hook_path, tmp_path, _mcp_event("mcp__ghost__do"), policy="enforce")
    assert r.returncode == 2
    assert "not been scanned" in r.stderr.lower()


def test_mcp_policy_off_ignores(hook_path, tmp_path):
    _mcp_dir(tmp_path)
    r = _run_hook_mcp(hook_path, tmp_path, _mcp_event("mcp__ghost__do"), policy="off")
    assert r.returncode == 0
    assert r.stdout.strip() == "" and r.stderr.strip() == ""


def test_mcp_scanned_clean_allows_silently(hook_path, tmp_path):
    _write_mcp_verdict(tmp_path, "weather", max_severity="clean")
    r = _run_hook_mcp(hook_path, tmp_path, _mcp_event("mcp__weather__forecast"), policy="warn")
    assert r.returncode == 0
    # Scanned-clean MCP allows are silent on stdout (MCP tools fire often).
    assert r.stdout.strip() == ""


def test_mcp_scanned_bad_enforce_blocks(hook_path, tmp_path):
    _write_mcp_verdict(tmp_path, "evil", max_severity="high", finding_count=3)
    r = _run_hook_mcp(hook_path, tmp_path, _mcp_event("mcp__evil__run"), policy="enforce")
    assert r.returncode == 2
    assert "finding(s)" in r.stderr


def test_mcp_scanned_bad_warn_allows(hook_path, tmp_path):
    _write_mcp_verdict(tmp_path, "evil", max_severity="high", finding_count=3)
    r = _run_hook_mcp(hook_path, tmp_path, _mcp_event("mcp__evil__run"), policy="warn")
    assert r.returncode == 0  # warn never blocks


def test_mcp_skipped_shows_reminder(hook_path, tmp_path):
    _write_mcp_verdict(tmp_path, "lazy", skipped=True)
    r = _run_hook_mcp(hook_path, tmp_path, _mcp_event("mcp__lazy__x"), policy="enforce")
    assert r.returncode == 0  # skipped allows even under enforce
    assert "SKIPPED" in r.stdout


def test_mcp_token_prefix_match_resolves_verdict(hook_path, tmp_path):
    """A tool name mcp__sun-signal__get_sun_data must map to the 'sun-signal'
    verdict via its match tokens, not be treated as unscanned."""
    _write_mcp_verdict(
        tmp_path, "sun-signal", max_severity="clean", match_tokens=["sun-signal", "sun_signal"]
    )
    r = _run_hook_mcp(
        hook_path, tmp_path, _mcp_event("mcp__sun-signal__get_sun_data"), policy="warn"
    )
    assert r.returncode == 0
    assert "unscanned" not in r.stdout.lower()  # proves the verdict was matched


def test_mcp_corrupted_verdict_enforce_blocks(hook_path, tmp_path):
    """An unreadable MCP verdict can't be matched → treated as unscanned →
    enforce blocks (fails toward safety)."""
    d = _mcp_dir(tmp_path)
    (d / "broken.json").write_text("{ not json :::")
    r = _run_hook_mcp(hook_path, tmp_path, _mcp_event("mcp__broken__x"), policy="enforce")
    assert r.returncode == 2
