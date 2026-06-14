#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""
SkillGuard's durable history + activity store (SQLite, stdlib only).

Two questions this answers that the per-target JSON cache can't:

  1. *What have we ever scanned, and what did each scan find?*  Every scan of
     every target (skill or MCP) is appended here — nothing is overwritten, so
     the full history is preserved and queryable long after the cache verdict
     has been re-written by a newer scan.

  2. *What has SkillGuard been doing, and how does the user interact with it?*
     The ``activities`` table is an append-only audit log: scans, skips,
     false-positive overrides, and every PreToolUse hook decision (allow /
     warn / block) with its outcome.

Design constraints:
  - **Stdlib only.** ``sqlite3`` ships with CPython; the scanner stays
    zero-dependency.
  - **No secrets, ever.** Callers must pass redacted data. This module stores
    whatever it is given; it is the caller's job (see ``mcp.py``) never to hand
    it an API key, token, or header value. Findings/metadata are model- and
    config-*shape*, never secret values.
  - **Concurrency-safe.** The hook runs in a separate process on every tool
    call and writes here too, so connections use WAL + a busy timeout. Callers
    that log from the hook must treat every write as best-effort (wrap in
    try/except) — a locked or unwritable DB must never block a tool call.
  - **Decoupled.** This module imports nothing from ``cli`` (which imports it),
    so it takes plain values and dicts, not ``Finding``/``SkillInfo`` objects.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Bump when the schema changes in a way that needs migration logic below.
SCHEMA_VERSION = 1


def default_db_path() -> Path:
    """Location of the history DB, alongside the per-target JSON caches."""
    return Path.home() / ".claude" / "skillguard-cache" / "skillguard.db"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _last_rowid(cur: sqlite3.Cursor) -> int:
    """Return the rowid of the just-inserted row.

    ``sqlite3`` types ``Cursor.lastrowid`` as ``int | None``, but it is always an
    ``int`` after a successful INSERT. Fail loud rather than let a ``None`` leak
    into an ``int`` id column downstream.
    """
    rowid = cur.lastrowid
    if rowid is None:  # pragma: no cover - an INSERT always populates lastrowid
        raise RuntimeError("INSERT produced no rowid")
    return rowid


# ─── Connection / schema ─────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    engines       TEXT,            -- comma-separated engine names
    scope         TEXT,            -- global | local | all
    target_kind   TEXT,            -- skills | mcps | all
    source        TEXT,            -- cli | hook | api
    command_line  TEXT,            -- argv as invoked, for provenance
    num_targets   INTEGER DEFAULT 0,
    num_findings  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS targets (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    kind              TEXT NOT NULL,   -- skill | mcp
    name              TEXT NOT NULL,
    scope             TEXT,            -- global | local | plugin | project
    first_seen_at     TEXT,
    last_scanned_at   TEXT,
    last_max_severity TEXT,
    scan_count        INTEGER DEFAULT 0,
    UNIQUE(kind, name, scope)
);

CREATE TABLE IF NOT EXISTS target_scans (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            INTEGER REFERENCES scan_runs(id),
    target_id         INTEGER REFERENCES targets(id),
    kind              TEXT,
    name              TEXT,
    scope             TEXT,
    scanned_at        TEXT NOT NULL,
    engines           TEXT,
    max_severity      TEXT,
    finding_count     INTEGER DEFAULT 0,
    triaged_fp_count  INTEGER DEFAULT 0,
    mtime_epoch       REAL DEFAULT 0,
    skipped           INTEGER DEFAULT 0,
    raw_json          TEXT             -- full verdict blob for fidelity / forward-compat
);

CREATE TABLE IF NOT EXISTS findings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    target_scan_id  INTEGER REFERENCES target_scans(id),
    engine          TEXT,
    severity        TEXT,
    category        TEXT,
    message         TEXT,
    file            TEXT,
    line            INTEGER DEFAULT 0,
    context         TEXT,
    triaged_fp      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS activities (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    actor        TEXT,     -- user | hook | cli | engine | system
    action       TEXT,     -- scan | skip | mark_fp | unmark_fp | hook_allow | hook_warn | hook_block | introspect | view_history | view_activity
    target_kind  TEXT,     -- skill | mcp
    target_name  TEXT,
    outcome      TEXT,     -- clean | findings | allow | warn | block | error | skipped | ok
    severity     TEXT,
    detail       TEXT,
    metadata     TEXT,     -- JSON object
    source       TEXT      -- cli | hook
);

CREATE INDEX IF NOT EXISTS idx_target_scans_target  ON target_scans(target_id);
CREATE INDEX IF NOT EXISTS idx_target_scans_when    ON target_scans(scanned_at);
CREATE INDEX IF NOT EXISTS idx_findings_scan        ON findings(target_scan_id);
CREATE INDEX IF NOT EXISTS idx_findings_severity    ON findings(severity);
CREATE INDEX IF NOT EXISTS idx_activities_ts        ON activities(ts);
CREATE INDEX IF NOT EXISTS idx_activities_action    ON activities(action);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open (creating if needed) the history DB with concurrency-safe pragmas.

    WAL + a busy timeout let the hook process write while a CLI scan holds the
    DB. ``row_factory`` is ``sqlite3.Row`` so callers get name-addressable rows.
    """
    path = Path(db_path) if db_path is not None else default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    # WAL allows one writer + concurrent readers without "database is locked"
    # for the common case; NORMAL sync is durable enough for an audit log.
    # Apply each independently — if WAL isn't available (e.g. on a network FS),
    # busy_timeout must still be set so the hook waits rather than erroring.
    for pragma in (
        "PRAGMA journal_mode=WAL",
        "PRAGMA synchronous=NORMAL",
        "PRAGMA busy_timeout=4000",
        "PRAGMA foreign_keys=ON",
    ):
        try:
            conn.execute(pragma)
        except sqlite3.DatabaseError:
            pass
    conn.executescript(_SCHEMA)
    _apply_migrations(conn)
    conn.commit()
    return conn


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Forward-compatible schema versioning via PRAGMA user_version."""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current == 0:
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    # Future migrations: `if current < N: ALTER TABLE ...; set user_version=N`.


# ─── Recording scans ─────────────────────────────────────────────────────────


def start_scan_run(
    conn: sqlite3.Connection,
    *,
    engines: Iterable[str],
    scope: str,
    target_kind: str,
    source: str = "cli",
    command_line: str = "",
    started_at: str | None = None,
) -> int:
    """Open a scan-run row; returns its id. Close it with ``finish_scan_run``."""
    cur = conn.execute(
        "INSERT INTO scan_runs (started_at, engines, scope, target_kind, source, command_line) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (started_at or _utcnow_iso(), ",".join(engines), scope, target_kind, source, command_line),
    )
    conn.commit()
    return _last_rowid(cur)


def finish_scan_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    num_targets: int,
    num_findings: int,
    finished_at: str | None = None,
) -> None:
    conn.execute(
        "UPDATE scan_runs SET finished_at=?, num_targets=?, num_findings=? WHERE id=?",
        (finished_at or _utcnow_iso(), num_targets, num_findings, run_id),
    )
    conn.commit()


def upsert_target(
    conn: sqlite3.Connection,
    *,
    kind: str,
    name: str,
    scope: str,
    scanned_at: str,
    max_severity: str,
) -> int:
    """Insert-or-update the dedup registry of everything ever scanned.

    Returns the stable ``targets.id`` so ``target_scans`` rows can reference it.
    """
    row = conn.execute(
        "SELECT id, scan_count FROM targets WHERE kind=? AND name=? AND scope=?",
        (kind, name, scope),
    ).fetchone()
    if row is None:
        cur = conn.execute(
            "INSERT INTO targets (kind, name, scope, first_seen_at, last_scanned_at, "
            "last_max_severity, scan_count) VALUES (?, ?, ?, ?, ?, ?, 1)",
            (kind, name, scope, scanned_at, scanned_at, max_severity),
        )
        conn.commit()
        return _last_rowid(cur)
    conn.execute(
        "UPDATE targets SET last_scanned_at=?, last_max_severity=?, scan_count=scan_count+1 WHERE id=?",
        (scanned_at, max_severity, row["id"]),
    )
    conn.commit()
    return int(row["id"])


def record_scan(
    conn: sqlite3.Connection,
    *,
    run_id: int | None,
    kind: str,
    name: str,
    scope: str,
    scanned_at: str,
    engines: Iterable[str],
    max_severity: str,
    finding_count: int,
    triaged_fp_count: int,
    mtime_epoch: float,
    skipped: bool,
    findings: Iterable[dict[str, Any]],
    raw_json: dict | None = None,
) -> int:
    """Record one target's scan: registry upsert + immutable scan row + findings.

    ``findings`` is an iterable of dicts with keys engine/severity/category/
    message/file/line/context/triaged_fp (e.g. ``dataclasses.asdict(Finding)``).
    Returns the ``target_scans.id``.
    """
    target_id = upsert_target(
        conn, kind=kind, name=name, scope=scope, scanned_at=scanned_at, max_severity=max_severity
    )
    cur = conn.execute(
        "INSERT INTO target_scans (run_id, target_id, kind, name, scope, scanned_at, engines, "
        "max_severity, finding_count, triaged_fp_count, mtime_epoch, skipped, raw_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            run_id,
            target_id,
            kind,
            name,
            scope,
            scanned_at,
            ",".join(engines),
            max_severity,
            finding_count,
            triaged_fp_count,
            float(mtime_epoch or 0),
            1 if skipped else 0,
            json.dumps(raw_json) if raw_json is not None else None,
        ),
    )
    scan_id = _last_rowid(cur)
    rows = [
        (
            scan_id,
            f.get("engine", ""),
            f.get("severity", ""),
            f.get("category", ""),
            f.get("message", ""),
            f.get("file", ""),
            int(f.get("line", 0) or 0),
            (f.get("context", "") or "")[:200],
            1 if f.get("triaged_fp") else 0,
        )
        for f in findings
    ]
    if rows:
        conn.executemany(
            "INSERT INTO findings (target_scan_id, engine, severity, category, message, file, "
            "line, context, triaged_fp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    conn.commit()
    return scan_id


# ─── Activity log ────────────────────────────────────────────────────────────


def log_activity(
    conn: sqlite3.Connection,
    *,
    actor: str,
    action: str,
    target_kind: str | None = None,
    target_name: str | None = None,
    outcome: str | None = None,
    severity: str | None = None,
    detail: str | None = None,
    metadata: dict | None = None,
    source: str = "cli",
    ts: str | None = None,
) -> int:
    """Append one row to the audit log. Returns its id."""
    cur = conn.execute(
        "INSERT INTO activities (ts, actor, action, target_kind, target_name, outcome, "
        "severity, detail, metadata, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            ts or _utcnow_iso(),
            actor,
            action,
            target_kind,
            target_name,
            outcome,
            severity,
            detail,
            json.dumps(metadata) if metadata else None,
            source,
        ),
    )
    conn.commit()
    return _last_rowid(cur)


def log_activity_safe(db_path: Path, **kwargs: Any) -> None:
    """Best-effort activity log for hot paths (the hook): open, write, close,
    and swallow *every* error so a logging problem can never block a tool call.
    """
    conn = None
    try:
        conn = connect(db_path)
        log_activity(conn, **kwargs)
    except Exception:
        pass
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ─── Queries ─────────────────────────────────────────────────────────────────


def recent_scan_runs(conn: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    return list(
        conn.execute("SELECT * FROM scan_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    )


def recent_target_scans(
    conn: sqlite3.Connection, limit: int = 50, kind: str | None = None
) -> list[sqlite3.Row]:
    if kind:
        return list(
            conn.execute(
                "SELECT * FROM target_scans WHERE kind=? ORDER BY id DESC LIMIT ?", (kind, limit)
            ).fetchall()
        )
    return list(
        conn.execute("SELECT * FROM target_scans ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    )


def target_history(conn: sqlite3.Connection, *, kind: str, name: str) -> list[sqlite3.Row]:
    """Every scan ever recorded for one target, newest first."""
    return list(
        conn.execute(
            "SELECT * FROM target_scans WHERE kind=? AND name=? ORDER BY id DESC", (kind, name)
        ).fetchall()
    )


def findings_for_scan(conn: sqlite3.Connection, target_scan_id: int) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM findings WHERE target_scan_id=? ORDER BY id", (target_scan_id,)
        ).fetchall()
    )


def list_targets(conn: sqlite3.Connection, kind: str | None = None) -> list[sqlite3.Row]:
    if kind:
        return list(
            conn.execute(
                "SELECT * FROM targets WHERE kind=? ORDER BY kind, name", (kind,)
            ).fetchall()
        )
    return list(conn.execute("SELECT * FROM targets ORDER BY kind, name").fetchall())


def recent_activity(
    conn: sqlite3.Connection,
    limit: int = 50,
    kind: str | None = None,
    action: str | None = None,
) -> list[sqlite3.Row]:
    clauses: list[str] = []
    params: list[Any] = []
    if kind:
        clauses.append("target_kind=?")
        params.append(kind)
    if action:
        clauses.append("action=?")
        params.append(action)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    return list(
        conn.execute(f"SELECT * FROM activities{where} ORDER BY id DESC LIMIT ?", params).fetchall()
    )


def stats(conn: sqlite3.Connection) -> dict:
    """Headline counts for summary lines."""

    def scalar(sql: str, *p: Any) -> int:
        r = conn.execute(sql, p).fetchone()
        return int(r[0]) if r and r[0] is not None else 0

    return {
        "targets_total": scalar("SELECT COUNT(*) FROM targets"),
        "skills_total": scalar("SELECT COUNT(*) FROM targets WHERE kind='skill'"),
        "mcps_total": scalar("SELECT COUNT(*) FROM targets WHERE kind='mcp'"),
        "scan_runs_total": scalar("SELECT COUNT(*) FROM scan_runs"),
        "target_scans_total": scalar("SELECT COUNT(*) FROM target_scans"),
        "findings_total": scalar("SELECT COUNT(*) FROM findings"),
        "activities_total": scalar("SELECT COUNT(*) FROM activities"),
        "critical_targets": scalar(
            "SELECT COUNT(*) FROM targets WHERE last_max_severity='critical'"
        ),
        "high_targets": scalar("SELECT COUNT(*) FROM targets WHERE last_max_severity='high'"),
    }
