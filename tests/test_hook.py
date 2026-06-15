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


def _run_hook_mcp(hook_path, tmp_home, stdin_text, policy=None, env_extra=None):
    env = dict(os.environ)
    env["HOME"] = str(tmp_home)
    env.pop("SKILLGUARD_ACTIVITY_LOG", None)
    env.pop("SKILLGUARD_MCP_GLOB_CAP", None)
    if policy:
        env["SKILLGUARD_MCP_POLICY"] = policy
    else:
        env.pop("SKILLGUARD_MCP_POLICY", None)
    if env_extra:
        env.update(env_extra)
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


# ══ 009-A: degraded path (skillguard package unimportable) must not silently ══
#         downgrade a configured `enforce` to the non-blocking `warn` default. ══
#         Skills already fail CLOSED on any uncertainty; MCP must be symmetric.


def _degraded_hook_path(hook_path: Path, tmp_home: Path) -> Path:
    """Copy the hook into a sandbox and plant a *broken* ``skillguard`` package at
    the path the hook prepends to ``sys.path`` (its parent.parent), so
    ``from skillguard import config, store`` raises and the hook runs with
    ``_HAVE_PKG=False`` — the exact degraded state 009-A is about (a partial
    install, or a syntax error in config.py/store.py)."""
    import shutil

    sandbox = tmp_home / "sandbox"
    sandbox.mkdir(parents=True, exist_ok=True)
    dst = sandbox / "hook.py"
    shutil.copy(hook_path, dst)
    broken = tmp_home / "skillguard"  # == dst.parent.parent / "skillguard"
    broken.mkdir(parents=True, exist_ok=True)
    (broken / "__init__.py").write_text("raise ImportError('simulated broken install')\n")
    return dst


def test_mcp_degraded_enforce_blocks_unscanned(hook_path, tmp_path):
    """A broken package install must NOT silently disable `enforce`: an unscanned
    MCP under enforce still blocks, read standalone from the env var."""
    _mcp_dir(tmp_path)
    degraded = _degraded_hook_path(hook_path, tmp_path)
    r = _run_hook_mcp(degraded, tmp_path, _mcp_event("mcp__ghost__do"), policy="enforce")
    assert r.returncode == 2
    assert "not been scanned" in r.stderr.lower()
    # Not frustrating: the block must still surface the proceed/skip escape hatch.
    assert "--skip-mcp" in r.stderr


def test_mcp_degraded_enforce_reads_settings_file(hook_path, tmp_path):
    """With no env override, the degraded hook must read `enforce` straight from
    the flat _settings.json (no package needed) and block an unscanned server."""
    cache = tmp_path / ".claude" / "skillguard-cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "_settings.json").write_text(json.dumps({"mcp_policy": "enforce"}))
    _mcp_dir(tmp_path)
    degraded = _degraded_hook_path(hook_path, tmp_path)
    r = _run_hook_mcp(degraded, tmp_path, _mcp_event("mcp__ghost__do"), policy=None)
    assert r.returncode == 2
    assert "not been scanned" in r.stderr.lower()


def test_mcp_degraded_defaults_to_enforce_blocks_unscanned(hook_path, tmp_path):
    """With no policy configured, the degraded hook must default to `enforce`
    (the package default) and block unscanned servers — the warn era is over."""
    _mcp_dir(tmp_path)
    degraded = _degraded_hook_path(hook_path, tmp_path)
    r = _run_hook_mcp(degraded, tmp_path, _mcp_event("mcp__ghost__do"), policy=None)
    assert r.returncode == 2
    assert "not been scanned" in r.stderr.lower()


def test_mcp_degraded_emits_visible_notice(hook_path, tmp_path):
    """The degradation itself must be visible (logging is off, policy is read
    standalone) so the operator can fix the install."""
    _mcp_dir(tmp_path)
    degraded = _degraded_hook_path(hook_path, tmp_path)
    r = _run_hook_mcp(degraded, tmp_path, _mcp_event("mcp__ghost__do"), policy="enforce")
    assert "degraded" in r.stderr.lower()


def test_skill_degraded_still_blocks_unscanned(hook_path, tmp_path):
    """Consistency check: skills already fail CLOSED regardless of the package —
    an unscanned skill blocks even on a broken install. Pins the symmetry 009-A
    brings MCP into line with."""
    _cache_dir(tmp_path)
    degraded = _degraded_hook_path(hook_path, tmp_path)
    r = _run_hook(degraded, tmp_path, _event("ghost-skill"))
    assert r.returncode == 2
    assert "never been scanned" in r.stderr


# ══ 009-D: a loose token match must not let one server inherit a DIFFERENT ════
#         server's clean verdict (a fail-open under enforce). ═══════════════════


def test_mcp_enforce_refuses_loose_cross_attribution(hook_path, tmp_path):
    """Under enforce, an unscanned server must NOT borrow another server's clean
    verdict via a loose substring match — it resolves toward 'unscanned' (the
    safe direction) and blocks."""
    _write_mcp_verdict(tmp_path, "github", max_severity="clean", match_tokens=["github"])
    r = _run_hook_mcp(
        hook_path, tmp_path, _mcp_event("mcp__github_enterprise__run"), policy="enforce"
    )
    assert r.returncode == 2  # must block, not inherit 'github' clean
    assert "not been scanned" in r.stderr.lower()


def test_mcp_enforce_exact_prefix_still_resolves(hook_path, tmp_path):
    """STOP-condition guard: a legitimate exact/prefix match STILL resolves under
    enforce, so tightening doesn't over-block real clean servers."""
    _write_mcp_verdict(tmp_path, "github", max_severity="clean", match_tokens=["github"])
    r = _run_hook_mcp(hook_path, tmp_path, _mcp_event("mcp__github__run"), policy="enforce")
    assert r.returncode == 0


def test_mcp_warn_loose_match_stays_permissive(hook_path, tmp_path):
    """The tightening is scoped to enforce: under the default warn policy (which
    never blocks), a long loose match still resolves silently so warn isn't
    flooded with new nudges (the plan's STOP condition)."""
    _write_mcp_verdict(tmp_path, "github", max_severity="clean", match_tokens=["github"])
    r = _run_hook_mcp(hook_path, tmp_path, _mcp_event("mcp__github_enterprise__run"), policy="warn")
    assert r.returncode == 0
    assert r.stdout.strip() == ""  # resolved to clean -> silent


def test_mcp_short_token_does_not_loose_cross_attribute(hook_path, tmp_path):
    """A too-short token (<4 chars) must not loose-match a longer different
    server even under warn: 'api' must not silently vouch for 'api_prod'."""
    _write_mcp_verdict(tmp_path, "api", max_severity="clean", match_tokens=["api"])
    r = _run_hook_mcp(hook_path, tmp_path, _mcp_event("mcp__api_prod__call"), policy="warn")
    assert r.returncode == 0  # warn never blocks
    assert "unscanned" in r.stdout.lower()  # api_prod treated as unscanned -> nudge


# ══ 009-B: find_mcp_verdict must not read+parse EVERY cache file on every call ═
#         (latency-tail DoS). Fast-path the expected filename; bound the glob. ══


def test_mcp_verdict_resolves_by_expected_filename_amid_many(hook_path, tmp_path):
    """Fast path: a known server resolves via its expected verdict filename even
    with many unrelated files present, without a full-dir scan."""
    d = _mcp_dir(tmp_path)
    for i in range(60):
        (d / f"junk_{i:04d}.json").write_text(
            json.dumps({"target_name": f"j{i}", "match_tokens": [f"junkserver{i}"]})
        )
    _write_mcp_verdict(tmp_path, "weather", max_severity="clean")
    r = _run_hook_mcp(hook_path, tmp_path, _mcp_event("mcp__weather__forecast"), policy="warn")
    assert r.returncode == 0
    assert r.stdout.strip() == ""  # matched (silent clean), not treated as unscanned


def test_mcp_glob_cap_bounds_the_fallback_scan(hook_path, tmp_path):
    """Cap: the loose fallback is bounded. With the cap set low, a verdict that
    sorts BEYOND the cap and is only loose-matchable is not scanned (treated as
    unscanned); without the cap the same verdict resolves. Exact-named verdicts
    are cap-independent (resolved by the fast path)."""
    d = _mcp_dir(tmp_path)
    for i in range(8):  # files that sort BEFORE the real one
        (d / f"aaa_{i:04d}.json").write_text(
            json.dumps({"target_name": f"a{i}", "match_tokens": [f"aaaaaserver{i}"]})
        )
    # Reachable only by a LOOSE match (filename != server token), sorts last.
    (d / "zzz_real.json").write_text(
        json.dumps(
            {"target_name": "zzz_real", "match_tokens": ["coolserver"], "max_severity": "clean"}
        )
    )
    capped = _run_hook_mcp(
        hook_path,
        tmp_path,
        _mcp_event("mcp__coolserver_x__go"),
        policy="warn",
        env_extra={"SKILLGUARD_MCP_GLOB_CAP": "5"},
    )
    assert capped.returncode == 0
    assert "unscanned" in capped.stdout.lower()  # beyond-cap verdict not scanned

    uncapped = _run_hook_mcp(
        hook_path, tmp_path, _mcp_event("mcp__coolserver_x__go"), policy="warn"
    )
    assert uncapped.stdout.strip() == ""  # default cap (4000): resolved via loose -> silent


def test_safe_name_mirrors_package():
    """The hook's standalone ``_safe_name`` must match the package's
    ``mcp.safe_name`` (the verdict-filename authority) so the fast-path filename
    probe targets the same files the scanner writes — pin them against drift."""
    import skillguard.hook as hook
    from skillguard.mcp import safe_name

    for name in ["weather", "api-prod", "api_prod", "sun signal", "weird/../name", "", "ünïcode!"]:
        assert hook._safe_name(name) == safe_name(name), name


# ══ Skill severity gate (critical/high block unless risk acknowledged) ════════
#     Mirrors the MCP gate; escape hatch is --ack (distinct from --skip).


def _high_cache(name: str, mtime: float = 0.0) -> dict:
    return {
        "skill_name": name,
        "scanned_at": "2026-06-03T12:00:00+00:00",
        "skill_mtime_epoch": mtime,
        "engines_used": ["local"],
        "skipped": False,
        "max_severity": "high",
        "finding_count": 2,
        "triaged_fp_count": 0,
        "findings_summary": ["[local/high] reverse shell in x:1"],
        "findings": [],
    }


def _crit_cache(name: str, mtime: float = 0.0) -> dict:
    d = _high_cache(name, mtime)
    d["max_severity"] = "critical"
    d["finding_count"] = 3
    d["findings_summary"] = ["[local/critical] data exfil in x:1"]
    return d


def _acked_cache(name: str, sev: str = "high", mtime: float = 0.0) -> dict:
    d = _high_cache(name, mtime) if sev != "critical" else _crit_cache(name, mtime)
    d["max_severity"] = sev
    d["risk_acknowledged"] = True
    d["acknowledged_at"] = "2026-06-14T00:00:00+00:00"
    d["acknowledged_severity"] = sev
    return d


def test_skill_scanned_high_blocks(hook_path, tmp_path):
    _write_cache_entry(tmp_path, "risky", _high_cache("risky"))
    r = _run_hook(hook_path, tmp_path, _event("risky"))
    assert r.returncode == 2
    assert "BLOCKED" in r.stderr
    assert "high" in r.stderr
    assert "--ack risky" in r.stderr
    assert "--skip risky" in r.stderr


def test_skill_scanned_critical_blocks(hook_path, tmp_path):
    _write_cache_entry(tmp_path, "evil", _crit_cache("evil"))
    r = _run_hook(hook_path, tmp_path, _event("evil"))
    assert r.returncode == 2
    assert "BLOCKED" in r.stderr
    assert "critical" in r.stderr
    assert "--ack evil" in r.stderr


def test_skill_scanned_high_with_ack_allows(hook_path, tmp_path):
    _write_cache_entry(tmp_path, "risky", _acked_cache("risky", "high"))
    r = _run_hook(hook_path, tmp_path, _event("risky"))
    assert r.returncode == 0
    assert "RISK ACKNOWLEDGED" in r.stdout
    assert "high" in r.stdout


def test_skill_scanned_medium_allows_without_ack(hook_path, tmp_path):
    """Non-block severities must pass even without ack (the gate is only crit/high)."""
    med = _high_cache("med")
    med["max_severity"] = "medium"
    med["finding_count"] = 1
    _write_cache_entry(tmp_path, "med", med)
    r = _run_hook(hook_path, tmp_path, _event("med"))
    assert r.returncode == 0
    assert "RISK ACKNOWLEDGED" not in r.stdout


# ══ MCP ack flow under enforce (symmetric to skill) ═══════════════════════════


def test_mcp_scanned_bad_enforce_with_ack_allows(hook_path, tmp_path):
    _write_mcp_verdict(tmp_path, "evil", max_severity="high", finding_count=3)
    # Manually inject the ack flag into the written verdict (simulates --ack-mcp).
    p = _mcp_dir(tmp_path) / "evil.json"
    v = json.loads(p.read_text())
    v["risk_acknowledged"] = True
    v["acknowledged_at"] = "2026-06-14T00:00:00+00:00"
    v["acknowledged_severity"] = "high"
    p.write_text(json.dumps(v))
    r = _run_hook_mcp(hook_path, tmp_path, _mcp_event("mcp__evil__run"), policy="enforce")
    assert r.returncode == 0
    # MCP allows stay silent on stdout even when risky+acked (high-frequency path).
    assert r.stdout.strip() == ""
