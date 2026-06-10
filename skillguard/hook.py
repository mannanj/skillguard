#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""
PreToolUse hook for SkillGuard.

Behavior:
  - No scan on record       → BLOCK (exit 2), offer to scan or skip
  - Corrupted cache entry   → BLOCK (exit 2), fail closed — never silently allow
  - Skill changed since scan → BLOCK (exit 2), re-scan required (TOCTOU guard)
  - Skipped (never scanned) → PASS but show reminder every time
  - Scanned                 → PASS with one-liner status (last date, result)

Exit codes:
  0 = allow (show status on stdout, never interrupts)
  2 = block (interrupts the action)
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

CACHE_DIR = Path.home() / ".claude" / "skillguard-cache"
GLOBAL_SKILLS_DIR = Path.home() / ".claude" / "skills"


def scan_cmd() -> str:
    """Best command for the user to run the scanner, wherever this hook lives."""
    if shutil.which("skillguard"):
        return "skillguard"
    cli = Path(__file__).resolve().parent / "cli.py"
    return f"python3 {cli}"


def block(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(2)


def find_skill_mtime(skill_name: str, short_name: str) -> float | None:
    """Current SKILL.md mtime for a globally-installed skill, or None if unresolvable."""
    for name in (skill_name, short_name):
        skill_md = GLOBAL_SKILLS_DIR / name / "SKILL.md"
        if skill_md.exists():
            try:
                return skill_md.stat().st_mtime
            except OSError:
                return None
    return None


def main() -> None:
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    skill_name = hook_input.get("tool_input", {}).get("skill", "")
    if not skill_name:
        sys.exit(0)

    cmd = scan_cmd()

    # Find cache file (check full name, then without namespace prefix)
    short_name = skill_name.split(":", 1)[1] if ":" in skill_name else skill_name
    cache_file = CACHE_DIR / f"{skill_name}.json"
    if not cache_file.exists():
        cache_file = CACHE_DIR / f"{short_name}.json"

    if not cache_file.exists():
        # BLOCK — never scanned, never skipped
        block(
            f"⚠ SkillGuard: '{skill_name}' has never been scanned.\n"
            f"  Option 1: {cmd} --skill {short_name}\n"
            f"  Option 2: {cmd} --skip {short_name}  (mark as skipped)"
        )

    # Cache exists — read it. A torn or unreadable cache fails CLOSED:
    # an attacker who can corrupt the cache must not gain silent approval.
    try:
        cache = json.loads(cache_file.read_text())
    except (json.JSONDecodeError, OSError):
        block(
            f"⚠ SkillGuard: cache entry for '{skill_name}' is corrupted or unreadable.\n"
            f"  Re-scan to restore it: {cmd} --skill {short_name}"
        )

    scanned_at = cache.get("scanned_at", "unknown")
    # Format date nicely
    try:
        dt = datetime.fromisoformat(scanned_at)
        date_str = dt.strftime("%b %d, %Y %H:%M")
    except (ValueError, TypeError):
        date_str = str(scanned_at)

    if cache.get("skipped"):
        # Skipped — reminder every time, but don't block
        print(
            f"⚠ SkillGuard: '{skill_name}' was SKIPPED (never scanned) — "
            f"run: {cmd} --skill {short_name}"
        )
        sys.exit(0)

    # TOCTOU guard — if the skill changed after it was scanned, the scan no
    # longer vouches for what's on disk. Only enforceable for skills we can
    # locate (global skills dir); plugin-namespaced skills resolve elsewhere.
    cached_mtime = cache.get("skill_mtime_epoch") or 0
    if cached_mtime:
        current_mtime = find_skill_mtime(skill_name, short_name)
        if current_mtime is not None and current_mtime > cached_mtime + 1:
            block(
                f"⚠ SkillGuard: '{skill_name}' was MODIFIED after its last scan "
                f"({date_str}).\n"
                f"  Re-scan before use: {cmd} --skill {short_name}"
            )

    # Scanned — show one-liner status
    max_sev = cache.get("max_severity", "clean")
    finding_count = cache.get("finding_count", 0)
    triaged = cache.get("triaged_fp_count", 0)
    fp_note = f" ({triaged} triaged FP)" if triaged else ""

    if max_sev == "clean":
        print(f"✓ SkillGuard: {skill_name} — clean{fp_note} | scanned {date_str}")
    else:
        print(
            f"✓ SkillGuard: {skill_name} — {finding_count} finding(s), "
            f"max: {max_sev}{fp_note} | scanned {date_str}"
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
