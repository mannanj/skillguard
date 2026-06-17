#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""CLI subcommand handlers — everything a non-scan invocation does.

The read-side reports (history / activity / show) are each split into a pure
``gather_*(conn, ...)`` that reads the store into a plain dict and a
``render_*(data, fmt)`` that prints it (text) or hands off to ``emit`` (json) and
returns a process exit code; the thin ``*_command`` wrappers own the DB
connection's lifecycle. ``log_activity`` (the write side of the activity log)
also lives here, as does ``_dispatch_early_exit`` — the router for every
subcommand that exits without scanning (reports, settings, overrides). ``cli``
re-exports ``log_activity`` (monkeypatched as ``cli.log_activity``) and calls
``_dispatch_early_exit`` from ``main``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from skillguard import config, store
from skillguard.agent_adapters import write_project_agent_adapters
from skillguard.agent_summary import (
    SEVERITY_RANK,
    active_verdicts,
    finding_count,
    load_cached_verdicts,
    render_agent_summary,
    target_name,
)
from skillguard.cache import write_ack_cache, write_skip_cache
from skillguard.paths import cache_dir, db_path
from skillguard.render.colors import bold, dim, reset, severity_color
from skillguard.render.reports import _fmt_ts, emit
from skillguard.review_text import action_help, finding_explanation
from skillguard.shell_integration import install_shell_integration
from skillguard.triage import mark_fp_command, unmark_fp_command


def log_activity(**kwargs) -> None:
    """Append to the activity audit log — unless the user has toggled it off.

    Gating here (not in store) keeps the toggle in one place and ensures it only
    affects the activity log: scan *history* is recorded separately and always.
    Best-effort: a logging failure never interrupts a scan.
    """
    if not config.activity_logging_enabled(cache_dir()):
        return
    kwargs.setdefault("source", "cli")
    try:
        conn = store.connect(db_path())
        try:
            store.log_activity(conn, **kwargs)
        finally:
            conn.close()
    except Exception:
        pass


# ─── history ─────────────────────────────────────────────────────────────────


def gather_history(conn, limit: int) -> dict:
    """Read preserved scan history (stats + tracked targets + recent scans)."""
    return {
        "stats": store.stats(conn),
        "targets": [dict(t) for t in store.list_targets(conn)],
        "recent_scans": [dict(r) for r in store.recent_target_scans(conn, limit=limit)],
    }


def render_history(data: dict, fmt: str) -> int:
    if emit(data, fmt):
        return 0
    st = data["stats"]
    rows = data["recent_scans"]
    print(f"\n{bold()}SkillGuard History{reset()}")
    print("=" * 64)
    print(
        f"Tracked: {st['skills_total']} skill(s), {st['mcps_total']} MCP(s) — "
        f"{st['target_scans_total']} scan(s) recorded, {st['findings_total']} finding(s) total"
    )
    if st["critical_targets"] or st["high_targets"]:
        print(
            f"{severity_color('high')}⚠ last verdict HIGH+: "
            f"{st['critical_targets']} critical, {st['high_targets']} high{reset()}"
        )
    print()
    if not rows:
        print(f"{dim()}No scans recorded yet. Run: skillguard --target all{reset()}\n")
        return 0
    print(
        f"{bold()}{'WHEN':<17}{'KIND':<6}{'TARGET':<26}{'VERDICT':<10}{'FINDS':>6}  ENGINES{reset()}"
    )
    print("─" * 78)
    for r in rows:
        sev = r["max_severity"] or "?"
        color = severity_color(sev)
        name = (r["name"] or "")[:25]
        print(
            f"{_fmt_ts(r['scanned_at']):<17}{r['kind'] or '?':<6}{name:<26}"
            f"{color}{sev:<10}{reset()}{r['finding_count']:>6}  {dim()}{r['engines'] or ''}{reset()}"
        )
    print()
    return 0


def history_command(limit: int, fmt: str) -> int:
    """Show preserved scan history (every scan of every target, never overwritten)."""
    conn = store.connect(db_path())
    try:
        data = gather_history(conn, limit)
    finally:
        conn.close()
    return render_history(data, fmt)


# ─── activity ────────────────────────────────────────────────────────────────


def gather_activity(conn, limit: int) -> dict:
    """Read the activity audit log plus whether logging is currently on."""
    return {
        "activity_logging_enabled": config.activity_logging_enabled(cache_dir()),
        "activities": [dict(r) for r in store.recent_activity(conn, limit=limit)],
    }


def render_activity(data: dict, fmt: str) -> int:
    if emit(data, fmt):
        return 0
    rows = data["activities"]
    logging_on = data["activity_logging_enabled"]
    print(f"\n{bold()}SkillGuard Activity{reset()}")
    print("=" * 64)
    if not rows:
        state = "ON" if logging_on else "OFF"
        print(f"{dim()}No activity recorded yet (logging is {state}).{reset()}")
    else:
        print(f"{bold()}{'WHEN':<17}{'ACTOR':<7}{'ACTION':<13}{'TARGET':<22}{'OUTCOME'}{reset()}")
        print("─" * 72)
        for r in rows:
            sev = r["severity"]
            color = severity_color(sev) if sev else ""
            outcome = f"{color}{r['outcome'] or ''}{reset()}" if color else (r["outcome"] or "")
            tgt = (r["target_name"] or "")[:21]
            print(
                f"{_fmt_ts(r['ts']):<17}{(r['actor'] or '')[:6]:<7}"
                f"{(r['action'] or '')[:12]:<13}{tgt:<22}{outcome}"
            )
            if r["detail"]:
                print(f"{dim()}                 └ {r['detail']}{reset()}")
    # Make the toggle discoverable — this is a setting the user controls.
    print()
    if logging_on:
        print(
            f"{dim()}Activity logging is ON. Turn it off with: "
            f"skillguard --set-activity-logging off{reset()}"
        )
    else:
        print(
            f"{dim()}Activity logging is OFF (scan history is still recorded). "
            f"Turn it on with: skillguard --set-activity-logging on{reset()}"
        )
    print()
    return 0


def activity_command(limit: int, fmt: str) -> int:
    """Show the activity audit log: scans, overrides, and hook decisions."""
    conn = store.connect(db_path())
    try:
        data = gather_activity(conn, limit)
    finally:
        conn.close()
    return render_activity(data, fmt)


# ─── show ────────────────────────────────────────────────────────────────────


def gather_show(conn, name: str) -> dict:
    """Read the full scan history for one target (skill or MCP), with findings."""
    rows = store.target_history(conn, kind="skill", name=name) + store.target_history(
        conn, kind="mcp", name=name
    )
    rows.sort(key=lambda r: r["id"], reverse=True)
    detail = {r["id"]: store.findings_for_scan(conn, r["id"]) for r in rows}
    return {
        "target": name,
        "scans": [{**dict(r), "findings": [dict(f) for f in detail[r["id"]]]} for r in rows],
    }


def render_show(data: dict, fmt: str) -> int:
    if emit(data, fmt):
        return 0
    name = data["target"]
    scans = data["scans"]
    print(f"\n{bold()}History for '{name}'{reset()}")
    print("=" * 64)
    if not scans:
        print(f"{dim()}No scans recorded for '{name}'.{reset()}\n")
        return 0
    for r in scans:
        sev = r["max_severity"] or "?"
        print(
            f"\n{_fmt_ts(r['scanned_at'])}  [{r['kind']}/{r['scope']}]  "
            f"{severity_color(sev)}{sev}{reset()}  "
            f"{dim()}({r['finding_count']} finding(s), engines: {r['engines']}){reset()}"
        )
        for f in r["findings"]:
            if f["severity"] == "info" and not f["message"]:
                continue
            loc = f" {f['file']}:{f['line']}" if f["file"] else ""
            print(
                f"    {severity_color(f['severity'])}{f['severity']:<8}{reset()}"
                f"[{f['engine']}] {f['message']}{dim()}{loc}{reset()}"
            )
    print()
    return 0


def show_command(name: str, fmt: str) -> int:
    """Show the full scan history for one target (skill or MCP), with findings."""
    conn = store.connect(db_path())
    try:
        data = gather_show(conn, name)
    finally:
        conn.close()
    return render_show(data, fmt)


# ─── agent launch summary / review ───────────────────────────────────────────


def agent_summary_command() -> int:
    """Print a no-scan, launch-friendly summary from the verdict cache."""
    print(render_agent_summary(load_cached_verdicts()))
    return 0


def _print_review_target(verdict: dict, index: int, total: int) -> None:
    name = target_name(verdict)
    sev = str(verdict.get("max_severity") or "unknown")
    count = finding_count(verdict)
    print(f"\n[{index}/{total}] {name} · {sev} · {count} finding(s)")
    findings = [f for f in verdict.get("findings", []) if not f.get("triaged_fp")]
    for f in findings[:5]:
        loc = f" {f.get('file')}:{f.get('line')}" if f.get("file") else ""
        print(f"  {f.get('severity')} [{f.get('engine')}] {f.get('message')}{loc}")
        if f.get("context"):
            print(f"    {f.get('context')}")
        for line in finding_explanation(f, target_kind=str(verdict.get("kind") or "skill")):
            print(f"    {line}")
    remaining = len(findings) - min(len(findings), 5)
    if remaining:
        print(f"  ... {remaining} more")
    print(action_help())


def _confirm_ack() -> bool:
    print("Type allow to acknowledge risk, or press Enter to cancel.")
    try:
        return input("> ").strip().lower() == "allow"
    except EOFError:
        print()
        return False


def review_command() -> int:
    """Walk cached active findings one target at a time."""
    verdicts = sorted(
        active_verdicts(load_cached_verdicts()),
        key=lambda v: (
            SEVERITY_RANK.get(str(v.get("max_severity")), 99),
            target_name(v),
        ),
    )
    if not verdicts:
        print("SkillGuard: no active cached findings.")
        print("Run: skillguard --target skills --scope all --engines local")
        return 0

    for idx, verdict in enumerate(verdicts, start=1):
        name = target_name(verdict)
        kind = str(verdict.get("kind") or "skill")
        while True:
            _print_review_target(verdict, idx, len(verdicts))
            try:
                choice = input("> ").strip().lower()
            except EOFError:
                print()
                return 0
            if choice in ("", "n", "next"):
                break
            if choice in ("q", "quit"):
                return 0
            if choice in ("m", "mark", "mark-fp"):
                mark_fp_command(name)
                log_activity(
                    actor="user",
                    action="mark_fp",
                    target_kind=kind,
                    target_name=name,
                    outcome="ok",
                    detail="findings marked false-positive via review",
                )
                break
            if choice in ("a", "ack"):
                if _confirm_ack():
                    _acknowledge(name, kind)
                    break
                print("Acknowledgement cancelled.")
                continue
            if choice in ("s", "show"):
                show_command(name, "table")
                continue
            print("Choose: m mark-fp, a ack, s show, enter next, q quit", file=sys.stderr)
    return 0


def _acknowledge(name: str, kind: str) -> int:
    """Record an explicit risk acknowledgment (``--ack`` / ``--ack-mcp``) so the
    hook allows a scanned-risky target. Unlike skip, this requires a prior scan;
    if there is none, tell the user to scan first and exit non-zero."""
    scan_flag = "--mcp" if kind == "mcp" else "--skill"
    try:
        verdict = write_ack_cache(name, kind)
    except ValueError as exc:
        print(f"Cannot acknowledge: {exc}.")
        print(f"Scan it first: skillguard {scan_flag} {name}")
        return 1
    sev = verdict.get("acknowledged_severity", "unknown")
    findings = verdict.get("finding_count", 0)
    log_activity(
        actor="user",
        action="acknowledge",
        target_kind=kind,
        target_name=name,
        outcome="ok",
        severity=sev,
        detail=f"risk acknowledged ({findings} finding(s), max {sev}) — hook will allow",
    )
    label = "MCP" if kind == "mcp" else "skill"
    print(
        f"Acknowledged risk for {label} '{name}' "
        f"({findings} finding(s), max severity: {sev}). The hook will now ALLOW it."
    )
    print(f"This is cleared automatically if you re-scan: skillguard {scan_flag} {name}")
    return 0


# ─── Early-exit dispatch (no-scan subcommands) ───────────────────────────────


def _dispatch_early_exit(args: argparse.Namespace) -> int | None:
    """Handle the subcommands that run without scanning — read-only reports,
    settings toggles, and override marks. Returns the process exit code when one
    fires, or ``None`` to fall through to a scan."""
    if args.install_shell_integration:
        changed = install_shell_integration(shell_only=bool(getattr(args, "shell_only", False)))
        print("SkillGuard shell integration installed:")
        for key, value in changed.items():
            print(f"  {key}: {value}")
        return 0
    if args.install_agent_adapters is not None:
        changed = write_project_agent_adapters(Path(args.install_agent_adapters), "skillguard")
        print("SkillGuard agent adapters installed:")
        for key, value in changed.items():
            print(f"  {key}: {value}")
        return 0

    # ── Read-only report commands (no scanning) ──────────────────────────────
    if args.history is not None:
        return history_command(args.history, args.format)
    if args.activity is not None:
        return activity_command(args.activity, args.format)
    if args.show:
        return show_command(args.show, args.format)
    if args.agent_summary:
        return agent_summary_command()
    if args.review:
        return review_command()

    # ── Settings ─────────────────────────────────────────────────────────────
    if args.set_activity_logging:
        on = args.set_activity_logging == "on"
        config.set_activity_logging(on, cache_dir())
        print(
            f"Activity logging is now {'ON' if on else 'OFF'}. "
            f"{'Scan history is recorded either way.' if not on else ''}".rstrip()
        )
        return 0
    if args.set_mcp_policy:
        config.set_mcp_policy(args.set_mcp_policy, cache_dir())
        print(f"MCP hook policy set to '{args.set_mcp_policy}'.")
        return 0

    # ── Overrides (logged as activities) ─────────────────────────────────────
    if args.skip:
        write_skip_cache(args.skip, "skill")
        log_activity(
            actor="user",
            action="skip",
            target_kind="skill",
            target_name=args.skip,
            outcome="skipped",
            detail="hook will allow with a reminder",
        )
        print(f"Marked skill '{args.skip}' as skipped. Hook will show a reminder on each use.")
        print(f"To scan it properly: skillguard --skill {args.skip}")
        return 0
    if args.skip_mcp:
        write_skip_cache(args.skip_mcp, "mcp")
        log_activity(
            actor="user",
            action="skip",
            target_kind="mcp",
            target_name=args.skip_mcp,
            outcome="skipped",
            detail="hook will allow with a reminder",
        )
        print(f"Marked MCP '{args.skip_mcp}' as skipped.")
        print(f"To scan it properly: skillguard --mcp {args.skip_mcp}")
        return 0
    if args.ack:
        return _acknowledge(args.ack, "skill")
    if args.ack_mcp:
        return _acknowledge(args.ack_mcp, "mcp")
    if args.mark_fp:
        mark_fp_command(args.mark_fp)
        log_activity(
            actor="user",
            action="mark_fp",
            target_name=args.mark_fp,
            outcome="ok",
            detail="findings marked false-positive",
        )
        return 0
    if args.unmark_fp:
        unmark_fp_command(args.unmark_fp)
        log_activity(
            actor="user",
            action="unmark_fp",
            target_name=args.unmark_fp,
            outcome="ok",
            detail="false-positive marks removed",
        )
        return 0

    return None
