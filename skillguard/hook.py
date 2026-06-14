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

Robustness: the optional integration with the skillguard package (settings +
activity log) is import-guarded. If the package can't be imported, the hook
still performs its core blocking duty with a default ``warn`` policy and no
logging — it never crashes a tool call.
"""

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

CACHE_DIR = Path.home() / ".claude" / "skillguard-cache"
GLOBAL_SKILLS_DIR = Path.home() / ".claude" / "skills"
MCP_CACHE_DIR = CACHE_DIR / "mcps"
NUDGE_DIR = MCP_CACHE_DIR / "_nudged"

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


def _mcp_policy() -> str:
    if _HAVE_PKG:
        try:
            return _config.mcp_policy(CACHE_DIR)
        except Exception:
            pass
    return "warn"


def _log(action: str, **kw) -> None:
    """Best-effort activity log of a hook decision; never raises, never blocks."""
    if not _HAVE_PKG:
        return
    try:
        if not _config.activity_logging_enabled(CACHE_DIR):
            return
        _store.log_activity_safe(CACHE_DIR / "skillguard.db", actor="hook",
                                 action=action, source="hook", **kw)
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
        _log("hook_block", target_kind="skill", target_name=skill_name, outcome="block",
             detail="never scanned")
        block(
            f"⚠ SkillGuard: '{skill_name}' has never been scanned.\n"
            f"  Option 1: {cmd} --skill {short_name}\n"
            f"  Option 2: {cmd} --skip {short_name}  (mark as skipped)"
        )

    # A torn or unreadable cache fails CLOSED.
    try:
        cache = json.loads(cache_file.read_text())
    except (json.JSONDecodeError, OSError):
        _log("hook_block", target_kind="skill", target_name=skill_name, outcome="block",
             detail="corrupted cache")
        block(
            f"⚠ SkillGuard: cache entry for '{skill_name}' is corrupted or unreadable.\n"
            f"  Re-scan to restore it: {cmd} --skill {short_name}"
        )

    scanned_at = cache.get("scanned_at", "unknown")
    date_str = _fmt_date(scanned_at)

    if cache.get("skipped"):
        _log("hook_warn", target_kind="skill", target_name=skill_name, outcome="warn",
             detail="skipped (never scanned)")
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
            _log("hook_block", target_kind="skill", target_name=skill_name, outcome="block",
                 detail="modified after scan")
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
        _log("hook_allow", target_kind="skill", target_name=skill_name, outcome="allow",
             detail=f"clean | {date_str}")
        print(f"✓ SkillGuard: {skill_name} — clean{fp_note} | scanned {date_str}")
    else:
        _log("hook_allow", target_kind="skill", target_name=skill_name, outcome="allow",
             severity=max_sev, detail=f"{finding_count} finding(s), max {max_sev}")
        print(
            f"✓ SkillGuard: {skill_name} — {finding_count} finding(s), "
            f"max: {max_sev}{fp_note} | scanned {date_str}"
        )
    sys.exit(0)


# ─── MCP gating ──────────────────────────────────────────────────────────────

def find_mcp_verdict(server_token: str) -> "dict | None":
    """Map an ``mcp__<server>__<tool>`` token back to a cached MCP verdict.

    Matches the longest cached match-token that the server portion starts with.
    Plugin-namespaced servers may not match perfectly (Claude's exact tool-name
    sanitization isn't reproduced); under the default non-blocking ``warn``
    policy that is harmless, and ``--skip-mcp`` / ``off`` cover ``enforce``.
    """
    if not MCP_CACHE_DIR.is_dir():
        return None
    best, best_len = None, -1
    server_part = server_token.split("__", 1)[0]
    for p in sorted(MCP_CACHE_DIR.glob("*.json")):
        try:
            # Bound the read — this runs on every MCP tool call; a pathological
            # verdict file must never stall the hook.
            if p.stat().st_size > 512 * 1024:
                continue
            cache = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        tokens = cache.get("match_tokens") or [cache.get("target_name", "")]
        for t in tokens:
            if not t:
                continue
            exact = server_token == t or server_token.startswith(t + "__")
            loose = ("_" + t + "_") in ("_" + server_part + "_") or server_part == t
            if (exact or loose) and len(t) > best_len:
                best, best_len = cache, len(t)
    return best


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
    policy = _mcp_policy()
    if policy == "off":
        sys.exit(0)

    server_token = tool_name[len("mcp__"):]
    server_label = server_token.split("__", 1)[0] if "__" in server_token else server_token
    cmd = scan_cmd()
    verdict = find_mcp_verdict(server_token)

    if verdict is None:
        if policy == "enforce":
            _log("hook_block", target_kind="mcp", target_name=server_label, outcome="block",
                 detail="unscanned MCP server")
            block(
                f"⚠ SkillGuard: MCP server '{server_label}' has not been scanned.\n"
                f"  Scan it:    {cmd} --mcp {server_label}\n"
                f"  Or allow:   {cmd} --skip-mcp {server_label}"
            )
        # warn: never block; nudge once, always log.
        _log("hook_warn", target_kind="mcp", target_name=server_label, outcome="warn",
             detail="unscanned MCP server (allowed under warn policy)")
        if _should_nudge(server_label):
            print(f"⚠ SkillGuard: MCP '{server_label}' is unscanned — scan with "
                  f"{cmd} --mcp {server_label}  (set 'enforce' to block)")
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
        _log("hook_block", target_kind="mcp", target_name=name, outcome="block", severity=max_sev,
             detail=f"{finding_count} finding(s), max {max_sev}")
        block(
            f"⚠ SkillGuard: MCP '{name}' has {finding_count} finding(s) (max: {max_sev}).\n"
            f"  Review:      {cmd} --show {name}\n"
            f"  Allow anyway: {cmd} --skip-mcp {name}"
        )

    # Allow. Scanned MCP allows are silent on stdout (MCP tools fire often) but
    # are recorded to the activity log so the audit trail stays complete.
    if max_sev == "clean":
        _log("hook_allow", target_kind="mcp", target_name=name, outcome="allow",
             detail=f"clean | {date_str}")
    else:
        _log("hook_allow", target_kind="mcp", target_name=name, outcome="allow", severity=max_sev,
             detail=f"{finding_count} finding(s), max {max_sev}")
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
