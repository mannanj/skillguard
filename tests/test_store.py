"""Tests for the SQLite history + activity store (skillguard/store.py).

Every test uses a fresh DB under tmp_path; the real cache DB is never touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillguard import store


@pytest.fixture
def db(tmp_path: Path) -> Path:
    return tmp_path / "skillguard.db"


def _finding(**kw) -> dict:
    base = {
        "engine": "mcp",
        "severity": "high",
        "category": "mcp_inline_secret",
        "message": "inline secret in env",
        "file": "mcp-config.json",
        "line": 0,
        "context": "",
        "triaged_fp": False,
    }
    base.update(kw)
    return base


def test_connect_creates_full_schema(db):
    conn = store.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"scan_runs", "targets", "target_scans", "findings", "activities"} <= tables
    # user_version stamped for future migrations
    assert conn.execute("PRAGMA user_version").fetchone()[0] == store.SCHEMA_VERSION
    conn.close()


def test_connect_is_idempotent(db):
    store.connect(db).close()
    conn = store.connect(db)  # second open must not error on existing schema
    assert conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 0
    conn.close()


def test_record_scan_preserves_every_scan(db):
    """The whole point of the history store: re-scanning a target appends a new
    row, never overwrites — so the full history survives."""
    conn = store.connect(db)
    run = store.start_scan_run(conn, engines=["local", "mcp"], scope="all", target_kind="mcps")

    sid1 = store.record_scan(
        conn,
        run_id=run,
        kind="mcp",
        name="srv",
        scope="global",
        scanned_at="2026-06-11T00:00:00+00:00",
        engines=["local", "mcp"],
        max_severity="high",
        finding_count=1,
        triaged_fp_count=0,
        mtime_epoch=1.0,
        skipped=False,
        findings=[_finding()],
        raw_json={"v": 1},
    )
    sid2 = store.record_scan(
        conn,
        run_id=run,
        kind="mcp",
        name="srv",
        scope="global",
        scanned_at="2026-06-11T01:00:00+00:00",
        engines=["local", "mcp"],
        max_severity="clean",
        finding_count=0,
        triaged_fp_count=0,
        mtime_epoch=2.0,
        skipped=False,
        findings=[],
        raw_json={"v": 2},
    )

    hist = store.target_history(conn, kind="mcp", name="srv")
    assert len(hist) == 2, "both scans must be preserved"
    assert {h["max_severity"] for h in hist} == {"high", "clean"}

    assert len(store.findings_for_scan(conn, sid1)) == 1
    assert store.findings_for_scan(conn, sid2) == []

    targets = store.list_targets(conn, kind="mcp")
    assert len(targets) == 1
    assert targets[0]["scan_count"] == 2
    assert targets[0]["last_max_severity"] == "clean"
    assert targets[0]["first_seen_at"] == "2026-06-11T00:00:00+00:00"
    conn.close()


def test_finish_scan_run_records_totals(db):
    conn = store.connect(db)
    run = store.start_scan_run(conn, engines=["local"], scope="all", target_kind="all")
    store.finish_scan_run(conn, run, num_targets=3, num_findings=7)
    row = store.recent_scan_runs(conn, limit=1)[0]
    assert row["num_targets"] == 3
    assert row["num_findings"] == 7
    assert row["finished_at"] is not None
    conn.close()


def test_activity_log_and_filtering(db):
    conn = store.connect(db)
    store.log_activity(
        conn,
        actor="hook",
        action="hook_block",
        target_kind="mcp",
        target_name="srv",
        outcome="block",
        severity="high",
    )
    store.log_activity(conn, actor="user", action="scan", outcome="clean")
    store.log_activity(
        conn,
        actor="hook",
        action="hook_allow",
        target_kind="skill",
        target_name="s",
        outcome="allow",
    )

    assert len(store.recent_activity(conn, limit=10)) == 3
    blocks = store.recent_activity(conn, action="hook_block")
    assert len(blocks) == 1 and blocks[0]["target_name"] == "srv"
    mcp_only = store.recent_activity(conn, kind="mcp")
    assert len(mcp_only) == 1
    conn.close()


def test_stats_counts(db):
    conn = store.connect(db)
    run = store.start_scan_run(conn, engines=["local"], scope="all", target_kind="all")
    store.record_scan(
        conn,
        run_id=run,
        kind="skill",
        name="sk",
        scope="global",
        scanned_at="t",
        engines=["local"],
        max_severity="clean",
        finding_count=0,
        triaged_fp_count=0,
        mtime_epoch=0,
        skipped=False,
        findings=[],
    )
    store.record_scan(
        conn,
        run_id=run,
        kind="mcp",
        name="m1",
        scope="global",
        scanned_at="t",
        engines=["mcp"],
        max_severity="critical",
        finding_count=2,
        triaged_fp_count=0,
        mtime_epoch=0,
        skipped=False,
        findings=[_finding(severity="critical"), _finding(severity="high")],
    )
    st = store.stats(conn)
    assert st["skills_total"] == 1
    assert st["mcps_total"] == 1
    assert st["targets_total"] == 2
    assert st["findings_total"] == 2
    assert st["critical_targets"] == 1
    conn.close()


def test_log_activity_safe_never_raises_on_bad_path(tmp_path):
    # A directory where a DB file is expected → connect fails → must be swallowed.
    bad = tmp_path / "iam_a_dir"
    bad.mkdir()
    store.log_activity_safe(bad, actor="hook", action="hook_allow")  # must not raise


def test_log_activity_safe_writes_when_path_ok(db):
    store.log_activity_safe(db, actor="hook", action="hook_warn", target_name="x", outcome="warn")
    conn = store.connect(db)
    rows = store.recent_activity(conn, limit=5)
    assert rows and rows[0]["action"] == "hook_warn"
    conn.close()


def test_concurrent_writers_share_db(db):
    """WAL must let a second connection write while the first is open (the hook
    writes while a CLI scan holds the DB)."""
    a = store.connect(db)
    b = store.connect(db)
    run = store.start_scan_run(a, engines=["local"], scope="all", target_kind="all")
    store.log_activity(b, actor="hook", action="hook_allow", target_name="x", outcome="allow")
    store.finish_scan_run(a, run, num_targets=0, num_findings=0)
    assert len(store.recent_activity(a, limit=5)) == 1
    a.close()
    b.close()
