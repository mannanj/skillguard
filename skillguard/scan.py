#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""The scan pipeline: run every engine over every target, persist verdicts +
history under a single DB-connection owner.

``store`` and ``time`` are referenced as module objects (not ``from ... import``
of their members) so the tests that drive ``cli.main()`` and monkeypatch
``cli.store.*`` / ``cli.time.sleep`` — the same module singletons — take effect
here too. ``cli`` re-exports ``run_scan_pipeline`` and ``_dedupe_mcp_findings``.
"""

from __future__ import annotations

import sys
import time

from skillguard import store
from skillguard.cache import write_cache
from skillguard.model import Engine, Finding, SkillInfo, worst_severity
from skillguard.paths import db_path
from skillguard.triage import apply_triage, load_triage


def _dedupe_mcp_findings(findings: list[Finding]) -> list[Finding]:
    """Collapse identical (engine, category, message) findings on an MCP target.

    A server's launch command is materialized into more than one surface file
    (``command.txt`` and the ``mcp-config.json`` args), so a regex engine
    legitimately reports the same issue from each. For a config audit that is
    one issue, not several — keep the most specific location. Applied to MCP
    targets only; skills keep every distinct occurrence.
    """
    rank = {"command.txt": 0, "endpoint.txt": 0, "mcp-config.json": 1}
    best: dict[tuple, tuple[int, Finding]] = {}
    order: list[tuple] = []
    for f in findings:
        key = (f.engine, f.category, f.message)
        r = rank.get(f.file, 2)
        if key not in best:
            best[key] = (r, f)
            order.append(key)
        elif r < best[key][0]:
            best[key] = (r, f)
    return [best[k][1] for k in order]


def run_scan_pipeline(
    targets: list[SkillInfo],
    engines: list[Engine],
    engine_names_used: list[str],
    *,
    scope: str,
    target_kind_label: str,
    quiet: bool,
    fmt: str,
) -> tuple[int, str]:
    """Scan every target through every engine, write verdict caches, and mirror
    each result into the history DB. Returns ``(total_active_findings, worst)``.

    History is best-effort but OBSERVABLE. A single try/finally owns the
    connection for the whole scan, so the handle is always closed — even if
    opening half-succeeds (connect OK, start_scan_run fails) or scanning raises
    mid-loop (no leak either way). DB failures are collected and surfaced once to
    stderr instead of silently swallowed, so a user never believes a scan was
    recorded when it wasn't. Recording stays independent of the activity-log
    toggle.
    """
    total = len(targets)
    triage = load_triage()

    conn = run_id = None
    history_error = None  # first DB error encountered; surfaced once after the loop
    try:
        try:
            conn = store.connect(db_path())
            run_id = store.start_scan_run(
                conn,
                engines=engine_names_used,
                scope=scope,
                target_kind=target_kind_label,
                source="cli",
                command_line=" ".join(sys.argv),
            )
        except Exception as e:
            history_error, run_id = (
                e,
                None,
            )  # history unavailable; conn (if opened) closed in finally

        for i, target in enumerate(targets):
            if not quiet and fmt == "table":
                print(
                    f"\r  Scanning {i + 1}/{total}: {target.name:<40}",
                    end="",
                    file=sys.stderr,
                    flush=True,
                )

            for engine in engines:
                target.findings.extend(engine.scan(target))
                # Throttle between targets for any engine that asks for it (e.g.
                # SkillAudit's rate limit) — by attribute, never by engine name.
                if i < total - 1 and engine.inter_target_delay:
                    time.sleep(engine.inter_target_delay)

            if target.kind == "mcp":
                target.findings = _dedupe_mcp_findings(target.findings)
            apply_triage(target, triage)
            cache = write_cache(target, engine_names_used)

            # History is ALWAYS preserved (independent of the activity-log toggle).
            if conn is not None and run_id is not None:
                try:
                    store.record_scan(
                        conn,
                        run_id=run_id,
                        kind=target.kind,
                        name=target.name,
                        scope=target.scope,
                        scanned_at=cache["scanned_at"],
                        engines=engine_names_used,
                        max_severity=cache["max_severity"],
                        finding_count=cache["finding_count"],
                        triaged_fp_count=cache["triaged_fp_count"],
                        mtime_epoch=cache["skill_mtime_epoch"],
                        skipped=False,
                        findings=cache["findings"],
                        raw_json=cache,
                    )
                except Exception as e:
                    history_error = history_error or e

        if not quiet and fmt == "table":
            print("\r" + " " * 60 + "\r", end="", file=sys.stderr, flush=True)

        total_findings = sum(len(t.active_findings) for t in targets)
        worst = worst_severity(t.max_severity for t in targets)
        if conn is not None and run_id is not None:
            try:
                store.finish_scan_run(conn, run_id, num_targets=total, num_findings=total_findings)
            except Exception as e:
                history_error = history_error or e
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    if history_error is not None and not quiet:
        print(f"[history] could not record scan: {history_error}", file=sys.stderr)

    return total_findings, worst
