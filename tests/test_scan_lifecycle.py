"""Scan-loop history-DB lifecycle invariants (plan 003, step 1).

The scan loop owns a sqlite connection. The invariant under test: a SINGLE owner
always closes that handle — on the happy path, when scanning raises mid-loop, and
when the run fails to open after connect succeeds — and a DB failure is surfaced
once, never silently swallowed.

A subprocess test can't see whether the in-process connection object was closed
(the OS reclaims the fd on exit regardless), so these drive main() in-process with
discovery/engines/store-open stubbed at their module seams.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import skillguard.cli as cli
from skillguard.cli import SkillInfo


class FakeConn:
    """Stand-in for the sqlite connection that records whether it was closed."""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class CleanEngine:
    name = "local"

    def scan(self, target):
        return []


class RaisingEngine:
    name = "local"

    def scan(self, target):
        raise RuntimeError("engine boom")


def _one_skill(tmp_path: Path) -> SkillInfo:
    d = tmp_path / "victim"
    d.mkdir(exist_ok=True)
    (d / "SKILL.md").write_text("---\nname: victim\n---\n# hi\n")
    return SkillInfo(name="victim", path=d, scope="global")


@pytest.fixture
def fake_conn(tmp_path, monkeypatch):
    """Redirect cache into tmp and stub discovery + store-open so main() reaches
    the scan loop with a single synthetic skill target and a fake connection."""
    monkeypatch.setattr(cli, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(cli, "discover_skills", lambda *a, **k: [_one_skill(tmp_path)])
    monkeypatch.setattr(cli, "discover_mcps", lambda *a, **k: [])
    monkeypatch.setattr(cli, "log_activity", lambda *a, **k: None)  # keep focus on the scan conn
    conn = FakeConn()
    monkeypatch.setattr(cli.store, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(cli.store, "start_scan_run", lambda *a, **k: 1)
    monkeypatch.setattr(cli.store, "record_scan", lambda *a, **k: None)
    monkeypatch.setattr(cli.store, "finish_scan_run", lambda *a, **k: None)
    return conn


def _run(monkeypatch, *argv):
    monkeypatch.setattr(
        sys, "argv", ["skillguard", "--target", "skills", "--engines", "local", *argv]
    )
    cli.main()


def test_normal_scan_records_then_closes(fake_conn, monkeypatch):
    recorded = []
    monkeypatch.setattr(cli.store, "record_scan", lambda *a, **k: recorded.append(k.get("name")))
    monkeypatch.setattr(cli, "_build_engines", lambda *a, **k: ([CleanEngine()], ["local"]))

    _run(monkeypatch, "--quiet")

    assert recorded == ["victim"]  # the target was mirrored into history
    assert fake_conn.closed is True  # and the owner closed the handle


def test_scan_loop_exception_still_closes_history_conn(fake_conn, monkeypatch):
    """If scanning raises mid-loop the exception must propagate (it's a real bug,
    not a swallowed DB error) — but the connection must NOT leak."""
    monkeypatch.setattr(cli, "_build_engines", lambda *a, **k: ([RaisingEngine()], ["local"]))

    with pytest.raises(RuntimeError, match="engine boom"):
        _run(monkeypatch, "--quiet")

    assert fake_conn.closed is True


def test_start_scan_run_failure_closes_conn_and_is_surfaced(fake_conn, monkeypatch, capsys):
    """connect() succeeds but start_scan_run() raises: the already-opened handle
    must still be closed (no leak), the scan must still complete, and the failure
    must be surfaced once to stderr — never silently swallowed."""
    monkeypatch.setattr(cli, "_build_engines", lambda *a, **k: ([CleanEngine()], ["local"]))

    def boom(*a, **k):
        raise RuntimeError("start boom")

    monkeypatch.setattr(cli.store, "start_scan_run", boom)

    _run(monkeypatch, "--format", "json")  # not quiet → the error is surfaced

    assert fake_conn.closed is True
    assert "could not record scan" in capsys.readouterr().err
