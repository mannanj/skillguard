#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""
PreToolUse hook for SkillGuard — gates both Skill and MCP tool calls.

Skills (matcher ``Skill``):
  - No scan on record        → BLOCK (exit 2), offer to scan or skip
  - Corrupted cache entry     → BLOCK (exit 2), fail closed — never silently allow
  - Skill changed since scan  → BLOCK (exit 2), re-scan required (TOCTOU guard)
  - Skipped (never scanned)   → PASS but show reminder every time
  - Scanned                   → PASS with one-liner status (last date, result)

MCP tools (matcher ``mcp__.*``), governed by the ``mcp_policy`` setting:
  - ``off``     → ignore MCP tool calls entirely
  - ``warn``    → never block; nudge once per unscanned server; log every call
  - ``enforce`` → BLOCK unscanned servers and critical/high verdicts (exit 2)
  Scanned-clean MCP allows are silent on stdout (MCP tools fire often) but are
  always recorded to the activity log.

Exit codes: 0 = allow (status on stdout, never interrupts) · 2 = block.

Robustness: the optional integration with the skillguard package (activity log)
is import-guarded — it never crashes a tool call. If the package can't be
imported, the hook still performs its core blocking duty and reads ``mcp_policy``
standalone from the env var / ``_settings.json`` (neither needs the package), so a
configured ``enforce`` keeps blocking instead of silently downgrading to ``warn``
(009-A) — symmetric with skills, which already fail closed. The degradation is
surfaced once on stderr (logging is off) so the operator can repair the install.
"""

import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# CACHE_DIR / DB_NAME mirror skillguard.branding.CACHE_DIR_NAME / DB_NAME as inline
# literals: this hook runs as a standalone script (see install.sh) and must resolve
# its cache path even when the skillguard package can't be imported, so it cannot
# import branding. tests/test_branding.py::test_hook_mirrors_branding pins them so
# a rename can't let them silently drift from the package's naming authority.
CACHE_DIR = Path.home() / ".claude" / "skillguard-cache"
DB_NAME = "skillguard.db"
GLOBAL_SKILLS_DIR = Path.home() / ".claude" / "skills"
MCP_CACHE_DIR = CACHE_DIR / "mcps"
NUDGE_DIR = MCP_CACHE_DIR / "_nudged"

# Standalone mcp_policy inputs for the degraded path (009-A): the policy lives in
# a flat settings file + an env var that need no package to read, so a configured
# `enforce` must survive a broken/partial install instead of silently degrading to
# the non-blocking `warn` default (skills already fail CLOSED — this keeps MCP
# symmetric). These mirror config.py / branding.py; the env name is pinned against
# branding by tests/test_branding.py::test_hook_mirrors_branding.
MCP_POLICY_ENV = "SKILLGUARD_MCP_POLICY"
SETTINGS_NAME = "_settings.json"
_VALID_MCP_POLICIES = ("off", "warn", "enforce")

# Optional package integration (settings + activity log). Never fatal.
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from skillguard import config as _config
    from skillguard import store as _store

    _HAVE_PKG = True
except Exception:  # pragma: no cover - defensive
    _HAVE_PKG = False


def scan_cmd() -> str:
    """Best command for the user to run the scanner, wherever this hook lives."""
    if shutil.which("skillguard"):
        return "skillguard"
    cli = Path(__file__).resolve().parent / "cli.py"
    return f"python3 {cli}"


def block(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(2)


def _fmt_date(scanned_at: str) -> str:
    try:
        return datetime.fromisoformat(scanned_at).strftime("%b %d, %Y %H:%M")
    except (ValueError, TypeError):
        return str(scanned_at)


def _standalone_mcp_policy() -> str:
    """Resolve mcp_policy WITHOUT the skillguard package — env var first, then the
    flat ``_settings.json`` — mirroring ``config.mcp_policy``'s resolution order.
    Used on the degraded path so an explicitly configured ``enforce`` is honored
    even when the package can't be imported (009-A)."""
    env = os.environ.get(MCP_POLICY_ENV)
    if env is not None and env.strip().lower() in _VALID_MCP_POLICIES:
        return env.strip().lower()
    try:
        data = json.loads((CACHE_DIR / SETTINGS_NAME).read_text())
        val = str(data.get("mcp_policy", "warn")).lower()
        if val in _VALID_MCP_POLICIES:
            return val
    except (OSError, json.JSONDecodeError, AttributeError, TypeError):
        pass
    return "warn"


def _mcp_policy() -> "tuple[str, bool]":
    """Return ``(policy, degraded)``. ``degraded`` is True when the package
    integration is unavailable and we fell back to the standalone reader — the
    caller surfaces a visible notice (activity logging is off; policy is read
    directly from settings) so the operator can repair the install."""
    if _HAVE_PKG:
        try:
            return _config.mcp_policy(CACHE_DIR), False
        except Exception:
            pass
    return _standalone_mcp_policy(), True


def _log(action: str, **kw) -> None:
    """Best-effort activity log of a hook decision; never raises, never blocks."""
    if not _HAVE_PKG:
        return
    try:
        if not _config.activity_logging_enabled(CACHE_DIR):
            return
        _store.log_activity_safe(
            CACHE_DIR / DB_NAME, actor="hook", action=action, source="hook", **kw
        )
    except Exception:
        pass


# ─── Skill gating (unchanged behavior) ───────────────────────────────────────


def find_skill_mtime(skill_name: str, short_name: str) -> "float | None":
    """Current SKILL.md mtime for a globally-installed skill, or None if unresolvable."""
    for name in (skill_name, short_name):
        skill_md = GLOBAL_SKILLS_DIR / name / "SKILL.md"
        if skill_md.exists():
            try:
                return skill_md.stat().st_mtime
            except OSError:
                return None
    return None


def handle_skill(skill_name: str) -> None:
    cmd = scan_cmd()
    short_name = skill_name.split(":", 1)[1] if ":" in skill_name else skill_name
    cache_file = CACHE_DIR / f"{skill_name}.json"
    if not cache_file.exists():
        cache_file = CACHE_DIR / f"{short_name}.json"

    if not cache_file.exists():
        _log(
            "hook_block",
            target_kind="skill",
            target_name=skill_name,
            outcome="block",
            detail="never scanned",
        )
        block(
            f"⚠ SkillGuard: '{skill_name}' has never been scanned.\n"
            f"  Option 1: {cmd} --skill {short_name}\n"
            f"  Option 2: {cmd} --skip {short_name}  (mark as skipped)"
        )

    # A torn or unreadable cache fails CLOSED.
    try:
        cache = json.loads(cache_file.read_text())
    except (json.JSONDecodeError, OSError):
        _log(
            "hook_block",
            target_kind="skill",
            target_name=skill_name,
            outcome="block",
            detail="corrupted cache",
        )
        block(
            f"⚠ SkillGuard: cache entry for '{skill_name}' is corrupted or unreadable.\n"
            f"  Re-scan to restore it: {cmd} --skill {short_name}"
        )

    scanned_at = cache.get("scanned_at", "unknown")
    date_str = _fmt_date(scanned_at)

    if cache.get("skipped"):
        _log(
            "hook_warn",
            target_kind="skill",
            target_name=skill_name,
            outcome="warn",
            detail="skipped (never scanned)",
        )
        print(
            f"⚠ SkillGuard: '{skill_name}' was SKIPPED (never scanned) — "
            f"run: {cmd} --skill {short_name}"
        )
        sys.exit(0)

    # TOCTOU guard — only enforceable for skills we can locate.
    cached_mtime = cache.get("skill_mtime_epoch") or 0
    if cached_mtime:
        current_mtime = find_skill_mtime(skill_name, short_name)
        if current_mtime is not None and current_mtime > cached_mtime + 1:
            _log(
                "hook_block",
                target_kind="skill",
                target_name=skill_name,
                outcome="block",
                detail="modified after scan",
            )
            block(
                f"⚠ SkillGuard: '{skill_name}' was MODIFIED after its last scan "
                f"({date_str}).\n"
                f"  Re-scan before use: {cmd} --skill {short_name}"
            )

    max_sev = cache.get("max_severity", "clean")
    finding_count = cache.get("finding_count", 0)
    triaged = cache.get("triaged_fp_count", 0)
    fp_note = f" ({triaged} triaged FP)" if triaged else ""

    if max_sev == "clean":
        _log(
            "hook_allow",
            target_kind="skill",
            target_name=skill_name,
            outcome="allow",
            detail=f"clean | {date_str}",
        )
        print(f"✓ SkillGuard: {skill_name} — clean{fp_note} | scanned {date_str}")
    else:
        _log(
            "hook_allow",
            target_kind="skill",
            target_name=skill_name,
            outcome="allow",
            severity=max_sev,
            detail=f"{finding_count} finding(s), max {max_sev}",
        )
        print(
            f"✓ SkillGuard: {skill_name} — {finding_count} finding(s), "
            f"max: {max_sev}{fp_note} | scanned {date_str}"
        )
    sys.exit(0)


# ─── MCP gating ──────────────────────────────────────────────────────────────


# Per-call bound on the verdict glob (009-B): find_mcp_verdict runs on EVERY
# mcp__* tool call; an unbounded cache dir would make every call read+parse every
# file (latency-tail DoS). Exact-named verdicts always resolve via the fast path
# below regardless of this cap; only best-effort loose matching is bounded.
# Overridable via env for operators with huge caches (and for tests).
try:
    MCP_GLOB_CAP = max(1, int(os.environ.get("SKILLGUARD_MCP_GLOB_CAP", "4000")))
except ValueError:
    MCP_GLOB_CAP = 4000
# Loose substring matches shorter than this are too ambiguous to trust (009-D):
# a 2–3 char token like "api" must not vouch for "api_prod".
MIN_LOOSE_TOKEN = 4


def _safe_name(name: str) -> str:
    """Mirror of ``skillguard.mcp.safe_name`` (the verdict-filename sanitizer) so
    the hook can probe a server's expected verdict file WITHOUT importing the
    package — it runs standalone. Pinned against the real one by
    tests/test_hook.py::test_safe_name_mirrors_package."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", name) or "_unnamed"


def _read_verdict(path: Path) -> "dict | None":
    """Bounded, fault-tolerant read of one verdict file. Runs on every MCP tool
    call, so a pathological (huge/corrupt) file must never stall the hook."""
    try:
        if path.stat().st_size > 512 * 1024:
            return None
        cache = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return cache if isinstance(cache, dict) else None


def _verdict_tokens(cache: dict) -> list:
    return cache.get("match_tokens") or [cache.get("target_name", "")]


def _is_exact_token(server_token: str, t: str) -> bool:
    """The server portion equals this token or is namespaced under it (prefix)."""
    return bool(t) and (server_token == t or server_token.startswith(t + "__"))


def _is_loose_token(server_part: str, t: str) -> bool:
    """A token long enough to trust, appearing as a whole ``_``-delimited segment
    of the server part (or equal to it)."""
    return (
        bool(t)
        and len(t) >= MIN_LOOSE_TOKEN
        and (("_" + t + "_") in ("_" + server_part + "_") or server_part == t)
    )


def find_mcp_verdict(server_token: str, *, strict: bool = False) -> "dict | None":
    """Map an ``mcp__<server>__<tool>`` token back to a cached MCP verdict.

    Resolution, safest-first:
      1. **Fast path** — probe the verdict file the server name maps to directly
         (``mcps/<safe_name(server)>.json`` and its ``-``/``_`` variants) and
         return on an exact/prefix token match. The common case is O(1) and never
         touches the directory glob (009-B).
      2. **Bounded fallback** — scan the cache dir (capped at ``MCP_GLOB_CAP``
         files), preferring the longest EXACT/prefix match. A loose substring
         match is a last resort, must clear ``MIN_LOOSE_TOKEN``, and is refused
         entirely under ``strict`` (enforce) so a risky/unscanned server can never
         inherit a *different* server's clean verdict (009-D, fail-closed).
    """
    if not MCP_CACHE_DIR.is_dir():
        return None
    server_part = server_token.split("__", 1)[0]

    # 1. Fast path: the exact verdict file, if the server name maps straight to it.
    probed: set[str] = set()
    for cand in (server_part, server_part.replace("_", "-"), server_part.replace("-", "_")):
        p = MCP_CACHE_DIR / f"{_safe_name(cand)}.json"
        key = str(p)
        if key in probed or not p.is_file():
            continue
        probed.add(key)
        cache = _read_verdict(p)
        if cache and any(_is_exact_token(server_token, t) for t in _verdict_tokens(cache)):
            return cache

    # 2. Bounded fallback: exact wins; loose only if non-strict and long enough.
    files = sorted(MCP_CACHE_DIR.glob("*.json"))
    if len(files) > MCP_GLOB_CAP:
        print(
            f"⚠ SkillGuard: MCP verdict cache has {len(files)} files; scanning only "
            f"the first {MCP_GLOB_CAP}. Exact-named verdicts still resolve; prune the "
            f"cache (or raise SKILLGUARD_MCP_GLOB_CAP) to restore loose matching.",
            file=sys.stderr,
        )
        files = files[:MCP_GLOB_CAP]
    best_exact: tuple[dict | None, int] = (None, -1)
    best_loose: tuple[dict | None, int] = (None, -1)
    for p in files:
        cache = _read_verdict(p)
        if cache is None:
            continue
        for t in _verdict_tokens(cache):
            if _is_exact_token(server_token, t) and len(t) > best_exact[1]:
                best_exact = (cache, len(t))
            elif not strict and _is_loose_token(server_part, t) and len(t) > best_loose[1]:
                best_loose = (cache, len(t))
    return best_exact[0] if best_exact[0] is not None else best_loose[0]


def _should_nudge(server_label: str) -> bool:
    """Nudge about an unscanned MCP at most once per server (gentle for the
    high-frequency MCP path). Returns True the first time, then marks it."""
    try:
        NUDGE_DIR.mkdir(parents=True, exist_ok=True)
        marker = NUDGE_DIR / (server_label.replace("/", "_") + ".flag")
        if marker.exists():
            return False
        marker.write_text(datetime.now(timezone.utc).isoformat())
        return True
    except OSError:
        return True


def handle_mcp(tool_name: str) -> None:
    policy, degraded = _mcp_policy()
    if policy == "off":
        sys.exit(0)

    # Make a broken/partial install visible (009-A): logging is off and the policy
    # is being read standalone. Throttled to once per marker so the high-frequency
    # MCP path isn't spammed; any enforce block below still prints its own reason.
    if degraded and _should_nudge("__skillguard_degraded__"):
        print(
            "⚠ SkillGuard: running in DEGRADED mode — the skillguard package could "
            "not be imported (partial/broken install). Activity logging is off and "
            "the MCP policy is read directly from settings. Reinstall to restore "
            "full integration.",
            file=sys.stderr,
        )

    server_token = tool_name[len("mcp__") :]
    server_label = server_token.split("__", 1)[0] if "__" in server_token else server_token
    cmd = scan_cmd()
    # Under enforce, refuse loose cross-server matches (009-D): an ambiguous match
    # must resolve toward "unscanned" rather than borrow another server's verdict.
    verdict = find_mcp_verdict(server_token, strict=(policy == "enforce"))

    if verdict is None:
        if policy == "enforce":
            _log(
                "hook_block",
                target_kind="mcp",
                target_name=server_label,
                outcome="block",
                detail="unscanned MCP server",
            )
            block(
                f"⚠ SkillGuard: MCP server '{server_label}' has not been scanned.\n"
                f"  Scan it:    {cmd} --mcp {server_label}\n"
                f"  Or allow:   {cmd} --skip-mcp {server_label}"
            )
        # warn: never block; nudge once, always log.
        _log(
            "hook_warn",
            target_kind="mcp",
            target_name=server_label,
            outcome="warn",
            detail="unscanned MCP server (allowed under warn policy)",
        )
        if _should_nudge(server_label):
            print(
                f"⚠ SkillGuard: MCP '{server_label}' is unscanned — scan with "
                f"{cmd} --mcp {server_label}  (set 'enforce' to block)"
            )
        sys.exit(0)

    name = verdict.get("target_name") or verdict.get("skill_name") or server_label
    date_str = _fmt_date(verdict.get("scanned_at", "unknown"))

    if verdict.get("skipped"):
        _log("hook_warn", target_kind="mcp", target_name=name, outcome="warn", detail="skipped MCP")
        if _should_nudge(name):
            print(f"⚠ SkillGuard: MCP '{name}' was SKIPPED — scan with {cmd} --mcp {name}")
        sys.exit(0)

    max_sev = verdict.get("max_severity", "clean")
    finding_count = verdict.get("finding_count", 0)

    if policy == "enforce" and max_sev in ("critical", "high"):
        _log(
            "hook_block",
            target_kind="mcp",
            target_name=name,
            outcome="block",
            severity=max_sev,
            detail=f"{finding_count} finding(s), max {max_sev}",
        )
        block(
            f"⚠ SkillGuard: MCP '{name}' has {finding_count} finding(s) (max: {max_sev}).\n"
            f"  Review:      {cmd} --show {name}\n"
            f"  Allow anyway: {cmd} --skip-mcp {name}"
        )

    # Allow. Scanned MCP allows are silent on stdout (MCP tools fire often) but
    # are recorded to the activity log so the audit trail stays complete.
    if max_sev == "clean":
        _log(
            "hook_allow",
            target_kind="mcp",
            target_name=name,
            outcome="allow",
            detail=f"clean | {date_str}",
        )
    else:
        _log(
            "hook_allow",
            target_kind="mcp",
            target_name=name,
            outcome="allow",
            severity=max_sev,
            detail=f"{finding_count} finding(s), max {max_sev}",
        )
    sys.exit(0)


def main() -> None:
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "") or ""
    tool_input = hook_input.get("tool_input", {})
    skill_name = tool_input.get("skill", "") if isinstance(tool_input, dict) else ""

    if skill_name:
        handle_skill(skill_name)
        return
    if isinstance(tool_name, str) and tool_name.startswith("mcp__"):
        handle_mcp(tool_name)
        return
    sys.exit(0)


if __name__ == "__main__":
    main()
